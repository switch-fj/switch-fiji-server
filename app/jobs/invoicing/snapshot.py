from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import joinedload, selectinload
from sqlmodel import Session, select

from app.core.logger import setup_logger
from app.database.celery import celery_dynamo_client, get_celery_db_session
from app.jobs.celery import celery_app
from app.jobs.invoicing.shared import _get_active_contracts
from app.modules.billing.engine import BillingEngine
from app.modules.contracts.model import Contract
from app.modules.contracts.schema import ContractBillingFrequencyEnum
from app.modules.contracts.wizard.ppa_off_grid import PPAOffGridContractWizard
from app.modules.contracts.wizard.ppa_on_grid_no_battery import (
    PPAOnGridNoBatteryContractWizard,
)
from app.modules.contracts.wizard.ppa_on_grid_with_battery import (
    PPAOnGridWithBatteryContractWizard,
)
from app.modules.devices.model import Device
from app.modules.devices.schema import DeviceType
from app.modules.invoices.model import (
    InvoiceSnapshot,
    InvoiceSnapshotLineItem,
    InvoiceSnapshotMeterData,
)
from app.modules.settings.model import ContractSettings
from app.utils.contracts import (
    is_lease,
    is_ppa_off_grid,
    is_ppa_on_grid_no_battery,
    is_ppa_on_grid_with_battery,
)

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
            # yesterday = (now_utc - timedelta(days=1)).date()
            commissioned_at = contract.details.actual_commissioned_at or contract.details.commissioned_at
            # snapshot_start = datetime(
            #     yesterday.year,
            #     yesterday.month,
            #     yesterday.day,
            #     0,
            #     0,
            #     0,
            #     tzinfo=timezone.utc,
            # )
            # snapshot_end = datetime(
            #     yesterday.year,
            #     yesterday.month,
            #     yesterday.day,
            #     23,
            #     59,
            #     59,
            #     999999,
            #     tzinfo=timezone.utc,
            # )

            all_periods = BillingEngine.get_all_billing_periods(
                commissioned_at=commissioned_at,
                billing_frequency=ContractBillingFrequencyEnum.DAILY.value,
                as_of=now_utc,
            )

            for idx, (period_start, period_end) in enumerate(all_periods):
                try:
                    logger.info(f"{idx}: {period_start} -> {period_end}")

                    _handle_snapshot(
                        session=session,
                        contract=contract,
                        contract_settings=contract_settings,
                        devices=devices,
                        gateway_id=gateway_id,
                        snapshot_start=period_start,
                        snapshot_end=period_end,
                    )

                    logger.info("Completed period")

                except Exception as exc:
                    logger.exception(f"Failed processing period {idx}: {period_start} -> {period_end}. Error: {exc}")

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

    if is_lease(contract=contract):
        # WIP: Factory under construction.
        pass

    if is_ppa_on_grid_with_battery(contract=contract):
        ppa_on_grid_with_battery_wizard = PPAOnGridWithBatteryContractWizard.factory(
            telemetry_start_reading=telemetry_start_reading,
            telemetry_end_reading=telemetry_end_reading,
            contract=contract,
            devices=devices,
            contract_settings=contract_settings,
        )

        snapshot = ppa_on_grid_with_battery_wizard.invoice_snapshot(
            period_start_at=snapshot_start, period_end_at=snapshot_end
        )
        invoice_meter_data = ppa_on_grid_with_battery_wizard.invoice_meter_data
        invoice_line_items = ppa_on_grid_with_battery_wizard.invoice_line_items

    if is_ppa_off_grid(contract=contract):
        ppa_off_grid_wizard = PPAOffGridContractWizard.factory(
            telemetry_start_reading=telemetry_start_reading,
            telemetry_end_reading=telemetry_end_reading,
            contract=contract,
            devices=devices,
            contract_settings=contract_settings,
        )

        snapshot = ppa_off_grid_wizard.invoice_snapshot(period_start_at=snapshot_start, period_end_at=snapshot_end)
        invoice_meter_data = ppa_off_grid_wizard.invoice_meter_data
        invoice_line_items = ppa_off_grid_wizard.invoice_line_items

    if is_ppa_on_grid_no_battery(contract=contract):
        ppa_on_grid_no_battery_wizard = PPAOnGridNoBatteryContractWizard.factory(
            telemetry_start_reading=telemetry_start_reading,
            telemetry_end_reading=telemetry_end_reading,
            contract=contract,
            devices=devices,
            contract_settings=contract_settings,
        )

        snapshot = ppa_on_grid_no_battery_wizard.invoice_snapshot(
            period_start_at=snapshot_start, period_end_at=snapshot_end
        )
        invoice_meter_data = ppa_on_grid_no_battery_wizard.invoice_meter_data
        invoice_line_items = ppa_on_grid_no_battery_wizard.invoice_line_items

    if not snapshot:
        logger.warning(f"Error creating invoice snapshot {gateway_id}")
        return

    try:
        session.add(snapshot)
        session.flush()

        session.add_all(
            [InvoiceSnapshotMeterData(**{**d.model_dump(), "snapshot_uid": snapshot.uid}) for d in invoice_meter_data]
        )
        session.add_all(
            [InvoiceSnapshotLineItem(**{**d.model_dump(), "snapshot_uid": snapshot.uid}) for d in invoice_line_items]
        )
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(e)
        raise e
