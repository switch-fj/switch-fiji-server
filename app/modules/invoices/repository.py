from datetime import datetime
from uuid import UUID

from fastapi import Depends
from sqlalchemy.orm import joinedload
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.auth import Authentication
from app.core.config import Config
from app.core.logger import setup_logger
from app.database.postgres import get_session
from app.modules.contracts.model import Contract
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

    @staticmethod
    def _build_invoice_ref() -> str:
        current_year = str(datetime.now().year)
        current_month = str(datetime.now().month).zfill(2)
        return f"INV-{current_year}-{current_month}-{Authentication.generate_otp()}"

    async def create_invoice(self, contract_uid: UUID, data: CreateInvoiceModel):
        data_dict = data.model_dump()
        data_dict["contract_uid"] = contract_uid
        data_dict["invoice_ref"] = self._build_invoice_ref()

        try:
            new_invoice = Invoice(**data_dict)
            self.session.add(new_invoice)
            await self.session.commit()
            await self.session.refresh(new_invoice)

            return new_invoice
        except Exception as e:
            await self.session.rollback()
            logger.error(f"error creating invoice {e}")
            raise e

    async def create_invoice_line_item(self, data: list[CreateInvoiceLineItemModel]):
        try:
            line_items = [InvoiceLineItem(**datum.model_dump()) for datum in data]
            self.session.add_all(line_items)
            await self.session.commit()

            return line_items
        except Exception as e:
            await self.session.rollback()
            logger.error(f"error creating invoice line item {e}")
            raise e

    async def create_invoice_meter_data(self, data: list[CreateInvoiceMeterDataModel]):
        try:
            meter_data = [InvoiceMeterData(**datum.model_dump()) for datum in data]
            self.session.add_all(meter_data)
            await self.session.commit()

            return meter_data
        except Exception as e:
            await self.session.rollback()
            logger.error(f"error creating invoice meter data {e}")
            raise e

    async def create_invoice_history(self, data: CreateInvoiceHistoryModel):
        data_dict = data.model_dump()

        try:
            new_invoice_history = InvoiceHistory(**data_dict)
            self.session.add(new_invoice_history)
            await self.session.commit()

            return new_invoice_history
        except Exception as e:
            await self.session.rollback()
            logger.error(f"error creating invoice history {e}")
            raise e

    async def get_invoice_history_by_contract_uid(
        self,
        contract_uid: UUID,
        limit: int = Config.DEFAULT_PAGE_LIMIT,
        offset: int = Config.DEFAULT_PAGE_OFFSET,
    ):
        statement = (
            select(InvoiceHistory, Invoice)
            .join(Invoice, Invoice.uid == InvoiceHistory.invoice_uid)
            .where(Invoice.contract_uid == contract_uid)
            .order_by(InvoiceHistory.sent_at.desc())
            .offset(offset)
            .limit(limit)
        )

        count_statement = select(func.count()).select_from(statement.subquery())

        result = await self.session.exec(statement)
        total = await self.session.scalar(count_statement)

        return result, total

    async def get_invoice_by_uid(self, invoice_uid: UUID):
        statement = (
            select(Invoice)
            .options(
                joinedload(Invoice.contract).options(
                    joinedload(Contract.client),
                    joinedload(Contract.site),
                ),
                joinedload(Invoice.line_items),
                joinedload(Invoice.meter_data),
            )
            .where(Invoice.uid == invoice_uid)
            .execution_options(populate_existing=True)
        )
        result = await self.session.exec(statement)
        invoice = result.unique().first()

        if not invoice:
            return None

        return (
            invoice,
            invoice.contract,
            invoice.line_items,
            invoice.meter_data,
        )


def get_invoice_repo(session: AsyncSession = Depends(get_session)):
    return InvoiceRepository(session=session)
