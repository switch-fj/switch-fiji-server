from uuid import UUID

from pydantic import BaseModel, Field, field_serializer

from app.shared.schema import DBModel
from app.utils import uuid_serializer


class SitePanelRefItemModel(BaseModel):
    panel_type: str = Field(...)
    watt: float = Field(...)
    vmp: float = Field(...)
    voc: float = Field(...)
    imp: float = Field(...)


class SiteSinglePanelRefItemModel(SitePanelRefItemModel):
    uid: UUID = Field(...)


class CreatePanelRefModel(BaseModel):
    refs: list[SitePanelRefItemModel] = Field(..., title="Panel Refs")


class UpdatePanelRefModel(BaseModel):
    refs: list[SiteSinglePanelRefItemModel] = Field(..., title="Panel Refs")


class PanelRefsModel(DBModel):
    site_uid: UUID
    user_uid: UUID
    panel_type: str = Field(...)
    watt: float = Field(...)
    vmp: float = Field(...)
    voc: float = Field(...)
    imp: float = Field(...)

    @field_serializer("site_uid", "user_uid")
    def serialize_panel_ref_uuids(self, value: UUID):
        """Serialise the uid UUID to a plain string.

        Args:
            value: The UUID value to serialise.

        Returns:
            A string representation of the UUID.
        """
        return uuid_serializer(value)
