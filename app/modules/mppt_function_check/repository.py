from datetime import date, time
from uuid import UUID

from fastapi import Depends
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database.postgres import get_session
from app.modules.mppt_function_check.model import SiteMPPTFunctionCheck


class SiteMpptFnCheckRepository:
    """Data-access layer for SiteMpptFnCheck configuration."""

    def __init__(self, session: AsyncSession):
        """Initialise the repository with a database session.

        Args:
            session: An async SQLAlchemy session used for all database operations.
        """
        self.session = session

    async def get_by_site_and_date(self, site_uid: UUID, date_at: date):
        statement = select(SiteMPPTFunctionCheck).where(
            SiteMPPTFunctionCheck.site_uid == site_uid,
            SiteMPPTFunctionCheck.date_at == date_at,
        )
        result = await self.session.exec(statement)
        site_mppt_fn_check = result.one_or_none()

        return site_mppt_fn_check

    async def create_mppt_fn_check(self, user_uid: UUID, site_uid: UUID, date_at: date):
        site_mppt_fn_check = SiteMPPTFunctionCheck(
            user_uid=user_uid,
            site_uid=site_uid,
            date_at=date_at,
            from_=time(9, 0),
            to=time(15, 0),
            interval_in_minutes=30,
            is_completed=False,
        )
        self.session.add(site_mppt_fn_check)
        await self.session.commit()

        return site_mppt_fn_check


def get_site_mppt_fn_check_repo(session: AsyncSession = Depends(get_session)):
    """FastAPI dependency that provides a SiteMpptFnCheckRepository instance.

    Args:
        session: Injected async database session from get_session.

    Returns:
        A SiteMpptFnCheckRepository bound to the provided session.
    """
    return SiteMpptFnCheckRepository(session=session)
