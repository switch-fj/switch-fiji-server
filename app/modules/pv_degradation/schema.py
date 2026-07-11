from __future__ import annotations

from datetime import date
from typing import Annotated, List
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    field_serializer,
    field_validator,
)

from app.shared.schema import DBModel
from app.utils import uuid_serializer

MONTH_ABBREVIATIONS = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
]


class YearlyDegradation(RootModel[dict[str, float]]):
    """
    One year's worth of monthly kWh degradation values, keyed by month
    abbreviation and ordered starting from the commissioning month
    (not necessarily Jan-Dec).
    """

    @field_validator("root")
    @classmethod
    def validate_months(cls, value: dict[str, float]) -> dict[str, float]:
        if len(value) != 12:
            raise ValueError(f"Expected exactly 12 months, got {len(value)}")

        invalid = set(value.keys()) - set(MONTH_ABBREVIATIONS)
        if invalid:
            raise ValueError(f"Invalid month abbreviation(s): {sorted(invalid)}")

        if len(set(value.keys())) != 12:
            raise ValueError("Duplicate month abbreviations in a single year")

        return value


class PvDegradationSchedule(RootModel[List[YearlyDegradation]]):
    """
    Full multi-year degradation schedule.
    index 0 -> Year 1, index 1 -> Year 2, etc.
    """

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, raw: str) -> "PvDegradationSchedule":
        return cls.model_validate_json(raw)

    @staticmethod
    def build_month_sequence(commissioning_at: date, num_years: int) -> list[str]:
        """Ordered month abbreviations, rolling from the commissioning month."""
        start_index = commissioning_at.month - 1  # 0-based
        total_months = num_years * 12
        return [MONTH_ABBREVIATIONS[(start_index + i) % 12] for i in range(total_months)]

    @classmethod
    def build(
        cls,
        commissioning_at: date,
        monthly_kwh_values: list[float],
    ) -> "PvDegradationSchedule":
        """
        Build a schedule from a flat list of monthly kWh values
        (length must be a multiple of 12), anchored to commissioning_at.
        """
        if len(monthly_kwh_values) % 12 != 0:
            raise ValueError("monthly_kwh_values length must be a multiple of 12")

        num_years = len(monthly_kwh_values) // 12
        months = cls.build_month_sequence(commissioning_at, num_years)

        years: list[YearlyDegradation] = []
        for year_idx in range(num_years):
            year_months = months[year_idx * 12 : (year_idx + 1) * 12]
            year_values = monthly_kwh_values[year_idx * 12 : (year_idx + 1) * 12]
            years.append(YearlyDegradation(root=dict(zip(year_months, year_values))))

        return cls(root=years)


class Year1DegradationInputModel(BaseModel):
    """What the POST endpoint accepts — just 12 raw monthly kWh values,
    in chronological order starting from the commissioning month."""

    model_config = ConfigDict(extra="forbid")

    monthly_kwh_values: Annotated[
        list[float],
        Field(min_length=12, max_length=12),
    ]


class PVDegradationModel(DBModel):
    site_uid: UUID
    user_uid: UUID
    degradation: str

    @field_serializer("site_uid", "user_uid")
    def serialize_pv_degradation_uuid(self, value: UUID):
        """Serialise the uid UUID to a plain string.

        Args:
            value: The UUID value to serialise.

        Returns:
            A string representation of the UUID.
        """
        return uuid_serializer(value)
