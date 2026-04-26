from typing import Optional
from uuid import UUID

from fastapi import Depends
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.auth import Authentication
from app.core.config import Config
from app.core.logger import setup_logger
from app.database.postgres import get_session
from app.modules.clients.model import Client
from app.modules.clients.schema import (
    ClientRespModel,
    CreateClientModel,
    UpdateClientModel,
)
from app.modules.sites.model import Site
from app.shared.schema import (
    CursorPaginationModel,
    PaginatedRespModel,
    UpdateIdentityPwdModel,
)
from app.utils.pagination import Pagination

logger = setup_logger(__name__)


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

    async def get_clients(
        self,
        q: Optional[str],
        limit: int = Config.DEFAULT_PAGE_LIMIT,
        next_cursor: Optional[str] = None,
        prev_cursor: Optional[str] = None,
    ):
        sites_count_subq = (
            select(Site.client_uid, func.count(Site.id).label("sites_count")).group_by(Site.client_uid).subquery()
        )

        statement = (
            select(
                Client,
                func.coalesce(sites_count_subq.c.sites_count, 0).label("sites_count"),
            )
            .outerjoin(sites_count_subq, sites_count_subq.c.client_uid == Client.uid)
            .order_by(Client.created_at.desc())
        )

        if next_cursor:
            cursor_id = Pagination.decrypt_cursor(next_cursor)
            statement = statement.where(Client.id < cursor_id)

        if prev_cursor:
            cursor_id = Pagination.decrypt_cursor(prev_cursor)
            statement = statement.where(Client.id > cursor_id)

        if q:
            search = f"%{q}%"
            statement = statement.where(Client.client_name.ilike(search) | Client.client_email.ilike(search))

        statement = statement.limit(limit + 1)

        result = await self.session.exec(statement)
        rows = result.all()

        has_more = len(rows) > limit
        items = rows[:limit]

        clients = [
            ClientRespModel.model_validate({**row.Client.__dict__, "sites_count": row.sites_count}) for row in items
        ]

        next_cursor_out = None
        prev_cursor_out = None

        if items:
            prev_cursor_out = Pagination.encrypt_cursor(items[0].Client.id)

        if has_more:
            next_cursor_out = Pagination.encrypt_cursor(items[-1].Client.id)

        return PaginatedRespModel.model_validate(
            {
                "items": clients,
                "pagination": CursorPaginationModel(
                    limit=limit,
                    next_cursor=next_cursor_out,
                    prev_cursor=prev_cursor_out,
                ),
            }
        )

    async def create_client(
        self,
        data: CreateClientModel,
        user_uid: Optional[UUID] = None,
    ):
        data_dict = data.model_dump()

        if user_uid:
            data_dict["user_uid"] = user_uid

        new_client = Client(**data_dict)

        try:
            self.session.add(new_client)
            await self.session.commit()
            await self.session.refresh(new_client)

            return new_client
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error creating client {e}")

    async def update_pwd(self, client: Client, data: UpdateIdentityPwdModel):
        client.password_hash = await Authentication.generate_password_hash(data.password)

        self.session.add(client)
        await self.session.commit()
        await self.session.refresh(client)

        return client

    async def verify_email(self, client: Client):
        client.is_email_verified = True

        self.session.add(client)
        await self.session.commit()
        await self.session.refresh(client)

        return client

    async def update_client(self, client: Client, data: UpdateClientModel):
        data_dict = data.model_dump(exclude_none=True)

        for key, value in data_dict.items():
            setattr(client, key, value)

        await self.session.commit()
        await self.session.refresh(client)
        return client


def get_client_repo(session: AsyncSession = Depends(get_session)):
    return ClientRepository(session=session)
