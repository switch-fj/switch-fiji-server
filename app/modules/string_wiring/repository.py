from uuid import UUID

from fastapi import Depends
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database.postgres import get_session
from app.modules.string_wiring.model import StringWiring
from app.modules.string_wiring.schema import StringsWiringInputModel


class StringWiringRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_uid(self, str_wiring_uid: UUID):
        result = await self.session.exec(select(StringWiring).where(StringWiring.uid == str_wiring_uid))
        string_wiring = result.one_or_none()

        return string_wiring

    async def get_by_site(self, site_uid: UUID):
        result = await self.session.exec(
            select(StringWiring).where(StringWiring.site_uid == site_uid, StringWiring.deleted_at.is_(None))
        )
        string_wiring = result.one_or_none()

        return string_wiring

    async def create(self, site_uid: UUID, user_uid: UUID, payload: StringsWiringInputModel):
        string_wiring = StringWiring(
            site_uid=site_uid,
            user_uid=user_uid,
            string_input=StringsWiringInputModel.to_json(payload.strings),
        )

        self.session.add(string_wiring)
        await self.session.commit()

        return string_wiring

    async def update(self, payload: StringsWiringInputModel, string_wiring: StringWiring):
        string_wiring.string_input = StringsWiringInputModel.to_json(items=payload.strings)
        await self.session.commit()

        return string_wiring


async def get_st_wiring_repo(session: AsyncSession = Depends(get_session)):
    return StringWiringRepository(session=session)
