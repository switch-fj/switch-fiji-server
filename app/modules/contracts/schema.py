from datetime import datetime, timezone
from enum import IntEnum, StrEnum
from typing import Optional
from uuid import UUID

from dateutil.relativedelta import relativedelta
from pydantic import BaseModel, Field, field_validator, model_validator

from app.shared.schema import CurrencyEnum


class ContractTypeEnum(StrEnum):
    PPA = "PPA"
    LEASE = "Lease"


class ContractSystemModeEnum(StrEnum):
    ON_GRID = "On Grid"
    OFF_GRID = "Off Grid"


class ContractDetailsStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    EXPIRED = "expired"


class ContractBillingFrequencyEnum(IntEnum):
    WEEKLY = "weekly"
    BI_WEEKLY = "bi-weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    SEMI_ANNUALLY = "semi-annually"
    ANNUALLY = "annually"


class TariffTypeEnum(StrEnum):
    FIXED = "Fixed"
    VARIABLE = "Variable"


class TariffSlotEnum(StrEnum):
    A = "A"
    B = "B"


class Tariff(BaseModel):
    period_number: int = Field(ge=1, le=4)
    slot: TariffSlotEnum = Field(...)
    tariff_type: TariffTypeEnum = Field(...)
    start_time: str = Field(...)
    end_time: str = Field(...)

    @field_validator("start_time", "end_time", mode="before")
    @classmethod
    def validate_time_format(cls, value) -> Optional[str]:
        if value is None:
            return None
        try:
            datetime.strptime(value, "%H:%M")
        except ValueError:
            raise ValueError(f"Time must be in HH:MM format, got '{value}'")
        return value


class CreateContractModel(BaseModel):
    client_uid: UUID = Field(...)
    site_uid: UUID = Field(...)
    contract_type: ContractTypeEnum = Field(...)
    system_mode: ContractSystemModeEnum = Field(...)
    currency: CurrencyEnum = Field(...)


class CreateContractDetailsModel(BaseModel):
    status: ContractDetailsStatus = Field(default=ContractDetailsStatus.DRAFT.value)
    term_years: Optional[int] = Field(default=None)
    billing_frequency: Optional[ContractBillingFrequencyEnum] = Field(default=None)
    implementation_period: Optional[int] = Field(default=None)
    signed_at: Optional[datetime] = Field(default=None)
    commissioned_at: Optional[datetime] = Field(default=None)
    end_at: Optional[datetime] = Field(default=None)
    monthly_baseline_consumption_kwh: Optional[float] = Field(default=None)
    minimum_consumption_monthly_kwh: Optional[float] = Field(default=None)
    minimum_spend: Optional[float] = Field(default=None)
    efl_rate: Optional[float] = Field(default=None)
    tariff_period: Optional[int] = Field(default=None, max=4, min=2)
    tariffs: Optional[list[Tariff]] = Field(...)

    # PPA / On-grid specific
    system_size_kwp: Optional[float] = Field(default=None)
    guaranteed_production_kwh_per_kwp: Optional[float] = Field(default=None)
    grid_meter_reading_at_commissioning: Optional[float] = Field(default=None)

    # On Grid Lease specific
    equipment_lease_amount: Optional[float] = Field(default=None)
    maintenance_amount: Optional[float] = Field(default=None)

    @field_validator("signed_at", "commissioned_at", "end_at", mode="before")
    @classmethod
    def parse_dates_as_utc(cls, value) -> Optional[datetime]:
        """Ensure all datetimes are timezone-aware UTC."""
        if value is None:
            return None
        if isinstance(value, str):
            value = datetime.fromisoformat(value)
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    @model_validator(mode="after")
    def validate_contract_dates_and_tariffs(self) -> "CreateContractDetailsModel":
        self._validate_dates()
        self._validate_tariffs_align_with_periods()
        return self

    def _validate_dates(self):
        """
        Three rules:
        1. end_at must be after commissioned_at
        2. If term_years and commissioned_at are both set,
           end_at must equal commissioned_at + term_years (±1 day tolerance)
        3. signed_at must be before or equal to commissioned_at
        """
        commissioned = self.commissioned_at
        end = self.end_at
        signed = self.signed_at

        if commissioned and end:
            if end <= commissioned:
                raise ValueError("end_at must be after commissioned_at")

            if self.term_years:
                expected_end = commissioned + relativedelta(years=self.term_years)
                delta_days = abs((end - expected_end).days)
                if delta_days > 1:
                    raise ValueError(
                        f"end_at ({end.date()}) does not match "
                        f"commissioned_at + {self.term_years} years "
                        f"(expected ~{expected_end.date()})"
                    )

        if signed and commissioned:
            if signed > commissioned:
                raise ValueError("signed_at must be before or on commissioned_at")

    def _validate_tariffs_align_with_periods(self):
        """
        If tariff_period and tariffs are both provided:
        - Each period must have exactly 2 tariff slots (A and B)
        - So total tariff rows must equal tariff_period × 2
        - Each period number must be represented (1 through tariff_period)
        - Each period must have both slot A and slot B
        """
        if not self.tariff_period or not self.tariffs:
            return

        expected_count = self.tariff_period * 2  # A + B per period
        if len(self.tariffs) != expected_count:
            raise ValueError(
                f"Expected {expected_count} tariffs for {self.tariff_period} "
                f"period(s) (A + B per period), got {len(self.tariffs)}"
            )

        # Check every period 1..N has exactly one A and one B
        from collections import defaultdict

        period_slots: dict[int, set[str]] = defaultdict(set)

        for tariff in self.tariffs:
            period_slots[tariff.period_number].add(tariff.slot.value)

        for period_num in range(1, self.tariff_period + 1):
            slots = period_slots.get(period_num, set())
            if slots != {"A", "B"}:
                raise ValueError(
                    f"Tariff period {period_num} must have both slot A and slot B, got: {slots or 'nothing'}"
                )
