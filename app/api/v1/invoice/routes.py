from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.core.config import Config
from app.core.security import AccessTokenBearer
from app.modules.invoices.schema import InvoiceHistoryRespModel, InvoiceRespModel
from app.services.contract import ContractService, get_contract_service
from app.services.invoice import InvoiceService, get_invoice_service
from app.shared.schema import (
    OffsetPaginationModel,
    PaginatedRespModel,
    ServerRespModel,
)

invoice_router = APIRouter(prefix="/invoice", tags=["invoice"])


@invoice_router.get(
    "/{invoice_uid}",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[InvoiceRespModel],
)
async def get_invoice_by_uid(
    invoice_uid: UUID,
    contract_service: ContractService = Depends(get_contract_service),
    invoice_service: InvoiceService = Depends(get_invoice_service),
    token_payload: dict = Depends(AccessTokenBearer()),
):
    invoice = await invoice_service.get_invoice_by_uid(invoice_uid=invoice_uid)
    await contract_service.get_contract_by_uid(contract_uid=invoice.contract.uid, token_payload=token_payload)

    return ServerRespModel[InvoiceRespModel](
        data=invoice,
        message="Invoice retrieved!.",
    )


@invoice_router.get(
    "/history/{contract_uid}",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[PaginatedRespModel[InvoiceHistoryRespModel, OffsetPaginationModel]],
)
async def get_invoice_history_by_contract_uid(
    contract_uid: UUID,
    contract_service: ContractService = Depends(get_contract_service),
    invoice_service: InvoiceService = Depends(get_invoice_service),
    token_payload: dict = Depends(AccessTokenBearer()),
    limit: Optional[int] = Query(
        default=Config.DEFAULT_PAGE_LIMIT,
        ge=Config.DEFAULT_PAGE_MIN_LIMIT,
        le=Config.DEFAULT_PAGE_MAX_LIMIT,
    ),
    offset: Optional[int] = Query(default=Config.DEFAULT_PAGE_OFFSET),
):
    await contract_service.get_contract_by_uid(contract_uid=contract_uid, token_payload=token_payload)
    resp = await invoice_service.get_invoice_history_by_contract_uid(
        contract_uid=contract_uid, limit=limit, offset=offset
    )

    return ServerRespModel[PaginatedRespModel[InvoiceHistoryRespModel, OffsetPaginationModel]](
        data=resp,
        message="Invoice history retrieved!.",
    )
