from pydantic import Field

from app.shared.schema import EmailModel, UserRoleEnum


class CreateUserModel(EmailModel):
    role: UserRoleEnum = Field(...)
