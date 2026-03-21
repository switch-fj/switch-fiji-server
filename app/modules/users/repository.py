from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.auth import Authentication
from app.core.exceptions import BadRequest, NotFound
from app.modules.users.model import User
from app.modules.users.schema import CreateUserModel
from app.shared.schema import UpdateIdentityPwdModel


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

    async def create_user(self, data: CreateUserModel):
        data_dict = data.model_dump()
        new_user = User(**data_dict)

        try:
            self.session.add(new_user)
            await self.session.commit()
            await self.session.refresh(new_user)

            return new_user
        except Exception as e:
            await self.session.rollback()
            raise BadRequest(f"Error creating user {e}")

    async def update_pwd(self, user_uid: str, data: UpdateIdentityPwdModel):
        user = await self.get_user_by_uid(user_uid=user_uid)

        if not user:
            raise NotFound("user not found")

        user.password_hash = Authentication.generate_password_hash(data.password)

        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)

        return user
