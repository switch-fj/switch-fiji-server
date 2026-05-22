from uuid import UUID

from fastapi import Depends
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database.postgres import get_session
from app.modules.job_run.model import JobRun


class JobRunRespository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_job_by_task_id(self, task_id: str, triggered_by_uid: UUID):
        await self.session.expire_all()
        result = await self.session.exec(
            select(JobRun).where(JobRun.task_id == task_id, JobRun.triggered_by_uid == triggered_by_uid)
        )

        return result.first()


def get_jobrun_repo(session: AsyncSession = Depends(get_session)):
    """FastAPI dependency that provides a JobRunRespository instance.

    Args:
        session: Injected async database session from get_session.

    Returns:
        A JobRunRespository bound to the provided session.
    """
    return JobRunRespository(session=session)
