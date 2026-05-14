from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import joinedload, selectinload
from sqlmodel import Session, select

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
    InvoiceSnapshot,
    InvoiceSnapshotLineItem,
    InvoiceSnapshotMeterData,
)
from app.modules.settings.model import ContractSettings

logger = setup_logger(__name__)


@celery_app.task(name="snapshot_active_contracts", bind=True, max_retries=3, default_retry_delay=5)
def snapshot_active_contracts(self):
    try:
        with get_celery_db_session() as session:
            ctive_contracts = _get_active_contracts(session)

        for datum in ctive_contracts:
            compute_contract_invoice_snapshot.delay(
                contract_uid=str(datum.contract_uid),
                gateway_id=datum.gateway_id,
                site_uid=str(datum.site_uid),
            )
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(
    name="compute_contract_invoice_snapshot",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def compute_contract_invoice_snapshot(self, contract_uid, gateway_id, site_uid):
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

            is_ppa = contract.contract_type == ContractTypeEnum.PPA.value
            is_ppa_off_grid = is_ppa and contract.system_mode == ContractSystemModeEnum.OFF_GRID.value
            is_ppa_on_grid_with_battery = (
                is_ppa
                and contract.system_mode == ContractSystemModeEnum.ON_GRID.value
                and contract.details.with_battery == "yes"
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

    result = BillingEngine.compute_invoice_data(
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
