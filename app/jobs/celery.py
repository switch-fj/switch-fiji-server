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
    "trigger_site_stats_every_5_minutes": {
        "task": "trigger_site_stats_computation_on_auto",
        "schedule": crontab(minute="*/5"),
    },
    "trigger_compute_active_contracts_every_hour": {
        "task": "trigger_compute_contract_invoice_on_auto",
        "schedule": crontab(minute=0),
    },
    "trigger_snapshot_active_contracts_at_00_30": {
        "task": "trigger_compute_contract_invoice_snapshot_on_auto",
        "schedule": crontab(hour=0, minute=30),
    },
    "trigger_todays_site_mppt_and_ba3_soc_every_30min_between_9_and_15": {
        "task": "trigger_todays_site_mppt_and_ba3_soc_on_auto",
        "schedule": crontab(minute="1,31", hour="9-15"),
    },
    "trigger_todays_site_energy_every_30min_between_12_and_23_on_auto": {
        "task": "trigger_daily_site_energy_usage_on_auto",
        "schedule": crontab(minute="1,31", hour="0-23"),
    },
    "trigger_site_flow_graph_energy_every_5min_on_auto": {
        "task": "trigger_site_flow_graph_computation_on_auto",
        "schedule": crontab(minute="*/5"),
    },
}


@celery_app.on_after_configure.connect
def setup_sync_redis(sender, **kwargs):
    sync_redis_client.init()


celery_app.conf.timezone = "UTC"
celery_app.autodiscover_tasks(["app.jobs"])

from app.jobs.on_demand.schedulers import auth  # noqa

from app.jobs.automatic.schedulers import site_stats as site_stats_schedulers  # noqa
from app.jobs.automatic.triggers import site_stats as site_stats_triggers  # noqa
from app.jobs.automatic.schedulers import invoice as invoice_schedulers  # noqa
from app.jobs.automatic.triggers import invoice as invoice_triggers  # noqa
from app.jobs.automatic.schedulers import snapshot as snapshot_schedulers  # noqa
from app.jobs.automatic.triggers import snapshot as snapshot_triggers  # noqa
from app.jobs.automatic.triggers import (  # noqa
    mppt_battery_soc as mppt_fn_check_triggers,
)  # noqa
from app.jobs.automatic.triggers import (  # noqa
    site_energy_usage as site_energy_usage_triggers,
)  # noqa

from app.jobs.automatic.triggers import (  # noqa
    site_flow_graph as site_flow_graph_triggers,
)  # noqa

from app.jobs.on_demand.triggers import invoice as invoice_on_demand_triggers  # noqa
from app.jobs.on_demand.schedulers import (  # noqa
    invoice as invoice_on_demand_schedulers,  # noqa
)  # noqa
from app.jobs.on_demand.triggers import (  # noqa
    degradation as degradation_on_demand_triggers,
)  # noqa
from app.jobs.on_demand.schedulers import (  # noqa
    degradation as degradation_on_demand_schedulers,
)  # noqa
from app.jobs.on_demand.triggers import (  # noqa
    string_wiring as string_wiring_on_demand_triggers,
)  # noqa
from app.jobs.on_demand.schedulers import (  # noqa
    string_wiring as string_wiring_on_demand_schedulers,
)  # noqa
from app.jobs.on_demand.schedulers import (  # noqa
    mppt_battery_soc as mppt_fn_check_on_demand_schedulers,
)  # noqa
from app.jobs.on_demand.schedulers import (  # noqa
    site_energy_usage as site_energy_usage_on_demand_schedulers,
)  # noqa
