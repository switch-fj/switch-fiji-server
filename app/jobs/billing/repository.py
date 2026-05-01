from sqlalchemy.orm import Session

from app.modules.invoices.model import (
    Invoice,
    InvoiceHistory,
    InvoiceLineItem,
    InvoiceMeterData,
    InvoiceSnapshot,
    InvoiceSnapshotLineItem,
    InvoiceSnapshotMeterData,
)


class SyncInvoiceRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_invoice(self, data: dict) -> Invoice:
        invoice = Invoice(**data)
        self.session.add(invoice)
        self.session.flush()

        return invoice

    def create_line_items(self, items: list[dict]) -> list[InvoiceLineItem]:
        line_items = [InvoiceLineItem(**item) for item in items]
        self.session.add_all(line_items)

        return line_items

    def create_meter_data(self, meter_data: list[dict]) -> list[InvoiceMeterData]:
        meter_data = [InvoiceMeterData(**meter_datum) for meter_datum in meter_data]
        self.session.add_all(meter_data)

        return meter_data

    def create_invoice_history(self, data: dict) -> InvoiceHistory:
        history = InvoiceHistory(**data)
        self.session.add(history)

        return history

    def create_invoice_snapshot(self, data: dict) -> InvoiceSnapshot:
        invoice_snapshot = InvoiceSnapshot(**data)
        self.session.add(InvoiceSnapshot)
        self.session.flush()

        return invoice_snapshot

    def create_snapshot_line_items(self, items: list[dict]) -> list[InvoiceSnapshotLineItem]:
        snapshot_line_items = [InvoiceSnapshotLineItem(**item) for item in items]
        self.session.add_all(snapshot_line_items)

        return snapshot_line_items

    def create_snapshot_meter_data(self, meter_data: list[dict]) -> list[InvoiceSnapshotMeterData]:
        snapshot_meter_data = [InvoiceSnapshotMeterData(**meter_datum) for meter_datum in meter_data]
        self.session.add_all(snapshot_meter_data)

        return snapshot_meter_data
