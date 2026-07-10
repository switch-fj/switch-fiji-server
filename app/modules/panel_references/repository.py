from uuid import UUID

from fastapi import Depends
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database.postgres import get_session
from app.modules.panel_references.model import PanelReference
from app.modules.panel_references.schema import CreatePanelRefModel, PanelRefsModel


class PanelRefRepository:
    """Data-access layer for PanelReferences configuration."""

    def __init__(self, session: AsyncSession):
        """Initialise the repository with a database session.

        Args:
            session: An async SQLAlchemy session used for all database operations.
        """
        self.session = session

    async def get_by_uid(self, panel_ref_uid: UUID):
        statement = select(PanelReference).where(
            PanelReference.uid == panel_ref_uid, PanelReference.deleted_at.is_(None)
        )
        result = await self.session.exec(statement)
        panel_ref = result.one_or_none()

        return panel_ref

    async def get_refs_by_site_uid(self, site_uid: UUID):
        statement = select(PanelReference).where(
            PanelReference.site_uid == site_uid, PanelReference.deleted_at.is_(None)
        )
        result = await self.session.exec(statement)
        panel_refs = result.fetchall()

        return [PanelRefsModel.model_validate(panel) for panel in panel_refs]

    async def create_panel_refs(self, site_uid: UUID, user_uid: UUID, payload: CreatePanelRefModel):
        panel_refs_model = [
            PanelReference(**ref.model_dump(), site_uid=site_uid, user_uid=user_uid) for ref in payload.refs
        ]

        await self.session.add_all(panel_refs_model)
        await self.session.commit()

        return panel_refs_model


def get_panel_ref_repo(session: AsyncSession = Depends(get_session)):
    """FastAPI dependency that provides a PanelRefRepository instance.

    Args:
        session: Injected async database session from get_session.

    Returns:
        A PanelRefRepository bound to the provided session.
    """
    return PanelRefRepository(session=session)
