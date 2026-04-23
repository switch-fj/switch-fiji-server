from sqlalchemy.orm import Session

from app.modules.invoices.model import Invoice, InvoiceHistory, InvoiceLineItem


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

    def create_invoice_history(self, data: dict) -> InvoiceHistory:
        history = InvoiceHistory(**data)
        self.session.add(history)
        return history
