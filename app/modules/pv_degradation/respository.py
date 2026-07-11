from uuid import UUID

from fastapi import Depends
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database.postgres import get_session
from app.modules.pv_degradation.model import PvDegradation
from app.modules.pv_degradation.schema import PvDegradationSchedule


class PvDegradationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_site_uid(self, site_uid: UUID):
        statement = select(PvDegradation).where(PvDegradation.site_uid == site_uid, PvDegradation.deleted_at.is_(None))
        result = await self.session.exec(statement)
        degradation = result.one_or_none()

        return degradation

    async def create(self, site_uid: UUID, user_uid: UUID, payload: PvDegradationSchedule):
        pv_degradation = PvDegradation(site_uid=site_uid, user_uid=user_uid, degradation=payload.to_json())

        self.session.add(pv_degradation)
        await self.session.commit()

        return pv_degradation

    async def update(self, payload: PvDegradationSchedule, pv_degradation: PvDegradation):
        pv_degradation.degradation = payload.to_json()

        await self.session.commit()

        return pv_degradation


async def get_pv_degradation_repo(session: AsyncSession = Depends(get_session)):
    return PvDegradationRepository(session=session)
