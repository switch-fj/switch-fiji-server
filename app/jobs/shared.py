from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlmodel import Session, select, text

from app.core.logger import setup_logger
from app.database.celery import get_celery_db_session
from app.modules.job_run.model import JobRun
from app.modules.job_run.schema import JobRunStatus

logger = setup_logger(__name__)


def get_active_contracts(session: Session) -> list:
    result = session.execute(
        text("""
        SELECT DISTINCT
            c.uid::text AS contract_uid,
            s.uid::text AS site_uid,
            s.gateway_id AS gateway_id
        FROM sites s
        JOIN contracts c ON c.site_uid = s.uid
        JOIN contract_details cd ON cd.contract_uid = c.uid
        WHERE COALESCE(cd.actual_commissioned_at, cd.commissioned_at) IS NOT NULL
            AND NOW() > COALESCE(cd.actual_commissioned_at, cd.commissioned_at)
            AND NOW() < COALESCE(cd.actual_end_at, cd.end_at)
    """)
    )
    return result.fetchall()


def get_active_contract(session: Session, contract_uid):
    result = session.execute(
        text("""
        SELECT DISTINCT
            c.uid::text AS contract_uid,
            s.uid::text AS site_uid,
            s.gateway_id AS gateway_id
        FROM sites s
        JOIN contracts c ON c.site_uid = s.uid
        JOIN contract_details cd ON cd.contract_uid = c.uid
        WHERE c.uid = :contract_uid
            AND COALESCE(cd.actual_commissioned_at, cd.commissioned_at) IS NOT NULL
            AND NOW() > COALESCE(cd.actual_commissioned_at, cd.commissioned_at)
            AND NOW() < COALESCE(cd.actual_end_at, cd.end_at)
        LIMIT 1      
        """),
        {"contract_uid": contract_uid},
    )
    return result.mappings().one_or_none()


def get_pv_summary(session: Session, site_uid):
    query = text("""
        SELECT
            pvs.uid::text AS pvs_uid,
            pvs.site_uid::text AS site_uid,
            pvs.user_uid::text AS user_uid,
            pvs.commissioned_at AS comissioned_at,
            pvs.expected_production_kwh AS expected_production_kwh,
            pvs.system_size_kwp AS system_size_kwp,
            pvs.year1_degradation AS year1_degradation,
            pvs.year2plus_degradation AS year2plus_degradation
        FROM pv_summary pvs
        WHERE pvs.site_uid = :site_uid
            AND pvs.deleted_at IS NULL
        LIMIT 1
    """)
    result = session.execute(query, {"site_uid": site_uid})
    return result.mappings().first()


def update_job_run(
    reference_uid: str,
    task_id: str,
    status: JobRunStatus,
    error: Optional[str] = None,
    started_at: Optional[datetime] = None,
    completed_at: Optional[datetime] = None,
    result_uid: Optional[str] = None,
):
    with get_celery_db_session() as session:
        job_run = session.execute(
            select(JobRun).where(
                JobRun.task_id == task_id,
                JobRun.reference_uid == UUID(reference_uid),
            )
        ).scalar_one_or_none()

        if not job_run:
            logger.warning(f"JobRun not found for task_id={task_id}")
            return

        job_run.status = status
        if error:
            job_run.error = error
        if started_at:
            job_run.started_at = started_at
        if completed_at:
            job_run.completed_at = completed_at
        if result_uid:
            job_run.result_uid = result_uid

        session.add(job_run)
        session.commit()
