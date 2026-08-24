import json
from datetime import datetime, timezone

from sqlalchemy.orm import joinedload
from sqlmodel import select

from app.core.logger import setup_logger
from app.database.celery import celery_dynamo_client, get_celery_db_session
from app.database.redis import sync_redis_client
from app.jobs.celery import celery_app
from app.modules.contracts.model import Contract
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
        redis_key = Constants.SITE_FLOW_GRAPH.replace("uid", site_uid)
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

            now = datetime.now(tz=timezone.utc)

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

            graph = {}

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
