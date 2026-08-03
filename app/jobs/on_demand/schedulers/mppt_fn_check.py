import json
from datetime import date, time
from uuid import UUID

from sqlalchemy.orm import joinedload
from sqlmodel import select

from app.core.logger import setup_logger
from app.database.celery import celery_dynamo_client, get_celery_db_session
from app.database.redis import sync_redis_client
from app.jobs.celery import celery_app
from app.modules.contracts.model import Contract
from app.modules.mppt_function_check.model import SiteMPPTFunctionCheck
from app.modules.mppt_function_check.schema import SiteMpptFunctionCheckTable
from app.modules.string_wiring.model import StringWiring
from app.modules.string_wiring.schema import (
    ExpectedMPPT_ATable,
)
from app.shared.constants import Constants
from app.utils import some
from app.utils.json_encoders import json_default

logger = setup_logger(__name__)

ASSUMED_IRRADIANCE: dict[time, int] = {
    time(9, 0): 700,
    time(9, 30): 750,
    time(10, 0): 750,
    time(10, 30): 800,
    time(11, 0): 850,
    time(11, 30): 850,
    time(12, 0): 900,
    time(12, 30): 900,
    time(13, 0): 900,
    time(13, 30): 850,
    time(14, 0): 800,
    time(14, 30): 750,
    time(15, 0): 700,
}


def compute_mppt_fn_check(site_uid: UUID, date_at: date):
    lock_key = Constants.MPPT_FN_CHECK_LOCK.format(
        site_uid=str(site_uid),
        date_at=date_at.isoformat(),
    )
    lock_acquired = sync_redis_client.client.set(lock_key, "1", nx=True, ex=300)

    if not lock_acquired:
        logger.info(f"Skipping compute for {site_uid}/{date_at} — already in progress")
        return

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

            expected_mppt_a_table = None

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
                logger.info(f"Telemetry data for site {site_uid} at date: {date_at} not found")
                return

            expected_mppt_current_list = expected_mppt_a_table.to_list()
            site_mppt_fn_check_table = SiteMpptFunctionCheckTable.build(
                telemetry_reading=mppt_site_reading_list,
                assumed_ir_wm2=ASSUMED_IRRADIANCE,
                expected_mppt_table=expected_mppt_current_list,
            )

            site_mppt_fn_check = session.execute(
                select(SiteMPPTFunctionCheck).where(
                    SiteMPPTFunctionCheck.site_uid == site_uid,
                    SiteMPPTFunctionCheck.date_at == date_at,
                )
            ).scalar_one_or_none()

            if not site_mppt_fn_check:
                logger.info(f"mppt function check for site {site_uid} at date: {date_at} not found")
                return

            site_mppt_fn_check.telemetry_reading_str = json.dumps(mppt_site_reading_list, default=json_default)
            site_mppt_fn_check.mppt_fn_check_table_str = site_mppt_fn_check_table.to_json()

            if not some(mppt_site_reading_list, lambda reading: reading is None):
                site_mppt_fn_check.is_completed = True

            session.commit()
            return

    except Exception as exc:
        raise exc
    finally:
        sync_redis_client.client.delete(lock_key)


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
