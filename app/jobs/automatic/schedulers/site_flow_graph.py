import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import joinedload
from sqlmodel import select

from app.core.logger import setup_logger
from app.database.celery import celery_dynamo_client, get_celery_db_session
from app.database.redis import sync_redis_client
from app.jobs.celery import celery_app
from app.modules.contracts.model import Contract
from app.modules.contracts.schema import ContractSystemModeEnum, ContractTypeEnum
from app.modules.sites.wizard.ppa_off_grid_energy_usage import (
    PPAOffGridEnergyUsageWizard,
)
from app.shared.constants import Constants

logger = setup_logger(__name__)


@celery_app.task(
    name="compute_site_flow_graph_on_auto",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def compute_site_flow_graph_on_auto(self, site_uid: str, gateway_id: str):
    """
    Computes Energy flow graph for a single site
    and writes the result to Redis.
    """
    try:
        celery_dynamo_client.init()
        redis_key = Constants.SITE_FLOW_GRAPH.replace("site_uid", site_uid)
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

            now = datetime.now(tz=timezone.utc).isoformat()

            if not contract or not contract.details:
                sync_redis_client._client.setex(
                    redis_key,
                    600,
                    json.dumps(
                        {
                            "graph": None,
                            "message": "Site has no contract",
                            "computed_at": now,
                        }
                    ),
                )
                return

            commissioned_at = contract.details.actual_commissioned_at or contract.details.commissioned_at

            if not commissioned_at or datetime.now(timezone.utc) <= commissioned_at:
                sync_redis_client._client.setex(
                    redis_key,
                    600,
                    json.dumps(
                        {
                            "graph": None,
                            "message": "site contract has not started",
                            "computed_at": now,
                        }
                    ),
                )
                return

            telemetry_reading_list = celery_dynamo_client.get_site_by_date(
                date_at=datetime.now(tz=ZoneInfo(contract.site.tz or contract.timezone)),
                gateway_id=gateway_id,
            )

            logger.info(f"redis key: {redis_key}")

            if telemetry_reading_list is None:
                sync_redis_client._client.setex(
                    redis_key,
                    600,
                    json.dumps(
                        {
                            "graph": None,
                            "message": "flow graph computed",
                            "computed_at": now,
                        }
                    ),
                )
                return

            graph: dict | None = None

            if (
                contract.contract_type == ContractTypeEnum.PPA
                and contract.system_mode == ContractSystemModeEnum.OFF_GRID
            ):
                energy_usage_wizard = PPAOffGridEnergyUsageWizard(telemetry_readings=telemetry_reading_list)
                energy_usage = energy_usage_wizard.compute_energy_usage()
                graph = energy_usage[0].data.model_dump() if energy_usage else None

            logger.info(f"graph: {graph}")
            sync_redis_client._client.setex(
                redis_key,
                600,
                json.dumps(
                    {
                        "graph": graph,
                        "message": "flow graph computed",
                        "computed_at": now,
                    }
                ),
            )

    except Exception as exc:
        raise self.retry(exc=exc)
