from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_serializer

from app.modules.clients.schema import ClientRespModel
from app.modules.contracts.schema import ContractDetailsRespModel, ContractRespModel
from app.shared.schema import DBModel
from app.utils import uuid_serializer


class CreateSiteModel(BaseModel):
    client_uid: UUID = Field(...)
    site_name: str = Field(...)


class UpdateSiteModel(BaseModel):
    site_id: Optional[str] = Field(default=None)
    site_name: Optional[str] = Field(default=None)
    gateway_id: Optional[str] = Field(default=None)
    firmware: Optional[str] = Field(default=None)


class SiteRespModel(DBModel):
    client_uid: UUID
    site_id: Optional[str]
    site_name: Optional[str]
    gateway_id: Optional[str]
    firmware: Optional[str]
    device_count: Optional[int]
    contract: Optional[ContractRespModel]

    @field_serializer("client_uid")
    def serialize_client_uid(self, value: UUID):
        return uuid_serializer(value)


class SiteDetailedRespModel(SiteRespModel):
    client: ClientRespModel
    contract: ContractRespModel
    details: ContractDetailsRespModel


# class SiteStatsModel(BaseModel):
#     site_uid: str
#     expected_generation_kwh: float
#     actual_generation_kwh: float
#     billing_progress_pct: float
#     deviation_pct: float
#     period_start: datetime
#     period_end: datetime
#     computed_at: datetime
#     status: Optional[str] = None
