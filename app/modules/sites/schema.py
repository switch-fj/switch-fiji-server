from uuid import UUID

from app.modules.clients.schema import ClientRespModel
from app.modules.contracts.schema import ContractDetailsRespModel, ContractRespModel
from app.shared.schema import DBModel


class SiteRespModel(DBModel):
    client_uid: UUID
    site_id: str
    gateway_id: str
    firmware: str


class SiteDetailedRespModel(SiteRespModel):
    client: ClientRespModel
    contract: ContractRespModel
    details: ContractDetailsRespModel
