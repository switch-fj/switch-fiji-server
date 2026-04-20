import json
from datetime import datetime, timezone

from sqlalchemy import text

from app.core.billing import Billing
from app.database.celery import get_celery_db_session
from app.database.redis import sync_redis_client
from app.jobs.celery import celery_app

celery_app.conf.beat_schedule = {
    "compute-site-stats-every-5-mins": {
        "task": "compute_all_site_stats",
        "schedule": 300,
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
                JOIN contracts c         ON c.site_uid    = s.uid
                JOIN contract_details cd ON cd.contract_uid = c.uid
                WHERE cd.commissioned_at IS NOT NULL
                    AND cd.commissioned_at <= NOW()
                    AND cd.end_at >= NOW()
            """
                )
            )
            sites = result.fetchall()

        for site in sites:
            compute_single_site_stats.delay(
                site.site_uid,
                site.gateway_id,
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
        with get_celery_db_session() as session:
            result = session.execute(
                text(
                    """
                SELECT
                    cd.system_size_kwp,
                    cd.guaranteed_production_kwh_per_kwp,
                    cd.commissioned_at,
                    cd.billing_frequency,
                    cd.grid_meter_reading_at_commissioning
                FROM contracts c
                JOIN contract_details cd ON cd.contract_uid = c.uid
                WHERE c.site_uid = :site_uid
                    AND cd.commissioned_at IS NOT NULL
                    AND cd.commissioned_at <= NOW()
                    AND cd.end_at >= NOW()
                LIMIT 1
            """
                ),
                {"site_uid": site_uid},
            )
            contract = result.fetchone()

        if not contract:
            return

        now = datetime.now(timezone.utc)

        # 1. billing period (contract math only)
        period_start, period_end = Billing.get_current_billing_period(
            commissioned_at=contract.commissioned_at,
            billing_frequency=contract.billing_frequency,
            as_of=now,
        )

        # 2. expected generation (contract math only)
        days_elapsed = (now - contract.commissioned_at).days
        expected_generation_kwh = round(
            (contract.system_size_kwp or 0) * (contract.guaranteed_production_kwh_per_kwp or 0) * (days_elapsed / 365),
            2,
        )

        # 3. billing progress (date math only)
        total_secs = (period_end - period_start).total_seconds()
        elapsed_secs = (now - period_start).total_seconds()
        billing_progress_pct = round((elapsed_secs / total_secs) * 100, 2)

        # 4. actual generation (DynamoDB only — sync boto3)
        billing_data = Billing.get_readings_for_billing_period_sync(
            gateway_id=gateway_id,
            period_start=period_start,
            period_end=period_end,
        )
        actual_generation_kwh = billing_data["actual_generation_kwh"]

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
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "computed_at": now.isoformat(),
        }

        sync_redis_client.setex(
            f"site_stats:{site_uid}",
            600,
            json.dumps(stats),
        )

    except Exception as exc:
        raise self.retry(exc=exc)
