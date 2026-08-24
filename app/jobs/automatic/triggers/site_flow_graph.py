from datetime import datetime, timedelta, timezone

from sqlmodel import func, select

from app.core.logger import setup_logger
from app.database.celery import get_celery_db_session
from app.jobs.automatic.schedulers.site_flow_graph import (
    compute_site_flow_graph_on_auto,
)
from app.jobs.celery import celery_app
from app.modules.devices.model import Device
from app.modules.sites.model import Site

logger = setup_logger(__name__)


@celery_app.task(
    name="trigger_site_flow_graph_computation_on_auto",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def trigger_site_flow_graph_computation_on_auto(self):
    """
    Beat triggers this every 5 mins.
    Fetches all sites and dispatches
    one compute task per site to the worker pool.
    """
    try:
        with get_celery_db_session() as session:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            result = session.execute(
                select(Site)
                .join(Device, Device.site_uid == Site.uid)
                .where(Site.deleted_at.is_(None))
                .group_by(Site.uid)
                .having(func.max(Device.last_seen_at) >= cutoff)
            )
            sites = result.scalars().all()

            for site in sites:
                compute_site_flow_graph_on_auto.delay(
                    site_uid=str(site.uid),
                    gateway_id=str(site.gateway_id),
                )

    except Exception as exc:
        raise self.retry(exc=exc)
