from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_serializer

from app.shared.schema import DBModel
from app.utils import uuid_serializer


class SitePVSItemModel(BaseModel):
    expected_production_kwh: Decimal = Field(...)
    system_size_kwp: Decimal = Field(...)
    year1_degradation: float = Field(..., precision=1, scale=2)
    year2plus_degradation: float = Field(..., precision=1, scale=2)


class UpdatePVSItemModel(SitePVSItemModel):
    uid: UUID = Field(...)


class PVSModel(DBModel):
    site_uid: UUID
    user_uid: UUID
    expected_production_kwh: Decimal = Field(...)
    system_size_kwp: Decimal = Field(...)
    year1_degradation: float = Field(..., precision=1, scale=2)
    year2plus_degradation: float = Field(..., precision=1, scale=2)

    @field_serializer("site_uid", "user_uid")
    def serialize_pvs_uuids(self, value: UUID):
        """Serialise the uid UUID to a plain string.

        Args:
            value: The UUID value to serialise.

        Returns:
            A string representation of the UUID.
        """
        return uuid_serializer(value)
