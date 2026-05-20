from celery import Celery
from celery.schedules import crontab

from app.database.redis import sync_redis_client
from app.utils import build_redis_url

redbeat_redis_url = build_redis_url()
broker_url = build_redis_url(db=1)
backend_url = build_redis_url(db=2)

celery_app = Celery(
    "switch-network",
    broker=broker_url,
    backend=backend_url,
)

celery_app.conf.update(
    beat_scheduler="redbeat.RedBeatScheduler",
    redbeat_redis_url=redbeat_redis_url,
)


celery_app.conf.beat_schedule = {
    # "trigger_site_stats_every_5_minutes": {
    #     "task": "compute_site_stats",
    #     "schedule": crontab(minute="*/1"),
    # },
    "trigger_compute_active_contracts_every_hour": {
        "task": "compute_active_contracts",
        "schedule": crontab(minute="*/1"),
    },
    # "trigger_snapshot_active_contracts_at_00_30": {
    #     "task": "snapshot_active_contracts",
    #     "schedule": crontab(minute="*/1"),
    # },
}


@celery_app.on_after_configure.connect
def setup_sync_redis(sender, **kwargs):
    sync_redis_client.init()


celery_app.conf.timezone = "UTC"
celery_app.autodiscover_tasks(["app.jobs"])

from app.jobs import auth  # noqa
from app.jobs.sites import stats  # noqa
from app.jobs.invoicing import invoice  # noqa
from app.jobs.invoicing import snapshot  # noqa
