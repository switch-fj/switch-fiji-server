import json
from uuid import UUID

from sqlmodel import select

from app.core.logger import setup_logger
from app.database.celery import get_celery_db_session
from app.jobs.celery import celery_app
from app.jobs.on_demand.schedulers.string_wiring import compute_string_wiring_on_demand
from app.jobs.shared import get_pv_summary, update_job_run
from app.modules.job_run.model import JobRun
from app.modules.job_run.schema import JobReferenceType, JobRunStatus, JobType

logger = setup_logger(__name__)


@celery_app.task(
    name="trigger_compute_string_wiring_on_demand",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def trigger_compute_string_wiring_on_demand(self, requesting_user_uid: str, site_uid: str, string_wiring_uid: str):
    """
    This is triggered manually based on changes in summary table from user.
    Fetches the string summary table, panel_reference and dispatches
    the compute task to the worker pool.
    """
    with get_celery_db_session() as session:
        meta = json.dumps(
            {
                "string_wiring_uid": string_wiring_uid,
                "site_uid": site_uid,
            },
            sort_keys=True,
        )

        existing = session.execute(
            select(JobRun).where(
                JobRun.reference_uid == UUID(string_wiring_uid),
                JobRun.job_type == JobType.COMPUTE_STRING_WIRING,
                JobRun.reference_type == JobReferenceType.STRING_WIRING,
                JobRun.meta == meta,
                JobRun.status.in_([JobRunStatus.PENDING, JobRunStatus.RUNNING]),
            )
        ).scalar_one_or_none()

        if existing:
            logger.info(
                f"Duplicate job request ignored — existing job {existing.task_id} "
                f"is {existing.status} for degradation {string_wiring_uid}"
            )
            return existing.task_id

        job_run = JobRun(
            task_id=self.request.id,
            job_type=JobType.COMPUTE_STRING_WIRING,
            reference_type=JobReferenceType.STRING_WIRING,
            reference_uid=UUID(string_wiring_uid),
            triggered_by_uid=UUID(requesting_user_uid),
            status=JobRunStatus.PENDING,
            meta=meta,
        )
        session.add(job_run)
        session.commit()

    try:
        with get_celery_db_session() as session:
            pv_summary = get_pv_summary(session, site_uid)

        if not pv_summary:
            logger.warning(f"Pv summary is invalid or doesn't exist: {site_uid}")
            update_job_run(
                reference_uid=string_wiring_uid,
                task_id=self.request.id,
                status=JobRunStatus.INVALID,
                error="pv summary not found or not active",
            )
            return

        compute_string_wiring_on_demand(
            site_uid=site_uid,
            string_wiring_uid=string_wiring_uid,
            job_run_task_id=self.request.id,
        )

    except Exception as exc:
        update_job_run(
            reference_uid=string_wiring_uid,
            task_id=self.request.id,
            status=JobRunStatus.FAILED,
            error=str(exc),
        )
        raise self.retry(exc=exc)
