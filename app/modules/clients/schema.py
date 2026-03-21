import email_validator
from pydantic import BaseModel, Field, field_validator


class CreateClientModel(BaseModel):
    client_id: str = Field(...)
    client_email: str = Field(...)
    client_name: str = Field(...)

    @field_validator("client_email")
    @classmethod
    def validate_email(cls, value):
        return email_validator(value)
