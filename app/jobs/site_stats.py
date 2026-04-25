import json
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import joinedload
from sqlmodel import select

from app.core.logger import setup_logger
from app.database.celery import celery_dynamo_client, get_celery_db_session
from app.database.redis import sync_redis_client
from app.jobs.billing.engine import BillingEngine
from app.jobs.celery import celery_app
from app.modules.contracts.model import Contract

logger = setup_logger(__name__)

celery_app.conf.beat_schedule = {
    "compute-site-stats-every-5-mins": {
        "task": "compute_all_site_stats",
        "schedule": 40,
    },
}


@celery_app.task(name="compute_all_site_stats", bind=True, max_retries=3, default_retry_delay=5)
def compute_all_site_stats(self):
    """
    Beat triggers this every 5 mins.
    Fetches all active sites and dispatches
    one compute task per site to the worker pool.
    """
    try:
        with get_celery_db_session() as session:
            result = session.execute(
                text(
                    """
                    SELECT DISTINCT
                        s.uid::text  AS site_uid,
                        s.gateway_id AS gateway_id
                    FROM sites s
                    JOIN contracts c ON c.site_uid = s.uid
                    JOIN contract_details cd ON cd.contract_uid = c.uid
                    WHERE cd.commissioned_at IS NOT NULL
                        AND NOW() > cd.commissioned_at
                        AND NOW() < cd.end_at
                    """
                )
            )
            sites = result.fetchall()

        for site in sites:
            compute_single_site_stats.delay(
                site_uid=site.site_uid,
                gateway_id=site.gateway_id,
            )

    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(name="compute_single_site_stats", bind=True, max_retries=3, default_retry_delay=5)
def compute_single_site_stats(self, site_uid: str, gateway_id: str):
    """
    Computes all 4 variables for a single site
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

        if not contract:
            return

        now = datetime.now(timezone.utc)

        # 1. billing period (contract math only)
        period_start, period_end = BillingEngine.get_current_billing_period(
            commissioned_at=contract.details.commissioned_at,
            billing_frequency=contract.details.billing_frequency,
            as_of=now,
        )

        # 2. expected generation (contract math only)
        days_elapsed = (now - contract.details.commissioned_at).days
        expected_generation_kwh = round(
            (contract.details.system_size_kwp or 0)
            * (contract.details.guaranteed_production_kwh_per_kwp or 0)
            * (days_elapsed / 365),
            2,
        )

        # 3. billing progress (contract lifespan: commissioned_at to end_at)
        contract_start = contract.details.commissioned_at
        contract_end = contract.details.end_at
        total_secs = (contract_end - contract_start).total_seconds()
        elapsed_secs = (now - contract_start).total_seconds()
        billing_progress_pct = round(max(0.0, min((elapsed_secs / total_secs) * 100, 100.0)), 2)

        # 4. actual generation (DynamoDB only — sync boto3)
        billing_data = celery_dynamo_client.get_readings_for_billing_period(
            gateway_id=gateway_id,
            period_start=period_start,
            period_end=period_end,
        )

        actual_generation_kwh = 0.0
        if billing_data:
            start_reading, end_reading = billing_data
            start_meter = BillingEngine._extract_meter_by_description(start_reading, "gen_meter")
            end_meter = BillingEngine._extract_meter_by_description(end_reading, "gen_meter")
            if start_meter and end_meter:
                actual_generation_kwh = round(float(end_meter["kwh_total"]) - float(start_meter["kwh_total"]), 2)

        # 5. deviation (derived)
        deviation_pct = 0.0
        if expected_generation_kwh > 0:
            deviation_pct = round(
                (actual_generation_kwh - expected_generation_kwh) / expected_generation_kwh * 100,
                2,
            )

        # 6. write to Redis
        stats = {
            "site_uid": site_uid,
            "expected_generation_kwh": expected_generation_kwh,
            "actual_generation_kwh": actual_generation_kwh,
            "billing_progress_pct": billing_progress_pct,
            "deviation_pct": deviation_pct,
        }

        sync_redis_client._client.setex(
            f"site_stats:{site_uid}",
            600,
            json.dumps(stats),
        )

    except Exception as exc:
        raise self.retry(exc=exc)
