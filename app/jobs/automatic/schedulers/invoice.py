from datetime import datetime, timezone
from zoneinfo import ZoneInfo

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
    name="compute_contract_invoice_on_auto",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def compute_contract_invoice_on_auto(self, contract_uid, gateway_id, site_uid):
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

            tz = ZoneInfo(contract.timezone)
            now_local = datetime.now(tz=timezone.utc)

            commissioned_at = contract.details.actual_commissioned_at or contract.details.commissioned_at

            # all_periods = BillingEngine.get_all_billing_periods(
            #     commissioned_at=commissioned_at,
            #     billing_frequency=contract.details.billing_frequency,
            #     as_of=now_local,
            #     weekly_billing_start_day=contract.details.weekly_billing_start_day,
            # )

            # for idx, (period_start, period_end) in enumerate(all_periods):
            #     try:
            #         logger.info(f"Processing period {period_start} -> {period_end}")

            #         BillingEngine.handle_invoice_bill(
            #             session=session,
            #             contract=contract,
            #             contract_settings=contract_settings,
            #             devices=devices,
            #             gateway_id=gateway_id,
            #             period_start=period_start,
            #             period_end=period_end,
            #         )

            #         logger.info("Completed period")

            #     except Exception as exc:
            #         logger.exception(
            #             f"Failed processing period {period_start} -> {period_end}. Error: {exc}"
            #         )

            period_start, period_end = BillingEngine.get_current_billing_period(
                commissioned_at=commissioned_at,
                billing_frequency=contract.details.billing_frequency,
                as_of=now_local,
                weekly_billing_start_day=contract.details.weekly_billing_start_day,
            )

            is_billing_date = now_local >= period_end.astimezone(tz)

            if is_billing_date:
                try:
                    logger.info(f"Processing period {period_start} -> {period_end}")

                    BillingEngine.handle_invoice_bill(
                        session=session,
                        contract=contract,
                        contract_settings=contract_settings,
                        devices=devices,
                        gateway_id=gateway_id,
                        period_start=period_start,
                        period_end=period_end,
                    )

                    logger.info("Completed period")

                except Exception as exc:
                    logger.exception(f"Failed processing period {period_start} -> {period_end}. Error: {exc}")

    except Exception as exc:
        raise self.retry(exc=exc)
