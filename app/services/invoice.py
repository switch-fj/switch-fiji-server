from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import Depends

from app.core.exceptions import InsufficientPermissions, NotFound
from app.core.logger import setup_logger
from app.modules.contracts.repository import ContractRepository, get_contract_repo
from app.modules.invoices.repository import InvoiceRepository, get_invoice_repo
from app.modules.invoices.schema import (
    InvoiceHistoryRespModel,
    InvoiceSnapshotRespModel,
)
from app.shared.schema import (
    CursorPaginationModel,
    IdentityTypeEnum,
    OffsetPaginationModel,
    PaginatedRespModel,
    UserRoleEnum,
)
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

        resp, total = await self.invoice_repo.get_invoice_history_by_contract_uid(
            contract_uid=contract_uid,
            limit=limit,
            offset=offset,
        )

        current_page, total_pages = Pagination.get_current_and_total_pages(limit=limit, offset=offset, total=total)

        return PaginatedRespModel.model_validate(
            {
                "items": [
                    InvoiceHistoryRespModel.model_validate({**invoice_history.__dict__, "invoice": invoice})
                    for invoice_history, invoice in resp
                ],
                "pagination": OffsetPaginationModel(
                    total=total,
                    current_page=current_page,
                    limit=limit,
                    total_pages=total_pages,
                ),
            }
        )

    async def get_invoice_by_uid(self, invoice_uid: UUID, token_payload: Optional[dict], secure: bool = True):
        invoice = await self.invoice_repo.get_invoice_by_uid(invoice_uid=invoice_uid)
        if not invoice:
            raise NotFound("Invoice not found")

        return invoice

    async def get_invoice_details_by_uid(self, invoice_uid: UUID, token_payload: Optional[dict], secure: bool = True):
        resp = await self.invoice_repo.get_invoice_details_by_uid(invoice_uid=invoice_uid)

        if not resp:
            raise NotFound("Invoice not found")
        invoice, _, _, _ = resp

        if secure and token_payload:
            token_user = token_payload.get("user")
            identity = token_user.get("identity")
            role = token_user.get("role")
            user_uid = token_user.get("uid")

            if identity == IdentityTypeEnum.USER.value and not role == UserRoleEnum.ADMIN:
                raise InsufficientPermissions("Access denied")

            if identity == IdentityTypeEnum.CLIENT.value and not invoice.contract.client_uid == user_uid:
                raise InsufficientPermissions("Access denied")

        return resp

    async def get_snapshots_by_contract_uid(
        self,
        contract_uid: UUID,
        token_payload: dict,
        limit: int,
        next_cursor: Optional[str],
        prev_cursor: Optional[str],
    ):
        contract_resp = await self.contract_repo.get_contract_by_uid(contract_uid=contract_uid)
        if not contract_resp:
            raise NotFound("Contract not found!")

        _, client, _, _ = contract_resp

        if token_payload:
            token_user = token_payload.get("user")
            identity = token_user.get("identity")
            role = token_user.get("role")
            user_uid = token_user.get("uid")

            if identity == IdentityTypeEnum.USER.value and not role == UserRoleEnum.ADMIN:
                raise InsufficientPermissions("Access denied")

            if identity == IdentityTypeEnum.CLIENT.value and not client.uid == user_uid:
                raise InsufficientPermissions("Access denied")

        items, next_cursor_out, prev_cursor_out = await self.invoice_repo.get_snapshots_by_contract_uid(
            contract_uid=contract_uid,
            limit=limit,
            next_cursor=next_cursor,
            prev_cursor=prev_cursor,
        )

        return PaginatedRespModel.model_validate(
            {
                "items": [InvoiceSnapshotRespModel.model_validate(s) for s in items],
                "pagination": CursorPaginationModel(
                    limit=limit,
                    next_cursor=next_cursor_out,
                    prev_cursor=prev_cursor_out,
                ),
            }
        )

    async def get_snapshots_by_period_range(
        self,
        contract_uid: UUID,
        token_payload: dict,
        period_start_date: datetime,
        period_end_date: datetime,
    ):
        contract_resp = await self.contract_repo.get_contract_by_uid(contract_uid=contract_uid)

        if not contract_resp:
            raise NotFound("Contract not found!")

        _, client, _, _ = contract_resp

        if token_payload:
            token_user = token_payload.get("user")
            identity = token_user.get("identity")
            role = token_user.get("role")
            user_uid = token_user.get("uid")

            if identity == IdentityTypeEnum.USER.value and not role == UserRoleEnum.ADMIN:
                raise InsufficientPermissions("Access denied")

            if identity == IdentityTypeEnum.CLIENT.value and not client.uid == user_uid:
                raise InsufficientPermissions("Access denied")

        result = await self.invoice_repo.get_snapshots_by_contract_uid_and_period_range(
            contract_uid=contract_uid,
            period_start_date=period_start_date,
            period_end_date=period_end_date,
        )

        invoice_snapshots = result.unique().all()

        resp = [item for item in invoice_snapshots]

        return resp

    async def save_pdf_s3_key(self, invoice_uid: UUID, key: str) -> None:
        await self.invoice_repo.update_pdf_s3_key(invoice_uid=invoice_uid, key=key)


def get_invoice_service(
    invoice_repo: InvoiceRepository = Depends(get_invoice_repo),
    contract_repo: ContractRepository = Depends(get_contract_repo),
):
    return InvoiceService(invoice_repo=invoice_repo, contract_repo=contract_repo)
