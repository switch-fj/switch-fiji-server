from datetime import datetime
from typing import TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator
from sqlalchemy.sql.selectable import Select

from app.utils import email_validator, uuid_serializer

T = TypeVar("T")
SelectOfScalar = Select[T]


class EmailModel(BaseModel):
    email: str = Field(...)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value):
        return email_validator(value)


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


class SetPwdModel(EmailModel):
    new_password: str


class ChangePwdModel(BaseModel):
    old_password: str
    new_password: str


class TokenModel(BaseModel):
    access_token: str
    is_email_verified: bool


class ResetPwdModel(BaseModel):
    token: str
    new_password: str


class TokenUserModel(BaseModel):
    id: int
    uid: UUID
    email: str
    is_email_verified: bool

    @field_serializer("uid")
    def serialize_uuid(self, value: UUID):
        return uuid_serializer(value)

    model_config = ConfigDict(from_attributes=True)


class UserLoginModel(EmailModel):
    password: str = Field(...)
