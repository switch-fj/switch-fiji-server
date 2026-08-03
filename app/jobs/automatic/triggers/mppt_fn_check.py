from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import selectinload
from sqlmodel import select

from app.core.logger import setup_logger
from app.database.celery import get_celery_db_session
from app.jobs.celery import celery_app
from app.jobs.on_demand.schedulers.mppt_fn_check import compute_mppt_fn_check
from app.modules.mppt_function_check.model import SiteMPPTFunctionCheck
from app.modules.sites.model import Site

logger = setup_logger(__name__)


@celery_app.task(
    name="trigger_todays_site_mppt_fn_check_on_auto",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def trigger_todays_site_mppt_fn_check_on_auto(self):
    """
    Runs every 30 min, 09:01-15:31 site-local window trigger times.
    Refreshes mppt-function-check entries only for sites that already
    have an existing (incomplete) row for today, whose window
    (09:00-15:00 site-local) hasn't closed yet.
    """
    try:
        with get_celery_db_session() as session:
            sites = (
                session.execute(
                    select(Site)
                    .join(
                        SiteMPPTFunctionCheck,
                        SiteMPPTFunctionCheck.site_uid == Site.uid,
                    )
                    .options(selectinload(Site.contract))
                    .where(
                        Site.deleted_at.is_(None),
                        SiteMPPTFunctionCheck.is_completed.is_(False),
                    )
                )
                .scalars()
                .unique()
                .all()
            )

            if not sites:
                return

            for site in sites:
                try:
                    tz = site.tz
                    date_at = datetime.now(ZoneInfo(tz)).date()
                    compute_mppt_fn_check(site_uid=site.uid, date_at=date_at)
                except Exception as e:
                    logger.error(f"MPPT fn check failed for site {site.uid}: {e}")
                    continue

    except Exception as exc:
        raise self.retry(exc=exc)
