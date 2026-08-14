import json
from datetime import date, time
from uuid import UUID

from sqlalchemy.orm import Session, joinedload
from sqlmodel import select

from app.core.logger import setup_logger
from app.database.celery import celery_dynamo_client, get_celery_db_session
from app.database.redis import sync_redis_client
from app.jobs.celery import celery_app
from app.modules.batteries_soc.model import (
    BatterySOCConfigHistory,
    BatteryStateofCharge,
)
from app.modules.batteries_soc.schema import (
    BatterySOCTableModel,
    ConfigBatterySOCInputModel,
)
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


def handle_battery_soc(
    telemetry_reading_list: list[dict],
    telemetry_reading_str: str,
    session: Session,
    site_uid: UUID,
    date_at: date,
    is_completed: bool,
):
    battery_soc_config = session.execute(
        select(BatterySOCConfigHistory).where(
            BatterySOCConfigHistory.site_uid == site_uid,
            BatterySOCConfigHistory.effective_to.is_(None),
        )
    ).scalar_one_or_none()

    if battery_soc_config is None:
        logger.info(f"Battery Soc Config for site {site_uid} at date: {date_at} not found")
        return

    battery_soc = session.execute(
        select(BatteryStateofCharge).where(
            BatteryStateofCharge.site_uid == site_uid,
            BatteryStateofCharge.date_at == date_at,
        )
    ).scalar_one_or_none()

    if battery_soc is None:
        battery_soc = BatteryStateofCharge(
            site_uid=site_uid,
            battery_soc_config_uid=battery_soc_config.uid,
            date_at=date_at,
            from_=time(9, 0),
            to=time(15, 0),
            interval_in_minutes=30,
            is_completed=False,
        )

    config_input = ConfigBatterySOCInputModel.from_json(battery_soc_config.config_input_str)

    battery_soc_table = BatterySOCTableModel.build(
        telemetry_reading=telemetry_reading_list,
        time_boundaries=list(ASSUMED_IRRADIANCE.keys()),
        battery_soc_input=config_input,
    )

    battery_soc.telemetry_reading_str = telemetry_reading_str
    battery_soc.battery_soc_table_str = battery_soc_table.to_json()
    battery_soc.is_completed = is_completed

    session.flush()
    session.refresh(battery_soc)
    return


def handle_mppt_fn(
    telemetry_reading_list: list[dict],
    telemetry_reading_str: str,
    session: Session,
    site_uid: UUID,
    date_at: date,
    expected_mppt_a_table: ExpectedMPPT_ATable,
    string_wiring: StringWiring,
    is_completed: bool,
):
    expected_mppt_current_list = expected_mppt_a_table.to_list()
    site_mppt_fn_check_table = SiteMpptFunctionCheckTable.build(
        telemetry_reading=telemetry_reading_list,
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

    site_mppt_fn_check.telemetry_reading_str = telemetry_reading_str
    site_mppt_fn_check.mppt_fn_check_table_str = site_mppt_fn_check_table.to_json()
    site_mppt_fn_check.is_completed = is_completed

    session.flush()
    session.refresh(string_wiring)
    return


def compute_mppt_and_ba3_soc(site_uid: UUID, date_at: date):
    lock_key = Constants.MPPT_BA3_SOC_LOCK.format(
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

            telemetry_reading_list = celery_dynamo_client.get_site_readings_by_date_and_interval(
                gateway_id=string_wiring.site.gateway_id,
                date_at=date_at,
                tz=string_wiring.site.tz or contract.timezone,
            )

            if telemetry_reading_list is None:
                logger.info(f"Telemetry data for site {site_uid} at date: {date_at} not found")
                return

            telemetry_reading_str = json.dumps(telemetry_reading_list, default=json_default)
            is_completed = True if not some(telemetry_reading_list, lambda reading: reading is None) else False

            handle_mppt_fn(
                session=session,
                site_uid=site_uid,
                date_at=date_at,
                telemetry_reading_list=telemetry_reading_list,
                telemetry_reading_str=telemetry_reading_str,
                expected_mppt_a_table=expected_mppt_a_table,
                is_completed=is_completed,
            )
            handle_battery_soc(
                session=session,
                site_uid=site_uid,
                date_at=date_at,
                telemetry_reading_list=telemetry_reading_list,
                telemetry_reading_str=telemetry_reading_str,
                is_completed=is_completed,
            )

            session.commit()
            return

    except Exception as exc:
        raise exc
    finally:
        sync_redis_client.client.delete(lock_key)


@celery_app.task(
    name="schedule_site_mppt_and_ba3_soc_on_demand",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def schedule_site_mppt_and_ba3_soc_on_demand(self, site_uid, date_at):
    try:
        compute_mppt_and_ba3_soc(site_uid=site_uid, date_at=date_at)
    except Exception as exc:
        logger.error(f"mppt fun check computation failed with reason: {exc}")
        raise self.retry(exc=exc)
