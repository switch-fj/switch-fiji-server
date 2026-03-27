from datetime import datetime

from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.auth import Authentication
from app.database.postgres import get_session


class InvoiceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _build_invoice_ref(self):
        current_year = str(datetime.now().year)

        return f"INV-{current_year}-{Authentication.generate_otp()}"

    def create_invoice(self):
        pass


def get_invoice_repo(session: AsyncSession = Depends(get_session)):
    return InvoiceRepository(session=session)
