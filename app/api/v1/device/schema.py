from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import field_serializer

from app.shared.schema import DBModel
from app.utils import uuid_serializer


class DeviceModel(DBModel):
    site_uid: UUID
    slave_id: int
    device_type: str
    meter_role: Optional[str]
    is_dual_tariff: Optional[bool]
    last_seen_at: Optional[datetime]

    @field_serializer("last_seen_at")
    def serialize_device_dt(self, value: datetime):
        """Serialise datetime fields to ISO-8601 strings.

        Args:
            value: The datetime value to serialise.

        Returns:
            ISO-8601 formatted string, or None if value is falsy.
        """
        if value:
            return value.isoformat()

    @field_serializer("site_uid")
    def serialize_device_uuid(self, value: UUID):
        """Serialise the uid UUID to a plain string.

        Args:
            value: The UUID value to serialise.

        Returns:
            A string representation of the UUID.
        """
        return uuid_serializer(value)
