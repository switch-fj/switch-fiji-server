from typing import Optional
from uuid import UUID

from fastapi import Depends
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.auth import Authentication
from app.core.logger import setup_logger
from app.database.postgres import get_session
from app.modules.users.model import User
from app.modules.users.schema import CreateUserModel
from app.shared.schema import UpdateIdentityPwdModel

logger = setup_logger(__name__)


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_user_by_uid(self, user_uid: UUID):
        statement = select(User).where(User.uid == user_uid)
        result = await self.session.exec(statement=statement)
        user = result.first()

        return user

    async def get_user_by_mail(self, email: str):
        statement = select(User).where(User.email == email)
        result = await self.session.exec(statement=statement)
        user = result.first()

        return user

    async def create_user(self, data: CreateUserModel, user_uid: Optional[UUID] = None):
        data_dict = data.model_dump()

        if user_uid:
            data_dict["registrar_uid"] = user_uid

        new_user = User(**data_dict)

        try:
            self.session.add(new_user)
            await self.session.commit()
            await self.session.refresh(new_user)

            return new_user
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            await self.session.rollback()

    async def update_pwd(self, user: User, data: UpdateIdentityPwdModel):
        user.password_hash = Authentication.generate_password_hash(data.password)

        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)

        return user

    async def verify_email(self, user: User):
        user.is_email_verified = True
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)

        return user


def get_user_repo(session: AsyncSession = Depends(get_session)):
    return UserRepository(session=session)
