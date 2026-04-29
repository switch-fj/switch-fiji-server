from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.shared.schema import DBModel
from app.utils import email_validator


class CreateClientModel(BaseModel):
    """Request model for creating a new client account."""

    client_email: str = Field(...)
    client_name: str = Field(...)

    @field_validator("client_email")
    @classmethod
    def validate_email(cls, value):
        """Normalise and validate the client email address.

        Args:
            value: The raw email string provided in the request.

        Returns:
            The lowercased, validated email string.
        """
        return email_validator(value)


class UpdateClientModel(BaseModel):
    """Request model for partially updating a client's mutable fields."""

    client_id: Optional[str] = Field(default=None)
    client_name: Optional[str] = Field(default=None)


class ClientRespModel(DBModel):
    """Response model for a client record including its site count."""

    client_id: Optional[str]
    client_name: str
    client_email: str
    sites_count: Optional[int]


class ClientRespWithoutSitesCountModel(DBModel):
    """Response model for a client record without site count (used in nested responses)."""

    client_id: Optional[str]
    client_name: str
    client_email: str


class ClientDetailedRespModel(ClientRespModel):
    """Extended client response model reserved for detailed client views."""

    pass
