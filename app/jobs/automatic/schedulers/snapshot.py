from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import joinedload, selectinload
from sqlmodel import select

from app.core.logger import setup_logger
from app.database.celery import celery_dynamo_client, get_celery_db_session
from app.jobs.celery import celery_app
from app.modules.billing.engine import BillingEngine
from app.modules.contracts.model import Contract
from app.modules.devices.model import Device
from app.modules.devices.schema import DeviceType
from app.modules.settings.model import ContractSettings

logger = setup_logger(__name__)


@celery_app.task(
    name="compute_contract_invoice_snapshot_on_auto",
    bind=True,
    max_retries=0,
    default_retry_delay=5,
)
def compute_contract_invoice_snapshot_on_auto(self, contract_uid, gateway_id, site_uid):
    try:
        celery_dynamo_client.init()
        with get_celery_db_session() as session:
            contract = session.execute(
                select(Contract)
                .options(
                    joinedload(Contract.details),
                    joinedload(Contract.client),
                )
                .where(Contract.uid == contract_uid)
            ).scalar_one_or_none()

            devices = (
                session.execute(
                    select(Device).where(
                        Device.site_uid == site_uid,
                        Device.device_type == DeviceType.METER.value,
                    )
                )
                .scalars()
                .all()
            )

            contract_settings = (
                session.execute(
                    select(ContractSettings).options(
                        selectinload(ContractSettings.efl_rate_history),
                        selectinload(ContractSettings.vat_rate_history),
                    )
                )
                .scalars()
                .first()
            )

            if not contract or not devices:
                return

            now_utc = datetime.now(timezone.utc)
            yesterday = (now_utc - timedelta(days=1)).date()
            snapshot_start = datetime(
                yesterday.year,
                yesterday.month,
                yesterday.day,
                0,
                0,
                0,
                tzinfo=timezone.utc,
            )
            snapshot_end = datetime(
                yesterday.year,
                yesterday.month,
                yesterday.day,
                23,
                59,
                59,
                999999,
                tzinfo=timezone.utc,
            )

            try:
                logger.info(f" {snapshot_start} -> {snapshot_end}")

                BillingEngine.handle_invoice_snapshot_bill(
                    session=session,
                    contract=contract,
                    contract_settings=contract_settings,
                    devices=devices,
                    gateway_id=gateway_id,
                    snapshot_start=snapshot_start,
                    snapshot_end=snapshot_end,
                )

                logger.info("Completed period")

            except Exception as exc:
                logger.exception(f"Failed processing period {snapshot_start} -> {snapshot_end}. Error: {exc}")

    except Exception as exc:
        raise self.retry(exc=exc)
