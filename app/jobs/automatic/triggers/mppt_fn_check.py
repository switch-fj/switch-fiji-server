from app.core.logger import setup_logger
from app.jobs.celery import celery_app

logger = setup_logger(__name__)


@celery_app.task(
    name="trigger_todays_site_mppt_fn_check_on_auto",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def trigger_todays_site_mppt_fn_check_on_auto(self):
    """
    Runs every 30 min. Refreshes mppt-function-check entries only for
    sites that have already been requested today (i.e. have an existing
    row for today's date) and whose window (09:00-15:00 site-local)
    hasn't closed yet.
    """
    try:
        pass
    except Exception as exc:
        raise self.retry(exc=exc)
