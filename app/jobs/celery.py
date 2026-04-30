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
    "compute-site-stats-every-5-minutes": {
        "task": "compute_all_site_stats",
        "schedule": 30,
    },
    "compute-contract-bill-every-day-at-midnight": {
        "task": "compute_all_contracts_bill",
        "schedule": crontab(minute=0, hour=0),
    },
}


@celery_app.on_after_configure.connect
def setup_sync_redis(sender, **kwargs):
    sync_redis_client.init()


celery_app.conf.timezone = "UTC"
celery_app.autodiscover_tasks(["app.jobs"])

from app.jobs import auth  # noqa
from app.jobs import site_stats  # noqa
from app.jobs import invoice  # noqa
