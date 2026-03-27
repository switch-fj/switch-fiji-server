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

    def _build_invoice_ref(self) -> str:
        current_year = str(datetime.now().year)
        current_month = str(datetime.now().month).zfill(2)
        return f"INV-{current_year}-{current_month}-{Authentication.generate_otp()}"

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

    async def create_invoice_line_item(self, data: list[CreateInvoiceLineItemModel]):
        try:
            line_items = [InvoiceLineItem(**datum.model_dump()) for datum in data]
            await self.session.add_all(line_items)
            await self.session.commit()

            return data
        except Exception as e:
            await self.session.rollback()
            logger.error(f"error creating invoice line item {e}")
            raise e

    async def create_invoice_meter_data(self, data: list[CreateInvoiceMeterDataModel]):
        try:
            meter_data = [InvoiceMeterData(**datum.model_dump()) for datum in data]
            await self.session.add_all(meter_data)
            await self.session.commit()

            return data
        except Exception as e:
            await self.session.rollback()
            logger.error(f"error creating invoice meter data {e}")
            raise e

    async def create_invoice_history(self, data: CreateInvoiceHistoryModel):
        data_dict = data.model_dump()

        try:
            new_invoice_history = InvoiceHistory(**data_dict)
            await self.session.add(new_invoice_history)
            await self.session.commit()

            return new_invoice_history
        except Exception as e:
            await self.session.rollback()
            logger.error(f"error creating invoice history {e}")
            raise e


def get_invoice_repo(session: AsyncSession = Depends(get_session)):
    return InvoiceRepository(session=session)
