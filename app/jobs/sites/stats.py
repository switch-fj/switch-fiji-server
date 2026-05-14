import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import joinedload
from sqlmodel import desc, select

from app.core.logger import setup_logger
from app.database.celery import celery_dynamo_client, get_celery_db_session
from app.database.redis import sync_redis_client
from app.jobs.billing.engine import BillingEngine
from app.jobs.celery import celery_app
from app.modules.contracts.model import Contract
from app.modules.invoices.model import Invoice
from app.shared.constants import Constants

logger = setup_logger(__name__)


@celery_app.task(name="compute_site_stats", bind=True, max_retries=3, default_retry_delay=5)
def compute_site_stats(self):
    """
    Beat triggers this every 5 mins.
    Fetches all sites and dispatches
    one compute task per site to the worker pool.
    """
    try:
        with get_celery_db_session() as session:
            result = session.execute(
                text("""
                SELECT
                    s.uid::text AS site_uid,
                    s.gateway_id AS gateway_id
                FROM sites s
            """)
            )
            sites = result.fetchall()

        for site in sites:
            compute_site_stat.delay(
                site_uid=site.site_uid,
                gateway_id=site.gateway_id,
            )

    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(name="compute_site_stat", bind=True, max_retries=3, default_retry_delay=5)
def compute_site_stat(self, site_uid: str, gateway_id: str):
    """
    Computes all site stats variables for a single site
    and writes the result to Redis.
    """
    try:
        celery_dynamo_client.init()
        with get_celery_db_session() as session:
            contract = session.execute(
                select(Contract)
                .options(joinedload(Contract.details), joinedload(Contract.client))
                .where(Contract.site_uid == site_uid)
            ).scalar_one_or_none()

        if not contract or not contract.details:
            sync_redis_client._client.setex(
                Constants.SITE_STATS_STREAM.replace("uid", site_uid),
                600,
                json.dumps(
                    {
                        "message": "site has no contract.",
                        "site_uid": site_uid,
                    }
                ),
            )
            return

        commissioned_at = contract.details.actual_commissioned_at or contract.details.commissioned_at

        if not commissioned_at or datetime.now(timezone.utc) <= commissioned_at:
            sync_redis_client._client.setex(
                Constants.SITE_STATS_STREAM.replace("uid", site_uid),
                600,
                json.dumps(
                    {
                        "message": "site contract has not started",
                        "site_uid": site_uid,
                    }
                ),
            )
            return

        tz = ZoneInfo(contract.timezone)
        now = datetime.now(tz=tz)

        end_at = contract.details.actual_end_at or contract.details.end_at

        period_start, period_end = BillingEngine.get_current_billing_period(
            commissioned_at=commissioned_at,
            billing_frequency=contract.details.billing_frequency,
            as_of=now,
        )

        period_total_secs = (period_end - period_start).total_seconds()
        period_elapsed_secs = (now - period_start).total_seconds()
        billing_period_progress_pct = round(max(0.0, min((period_elapsed_secs / period_total_secs) * 100, 100.0)), 2)

        contract_total_secs = (end_at - commissioned_at).total_seconds()
        contract_elapsed_secs = (now - commissioned_at).total_seconds()
        contract_progress_pct = round(max(0.0, min((contract_elapsed_secs / contract_total_secs) * 100, 100.0)), 2)

        days_in_period = (period_end - period_start).days or 1
        days_elapsed_in_period = min((now - period_start).days, days_in_period)
        expected_generation_kwh = round(
            (contract.details.system_size_kwp or 0)
            * (contract.details.guaranteed_production_kwh_per_kwp or 0)
            * (days_elapsed_in_period / 365),
            2,
        )

        actual_generation_kwh = 0.0
        billing_data = celery_dynamo_client.get_readings_for_billing_period(
            gateway_id=gateway_id,
            period_start=period_start,
            period_end=period_end,
        )

        if billing_data:
            start_reading, end_reading = billing_data
            start_meter = BillingEngine._extract_meter_by_description(start_reading, "gen_meter")
            end_meter = BillingEngine._extract_meter_by_description(end_reading, "gen_meter")

            if start_meter and end_meter:
                if end_meter["kwh_total"]:
                    end_meter_kwh_total = float(end_meter["kwh_total"])
                else:
                    end_meter_kwh_total = float(end_meter["tariff"]["kwh_t1"]) + float(end_meter["tariff"]["kwh_t2"])

                if start_meter["kwh_total"]:
                    start_meter_kwh_total = float(start_meter["kwh_total"])
                else:
                    start_meter_kwh_total = float(start_meter["tariff"]["kwh_t1"]) + float(
                        start_meter["tariff"]["kwh_t2"]
                    )

                actual_generation_kwh = round(end_meter_kwh_total - start_meter_kwh_total, 2)

        projected_generation_kwh = 0.0
        projected_invoice_value = 0.0
        if billing_period_progress_pct > 0:
            projected_generation_kwh = round(actual_generation_kwh / (billing_period_progress_pct / 100), 2)
            projected_invoice_value = round(
                projected_generation_kwh * float(contract.details.efl_standard_rate_kwh or 0),
                2,
            )

        mtd_generation_kwh = 0.0
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        mtd_data = celery_dynamo_client.get_readings_for_billing_period(
            gateway_id=gateway_id,
            period_start=month_start,
            period_end=now,
        )
        if mtd_data:
            mtd_start_reading, mtd_end_reading = mtd_data
            mtd_start_meter = BillingEngine._extract_meter_by_description(mtd_start_reading, "gen_meter")
            mtd_end_meter = BillingEngine._extract_meter_by_description(mtd_end_reading, "gen_meter")

            if mtd_start_meter and mtd_end_meter:
                if mtd_end_meter["kwh_total"]:
                    mtd_end_kwh = float(mtd_end_meter["kwh_total"])
                else:
                    mtd_end_kwh = float(mtd_end_meter["tariff"]["kwh_t1"]) + float(mtd_end_meter["tariff"]["kwh_t2"])

                if mtd_start_meter["kwh_total"]:
                    mtd_start_kwh = float(mtd_start_meter["kwh_total"])
                else:
                    mtd_start_kwh = float(mtd_start_meter["tariff"]["kwh_t1"]) + float(
                        mtd_start_meter["tariff"]["kwh_t2"]
                    )

                mtd_generation_kwh = round(mtd_end_kwh - mtd_start_kwh, 2)

        performance_vs_baseline_pct = 0.0
        full_period_baseline_kwh = (contract.details.guaranteed_production_kwh_per_kwp or 0) * (
            contract.details.system_size_kwp or 0
        )
        baseline_kwh = round(full_period_baseline_kwh * (billing_period_progress_pct / 100), 2)
        if baseline_kwh > 0:
            performance_vs_baseline_pct = round(
                (actual_generation_kwh - baseline_kwh) / baseline_kwh * 100,
                2,
            )

        with get_celery_db_session() as session:
            last_invoice = session.execute(
                select(Invoice)
                .where(Invoice.contract_uid == contract.uid)
                .order_by(desc(Invoice.period_end_at))
                .limit(1)
            ).scalar_one_or_none()

        last_invoice_date = last_invoice.period_end_at.isoformat() if last_invoice else None
        last_invoice_amount = float(last_invoice.total) if last_invoice else None

        stats = {
            "computed_at": now.astimezone(tz=timezone.utc).isoformat(),
            "site_uid": site_uid,
            "expected_generation_kwh": expected_generation_kwh,
            "actual_generation_kwh": actual_generation_kwh,
            "mtd_generation_kwh": mtd_generation_kwh,
            "projected_generation_kwh": projected_generation_kwh,
            "projected_invoice_value": projected_invoice_value,
            "billing_period_progress_pct": billing_period_progress_pct,
            "contract_progress_pct": contract_progress_pct,
            "performance_vs_baseline_pct": performance_vs_baseline_pct,
            "last_invoice_date": last_invoice_date,
            "last_invoice_amount": last_invoice_amount,
        }

        sync_redis_client._client.setex(
            Constants.SITE_STATS_STREAM.replace("uid", site_uid),
            600,
            json.dumps(stats),
        )

    except Exception as exc:
        raise self.retry(exc=exc)
