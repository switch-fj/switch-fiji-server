from uuid import UUID

from pydantic import field_serializer

from app.modules.clients.schema import ClientRespModel
from app.modules.contracts.schema import ContractDetailsRespModel, ContractRespModel
from app.shared.schema import DBModel
from app.utils import uuid_serializer


class SiteRespModel(DBModel):
    client_uid: UUID
    site_id: str
    gateway_id: str
    firmware: str

    @field_serializer("client_uid")
    def serialize_client_uid(self, value: UUID):
        return uuid_serializer(value)


class SiteDetailedRespModel(SiteRespModel):
    client: ClientRespModel
    contract: ContractRespModel
    details: ContractDetailsRespModel
