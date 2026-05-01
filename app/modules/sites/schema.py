from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_serializer

from app.modules.clients.schema import ClientRespModel
from app.modules.contracts.schema import ContractDetailsRespModel, ContractRespModel
from app.shared.schema import DBModel
from app.utils import uuid_serializer


class CreateSiteModel(BaseModel):
    """Request model for creating a new site under a client."""

    client_uid: UUID = Field(...)
    site_name: str = Field(...)


class UpdateSiteModel(BaseModel):
    """Request model for partially updating a site's mutable fields."""

    site_id: Optional[str] = Field(default=None)
    site_name: Optional[str] = Field(default=None)
    gateway_id: Optional[str] = Field(default=None)
    firmware: Optional[str] = Field(default=None)


class SiteRespModel(DBModel):
    """Response model for a site record including device count and contract summary."""

    client_uid: UUID
    site_id: Optional[str]
    site_name: Optional[str]
    gateway_id: Optional[str]
    firmware: Optional[str]
    device_count: Optional[int]
    contract: Optional[ContractRespModel]

    @field_serializer("client_uid")
    def serialize_client_uid(self, value: UUID):
        """Serialise the client_uid UUID to a plain string.

        Args:
            value: The UUID value to serialise.

        Returns:
            A string representation of the UUID.
        """
        return uuid_serializer(value)


class SiteDetailedRespModel(SiteRespModel):
    """Extended site response model including full client, contract, and contract details."""

    client: ClientRespModel
    contract: ContractRespModel
    details: ContractDetailsRespModel
