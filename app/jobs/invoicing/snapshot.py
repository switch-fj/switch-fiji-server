from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import joinedload, selectinload
from sqlmodel import Session, select

from app.core.logger import setup_logger
from app.database.celery import celery_dynamo_client, get_celery_db_session
from app.jobs.celery import celery_app
from app.jobs.invoicing.shared import _get_active_contracts
from app.modules.billing.ppa_off_grid import PPAOffGridFactory
from app.modules.billing.ppa_on_grid_no_battery import PPAOnGridNoBatteryFactory
from app.modules.billing.ppa_on_grid_with_battery import PPAOnGridWithBatteryFactory
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
    max_retries=0,
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

            is_lease = contract.contract_type == ContractTypeEnum.LEASE.value
            is_ppa = contract.contract_type == ContractTypeEnum.PPA.value
            is_ppa_off_grid = is_ppa and contract.system_mode == ContractSystemModeEnum.OFF_GRID.value
            is_ppa_on_grid_with_battery = (
                is_ppa
                and contract.system_mode == ContractSystemModeEnum.ON_GRID.value
                and contract.details.with_battery == "yes"
            )
            is_ppa_on_grid_no_battery = (
                is_ppa
                and contract.system_mode == ContractSystemModeEnum.ON_GRID.value
                and contract.details.with_battery == "no"
            )

            try:
                logger.info(f"{snapshot_start} -> {snapshot_end}")

                _handle_snapshot(
                    session=session,
                    contract=contract,
                    contract_settings=contract_settings,
                    devices=devices,
                    gateway_id=gateway_id,
                    snapshot_start=snapshot_start,
                    snapshot_end=snapshot_end,
                    is_lease=is_lease,
                    is_ppa_off_grid=is_ppa_off_grid,
                    is_ppa_on_grid_with_battery=is_ppa_on_grid_with_battery,
                    is_ppa_on_grid_no_battery=is_ppa_on_grid_no_battery,
                )

                logger.info("Completed period")

            except Exception as exc:
                logger.exception(f"Failed processing period {snapshot_start} -> {snapshot_end}. Error: {exc}")

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
    is_lease: bool,
    is_ppa_off_grid: bool,
    is_ppa_on_grid_with_battery: bool,
    is_ppa_on_grid_no_battery: bool,
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

    readings = celery_dynamo_client.get_readings_for_billing_period(
        gateway_id=gateway_id,
        period_start=snapshot_start,
        period_end=snapshot_end,
    )

    if not readings:
        logger.warning(f"No readings found for gateway {gateway_id}")
        return

    telemetry_start_reading, telemetry_end_reading = readings
    snapshot: Optional[InvoiceSnapshot] = None
    invoice_meter_data = None
    invoice_line_items = None

    if is_lease:
        # WIP: Factory under construction.
        pass

    if is_ppa_on_grid_with_battery:
        ppa_on_grid_with_battery_factory = PPAOnGridWithBatteryFactory.factory(
            telemetry_start_reading=telemetry_start_reading,
            telemetry_end_reading=telemetry_end_reading,
            contract=contract,
            devices=devices,
            contract_settings=contract_settings,
        )

        snapshot = ppa_on_grid_with_battery_factory.invoice_snapshot(
            period_start_at=snapshot_start, period_end_at=snapshot_end
        )
        invoice_meter_data = ppa_on_grid_with_battery_factory.invoice_meter_data
        invoice_line_items = ppa_on_grid_with_battery_factory.invoice_line_items

    if is_ppa_off_grid:
        ppa_off_grid_factory = PPAOffGridFactory.factory(
            telemetry_start_reading=telemetry_start_reading,
            telemetry_end_reading=telemetry_end_reading,
            contract=contract,
            devices=devices,
            contract_settings=contract_settings,
        )

        snapshot = ppa_off_grid_factory.invoice_snapshot(period_start_at=snapshot_start, period_end_at=snapshot_end)
        invoice_meter_data = ppa_off_grid_factory.invoice_meter_data
        invoice_line_items = ppa_off_grid_factory.invoice_line_items

    if is_ppa_on_grid_no_battery:
        ppa_on_grid_no_battery_factory = PPAOnGridNoBatteryFactory(
            telemetry_start_reading=telemetry_start_reading,
            telemetry_end_reading=telemetry_end_reading,
            contract=contract,
            devices=devices,
            contract_settings=contract_settings,
        )

        snapshot = ppa_on_grid_no_battery_factory.invoice_snapshot(
            period_start_at=snapshot_start, period_end_at=snapshot_end
        )
        invoice_meter_data = ppa_on_grid_no_battery_factory.invoice_meter_data
        invoice_line_items = ppa_on_grid_no_battery_factory.invoice_line_items

    if not snapshot:
        logger.warning(f"Error creating invoice snapshot {gateway_id}")
        return

    session.add(snapshot)
    session.flush()

    session.add_all(
        [InvoiceSnapshotMeterData(**{**d.model_dump(), "snapshot_uid": snapshot.uid}) for d in invoice_meter_data]
    )
    session.add_all(
        [InvoiceSnapshotLineItem(**{**d.model_dump(), "snapshot_uid": snapshot.uid}) for d in invoice_line_items]
    )
    session.commit()
