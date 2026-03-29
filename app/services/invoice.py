from uuid import UUID

from fastapi import Depends

from app.modules.invoices.repository import InvoiceRepository, get_invoice_repo


class InvoiceService:
    def __init__(self, invoice_repo: InvoiceRepository):
        self.invoice_repo = invoice_repo

    async def get_invoice_history(self, contract_uid: UUID):
        pass


def get_invoice_service(invoice_repo: InvoiceRepository = Depends(get_invoice_repo)):
    return InvoiceService(invoice_repo=invoice_repo)
