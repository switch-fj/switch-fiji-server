from typing import Optional
from uuid import UUID

from pydantic import Field, field_serializer

from app.shared.schema import DBModel, EmailModel, UserRoleEnum
from app.utils import uuid_serializer


class CreateUserModel(EmailModel):
    """Request model for creating a new internal platform user."""

    role: UserRoleEnum = Field(...)


class UserSummary(DBModel):
    email: str
    role: UserRoleEnum


class UsersRespModel(DBModel):
    email: str
    is_email_verified: bool
    role: UserRoleEnum
    registrar_uid: Optional[UUID] = None
    registrar: Optional[UserSummary] = None

    @field_serializer("registrar_uid")
    def user_serialize_uuid(self, value: UUID):
        """Serialise the uid UUID to a plain string.

        Args:
            value: The UUID value to serialise.

        Returns:
            A string representation of the UUID.
        """
        if value:
            return uuid_serializer(value)

        return None
