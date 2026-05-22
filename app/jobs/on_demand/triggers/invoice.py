import json
from datetime import datetime
from uuid import UUID

from sqlmodel import select

from app.core.logger import setup_logger
from app.database.celery import get_celery_db_session
from app.jobs.celery import celery_app
from app.jobs.on_demand.schedulers.invoice import (
    compute_contract_invoice_for_period_on_demand,
)
from app.jobs.shared import _get_active_contract, update_job_run
from app.modules.job_run.model import JobRun
from app.modules.job_run.schema import JobReferenceType, JobRunStatus, JobType

logger = setup_logger(__name__)


@celery_app.task(
    name="trigger_compute_contract_invoice_on_demand",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def trigger_compute_contract_invoice_for_period_on_demand(
    self,
    requesting_user_uid: str,
    contract_uid: str,
    period_start: datetime,
    period_end: datetime,
):
    """
    This is triggered manually based on demand from user.
    Fetches all active contracts and dispatches
    one compute task per contract to the worker pool.
    """
    with get_celery_db_session() as session:
        # Normalise meta so comparison is consistent and sorted alphabetically
        meta = json.dumps(
            {
                "period_end": period_end.isoformat(),
                "period_start": period_start.isoformat(),
            },
            sort_keys=True,
        )

        existing = session.execute(
            select(JobRun).where(
                JobRun.reference_uid == UUID(contract_uid),
                JobRun.job_type == JobType.COMPUTE_INVOICE,
                JobRun.reference_type == JobReferenceType.CONTRACT,
                JobRun.meta == meta,
                JobRun.status.in_([JobRunStatus.PENDING, JobRunStatus.RUNNING]),
            )
        ).scalar_one_or_none()

        if existing:
            logger.info(
                f"Duplicate job request ignored — existing job {existing.task_id} "
                f"is {existing.status} for contract {contract_uid}"
            )
            return existing.task_id

        job_run = JobRun(
            task_id=self.request.id,
            job_type=JobType.COMPUTE_INVOICE,
            reference_type=JobReferenceType.CONTRACT,
            reference_uid=UUID(contract_uid),
            triggered_by_uid=UUID(requesting_user_uid),
            status=JobRunStatus.PENDING,
            meta=meta,
        )
        session.add(job_run)
        session.commit()

    try:
        with get_celery_db_session() as session:
            active_contract = _get_active_contract(session, contract_uid)

        if not active_contract:
            logger.warning(f"Contract is invalid or doesn't exist: {contract_uid}")
            update_job_run(
                reference_uid=contract_uid,
                task_id=self.request.id,
                status=JobRunStatus.INVALID,
                error="Contract not found or not active",
            )
            return

        compute_contract_invoice_for_period_on_demand.delay(
            job_run_task_id=self.request.id,
            contract_uid=contract_uid,
            gateway_id=active_contract.gateway_id,
            site_uid=active_contract.site_uid,
            period_start=period_start,
            period_end=period_end,
        )

    except Exception as exc:
        update_job_run(
            reference_uid=contract_uid,
            task_id=self.request.id,
            status=JobRunStatus.FAILED,
            error=str(exc),
        )
        raise self.retry(exc=exc)
