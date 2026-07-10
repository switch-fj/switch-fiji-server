from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_serializer

from app.shared.schema import DBModel
from app.utils import uuid_serializer


class SitePVSItemModel(BaseModel):
    commissioned_at: datetime = Field(...)
    expected_production_kwh: Decimal = Field(...)
    system_size_kwp: Decimal = Field(...)
    year1_degradation: float = Field(..., precision=1, scale=2)
    year2plus_degradation: float = Field(..., precision=1, scale=2)


class UpdatePVSItemModel(SitePVSItemModel):
    uid: UUID = Field(...)


class PVSModel(DBModel):
    site_uid: UUID
    user_uid: UUID
    commissioned_at: datetime
    expected_production_kwh: Decimal
    system_size_kwp: Decimal
    year1_degradation: float
    year2plus_degradation: float

    @field_serializer("commissioned_at")
    def serialize_pv_dt(self, value: datetime):
        """Serialise datetime fields to ISO-8601 strings.

        Args:
            value: The datetime value to serialise.

        Returns:
            ISO-8601 formatted string, or None if value is falsy.
        """
        if value:
            return value.isoformat()

    @field_serializer("site_uid", "user_uid")
    def serialize_pvs_uuids(self, value: UUID):
        """Serialise the uid UUID to a plain string.

        Args:
            value: The UUID value to serialise.

        Returns:
            A string representation of the UUID.
        """
        return uuid_serializer(value)

    @field_serializer("expected_production_kwh", "system_size_kwp")
    def serialize_pv_decimals(self, value: Decimal):
        """Serialise Decimal financial fields to two-decimal-place strings.

        Args:
            value: The Decimal value to serialise.

        Returns:
            A string formatted to two decimal places, or None if value is falsy.
        """
        if value:
            return f"{value:.2f}"
