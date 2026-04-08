from typing import Optional

import email_validator
from pydantic import BaseModel, Field, field_validator

from app.shared.schema import DBModel


class CreateClientModel(BaseModel):
    client_email: str = Field(...)
    client_name: str = Field(...)

    @field_validator("client_email")
    @classmethod
    def validate_email(cls, value):
        return email_validator(value)


class UpdateClientModel(BaseModel):
    client_id: Optional[str] = Field(default=None)
    client_name: Optional[str] = Field(default=None)


class ClientRespModel(DBModel):
    client_id: Optional[str]
    client_name: str
    client_email: str
    sites_count: Optional[int]


class ClientDetailedRespModel(ClientRespModel):
    pass
