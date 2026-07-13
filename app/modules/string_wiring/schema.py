import json
from typing import List, Optional
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    computed_field,
    field_serializer,
)

from app.shared.schema import DBModel
from app.utils import uuid_serializer


class StringsInputItemModel(BaseModel):
    inverter: int = Field(..., title="inveter slave id from devices table")
    mppt: int = Field(..., title="mppt value")
    string_id: int = Field(..., title="string number")
    panel_ref_uid: UUID = Field(..., title="Panel reference uid")
    panel_qty: int = Field(..., title="quantity of panels")


class StringsWiringInputModel(BaseModel):
    strings: List[StringsInputItemModel]

    def to_json(self) -> str:
        return json.dumps(self.strings)


class StringSchematicsModel(BaseModel):
    inverter: int
    mppt: int
    string_id: int
    panel_ref_uid: UUID
    panel_watt: float
    panel_qty: int
    panel_voc: float
    panel_vmp: float
    ip: float

    @computed_field
    @property
    def string_identity(self) -> str:
        return f"{self.inverter}.{self.mppt}.{self.string_id}"

    @computed_field
    @property
    def watt(self) -> float:
        value = self.panel_watt * self.panel_qty

        return float(f"{value:.2f}")

    @computed_field
    @property
    def voc(self) -> float:
        value = self.panel_voc * self.panel_qty

        return float(f"{value:.2f}")

    @computed_field
    @property
    def vmp(self) -> float:
        value = self.panel_vmp * self.panel_qty

        return float(f"{value:.2f}")

    @computed_field
    @property
    def mppt_key(self) -> str:
        return f"{self.inverter}.{self.mppt}"


class MPPTItemModel(BaseModel):
    inverter: int
    mppt: int
    mppt_key: str
    mppt_p_kw: float
    mppt_ip: float
    mppt_vp: float


class MPPTFunctionTable(RootModel[List[MPPTItemModel]]):
    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, raw: str) -> "MPPTFunctionTable":
        return cls.model_validate_json(raw)

    @classmethod
    def build(cls, strings: List[StringSchematicsModel]) -> "MPPTFunctionTable":
        acc: dict[str, dict] = {}

        for s in strings:
            bucket = acc.setdefault(
                s.mppt_key,
                {
                    "inverter": s.inverter,
                    "mppt": s.mppt,
                    "mppt_key": s.mppt_key,
                    "watt_total": 0.0,
                    "ip_total": 0.0,
                    "vmp_values": set(),
                },
            )
            bucket["watt_total"] += s.watt
            bucket["ip_total"] += s.ip
            bucket["vmp_values"].add(round(s.vmp, 2))

        table = []
        for bucket in acc.values():
            if len(bucket["vmp_values"]) > 1:
                raise ValueError(
                    f"Vmp mismatch on MPPT {bucket['mppt_key']}: "
                    f"{bucket['vmp_values']} — parallel strings must match voltage"
                )
            table.append(
                MPPTItemModel(
                    inverter=bucket["inverter"],
                    mppt=bucket["mppt"],
                    mppt_key=bucket["mppt_key"],
                    mppt_p_kw=round(bucket["watt_total"] / 1000, 2),
                    mppt_ip=round(bucket["ip_total"], 2),
                    mppt_vp=bucket["vmp_values"].pop(),
                )
            )

        return cls(root=table)


IR_W_M = [1000, 950, 900, 850, 800, 750, 700, 650, 600]


class MPPTExpectedCurrentModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ir_wm2: int
    mppt_key: str
    expected_ip: float


class ExpectedMPPT_ATable(RootModel[List[MPPTExpectedCurrentModel]]):
    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, raw: str) -> "ExpectedMPPT_ATable":
        return cls.model_validate_json(raw)

    @classmethod
    def build(cls, mppt_table: List[MPPTItemModel]) -> "ExpectedMPPT_ATable":
        rows = [
            MPPTExpectedCurrentModel(
                ir_wm2=ir_value,
                mppt_key=mppt.mppt_key,
                expected_ip=round((ir_value / 1000) * mppt.mppt_ip, 2),
            )
            for ir_value in IR_W_M
            for mppt in mppt_table
        ]
        return cls(root=rows)


class StringWiringRespModel(DBModel):
    site_uid: UUID
    user_uid: UUID
    string_input: str
    wring_schematics: Optional[str]
    mppt_fn_table: Optional[str]
    expected_mppt_a_table: Optional[str]

    @field_serializer("site_uid", "user_uid")
    def serialize_uuid(self, value: UUID):
        """Serialise the uid UUID to a plain string.

        Args:
            value: The UUID value to serialise.

        Returns:
            A string representation of the UUID.
        """
        return uuid_serializer(value)
