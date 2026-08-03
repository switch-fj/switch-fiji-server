from datetime import date, time
from typing import List, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, RootModel, field_serializer

from app.modules.string_wiring.schema import MPPTExpectedCurrentModel
from app.shared.schema import DBModel
from app.utils import uuid_serializer


class MPPTFnCheckQuery(BaseModel):
    date_at: int

    model_config = ConfigDict(extra="forbid")


class SiteMpptFunctionRespModel(DBModel):
    site_uid: UUID
    user_uid: UUID
    date_at: date
    from_: time
    to: time
    interval_in_minutes: int
    telemetry_reading_str: str | None = None
    mppt_fn_check_table_str: str | None = None
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

    @field_serializer("site_uid", "user_uid")
    def serialize_fn_uuid(self, value: UUID):
        """Serialise the uid UUID to a plain string.

        Args:
            value: The UUID value to serialise.

        Returns:
            A string representation of the UUID.
        """
        return uuid_serializer(value)


class MpptKeyFnCheckItemModel(BaseModel):
    mppt_key: str
    pvn_ip: float
    pct: float


class MpptFnCheckItemModel(BaseModel):
    time_at: time
    ir_w_per_m2: int
    irradiance_source: Literal["measured", "assumed"]
    mppt_keys: List[MpptKeyFnCheckItemModel]


class SiteMpptFunctionCheckTable(RootModel[List[MpptFnCheckItemModel]]):
    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, raw: str) -> "SiteMpptFunctionCheckTable":
        return cls.model_validate_json(raw)

    @classmethod
    def build(
        cls,
        telemetry_reading: List[dict | None],
        assumed_ir_wm2: dict[time, int],
        expected_mppt_table: List[MPPTExpectedCurrentModel],
    ) -> "SiteMpptFunctionCheckTable":
        rows = []
        expected_lookup = {(item.mppt_key, item.ir_wm2): item.expected_ip for item in expected_mppt_table}

        for time_at, assumed_ir, reading in zip(assumed_ir_wm2.keys(), assumed_ir_wm2.values(), telemetry_reading):
            resolved_ir = assumed_ir
            irradiance_source = "assumed"
            mppt_keys: List[MpptKeyFnCheckItemModel] = []

            if reading:
                irradiance_meters = reading.get("irradiance_meters", [])
                if irradiance_meters:
                    measured = irradiance_meters[0].get("irradiance_w_per_m2")
                    if measured:
                        resolved_ir = measured
                        irradiance_source = "measured"

                for inverter in reading.get("inverters", []):
                    slave_id = inverter.get("slave_id")
                    if slave_id is None:
                        continue
                    for n in range(1, 5):  # pv1_i..pv4_i
                        pvn_ip = inverter.get(f"pv{n}_i")
                        if pvn_ip is None:
                            continue
                        mppt_key = f"{slave_id}.{n}"
                        expected_ip = expected_lookup.get((mppt_key, resolved_ir))
                        pct = float(round((float(pvn_ip) / float(expected_ip)) * 100, 2)) if expected_ip else 0.0
                        mppt_keys.append(MpptKeyFnCheckItemModel(mppt_key=mppt_key, pct=pct, pvn_ip=float(pvn_ip)))

            rows.append(
                MpptFnCheckItemModel(
                    time_at=time_at,
                    ir_w_per_m2=resolved_ir,
                    irradiance_source=irradiance_source,
                    mppt_keys=mppt_keys,
                )
            )

        return cls(root=rows)

    def to_list(self) -> List[MpptFnCheckItemModel]:
        return self.root
