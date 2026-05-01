from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import RedirectResponse

from app.core.config import Config
from app.core.logger import setup_logger
from app.core.security import AccessTokenBearer
from app.jobs.billing.engine import BillingEngine
from app.modules.invoices.schema import (
    InvoiceDetailedRespModel,
    InvoiceHistoryRespModel,
)
from app.services.contract import ContractService, get_contract_service
from app.services.invoice import InvoiceService, get_invoice_service
from app.services.s3 import S3Service
from app.services.settings import SettingsService, get_settings_service
from app.shared.schema import (
    OffsetPaginationModel,
    PaginatedRespModel,
    ServerRespModel,
)

invoice_router = APIRouter(prefix="/invoice", tags=["invoice"])

logger = setup_logger(__name__)


@invoice_router.get(
    "/{invoice_uid}",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[InvoiceDetailedRespModel],
)
async def get_invoice_details_by_uid(
    invoice_uid: UUID,
    invoice_service: InvoiceService = Depends(get_invoice_service),
    token_payload: dict = Depends(AccessTokenBearer()),
):
    resp = await invoice_service.get_invoice_details_by_uid(invoice_uid=invoice_uid, token_payload=token_payload)

    invoice, contract, line_items, meter_data = resp
    invoice_resp = InvoiceDetailedRespModel.model_validate(
        {
            **invoice.__dict__,
            "contract": contract,
            "line_items": line_items,
            "meter_data": meter_data,
        }
    )

    return ServerRespModel[InvoiceDetailedRespModel](
        data=invoice_resp,
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


@invoice_router.get(
    "/{invoice_uid}/pdf",
    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
)
async def download_invoice_pdf(
    invoice_uid: UUID,
    invoice_service: InvoiceService = Depends(get_invoice_service),
    settings_service: SettingsService = Depends(get_settings_service),
    token_payload: dict = Depends(AccessTokenBearer()),
):
    resp = await invoice_service.get_invoice_details_by_uid(invoice_uid=invoice_uid, token_payload=token_payload)
    invoice, contract, line_items, meter_data = resp
    presigned_url = ""

    if not invoice.pdf_s3_key:
        contract_settings = await settings_service.get_contract_general_settings()
        pdf_bytes, key = BillingEngine.generate_pdf(
            contract=contract,
            result=(invoice, meter_data, line_items),
            contract_settings=contract_settings,
        )
        BillingEngine.store_pdf_in_s3(pdf_bytes=pdf_bytes, key=key, invoice_ref=invoice.invoice_ref)
        await invoice_service.save_pdf_s3_key(invoice_uid=invoice.uid, key=key)
        presigned_url = S3Service.generate_presigned_url(key=key)
    else:
        presigned_url = S3Service.generate_presigned_url(key=invoice.pdf_s3_key)

    return RedirectResponse(url=presigned_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
