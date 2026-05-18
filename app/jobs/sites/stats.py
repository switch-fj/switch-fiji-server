import calendar
import json
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import joinedload, selectinload
from sqlmodel import desc, select

from app.core.logger import setup_logger
from app.database.celery import celery_dynamo_client, get_celery_db_session
from app.database.redis import sync_redis_client
from app.jobs.celery import celery_app
from app.modules.billing.engine import BillingEngine
from app.modules.contracts.model import Contract
from app.modules.devices.model import Device
from app.modules.devices.schema import DeviceType
from app.modules.invoices.model import Invoice
from app.modules.settings.model import ContractSettings
from app.modules.sites.wizard.site_stats import SiteStatsWizard
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
                .options(
                    joinedload(Contract.details),
                    joinedload(Contract.client),
                    joinedload(Contract.site),
                )
                .where(Contract.site_uid == site_uid)
            ).scalar_one_or_none()

            devices = (
                session.execute(
                    select(Device).where(
                        Device.site_uid == site_uid,
                        Device.device_type == DeviceType.METER.value,
                    )
                )
                .scalars()
                .all()
            )

            contract_settings = (
                session.execute(
                    select(ContractSettings).options(
                        selectinload(ContractSettings.efl_rate_history),
                        selectinload(ContractSettings.vat_rate_history),
                    )
                )
                .scalars()
                .first()
            )

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

        with get_celery_db_session() as session:
            last_invoice = session.execute(
                select(Invoice)
                .where(Invoice.contract_uid == contract.uid)
                .order_by(desc(Invoice.period_end_at))
                .limit(1)
            ).scalar_one_or_none()

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

        site_stats_wizard = SiteStatsWizard(
            contract=contract,
            last_invoice=last_invoice,
            contract_settings=contract_settings,
            devices=devices,
        )
        now = site_stats_wizard.now

        period_start, period_end = BillingEngine.get_current_billing_period(
            commissioned_at=commissioned_at,
            billing_frequency=contract.details.billing_frequency,
            as_of=now,
        )

        billing_period_progress_percentage = site_stats_wizard.billing_period_progress_percentage(
            period_start=period_start, period_end=period_end
        )
        contract_progress_percentage = site_stats_wizard.contract_progress_percentage()
        expected_generation_kwh = site_stats_wizard.expected_generation_for_period_kwh(
            period_start=period_start, period_end=period_end
        )

        actual_generation_kwh = 0.0
        billing_data = celery_dynamo_client.get_readings_for_billing_period(
            gateway_id=gateway_id,
            period_start=period_start,
            period_end=period_end,
        )

        if billing_data:
            telemetry_start_reading, telemetry_end_reading = billing_data
            actual_generation_kwh = site_stats_wizard.actual_generation_kwh_for_reading(
                telemetry_start_reading=telemetry_start_reading,
                telemetry_end_reading=telemetry_end_reading,
            )

        projected_generation_kwh = 0.0
        projected_invoice_value = 0.0
        performance_vs_mtd_expected_percentage = 0.0
        mtd_generation_kwh = 0.0

        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        year = now.year
        month = now.month
        _, total_days_in_month = calendar.monthrange(year, month)
        end_of_month = now.replace(day=total_days_in_month, hour=23, minute=59, second=59)

        mtd_data = celery_dynamo_client.get_readings_for_billing_period(
            gateway_id=gateway_id,
            period_start=month_start,
            period_end=now,
        )

        if mtd_data:
            mtd_start_reading, mtd_end_reading = mtd_data

            mtd_generation_kwh = site_stats_wizard.actual_generation_kwh_for_reading(
                telemetry_start_reading=mtd_start_reading,
                telemetry_end_reading=mtd_end_reading,
            )

            performance_vs_mtd_expected_percentage = site_stats_wizard.performance_vs_mtd_expected_percentage(
                actual_generation_kwh=mtd_generation_kwh,
                period_start=month_start,
                period_end=end_of_month,
            )

            projected_generation_kwh = site_stats_wizard.linear_projected_generation_kwh(
                actual_generation_kwh_for_reading=mtd_generation_kwh
            )

            projected_invoice_value = site_stats_wizard.projected_invoice_value(
                projected_generation_kwh=projected_generation_kwh
            )

        performance_vs_baseline_percentage = 0.0
        if site_stats_wizard.baseline_kwh > 0:
            performance_vs_baseline_percentage = site_stats_wizard.performance_vs_baseline_percentage(
                actual_generation_kwh=actual_generation_kwh,
                baseline_kwh=site_stats_wizard.baseline_kwh,
            )

        stats = {
            "computed_at": now.astimezone(timezone.utc).isoformat(),
            "site_uid": site_uid,
            "expected_generation_kwh": expected_generation_kwh,
            "actual_generation_kwh": actual_generation_kwh,
            "mtd_generation_kwh": mtd_generation_kwh,
            "projected_generation_kwh": projected_generation_kwh,
            "projected_invoice_value": projected_invoice_value,
            "billing_period_progress_percentage": billing_period_progress_percentage,
            "contract_progress_percentage": contract_progress_percentage,
            "performance_vs_baseline_percentage": performance_vs_baseline_percentage,
            "performance_vs_mtd_expected_percentage": performance_vs_mtd_expected_percentage,
            "last_invoice_date": site_stats_wizard.last_invoice_date,
            "last_invoice_amount": site_stats_wizard.last_invoice_amount,
        }

        sync_redis_client._client.setex(
            Constants.SITE_STATS_STREAM.replace("uid", site_uid),
            600,
            json.dumps(stats),
        )

    except Exception as exc:
        raise self.retry(exc=exc)
