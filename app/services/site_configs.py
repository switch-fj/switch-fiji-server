from uuid import UUID

from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.exceptions import Forbidden, NotFound, ResourceExists
from app.database.postgres import get_session
from app.modules.clients.repository import ClientRepository
from app.modules.panel_references.repository import PanelRefRepository
from app.modules.panel_references.schema import CreatePanelRefModel, UpdatePanelRefModel
from app.modules.pv_summary.repository import PvSummaryRepository
from app.modules.pv_summary.schema import SitePVSItemModel, UpdatePVSItemModel
from app.modules.sites.repository import SiteRepository
from app.modules.users.repository import UserRepository
from app.services.sites import SiteService
from app.shared.schema import UserRoleEnum


class SiteConfigService(SiteService):
    def __init__(
        self,
        session: AsyncSession,
    ):
        self.session = session
        self.site_repo = SiteRepository(session=session)
        self.user_repo = UserRepository(session=session)
        self.client_repo = ClientRepository(session=session)
        self.panel_ref_repo = PanelRefRepository(session=session)
        self.pvs_repo = PvSummaryRepository(session=session)

        super().__init__(site_repo=self.site_repo, client_repo=self.client_repo)

    async def add_panel_refs(self, user_uid: UUID, site_uid: UUID, payload: CreatePanelRefModel):
        user = await self.user_repo.get_user_by_uid(user_uid=user_uid)

        if not user:
            raise NotFound("User doesn't exist!")

        if not user.role == UserRoleEnum.ENGINEER:
            raise Forbidden("Insufficient permission")

        site = await self.site_repo.get_site_by_uid(site_uid=site_uid)

        if not site:
            raise NotFound("Site doesn't exist!")

        await self.panel_ref_repo.create_panel_refs(site_uid=site_uid, user_uid=user_uid, payload=payload)

        return True

    async def edit_panel_ref(self, site_uid: UUID, user_uid: UUID, payload: UpdatePanelRefModel):
        for ref in payload.refs:
            existing_panel_ref = await self.panel_ref_repo.get_by_uid(panel_ref_uid=ref.uid)

            if not existing_panel_ref:
                raise NotFound(f"Solar  with ref: {ref.uid} not found!")

            if not existing_panel_ref.site_uid == site_uid:
                raise Forbidden()

            if not existing_panel_ref.user_uid == user_uid:
                raise Forbidden()

            for k, v in ref.model_dump(exclude={"uid"}).items():
                setattr(existing_panel_ref, k, v)

            await self.session.flush()

        await self.session.commit()

        return True

    async def get_site_panels(self, site_uid: UUID):
        panel_refs = await self.panel_ref_repo.get_refs_by_site_uid(site_uid=site_uid)

        return panel_refs

    async def create_pvs(self, user_uid: UUID, site_uid: UUID, payload: SitePVSItemModel):
        user = await self.user_repo.get_user_by_uid(user_uid=user_uid)

        if not user:
            raise NotFound("User doesn't exist!")

        if not user.role == UserRoleEnum.ENGINEER:
            raise Forbidden("Insufficient permission")

        site = await self.site_repo.get_site_by_uid(site_uid=site_uid)

        if not site:
            raise NotFound("Site doesn't exist!")

        existing_site_pvs = await self.pvs_repo.get_pvs_by_site_uid(site_uid=site_uid)

        if existing_site_pvs:
            raise ResourceExists("PVS exists for this site. Edit it instead.")

        await self.pvs_repo.create_pvs(site_uid=site_uid, user_uid=user_uid, payload=payload)

        return True

    async def edit_pvs(self, site_uid: UUID, user_uid: UUID, payload: UpdatePVSItemModel):
        existing_pvs = await self.pvs_repo.get_by_uid(pvs_uid=payload.uid)

        if not existing_pvs:
            raise NotFound(f"Solar  with pv summary: {payload.uid} not found!")

        if not existing_pvs.site_uid == site_uid:
            raise Forbidden()

        if not existing_pvs.user_uid == user_uid:
            raise Forbidden()

        await self.pvs_repo.edit_pvs(existing_pvs=existing_pvs, payload=payload)
        return True

    async def get_site_pvs(self, site_uid: UUID):
        pvs = await self.pvs_repo.get_pvs_by_site_uid(site_uid=site_uid)

        return pvs


def get_site_configs_service(
    session: AsyncSession = Depends(get_session),
):
    return SiteConfigService(session=session)
