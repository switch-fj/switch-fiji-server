from datetime import date
from uuid import UUID

from sqlalchemy.orm import joinedload
from sqlmodel import select

from app.core.logger import setup_logger
from app.database.celery import celery_dynamo_client, get_celery_db_session
from app.jobs.celery import celery_app
from app.modules.contracts.model import Contract
from app.modules.string_wiring.model import StringWiring
from app.modules.string_wiring.schema import (
    ExpectedMPPT_ATable,
)

logger = setup_logger(__name__)


def compute_mppt_fn_check(site_uid: UUID, date_at: date):

    try:
        celery_dynamo_client.init()
        with get_celery_db_session() as session:
            contract = session.execute(select(Contract).where(Contract.site_uid == site_uid)).scalar_one_or_none()

            if contract is None:
                return

            string_wiring = session.execute(
                select(StringWiring).options(joinedload(StringWiring.site)).where(StringWiring.site_uid == site_uid)
            ).scalar_one_or_none()

            if string_wiring is None:
                return

            # string_schematics_model_adapter = TypeAdapter(List[StringSchematicsModel])
            # wiring_schematics = None
            # mppt_fn_table = None
            expected_mppt_a_table = None

            # if string_wiring.wring_schematics:
            #     wiring_schematics = string_schematics_model_adapter.validate_json(
            #         string_wiring.wring_schematics
            #     )

            # if string_wiring.mppt_fn_table:
            #     mppt_fn_table = MPPTFunctionTable.from_json(string_wiring.mppt_fn_table)

            if string_wiring.mppt_fn_table:
                expected_mppt_a_table = ExpectedMPPT_ATable.from_json(string_wiring.expected_mppt_a_table)

            if not expected_mppt_a_table:
                return

            if not string_wiring.site.gateway_id:
                return

            mppt_site_reading_list = celery_dynamo_client.get_site_readings_for_mppt_fn_check(
                gateway_id=string_wiring.site.gateway_id,
                date_at=date_at,
                tz=string_wiring.site.tz or contract.timezone,
            )

            if mppt_site_reading_list is None:
                return

            # expected_mppt_current_list = expected_mppt_a_table.to_list()
            logger.info(f"site reading list: {mppt_site_reading_list}")

    except Exception as exc:
        raise exc


@celery_app.task(
    name="schedule_site_mppt_fn_check_on_demand",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def schedule_site_mppt_fn_check_on_demand(self, site_uid, date_at):
    try:
        compute_mppt_fn_check(site_uid=site_uid, date_at=date_at)
    except Exception as exc:
        logger.error(f"mppt fun check computation failed with reason: {exc}")
        raise self.retry(exc=exc)
