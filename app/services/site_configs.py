from uuid import UUID

from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.exceptions import (
    Forbidden,
    InsufficientPermissions,
    NotFound,
    ResourceExists,
)
from app.database.postgres import get_session
from app.jobs.on_demand.triggers.degradation import (
    trigger_compute_site_yearly_degradation_on_demand,
)
from app.jobs.on_demand.triggers.string_wiring import (
    trigger_compute_string_wiring_on_demand,
)
from app.modules.clients.repository import ClientRepository
from app.modules.panel_references.repository import PanelRefRepository
from app.modules.panel_references.schema import CreatePanelRefModel, UpdatePanelRefModel
from app.modules.pv_degradation.respository import PvDegradationRepository
from app.modules.pv_degradation.schema import (
    PvDegradationSchedule,
    Year1DegradationInputModel,
    YearlyDegradation,
)
from app.modules.pv_summary.repository import PvSummaryRepository
from app.modules.pv_summary.schema import SitePVSItemModel, UpdatePVSItemModel
from app.modules.sites.repository import SiteRepository
from app.modules.string_wiring.repository import StringWiringRepository
from app.modules.string_wiring.schema import (
    StringsWiringInputModel,
    StringWiringRespModel,
)
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
        self.pv_degradation_repo = PvDegradationRepository(session=session)
        self.st_wiring_repo = StringWiringRepository(session=session)

        super().__init__(site_repo=self.site_repo, client_repo=self.client_repo)

    async def _initiate_degradation_computation_task(self, user_uid: UUID, degradation_uid: UUID, site_uid: UUID):
        trigger_compute_site_yearly_degradation_on_demand.delay(
            requesting_user_uid=str(user_uid),
            degradation_uid=str(degradation_uid),
            site_uid=str(site_uid),
        )

        return

    async def _initiate_string_wiring_task(self, user_uid: UUID, string_wiring_uid: UUID, site_uid: UUID):
        trigger_compute_string_wiring_on_demand.delay(
            requesting_user_uid=str(user_uid),
            string_wiring_uid=str(string_wiring_uid),
            site_uid=str(site_uid),
        )

        return

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
        ref_uids = [ref.uid for ref in payload.refs]
        existing_refs = await self.panel_ref_repo.get_by_uids(panel_ref_uids=ref_uids)
        existing_by_uid = {ref.uid: ref for ref in existing_refs}

        missing = set(ref_uids) - existing_by_uid.keys()
        if missing:
            raise NotFound(f"Panel ref(s) not found: {missing}")

        for ref in payload.refs:
            existing = existing_by_uid[ref.uid]
            if str(existing.site_uid) != str(site_uid) or str(existing.user_uid) != str(user_uid):
                raise Forbidden()

        updates_by_uid = {ref.uid: ref for ref in payload.refs}
        await self.panel_ref_repo.update_panel_refs(existing_refs, updates_by_uid)

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

        if str(existing_pvs.site_uid) != str(site_uid):
            raise Forbidden()

        if str(existing_pvs.user_uid) != str(user_uid):
            raise Forbidden()

        await self.pvs_repo.edit_pvs(existing_pvs=existing_pvs, payload=payload)
        return True

    async def get_site_pvs(self, site_uid: UUID):
        pvs = await self.pvs_repo.get_pvs_by_site_uid(site_uid=site_uid)
        return pvs

    async def create_or_update_year_one_degradation(
        self, site_uid: UUID, user_uid: UUID, payload: Year1DegradationInputModel
    ):
        site_pvs = await self.pvs_repo.get_pvs_by_site_uid(site_uid=site_uid)

        if not site_pvs:
            return None

        year_1 = YearlyDegradation(
            root=dict(
                zip(
                    PvDegradationSchedule.build_month_sequence(site_pvs.commissioned_at, num_years=1),
                    payload.monthly_kwh_values,
                )
            )
        )

        partial_schedule = PvDegradationSchedule(root=[year_1])

        pv_degradation = await self.pv_degradation_repo.get_by_site_uid(site_uid=site_uid)

        if not pv_degradation:
            pv_degradation = await self.pv_degradation_repo.create(
                site_uid=site_uid, user_uid=user_uid, payload=partial_schedule
            )
        else:
            pv_degradation = await self.pv_degradation_repo.update(
                payload=partial_schedule, pv_degradation=pv_degradation
            )

        # initiate background job here for year 2 plus degradation computation:
        await self._initiate_degradation_computation_task(
            user_uid=user_uid, degradation_uid=pv_degradation.uid, site_uid=site_uid
        )
        return pv_degradation

    async def get_degradation_by_site(self, site_uid: UUID):
        site_degradation = await self.pv_degradation_repo.get_by_site_uid(site_uid=site_uid)

        return site_degradation

    async def create_string_wiring(self, site_uid: UUID, user_uid: UUID, payload: StringsWiringInputModel):
        existing_str_wiring = await self.st_wiring_repo.get_by_site(site_uid=site_uid)

        if existing_str_wiring:
            raise ResourceExists("string configuration exists. Update it instead.")

        site = await self.site_repo.get_site_by_uid(site_uid=site_uid)

        if not site:
            raise NotFound("Site not found!")

        string_wiring = await self.st_wiring_repo.create(user_uid=user_uid, site_uid=site_uid, payload=payload)

        await self._initiate_string_wiring_task(
            user_uid=user_uid,
            string_wiring_uid=string_wiring.uid,
            site_uid=site_uid,
        )

        return string_wiring

    async def update_string_wiring(
        self,
        site_uid: UUID,
        user_uid: UUID,
        payload: StringsWiringInputModel,
    ):
        existing_str_wiring = await self.st_wiring_repo.get_by_site(site_uid=site_uid)

        if not existing_str_wiring:
            raise NotFound()

        has_permission = existing_str_wiring.site_uid == site_uid and existing_str_wiring.user_uid == user_uid

        if not has_permission:
            raise InsufficientPermissions()

        existing_str_wiring = await self.st_wiring_repo.update(payload=payload, string_wiring=existing_str_wiring)

        await self._initiate_string_wiring_task(user_uid=user_uid, string_wiring_uid=existing_str_wiring.uid)
        return existing_str_wiring

    async def get_str_wiring(self, site_uid: UUID):
        result = await self.st_wiring_repo.get_by_site(site_uid=site_uid)

        if not result:
            raise NotFound()

        return StringWiringRespModel.model_validate(result.model_dump())


def get_site_configs_service(
    session: AsyncSession = Depends(get_session),
):
    return SiteConfigService(session=session)
