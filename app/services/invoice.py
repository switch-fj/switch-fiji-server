from uuid import UUID

from fastapi import Depends

from app.core.exceptions import NotFound
from app.core.logger import setup_logger
from app.modules.contracts.repository import ContractRepository, get_contract_repo
from app.modules.invoices.repository import InvoiceRepository, get_invoice_repo
from app.modules.invoices.schema import InvoiceHistoryRespModel, InvoiceRespModel
from app.shared.schema import OffsetPaginationModel, PaginatedRespModel
from app.utils.pagination import Pagination

logger = setup_logger(__name__)


class InvoiceService:
    def __init__(
        self,
        invoice_repo: InvoiceRepository = Depends(get_invoice_repo),
        contract_repo: ContractRepository = Depends(get_contract_repo),
    ):
        self.invoice_repo = invoice_repo
        self.contract_repo = contract_repo

    async def get_invoice_history_by_contract_uid(
        self,
        contract_uid: UUID,
        limit: int,
        offset: int,
    ):
        contract = await self.contract_repo.get_contract_by_uid(contract_uid=contract_uid)

        if not contract:
            raise NotFound("Contract not found!")

        invoice_histories, total = await self.invoice_repo.get_invoice_history_by_contract_uid(
            contract_uid=contract_uid,
            limit=limit,
            offset=offset,
        )

        current_page, total_pages = Pagination.get_current_and_total_pages(limit=limit, offset=offset, total=total)

        return PaginatedRespModel.model_validate(
            {
                "items": [InvoiceHistoryRespModel.model_validate(h) for h in invoice_histories],
                "pagination": OffsetPaginationModel(
                    total=total,
                    current_page=current_page,
                    limit=limit,
                    total_pages=total_pages,
                ),
            }
        )

    async def get_invoice_by_uid(
        self,
        invoice_uid: UUID,
    ):
        invoice = await self.invoice_repo.get_invoice_by_uid(invoice_uid=invoice_uid)

        if not invoice:
            raise NotFound("Invoice not found")

        return InvoiceRespModel.model_validate(invoice)


def get_invoice_service(
    invoice_repo: InvoiceRepository = Depends(get_invoice_repo),
    contract_repo: ContractRepository = Depends(get_contract_repo),
):
    return InvoiceService(invoice_repo=invoice_repo, contract_repo=contract_repo)
