from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from dateutil.relativedelta import relativedelta
from sqlmodel import Session, select

from app.core.logger import setup_logger
from app.database.celery import celery_dynamo_client
from app.modules.contracts.model import Contract
from app.modules.contracts.schema import (
    ContractBillingFrequencyEnum,
    DayOfWeekEnum,
)
from app.modules.contracts.wizard.ppa_off_grid import PPAOffGridContractWizard
from app.modules.contracts.wizard.ppa_on_grid_no_battery import (
    PPAOnGridNoBatteryContractWizard,
)
from app.modules.contracts.wizard.ppa_on_grid_with_battery import (
    PPAOnGridWithBatteryContractWizard,
)
from app.modules.devices.model import Device
from app.modules.invoices.model import (
    Invoice,
    InvoiceHistory,
    InvoiceLineItem,
    InvoiceMeterData,
    InvoiceSnapshot,
    InvoiceSnapshotLineItem,
    InvoiceSnapshotMeterData,
)
from app.modules.invoices.pdf import InvoicePDF
from app.modules.invoices.repository import InvoiceRepository
from app.modules.invoices.schema import CreateInvoiceHistoryModel
from app.modules.settings.model import ContractSettings
from app.services.s3 import S3Service
from app.utils.contracts import (
    is_lease,
    is_ppa_off_grid,
    is_ppa_on_grid_no_battery,
    is_ppa_on_grid_with_battery,
)

logger = setup_logger(__name__)


class BillingEngine:
    @staticmethod
    def _extract_meter_by_description(reading: dict, description: str):
        selected_meter = []
        for meter in reading.get("meters", []):
            if meter.get("description") == description:
                selected_meter.append(meter)
        return selected_meter

    @staticmethod
    def get_current_billing_period(
        commissioned_at: datetime,
        billing_frequency: str,
        as_of: datetime,
        weekly_billing_start_day: Optional[DayOfWeekEnum],
    ):

        try:
            freq = ContractBillingFrequencyEnum(billing_frequency.lower())
        except ValueError:
            raise ValueError(f"Unsupported billing frequency: {billing_frequency}")

        if as_of < commissioned_at:
            raise ValueError("as_of cannot be before commissioned_at")

        if freq == ContractBillingFrequencyEnum.WEEKLY:
            if weekly_billing_start_day is None:
                weekly_billing_start_day = commissioned_at.weekday()
            periods = BillingEngine.get_all_billing_periods(
                commissioned_at=commissioned_at,
                billing_frequency=billing_frequency,
                as_of=as_of,
                weekly_billing_start_day=weekly_billing_start_day,
            )
            return periods[-1] if periods else None

        match freq:
            case ContractBillingFrequencyEnum.DAILY:
                n = (as_of - commissioned_at).days
                delta = relativedelta(days=1)
            case ContractBillingFrequencyEnum.BI_WEEKLY:
                n = (as_of - commissioned_at).days // 14
                delta = relativedelta(weeks=2)
            case ContractBillingFrequencyEnum.MONTHLY:
                diff = relativedelta(as_of, commissioned_at)
                n = diff.years * 12 + diff.months
                delta = relativedelta(months=1)
            case ContractBillingFrequencyEnum.QUARTERLY:
                diff = relativedelta(as_of, commissioned_at)
                total_months = diff.years * 12 + diff.months
                n = total_months // 3
                delta = relativedelta(months=3)
            case ContractBillingFrequencyEnum.SEMI_ANNUALLY:
                diff = relativedelta(as_of, commissioned_at)
                total_months = diff.years * 12 + diff.months
                n = total_months // 6
                delta = relativedelta(months=6)
            case ContractBillingFrequencyEnum.ANNUALLY:
                diff = relativedelta(as_of, commissioned_at)
                n = diff.years
                delta = relativedelta(years=1)

        period_start = commissioned_at + (delta * n)
        period_end = period_start + delta - relativedelta(seconds=1)

        return (period_start, period_end)

    @staticmethod
    def get_all_billing_periods(
        commissioned_at: datetime,
        billing_frequency: str,
        as_of: datetime,
        weekly_billing_start_day: Optional[DayOfWeekEnum] = None,
    ) -> list[tuple[datetime, datetime]]:
        """Returns all billing periods from commissioned_at up to as_of."""
        try:
            freq = ContractBillingFrequencyEnum(billing_frequency.lower())
        except ValueError:
            raise ValueError(f"Unsupported billing frequency: {billing_frequency}")

        if as_of < commissioned_at:
            raise ValueError("as_of cannot be before commissioned_at")

        if freq == ContractBillingFrequencyEnum.WEEKLY:
            if weekly_billing_start_day is None:
                weekly_billing_start_day = commissioned_at.weekday()
            return BillingEngine._get_weekly_billing_periods(
                commissioned_at=commissioned_at,
                start_day=weekly_billing_start_day,
                as_of=as_of,
            )

        match freq:
            case ContractBillingFrequencyEnum.DAILY:
                delta = relativedelta(days=1)
            case ContractBillingFrequencyEnum.BI_WEEKLY:
                delta = relativedelta(weeks=2)
            case ContractBillingFrequencyEnum.MONTHLY:
                delta = relativedelta(months=1)
            case ContractBillingFrequencyEnum.QUARTERLY:
                delta = relativedelta(months=3)
            case ContractBillingFrequencyEnum.SEMI_ANNUALLY:
                delta = relativedelta(months=6)
            case ContractBillingFrequencyEnum.ANNUALLY:
                delta = relativedelta(years=1)

        periods = []
        period_start = commissioned_at
        while True:
            period_end = period_start + delta - relativedelta(seconds=1)
            if period_end > as_of:
                break
            periods.append((period_start, period_end))
            period_start = period_end + relativedelta(seconds=1)

        return periods

    @staticmethod
    def _get_weekly_billing_periods(
        commissioned_at: datetime,
        start_day: DayOfWeekEnum,
        as_of: datetime,
    ) -> list[tuple[datetime, datetime]]:
        """
        Builds weekly billing periods where:
        - The first period starts on commissioned_at (which should fall on start_day).
        - Every period ends at end-of-day Sunday (23:59:59).
        - The next period starts on the configured start_day
        the following week, i.e. the day after Sunday + (start_day) days.
        """
        SUNDAY = DayOfWeekEnum.SUNDAY.value

        def next_sunday_eod(dt: datetime) -> datetime:
            """Return end-of-day (23:59:59) of the Sunday on or after dt."""
            days_until_sunday = (SUNDAY - dt.weekday()) % 7
            sunday = dt + relativedelta(days=days_until_sunday)
            return sunday.replace(hour=23, minute=59, second=59, microsecond=0)

        periods = []
        period_start = commissioned_at.replace(hour=0, minute=0, second=0, microsecond=0)

        # Align the first period_start to the configured start_day
        # if commissioned_at doesn't already land on it
        if period_start.weekday() != start_day:
            days_ahead = (start_day - period_start.weekday()) % 7
            period_start = period_start + relativedelta(days=days_ahead)

        while True:
            period_end = next_sunday_eod(period_start)
            if period_end > as_of:
                break
            periods.append((period_start, period_end))
            # Next period starts on the same weekday the following week (day after Sunday)
            period_start = period_end + relativedelta(days=1)  # Monday
            # Advance to the configured start_day of that same week
            days_to_start = (start_day - period_start.weekday()) % 7
            period_start = period_start + relativedelta(days=days_to_start)

        return periods

    @staticmethod
    def generate_pdf(
        contract: Contract,
        result: tuple[Invoice, list[InvoiceMeterData], list[InvoiceLineItem]],
        invoice_snapshots: list[InvoiceSnapshot],
        contract_settings: ContractSettings,
    ):
        invoice, meter_data, line_items = result

        pdf_bytes = InvoicePDF.render_invoice_pdf(
            invoice=invoice,
            contract=contract,
            line_items=line_items,
            meter_data=meter_data,
            invoice_snapshots=invoice_snapshots,
            contract_settings=contract_settings,
        )

        key = f"invoices/{invoice.invoice_ref}.pdf"

        return pdf_bytes, key

    @staticmethod
    def store_pdf_in_s3(pdf_bytes: bytes, key: str, invoice_ref: str):
        try:
            S3Service.upload_pdf(key=key, pdf_bytes=pdf_bytes)
        except Exception as e:
            logger.error(f"Failed to upload PDF to S3 for invoice {invoice_ref}: {e}")
            return

    @staticmethod
    def handle_invoice_snapshot_bill(
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
                [
                    InvoiceSnapshotMeterData(**{**d.model_dump(), "snapshot_uid": snapshot.uid})
                    for d in invoice_meter_data
                ]
            )
            session.add_all(
                [
                    InvoiceSnapshotLineItem(**{**d.model_dump(), "snapshot_uid": snapshot.uid})
                    for d in invoice_line_items
                ]
            )
            session.commit()

        except Exception as e:
            session.rollback()
            logger.error(e)
            raise e

    @staticmethod
    def handle_invoice_bill(
        session: Session,
        contract: Contract,
        contract_settings: ContractSettings,
        devices: Device,
        gateway_id: str,
        period_start: datetime,
        period_end: datetime,
    ):
        already_invoiced = session.execute(
            select(Invoice).where(
                Invoice.contract_uid == contract.uid,
                Invoice.period_start_at == period_start,
                Invoice.period_end_at == period_end,
            )
        ).scalar_one_or_none()

        if already_invoiced:
            logger.warning("Invoice already exists!")
            return

        readings = celery_dynamo_client.get_readings_for_billing_period(
            gateway_id=gateway_id,
            period_start=period_start.astimezone(tz=ZoneInfo(contract.timezone)),
            period_end=period_end.astimezone(tz=ZoneInfo(contract.timezone)),
            is_multi_day=True,
        )

        if not readings:
            logger.warning(f"No readings found for gateway {gateway_id}")
            return

        telemetry_start_reading, telemetry_end_reading = readings
        create_invoice = None
        invoice_meter_data = None
        invoice_line_items = None

        if is_lease(contract=contract):
            # Pending
            pass

        if is_ppa_on_grid_with_battery(contract=contract):
            ppa_on_grid_with_battery_wizard = PPAOnGridWithBatteryContractWizard.factory(
                telemetry_start_reading=telemetry_start_reading,
                telemetry_end_reading=telemetry_end_reading,
                contract=contract,
                devices=devices,
                contract_settings=contract_settings,
            )

            create_invoice = ppa_on_grid_with_battery_wizard.invoice(
                period_start_at=period_start,
                period_end_at=period_end,
                contract_uid=contract.uid,
                invoice_ref=InvoiceRepository._build_invoice_ref(),
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

            create_invoice = ppa_off_grid_wizard.invoice(
                period_start_at=period_start,
                period_end_at=period_end,
                contract_uid=contract.uid,
                invoice_ref=InvoiceRepository._build_invoice_ref(),
            )
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

            create_invoice = ppa_on_grid_no_battery_wizard.invoice(
                period_start_at=period_start,
                period_end_at=period_end,
                contract_uid=contract.uid,
                invoice_ref=InvoiceRepository._build_invoice_ref(),
            )
            invoice_meter_data = ppa_on_grid_no_battery_wizard.invoice_meter_data
            invoice_line_items = ppa_on_grid_no_battery_wizard.invoice_line_items

        if not create_invoice:
            logger.warning(f"Error creating invoice {gateway_id}")
            return

        try:
            new_invoice = Invoice(**create_invoice)
            session.add(new_invoice)
            session.flush()

            session.add_all(
                [InvoiceMeterData(**{**d.model_dump(), "invoice_uid": new_invoice.uid}) for d in invoice_meter_data]
            )
            session.add_all(
                [InvoiceLineItem(**{**d.model_dump(), "invoice_uid": new_invoice.uid}) for d in invoice_line_items]
            )
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
            session.refresh(new_invoice)
            invoice_uid = new_invoice.uid
        except Exception:
            session.rollback()
            raise

        return invoice_uid
