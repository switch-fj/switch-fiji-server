from typing import Optional
from uuid import UUID

from fastapi import Depends
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import Config
from app.database.postgres import get_session
from app.modules.job_run.model import JobRun
from app.modules.job_run.schema import JobRunResp, JobRunStatus
from app.shared.schema import CursorPaginationModel, PaginatedRespModel
from app.utils.pagination import Pagination


class JobRunRespository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_job_by_task_id(self, task_id: str, triggered_by_uid: UUID):
        await self.session.expire_all()
        result = await self.session.exec(
            select(JobRun).where(JobRun.task_id == task_id, JobRun.triggered_by_uid == triggered_by_uid)
        )

        return result.first()

    async def get_jobs(
        self,
        user_uid: UUID,
        limit: int = Config.DEFAULT_PAGE_LIMIT,
        status: Optional[JobRunStatus] = None,
        next_cursor: Optional[str] = None,
        prev_cursor: Optional[str] = None,
    ):
        statement = (
            select(
                JobRun,
            )
            .where(JobRun.triggered_by_uid == user_uid)
            .order_by(JobRun.created_at.desc())
        )

        if next_cursor:
            cursor_id = Pagination.decrypt_cursor(next_cursor)
            statement = statement.where(JobRun.id < cursor_id)

        if prev_cursor:
            cursor_id = Pagination.decrypt_cursor(prev_cursor)
            statement = statement.where(JobRun.id > cursor_id)

        if status:
            statement = statement.where(JobRun.status == status)

        statement = statement.limit(limit + 1)

        result = await self.session.exec(statement)
        rows = result.all()

        has_more = len(rows) > limit
        items = rows[:limit]

        job_runs = [JobRunResp.model_validate({**row.__dict__}) for row in items]

        next_cursor_out = None
        prev_cursor_out = None

        if items:
            prev_cursor_out = Pagination.encrypt_cursor(items[0].id)

        if has_more:
            next_cursor_out = Pagination.encrypt_cursor(items[-1].id)

        return PaginatedRespModel.model_validate(
            {
                "items": job_runs,
                "pagination": CursorPaginationModel(
                    limit=limit,
                    next_cursor=next_cursor_out,
                    prev_cursor=prev_cursor_out,
                ),
            }
        )


def get_jobrun_repo(session: AsyncSession = Depends(get_session)):
    """FastAPI dependency that provides a JobRunRespository instance.

    Args:
        session: Injected async database session from get_session.

    Returns:
        A JobRunRespository bound to the provided session.
    """
    return JobRunRespository(session=session)
