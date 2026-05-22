from datetime import timezone
from typing import Optional
from uuid import UUID

from fastapi import Depends

from app.core.config import Config
from app.core.exceptions import BadRequest, NotFound
from app.jobs.on_demand.triggers.invoice import (
    trigger_compute_contract_invoice_for_period_on_demand,
)
from app.modules.job_run.repository import JobRunRespository, get_jobrun_repo
from app.modules.job_run.schema import (
    JobComputeContractInvoice,
    JobComputeContractInvoiceResp,
    JobRunResp,
    JobRunStatus,
)


class JobRunService:
    def __init__(
        self,
        jobrun_repo: JobRunRespository = Depends(get_jobrun_repo),
    ):
        self.jobrun_repo = jobrun_repo

    async def trigger_compute_contract_invoice(self, data: JobComputeContractInvoice, token_payload: dict):
        token_user = token_payload.get("user")
        user_uid = token_user.get("uid")

        task = trigger_compute_contract_invoice_for_period_on_demand.delay(
            requesting_user_uid=str(user_uid),
            contract_uid=str(data.contract_uid),
            period_start=data.period_start.astimezone(tz=timezone.utc),
            period_end=data.period_end.astimezone(tz=timezone.utc),
        )

        return JobComputeContractInvoiceResp(task_id=str(task.id))

    async def get_job_by_task_id(self, task_id: str, token_payload: dict):
        token_user = token_payload.get("user")
        user_uid = token_user.get("uid")
        jobrun = await self.jobrun_repo.get_job_by_task_id(task_id=task_id, triggered_by_uid=UUID(user_uid))

        if not jobrun:
            raise NotFound("Job not found!")

        return JobRunResp.model_validate(jobrun)

    async def get_user_jobs(
        self,
        token_payload: dict,
        limit: int = Config.DEFAULT_PAGE_LIMIT,
        status: Optional[JobRunStatus] = None,
        next_cursor: Optional[str] = None,
        prev_cursor: Optional[str] = None,
    ):
        if next_cursor and prev_cursor:
            raise BadRequest("Provide either next_cursor or prev_cursor, not both")

        token_user = token_payload.get("user")
        user_uid = token_user.get("uid")
        resp = await self.jobrun_repo.get_jobs(
            user_uid=user_uid,
            limit=limit,
            status=status,
            next_cursor=next_cursor,
            prev_cursor=prev_cursor,
        )

        return resp


def get_jobrun_service(
    jobrun_repo: JobRunRespository = Depends(get_jobrun_repo),
):
    return JobRunService(jobrun_repo=jobrun_repo)
