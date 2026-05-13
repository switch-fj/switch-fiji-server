from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import joinedload, selectinload
from sqlmodel import Session, select, update

from app.core.logger import setup_logger
from app.database.celery import celery_dynamo_client, get_celery_db_session
from app.jobs.billing.engine import BillingEngine
from app.jobs.celery import celery_app
from app.jobs.contracts.shared import _get_active_contracts
from app.modules.contracts.model import Contract
from app.modules.contracts.schema import ContractSystemModeEnum, ContractTypeEnum
from app.modules.devices.model import Device
from app.modules.devices.schema import DeviceType
from app.modules.invoices.model import (
    Invoice,
    InvoiceHistory,
    InvoiceLineItem,
    InvoiceMeterData,
)
from app.modules.invoices.schema import CreateInvoiceHistoryModel
from app.modules.settings.model import ContractSettings

logger = setup_logger(__name__)


@celery_app.task(
    name="compute_active_contracts",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def compute_active_contracts(self):
    """
    Beat triggers this every hour.
    Fetches all active contracts and dispatches
    one compute task per contract to the worker pool.
    """
    try:
        with get_celery_db_session() as session:
            active_contracts = _get_active_contracts(session)

        for datum in active_contracts:
            compute_contract_invoice.delay(
                contract_uid=datum.contract_uid,
                gateway_id=datum.gateway_id,
                site_uid=datum.site_uid,
            )

    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(
    name="compute_contract_invoice",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def compute_contract_invoice(self, contract_uid, gateway_id, site_uid):
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
            now_local = datetime.now(tz=tz)

            commissioned_at = contract.details.actual_commissioned_at or contract.details.commissioned_at

            period_start, period_end = BillingEngine.get_current_billing_period(
                commissioned_at=commissioned_at,
                billing_frequency=contract.details.billing_frequency,
                as_of=now_local,
            )

            is_ppa = contract.contract_type == ContractTypeEnum.PPA.value
            is_ppa_off_grid = is_ppa and contract.system_mode == ContractSystemModeEnum.OFF_GRID.value
            is_ppa_on_grid_with_battery = (
                is_ppa
                and contract.system_mode == ContractSystemModeEnum.ON_GRID.value
                and contract.details.with_battery == "yes"
            )

            if not is_ppa:
                # WIP: lease computation
                return

            is_billing_date = now_local >= period_end.astimezone(tz)

            if is_billing_date:
                _handle_invoice(
                    session=session,
                    contract=contract,
                    contract_settings=contract_settings,
                    devices=devices,
                    gateway_id=gateway_id,
                    period_start=period_start,
                    period_end=period_end,
                    tz=tz,
                    is_ppa_off_grid=is_ppa_off_grid,
                    is_ppa_on_grid_with_battery=is_ppa_on_grid_with_battery,
                )

    except Exception as exc:
        raise self.retry(exc=exc)


def _handle_invoice(
    session: Session,
    contract: Contract,
    contract_settings: ContractSettings,
    devices: Device,
    gateway_id: str,
    period_start: datetime,
    period_end: datetime,
    is_ppa_off_grid: bool,
    is_ppa_on_grid_with_battery: bool,
):
    already_invoiced = session.execute(
        select(Invoice).where(
            Invoice.contract_uid == contract.uid,
            Invoice.period_start_at == period_start,
            Invoice.period_end_at == period_end,
        )
    ).scalar_one_or_none()

    if already_invoiced:
        return

    result = BillingEngine.compute_invoice_data(
        contract=contract,
        contract_settings=contract_settings,
        devices=devices,
        gateway_id=gateway_id,
        period_start=period_start,
        period_end=period_end,
        is_ppa_off_grid=is_ppa_off_grid,
        is_ppa_on_grid_with_battery=is_ppa_on_grid_with_battery,
    )
    if result is None:
        logger.warning(f"Invoice computation returned no data for contract {contract.uid}")
        return

    create_invoice_dict, invoice_details_dict = result
    invoice_meter_data = invoice_details_dict.invoice_meter_data
    invoice_line_items = invoice_details_dict.invoice_line_items

    new_invoice = Invoice(**create_invoice_dict)
    session.add(new_invoice)
    session.flush()

    session.add_all(
        [InvoiceMeterData(**{**d.model_dump(), "invoice_uid": new_invoice.uid}) for d in invoice_meter_data]
    )
    session.add_all([InvoiceLineItem(**{**d.model_dump(), "invoice_uid": new_invoice.uid}) for d in invoice_line_items])
    session.add(
        InvoiceHistory(
            **CreateInvoiceHistoryModel(
                invoice_uid=new_invoice.uid,
                sent_to=contract.client.client_email,
                sent_at=datetime.now(timezone.utc),
                was_successful=True,
            ).model_dump()
        )
    )
    session.commit()

    pdf_bytes, key = BillingEngine.generate_pdf(
        contract=contract,
        contract_settings=contract_settings,
        result=(new_invoice, invoice_meter_data, invoice_line_items),
    )
    BillingEngine.store_pdf_in_s3(pdf_bytes=pdf_bytes, key=key, invoice_ref=new_invoice.invoice_ref)
    session.execute(update(Invoice).where(Invoice.uid == new_invoice.uid).values(pdf_s3_key=key))
    session.commit()
