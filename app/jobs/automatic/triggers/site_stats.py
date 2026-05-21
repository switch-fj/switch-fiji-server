from sqlalchemy import text

from app.core.logger import setup_logger
from app.database.celery import get_celery_db_session
from app.jobs.automatic.schedulers.site_stats import compute_site_stat_on_auto
from app.jobs.celery import celery_app

logger = setup_logger(__name__)


@celery_app.task(
    name="trigger_site_stats_computation_on_auto",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def trigger_site_stats_computation_on_auto(self):
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
            compute_site_stat_on_auto.delay(
                site_uid=site.site_uid,
                gateway_id=site.gateway_id,
            )

    except Exception as exc:
        raise self.retry(exc=exc)
