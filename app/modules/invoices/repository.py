from datetime import datetime
from uuid import UUID

from fastapi import Depends
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.auth import Authentication
from app.core.logger import setup_logger
from app.database.postgres import get_session
from app.modules.contracts.repository import ContractRepository
from app.modules.invoices.model import (
    Invoice,
    InvoiceHistory,
    InvoiceLineItem,
    InvoiceMeterData,
)
from app.modules.invoices.schema import (
    CreateInvoiceHistoryModel,
    CreateInvoiceLineItemModel,
    CreateInvoiceMeterDataModel,
    CreateInvoiceModel,
)

logger = setup_logger(__name__)


class InvoiceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.contract_repo = ContractRepository(session=session)

    def _build_invoice_ref(self):
        current_year = str(datetime.now().year)

        return f"INV-{current_year}-{Authentication.generate_otp()}"

    async def get_invoice_by_uid(self, invoice_uid: UUID):
        statement = (
            select(Invoice)
            .options(
                selectinload(Invoice.contract),
                selectinload(Invoice.line_items),
                selectinload(Invoice.meter_data),
            )
            .where(Invoice.uid == invoice_uid)
        )

        result = await self.session.exec(statement=statement)
        invoice = result.first()

        return invoice

    async def create_invoice(self, contract_uid: UUID, data: CreateInvoiceModel):
        data_dict = data.model_dump()
        data_dict["contract_uid"] = contract_uid
        data_dict["invoice_ref"] = self._build_invoice_ref()

        try:
            new_invoice = Invoice(**data_dict)
            await self.session.add(new_invoice)
            await self.session.commit()

            return new_invoice
        except Exception as e:
            await self.session.rollback()
            logger.error(f"error creating invoice {e}")

    async def create_invoice_line_item(self, data: CreateInvoiceLineItemModel):
        await self.get_invoice_by_uid(invoice_uid=data.invoice_uid)
        data_dict = data.model_dump()

        try:
            new_invoice_line_item = InvoiceLineItem(**data_dict)
            await self.session.add(new_invoice_line_item)
            await self.session.commit()

            return new_invoice_line_item
        except Exception as e:
            await self.session.rollback()
            logger.error(f"error creating invoice line item {e}")

    async def create_invoice_meter_data(self, data: CreateInvoiceMeterDataModel):
        await self.get_invoice_by_uid(invoice_uid=data.invoice_uid)
        data_dict = data.model_dump()

        try:
            new_invoice_meter_data = InvoiceMeterData(**data_dict)
            await self.session.add(new_invoice_meter_data)
            await self.session.commit()

            return new_invoice_meter_data
        except Exception as e:
            await self.session.rollback()
            logger.error(f"error creating invoice meter data {e}")

    async def create_invoice_history(self, data: CreateInvoiceHistoryModel):
        await self.get_invoice_by_uid(invoice_uid=data.invoice_uid)
        data_dict = data.model_dump()

        try:
            new_invoice_history = InvoiceHistory(**data_dict)
            await self.session.add(new_invoice_history)
            await self.session.commit()

            return new_invoice_history
        except Exception as e:
            await self.session.rollback()
            logger.error(f"error creating invoice history {e}")


def get_invoice_repo(session: AsyncSession = Depends(get_session)):
    return InvoiceRepository(session=session)
