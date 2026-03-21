from datetime import datetime
from enum import IntEnum, StrEnum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from app.utils import email_validator, uuid_serializer


class UserRoleEnum(IntEnum):
    """Internal staff roles — controls what they can do on the platform."""

    ADMIN = 0
    ENGINEER = 1


class IdentityTypeEnum(IntEnum):
    """
    Used in JWT claims to distinguish token type.
    Not stored in any table — only lives in the token payload.
    """

    USER = 0
    CLIENT = 1


class AuthType(StrEnum):
    TOKEN = "token"
    PWD = "pwd"


class DBModel(BaseModel):
    uid: UUID
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def serialize_dt(self, value: datetime):
        if value:
            return value.isoformat()

    @field_serializer("uid")
    def serialize_uuid(self, value: UUID):
        return uuid_serializer(value)

    model_config = ConfigDict(from_attributes=True)


class TokenIdentityModel(BaseModel):
    id: int
    uid: UUID
    email: str
    identity: int
    user_type: Optional[int]
    is_email_verified: bool

    @field_serializer("uid")
    def serialize_uuid(self, value: UUID):
        return uuid_serializer(value)

    model_config = ConfigDict(from_attributes=True)


class EmailModel(BaseModel):
    email: str = Field(...)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value):
        return email_validator(value)


class UpdateIdentityPwdModel(BaseModel):
    password: str = Field(...)


class SetPwdModel(EmailModel):
    new_password: str


class ChangePwdModel(BaseModel):
    old_password: str
    new_password: str


class TokenModel(BaseModel):
    access_token: str
    is_email_verified: bool
    auth_type: AuthType


class ResetPwdModel(BaseModel):
    token: str
    new_password: str


class UserLoginModel(EmailModel):
    password: str = Field(...)
