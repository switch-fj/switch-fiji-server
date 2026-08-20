from datetime import date, time
from uuid import UUID

from sqlalchemy.orm import Session
from sqlmodel import select

from app.core.logger import setup_logger
from app.database.celery import celery_dynamo_client, get_celery_db_session
from app.database.redis import sync_redis_client
from app.jobs.celery import celery_app
from app.modules.contracts.model import Contract
from app.modules.sites.model import Site, SiteEnergyUsage
from app.shared.constants import Constants

logger = setup_logger(__name__)


def update_site_energy_usage(
    telemetry_reading_list: list[dict],
    telemetry_reading_str: str,
    session: Session,
    site_uid: UUID,
    date_at: date,
    is_completed: bool,
):
    site_energy_usage = session.execute(
        select(SiteEnergyUsage).where(
            SiteEnergyUsage.site_uid == site_uid,
            SiteEnergyUsage.date_at == date_at,
            SiteEnergyUsage.deleted_at.is_(None),
        )
    ).scalar_one_or_none()

    if site_energy_usage is None:
        site_energy_usage = SiteEnergyUsage(
            site_uid=site_uid,
            telemetry_reading_str=telemetry_reading_str,
            date_at=date_at,
            interval_in_minutes=30,
            is_completed=False,
        )

    site_energy_usage.is_completed = is_completed

    session.flush()
    session.refresh(site_energy_usage)
    return


def compute_site_energy_usage(site_uid: UUID, date_at: date):
    lock_key = Constants.SITE_ENERGY_USAGE_LOCK.format(
        site_uid=str(site_uid),
        date_at=date_at.isoformat(),
    )
    lock_acquired = sync_redis_client.client.set(lock_key, "1", nx=True, ex=300)

    if not lock_acquired:
        logger.info(f"Skipping compute for site energy usage {site_uid}/{date_at} — already in progress")
        return

    try:
        celery_dynamo_client.init()
        with get_celery_db_session() as session:
            contract = session.execute(select(Contract).where(Contract.site_uid == site_uid)).scalar_one_or_none()

            if contract is None:
                return

            site = session.execute(select(Site).where(Site.uid == site_uid)).scalar_one_or_none()

            if site is None:
                return

            telemetry_reading_list = celery_dynamo_client.get_site_readings_by_date_and_interval(
                gateway_id=site.gateway_id,
                date_at=date_at,
                _from=time(0, 0),
                to=time(23, 0),
                tz=site.tz or contract.timezone,
            )

            if telemetry_reading_list is None:
                logger.info(f"Telemetry data for Computing site energy usage {site_uid} at date: {date_at} not found")
                return

            # telemetry_reading_str = json.dumps(
            #     telemetry_reading_list, default=json_default
            # )
            # is_completed = (
            #     True
            #     if not some(telemetry_reading_list, lambda reading: reading is None)
            #     else False
            # )

            logger.info(telemetry_reading_list)

            session.commit()
            return

    except Exception as exc:
        raise exc
    finally:
        sync_redis_client.client.delete(lock_key)


@celery_app.task(
    name="schedule_site_energy_usage_on_demand",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def schedule_site_energy_usage_on_demand(self, site_uid, date_at):
    try:
        compute_site_energy_usage(site_uid=site_uid, date_at=date_at)
    except Exception as exc:
        logger.error(f"Site energy usage failed with reason: {exc}")
        raise self.retry(exc=exc)
