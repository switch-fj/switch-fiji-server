from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import joinedload
from sqlmodel import select

from app.core.logger import setup_logger
from app.database.celery import celery_dynamo_client, get_celery_db_session
from app.jobs.billing.engine import BillingEngine
from app.jobs.celery import celery_app
from app.modules.contracts.model import Contract
from app.modules.contracts.schema import ContractSystemModeEnum, ContractTypeEnum
from app.modules.devices.model import Device
from app.modules.devices.schema import DeviceType
from app.modules.invoices.model import (
    Invoice,
)
from app.modules.settings.model import ContractSettings

logger = setup_logger(__name__)


@celery_app.task(
    name="compute_all_contracts_bill",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def compute_all_contracts_bill(self):
    """
    Beat triggers this every hour.
    Fetches all active contracts and dispatches
    one compute task per contract to the worker pool.
    """
    try:
        with get_celery_db_session() as session:
            result = session.execute(
                text("""
                SELECT
                    c.uid AS contract_uid,
                    s.gateway_id AS gateway_id,
                    s.site_id AS site_id,
                    s.uid as site_uid
                FROM contracts c
                JOIN sites s ON s.uid = c.site_uid
                JOIN contract_details cd ON cd.contract_uid = c.uid
                WHERE cd.commissioned_at IS NOT NULL
                    AND NOW() > cd.commissioned_at
                    AND NOW() < cd.end_at
                """)
            )
            contract_data = result.fetchall()

        for datum in contract_data:
            compute_single_contract_bill.delay(
                contract_uid=str(datum.contract_uid),
                gateway_id=datum.gateway_id,
                site_uid=str(datum.site_uid),
            )
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(name="compute_single_contract_bill", bind=True, max_retries=3, default_retry_delay=5)
def compute_single_contract_bill(self, contract_uid, gateway_id, site_uid):
    try:
        celery_dynamo_client.init()
        with get_celery_db_session() as session:
            contract = session.execute(
                select(Contract)
                .options(joinedload(Contract.details), joinedload(Contract.client))
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

            contract_settings = session.execute(select(ContractSettings)).scalars().first()

            if not contract or not devices:
                return

            tz = ZoneInfo(contract.timezone)
            now_local = datetime.now(tz=tz)

            period_start, period_end = BillingEngine.get_current_billing_period(
                timezone_key=contract.timezone,
                commissioned_at=contract.details.actual_commissioned_at or contract.details.commissioned_at,
                billing_frequency=contract.details.billing_frequency,
            )

            is_billing_date = now_local >= period_end.astimezone(tz)

            if is_billing_date:
                already_invoiced = session.execute(
                    select(Invoice).where(
                        Invoice.contract_uid == contract.uid,
                        Invoice.period_start_at == period_start,
                        Invoice.period_end_at == period_end,
                    )
                ).scalar_one_or_none()

                if already_invoiced:
                    return

            result = None

            if contract.contract_type == ContractTypeEnum.PPA.value:
                if contract.system_mode == ContractSystemModeEnum.OFF_GRID.value:
                    result = BillingEngine.compute_ppa_off_grid_invoice(
                        session=session,
                        contract=contract,
                        devices=devices,
                        contract_settings=contract_settings,
                        gateway_id=gateway_id,
                        period_start=period_start,
                        period_end=period_end,
                        is_billing_date=is_billing_date,
                    )

            if result is None:
                return

            if is_billing_date:
                BillingEngine.generate_pdf_in_background(
                    session=session,
                    contract=contract,
                    contract_settings=contract_settings,
                    result=result,
                )

    except Exception as exc:
        raise self.retry(exc=exc)
