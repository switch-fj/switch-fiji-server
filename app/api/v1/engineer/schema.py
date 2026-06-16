from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, field_serializer

from app.shared.schema import DBModel


class ResourceStatsModel(BaseModel):
    clients: int
    sites: int
    devices: int


class EngineeringDashboardDeviceModel(DBModel):
    device_type: str
    meter_role: Optional[str]
    is_dual_tariff: Optional[bool]
    last_seen_at: Optional[datetime]
    is_online: bool

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


class EngineeringDashboardSiteModel(DBModel):
    site_name: Optional[str]
    gateway_id: str
    firmware: Optional[str]
    first_seen_at: Optional[datetime]

    devices: List[EngineeringDashboardDeviceModel]

    @field_serializer("first_seen_at")
    def serialize_site_dt(self, value: datetime):
        """Serialise datetime fields to ISO-8601 strings.

        Args:
            value: The datetime value to serialise.

        Returns:
            ISO-8601 formatted string, or None if value is falsy.
        """
        if value:
            return value.isoformat()


class EngineeringDashboardClientModel(DBModel):
    client_id: Optional[str]
    client_name: str
    client_email: str
    sites: List[EngineeringDashboardSiteModel]
