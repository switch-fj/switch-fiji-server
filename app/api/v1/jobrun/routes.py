import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import StreamingResponse

from app.core.config import Config
from app.core.logger import setup_logger
from app.core.security import AccessTokenBearer
from app.modules.job_run.schema import (
    JobComputeContractInvoice,
    JobComputeContractInvoiceResp,
    JobRunResp,
    JobRunStatus,
)
from app.services.job_run import JobRunService, get_jobrun_service
from app.shared.schema import CursorPaginationModel, PaginatedRespModel, ServerRespModel

jobrun_router = APIRouter(prefix="/jobrun", tags=["jobrun"])

logger = setup_logger(__name__)


@jobrun_router.get(
    "/user",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[PaginatedRespModel[JobRunResp, CursorPaginationModel]],
)
async def get_all_jobs(
    status: Optional[JobRunStatus] = Query(default=None),
    limit: int = Query(default=Config.DEFAULT_PAGE_LIMIT),
    next_cursor: Optional[str] = Query(default=None),
    prev_cursor: Optional[str] = Query(default=None),
    token_payload: dict = Depends(AccessTokenBearer()),
    jobrun_service: JobRunService = Depends(get_jobrun_service),
):

    result = await jobrun_service.get_user_jobs(
        token_payload=token_payload,
        status=status,
        limit=limit,
        next_cursor=next_cursor,
        prev_cursor=prev_cursor,
    )

    return ServerRespModel[PaginatedRespModel[JobRunResp, CursorPaginationModel]](
        data=result, message="User jobs retrieved"
    )


@jobrun_router.post(
    "/invoice/compute",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[JobComputeContractInvoiceResp],
)
async def trigger_compute_invoice_for_period(
    data: JobComputeContractInvoice,
    token_payload: dict = Depends(AccessTokenBearer()),
    jobrun_service: JobRunService = Depends(get_jobrun_service),
):
    result = await jobrun_service.trigger_compute_contract_invoice(data=data, token_payload=token_payload)

    return ServerRespModel[JobComputeContractInvoiceResp](
        data=result,
        message="Job started!",
    )


@jobrun_router.get(
    "/invoices/compute/{task_id}",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[JobRunResp],
)
async def get_job_status(
    task_id: str,
    token_payload: dict = Depends(AccessTokenBearer()),
    jobrun_service: JobRunService = Depends(get_jobrun_service),
):

    job_run = await jobrun_service.get_job_by_task_id(task_id=task_id, token_payload=token_payload)

    return ServerRespModel[JobRunResp](
        data=job_run,
        message="Job details retrieved.",
    )


@jobrun_router.get(
    "/invoices/compute/{task_id}/stream",
    status_code=status.HTTP_200_OK,
    summary="Stream live stats for a single site via SSE",
)
async def stream_job_status(
    task_id: str,
    request: Request,
    token_payload: dict = Depends(AccessTokenBearer()),
    jobrun_service: JobRunService = Depends(get_jobrun_service),
):

    async def event_generator():
        terminal_statuses = {
            JobRunStatus.COMPLETED,
            JobRunStatus.FAILED,
            JobRunStatus.INVALID,
        }

        while True:
            # Client disconnected — stop polling
            if await request.is_disconnected():
                break

            job_run = await jobrun_service.get_job_by_task_id(task_id=task_id, token_payload=token_payload)

            if not job_run:
                yield f"event: error\ndata: {json.dumps({'detail': 'Job not found'})}\n\n"
                break

            payload = job_run.model_dump_json()

            yield f"event: status\ndata: {payload}\n\n"

            if job_run.status in terminal_statuses:
                break

            await asyncio.sleep(3)

    return StreamingResponse(
        event_generator(),
        status_code=status.HTTP_200_OK,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
