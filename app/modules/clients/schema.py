import email_validator
from pydantic import BaseModel, Field, field_validator

from app.shared.schema import DBModel


class CreateClientModel(BaseModel):
    client_id: str = Field(...)
    client_email: str = Field(...)
    client_name: str = Field(...)

    @field_validator("client_email")
    @classmethod
    def validate_email(cls, value):
        return email_validator(value)


class ClientRespModel(DBModel):
    client_id: str
    client_name: str
    client_email: str
    sites_count: int


class ClientDetailedRespModel(ClientRespModel):
    pass
