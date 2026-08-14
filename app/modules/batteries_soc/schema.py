from datetime import date, datetime, time
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, RootModel, field_serializer

from app.shared.schema import DBModel
from app.utils import uuid_serializer


class BatteryDataItem(BaseModel):
    battery_keys: List[str]
    capacity_kwh: float
    low_soc_threshold: int
    high_soc_threshold: int


class BatterySOCInputItem(BaseModel):
    inverter_slave_id: int
    battery_data: BatteryDataItem


class BatteryReadingItem(BaseModel):
    inverter_slave_id: int
    battery_socs: dict[str, float]
    battery_power_w: float
    battery_current_a: float


class BatterySOCTableModel(BaseModel):
    time_at: time
    batteries: list[BatteryReadingItem]


class ConfigBatterySOCInputModel(BaseModel):
    config_input: list[BatterySOCInputItem]

    @classmethod
    def from_json(cls, raw: str):
        return cls.model_validate_json(raw)


class BatterySOCTableModel(RootModel[List[BatterySOCTableModel]]):
    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, raw: str) -> "BatterySOCTableModel":
        return cls.model_validate_json(raw)

    @classmethod
    def build(
        cls,
        telemetry_reading: List[dict | None],
        time_boundaries: list[time],
        battery_soc_input: ConfigBatterySOCInputModel,
    ) -> "BatterySOCTableModel":
        rows = []
        config_by_slave_id = {item.inverter_slave_id: item.battery_data for item in battery_soc_input.config_input}

        for time_at, reading in zip(time_boundaries, telemetry_reading):
            batteries: list[BatteryReadingItem] = []

            if reading:
                for inverter in reading.get("inverters", []):
                    slave_id = inverter.get("slave_id")
                    if slave_id is None or slave_id not in config_by_slave_id:
                        continue

                    battery_data = config_by_slave_id[slave_id]
                    socs = {}
                    for key in battery_data.battery_keys:
                        value = inverter.get(key)
                        if value is not None:
                            socs[key] = float(value)

                    batteries.append(
                        BatteryReadingItem(
                            inverter_slave_id=slave_id,
                            battery_socs=socs,
                            battery_power_w=float(inverter.get("battery_power_w", 0)),
                            battery_current_a=float(inverter.get("battery_current_a", 0)),
                        )
                    )

            rows.append(BatterySOCTableModel(time_at=time_at, batteries=batteries))

        return cls(root=rows)

    def to_list(self) -> List[BatterySOCTableModel]:
        return self.root


class BatterySOCRespModel(DBModel):
    site_uid: UUID
    battery_soc_config_uid: UUID
    date_at: date
    from_: time
    to: time
    interval_in_minutes: int
    telemetry_reading_str: str | None = None
    battery_soc_table_str: str | None = None
    is_completed: bool

    @field_serializer("date_at")
    def serialize_fn_dt(self, value: date):
        """Serialise datetime fields to ISO-8601 strings.

        Args:
            value: The date value to serialise.

        Returns:
            ISO-8601 formatted string, or None if value is falsy.
        """
        if value:
            return value.isoformat()

    @field_serializer("site_uid", "battery_soc_config_uid")
    def serialize_fn_uuid(self, value: UUID):
        """Serialise the uid UUID to a plain string.

        Args:
            value: The UUID value to serialise.

        Returns:
            A string representation of the UUID.
        """
        return uuid_serializer(value)


class BatterySOCConfigModel(DBModel):
    site_uid: UUID
    user_uid: UUID
    config_input_str: str
    effective_from: datetime
    effective_to: Optional[datetime]

    @field_serializer("effective_from", "effective_to")
    def serialize_fn_dt(self, value: datetime):
        """Serialise datetime fields to ISO-8601 strings.

        Args:
            value: The date value to serialise.

        Returns:
            ISO-8601 formatted string, or None if value is falsy.
        """
        if value:
            return value.isoformat()

    @field_serializer("site_uid", "user_uid")
    def serialize_fn_uuid(self, value: UUID):
        """Serialise the uid UUID to a plain string.

        Args:
            value: The UUID value to serialise.

        Returns:
            A string representation of the UUID.
        """
        return uuid_serializer(value)
