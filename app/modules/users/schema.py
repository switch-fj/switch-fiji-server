from pydantic import Field

from app.shared.schema import EmailModel, UserRoleEnum


class CreateUserModel(EmailModel):
    """Request model for creating a new internal platform user."""

    role: UserRoleEnum = Field(...)
