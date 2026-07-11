from uuid import UUID

from fastapi import Depends
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database.postgres import get_session
from app.modules.pv_summary.model import PVSummary
from app.modules.pv_summary.schema import SitePVSItemModel, UpdatePVSItemModel


class PvSummaryRepository:
    """Data-access layer for PVSummary configuration."""

    def __init__(self, session: AsyncSession):
        """Initialise the repository with a database session.

        Args:
            session: An async SQLAlchemy session used for all database operations.
        """
        self.session = session

    async def get_by_uid(self, pvs_uid: UUID):
        statement = select(PVSummary).where(PVSummary.uid == pvs_uid, PVSummary.deleted_at.is_(None))
        result = await self.session.exec(statement)
        pvs = result.one_or_none()

        return pvs

    async def get_pvs_by_site_uid(self, site_uid):
        statement = select(PVSummary).where(PVSummary.site_uid == site_uid, PVSummary.deleted_at.is_(None))
        result = await self.session.exec(statement)
        pvs = result.one_or_none()

        return pvs

    async def create_pvs(self, site_uid: UUID, user_uid: UUID, payload: SitePVSItemModel):
        new_pvs = PVSummary(**payload.model_dump(), user_uid=user_uid, site_uid=site_uid)

        await self.session.add_all(new_pvs)
        await self.session.commit()

        return new_pvs

    async def edit_pvs(self, existing_pvs: PVSummary, payload: UpdatePVSItemModel):
        for k, v in payload.model_dump(exclude={"uid"}).items():
            setattr(existing_pvs, k, v)

        await self.session.commit()


def get_pv_summary_repo(session: AsyncSession = Depends(get_session)):
    """FastAPI dependency that provides a PvSummaryRepository instance.

    Args:
        session: Injected async database session from get_session.

    Returns:
        A PanelRefRepository bound to the provided session.
    """
    return PvSummaryRepository(session=session)
