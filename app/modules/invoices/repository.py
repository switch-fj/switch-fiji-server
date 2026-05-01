from datetime import datetime
from uuid import UUID

from fastapi import Depends
from sqlalchemy.orm import joinedload
from sqlmodel import func, select, update
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
    """Data-access layer for Invoice and related invoice sub-models."""

    def __init__(self, session: AsyncSession):
        """Initialise the repository with a database session.

        Args:
            session: An async SQLAlchemy session used for all database operations.
        """
        self.session = session

    @staticmethod
    def _build_invoice_ref() -> str:
        """Generate a unique invoice reference string based on the current year and month.

        Returns:
            A formatted invoice reference string such as "INV-2025-05-AB1C2D".
        """
        current_year = str(datetime.now().year)
        current_month = str(datetime.now().month).zfill(2)
        return f"INV-{current_year}-{current_month}-{Authentication.generate_otp()}"

    async def create_invoice(self, contract_uid: UUID, data: CreateInvoiceModel):
        """Create and persist a new invoice for a contract.

        Args:
            contract_uid: The UUID of the contract this invoice belongs to.
            data: The validated model containing invoice creation fields.

        Returns:
            The newly created Invoice ORM instance.

        Raises:
            Exception: Re-raises any database error after rolling back.
        """
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
        """Bulk-create and persist invoice line items.

        Args:
            data: A list of validated models containing line item creation fields.

        Returns:
            The list of newly created InvoiceLineItem ORM instances.

        Raises:
            Exception: Re-raises any database error after rolling back.
        """
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
        """Bulk-create and persist invoice meter data records.

        Args:
            data: A list of validated models containing meter data creation fields.

        Returns:
            The list of newly created InvoiceMeterData ORM instances.

        Raises:
            Exception: Re-raises any database error after rolling back.
        """
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
        """Create and persist an invoice delivery history record.

        Args:
            data: The validated model containing invoice history creation fields.

        Returns:
            The newly created InvoiceHistory ORM instance.

        Raises:
            Exception: Re-raises any database error after rolling back.
        """
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
        """Retrieve paginated invoice history records for a given contract.

        Args:
            contract_uid: The UUID of the contract whose history to retrieve.
            limit: Maximum number of records to return.
            offset: Number of records to skip for pagination.

        Returns:
            A tuple of (result_rows, total_count) where result_rows is a SQLAlchemy result.
        """
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
        """Fetch a single invoice by its primary UUID.

        Args:
            invoice_uid: The UUID of the invoice to retrieve.

        Returns:
            The matching Invoice ORM instance, or None if not found.
        """
        statement = select(Invoice).where(Invoice.uid == invoice_uid)
        result = await self.session.exec(statement)
        invoice = result.first()

        if not invoice:
            return None

        return invoice

    async def get_invoice_details_by_uid(self, invoice_uid: UUID):
        """Fetch an invoice with its contract (including client and site), line items, and meter data loaded.

        Args:
            invoice_uid: The UUID of the invoice to retrieve.

        Returns:
            A tuple of (invoice, contract, line_items, meter_data), or None if the invoice is not found.
        """
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

    async def update_pdf_s3_key(self, invoice_uid: UUID, key: str) -> None:
        """Update the pdf_s3_key field for an invoice after PDF upload.

        Args:
            invoice_uid: The UUID of the invoice to update.
            key: The S3 object key of the uploaded PDF.

        Returns:
            None
        """
        statement = update(Invoice).where(Invoice.uid == invoice_uid).values(pdf_s3_key=key)
        await self.session.exec(statement)
        await self.session.commit()


def get_invoice_repo(session: AsyncSession = Depends(get_session)):
    """FastAPI dependency that provides an InvoiceRepository instance.

    Args:
        session: Injected async database session from get_session.

    Returns:
        An InvoiceRepository bound to the provided session.
    """
    return InvoiceRepository(session=session)
