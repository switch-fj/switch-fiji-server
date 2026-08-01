from datetime import date, time
from typing import List
from uuid import UUID

from pydantic import BaseModel, ConfigDict, RootModel, field_serializer

from app.shared.schema import DBModel
from app.utils import uuid_serializer


class MPPTFnCheckQuery(BaseModel):
    date: int

    model_config = ConfigDict(extra="forbid")


class SiteMpptFunctionRespModel(DBModel):
    site_uid: UUID
    user_uid: UUID
    date_at: date
    from_: time
    to: time
    interval_in_minutes: int
    mppt_fn_check_table_str: str | None = None

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
    pct: float


class MpptFnCheckItemModel(BaseModel):
    time: str
    ir_wm2: int
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
        telemetry_reading: List[dict],
        mppt_fn_check_item_list: List[MpptKeyFnCheckItemModel],
    ) -> "SiteMpptFunctionCheckTable":
        rows = []

        return cls(root=rows)

    def to_list(self) -> List[MpptFnCheckItemModel]:
        return self.root
