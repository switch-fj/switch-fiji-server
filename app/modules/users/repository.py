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
    """Data-access layer for the User model."""

    def __init__(self, session: AsyncSession):
        """Initialise the repository with a database session.

        Args:
            session: An async SQLAlchemy session used for all database operations.
        """
        self.session = session

    async def get_user_by_uid(self, user_uid: UUID):
        """Fetch a user by their primary UUID.

        Args:
            user_uid: The UUID of the user to retrieve.

        Returns:
            The matching User ORM instance, or None if not found.
        """
        statement = select(User).where(User.uid == user_uid)
        result = await self.session.exec(statement=statement)
        user = result.first()

        return user

    async def get_user_by_mail(self, email: str):
        """Fetch a user by their email address.

        Args:
            email: The email address to look up.

        Returns:
            The matching User ORM instance, or None if not found.
        """
        statement = select(User).where(User.email == email)
        result = await self.session.exec(statement=statement)
        user = result.first()

        return user

    async def create_user(self, data: CreateUserModel, user_uid: Optional[UUID] = None):
        """Create and persist a new user record.

        Args:
            data: The validated model containing user creation fields.
            user_uid: Optional UUID of the admin user registering this new user.

        Returns:
            The newly created User ORM instance, or None if an error occurs.
        """
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
        """Hash and update the password for an existing user.

        Args:
            user: The User ORM instance whose password will be updated.
            data: The validated model containing the new plain-text password.

        Returns:
            The updated User ORM instance.
        """
        user.password_hash = await Authentication.generate_password_hash(data.password)

        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)

        return user

    async def verify_email(self, user: User):
        """Mark a user's email as verified.

        Args:
            user: The User ORM instance to update.

        Returns:
            The updated User ORM instance with is_email_verified set to True.
        """
        user.is_email_verified = True
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)

        return user


def get_user_repo(session: AsyncSession = Depends(get_session)):
    """FastAPI dependency that provides a UserRepository instance.

    Args:
        session: Injected async database session from get_session.

    Returns:
        A UserRepository bound to the provided session.
    """
    return UserRepository(session=session)
