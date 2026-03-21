from typing import Optional
from uuid import UUID

from fastapi import Depends
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.auth import Authentication
from app.core.exceptions import BadRequest, NotFound
from app.database.postgres import get_session
from app.modules.clients.model import Client
from app.modules.clients.schema import CreateClientModel
from app.shared.schema import UpdateIdentityPwdModel


class ClientRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_client_by_uid(self, client_uid: UUID):
        statement = select(Client).where(Client.uid == client_uid)
        result = await self.session.exec(statement=statement)
        client = result.first()

        return client

    async def get_client_by_mail(self, email: str):
        statement = select(Client).where(Client.client_email == email)
        result = await self.session.exec(statement=statement)
        client = result.first()

        return client

    async def create_client(
        self,
        data: CreateClientModel,
        user_uid: Optional[UUID] = None,
    ):
        data_dict = data.model_dump()
        data_dict["user_uid"] = user_uid
        new_client = Client(**data_dict)

        try:
            self.session.add(new_client)
            await self.session.commit()
            await self.session.refresh(new_client)

            return new_client
        except Exception as e:
            await self.session.rollback()
            raise BadRequest(f"Error creating client {e}")

    async def update_pwd(self, client_uid: str, data: UpdateIdentityPwdModel):
        client = await self.get_client_by_uid(client_uid=client_uid)

        if not client:
            raise NotFound("client not found")

        client.password_hash = Authentication.generate_password_hash(data.password)

        self.session.add(client)
        await self.session.commit()
        await self.session.refresh(client)

        return client


def get_client_repo(session: AsyncSession = Depends(get_session)):
    return ClientRepository(session=session)
