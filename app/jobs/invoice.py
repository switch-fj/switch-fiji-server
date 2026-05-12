from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import joinedload, selectinload
from sqlmodel import Session, select, update

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
    InvoiceHistory,
    InvoiceLineItem,
    InvoiceMeterData,
    InvoiceSnapshot,
    InvoiceSnapshotLineItem,
    InvoiceSnapshotMeterData,
)
from app.modules.invoices.schema import CreateInvoiceHistoryModel
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
                SELECT DISTINCT
                    c.uid::text AS contract_uid, 
                    s.uid::text  AS site_uid,
                    s.gateway_id AS gateway_id
                FROM sites s
                JOIN contracts c ON c.site_uid = s.uid
                JOIN contract_details cd ON cd.contract_uid = c.uid
                WHERE COALESCE(cd.actual_commissioned_at, cd.commissioned_at) IS NOT NULL
                    AND NOW() > COALESCE(cd.actual_commissioned_at, cd.commissioned_at)
                    AND NOW() < COALESCE(cd.actual_end_at, cd.end_at)
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
            elif now_local.hour == 0:
                snapshot_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
                snapshot_end = now_local.replace(hour=23, minute=59, second=59, microsecond=999999).astimezone(
                    timezone.utc
                )

                _handle_snapshot(
                    session=session,
                    contract=contract,
                    contract_settings=contract_settings,
                    devices=devices,
                    gateway_id=gateway_id,
                    snapshot_start=snapshot_start,
                    snapshot_end=snapshot_end,
                    is_ppa_off_grid=is_ppa_off_grid,
                    is_ppa_on_grid_with_battery=is_ppa_on_grid_with_battery,
                )

    except Exception as exc:
        raise self.retry(exc=exc)


def _compute_invoice_data(
    contract: Contract,
    contract_settings: ContractSettings,
    devices: Device,
    gateway_id: str,
    period_start: datetime,
    period_end: datetime,
    is_ppa_off_grid: bool,
    is_ppa_on_grid_with_battery: bool,
):
    """
    Run billing engine computation for a given period.
    Returns:
        (create_invoice_dict, invoice_details_dict) or None.
    """
    create_invoice_dict = None
    invoice_details_dict = None

    if is_ppa_off_grid or is_ppa_on_grid_with_battery:
        off_grid_result = BillingEngine.compute_ppa_off_grid_invoice(
            contract=contract,
            contract_settings=contract_settings,
            gateway_id=gateway_id,
            period_start=period_start,
            period_end=period_end,
        )
        if off_grid_result is None:
            return None

        create_invoice_dict, readings = off_grid_result
        invoice_details_dict = BillingEngine.build_ppa_off_grid_invoice_details(
            devices=devices,
            contract_settings=contract_settings,
            active_tariff_slots=contract.details.active_tariff_slots,
            tariff_indexed_rule_type=contract.details.tariff_indexed_rule_type,
            readings=readings,
        )
    else:
        computed = BillingEngine.compute_ppa_on_grid_no_battery_invoice(
            contract=contract,
            contract_settings=contract_settings,
            gateway_id=gateway_id,
            period_start=period_start,
            period_end=period_end,
        )
        if computed is None:
            return None

        create_invoice_dict = computed.create_invoice_dict
        invoice_details_dict = BillingEngine.build_ppa_on_grid_no_battery_invoice_details(
            devices=devices,
            contract_settings=contract_settings,
            computed_ppa_no_battery_invoice_resp=computed,
        )

    if create_invoice_dict is None or invoice_details_dict is None:
        return None

    return create_invoice_dict, invoice_details_dict


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

    result = _compute_invoice_data(
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


def _handle_snapshot(
    session: Session,
    contract: Contract,
    contract_settings: ContractSettings,
    devices: Device,
    gateway_id: str,
    snapshot_start: datetime,
    snapshot_end: datetime,
    is_ppa_off_grid: bool,
    is_ppa_on_grid_with_battery: bool,
):
    existing_snapshot = session.execute(
        select(InvoiceSnapshot).where(
            InvoiceSnapshot.contract_uid == contract.uid,
            InvoiceSnapshot.period_start_at == snapshot_start,
            InvoiceSnapshot.period_end_at == snapshot_end,
        )
    ).scalar_one_or_none()

    if existing_snapshot:
        return

    result = _compute_invoice_data(
        contract=contract,
        contract_settings=contract_settings,
        devices=devices,
        gateway_id=gateway_id,
        period_start=snapshot_start,
        period_end=snapshot_end,
        is_ppa_off_grid=is_ppa_off_grid,
        is_ppa_on_grid_with_battery=is_ppa_on_grid_with_battery,
    )
    if result is None:
        logger.warning(
            f"Snapshot computation returned no data for contract {contract.uid} ({snapshot_start} → {snapshot_end})"
        )
        return

    create_invoice_dict, invoice_details_dict = result
    invoice_meter_data = invoice_details_dict.invoice_meter_data
    invoice_line_items = invoice_details_dict.invoice_line_items

    snapshot = InvoiceSnapshot(
        contract_uid=contract.uid,
        period_start_at=snapshot_start,
        period_end_at=snapshot_end,
        period_start_telemetry_data=create_invoice_dict.get("period_start_telemetry_data"),
        period_end_telemetry_data=create_invoice_dict.get("period_end_telemetry_data"),
        subtotal=invoice_details_dict.subtotal,
        vat_rate=invoice_details_dict.vat_rate,
        efl_standard_rate_kwh=invoice_details_dict.efl_standard_rate_kwh,
        energy_mix=invoice_details_dict.energy_mix,
    )

    session.add(snapshot)
    session.flush()

    session.add_all(
        [InvoiceSnapshotMeterData(**{**d.model_dump(), "snapshot_uid": snapshot.uid}) for d in invoice_meter_data]
    )
    session.add_all(
        [InvoiceSnapshotLineItem(**{**d.model_dump(), "snapshot_uid": snapshot.uid}) for d in invoice_line_items]
    )
    session.commit()
