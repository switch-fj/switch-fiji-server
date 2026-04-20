from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Optional
from uuid import UUID

from dateutil.relativedelta import relativedelta
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    field_serializer,
    field_validator,
    model_validator,
)

from app.core.exceptions import BadRequest
from app.modules.clients.schema import ClientRespModel
from app.shared.schema import CurrencyEnum, DBModel
from app.utils import uuid_serializer


class ContractTypeEnum(StrEnum):
    PPA = "PPA"
    LEASE = "Lease"


class ContractSystemModeEnum(StrEnum):
    ON_GRID = "On Grid"
    OFF_GRID = "Off Grid"


class ContractDetailsStatus(StrEnum):
    DRAFT = "draft"
    PENDING = "pending"
    ACTIVE = "active"
    EXPIRED = "expired"


class ContractBillingFrequencyEnum(StrEnum):
    WEEKLY = "weekly"
    BI_WEEKLY = "bi-weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    SEMI_ANNUALLY = "semi-annually"
    ANNUALLY = "annually"


class TariffSlotTypeEnum(StrEnum):
    FIXED = "Fixed"
    VARIABLE = "Variable"


class TariffSlotEnum(StrEnum):
    A = "A"
    B = "B"


class TariffSlotModel(BaseModel):
    _start_time: str = PrivateAttr("")
    _end_time: str = PrivateAttr("")

    period_number: int = Field(ge=1, le=4)
    slot: TariffSlotEnum = Field(...)
    slot_type: TariffSlotTypeEnum = Field(...)
    rate: float = Field(...)

    @model_validator(mode="after")
    def validate(self):
        match self.slot:
            case TariffSlotEnum.A:
                self._start_time = "07:30"
                self._end_time = "16:30"
            case TariffSlotEnum.B:
                self._start_time = "16:30"
                self._end_time = "07:30"

        if self.slot_type == TariffSlotTypeEnum.FIXED:
            if not (0 <= self.rate <= 1):
                raise BadRequest(f"Slot {self.slot.value} (FIXED) rate must be between 0 and 1, got {self.rate}")

        elif self.slot_type == TariffSlotTypeEnum.VARIABLE:
            if not (-100 <= self.rate <= 100):
                raise BadRequest(
                    f"Slot {self.slot.value} (VARIABLE) rate must be between -100 and 100, got {self.rate}"
                )

        return self


class CreateContractModel(BaseModel):
    client_uid: UUID = Field(...)
    site_uid: UUID = Field(...)
    contract_type: ContractTypeEnum = Field(...)
    system_mode: ContractSystemModeEnum = Field(...)
    currency: CurrencyEnum = Field(...)

    @model_validator(mode="after")
    def validate_contract(self):
        contract_type = self.contract_type
        system_mode = self.system_mode

        if contract_type == ContractTypeEnum.LEASE and system_mode == ContractSystemModeEnum.OFF_GRID:
            raise BadRequest(f"Contract type of {contract_type} can't have system mode of {system_mode}")

        return self


class CreateContractDetailsModel(BaseModel):
    term_years: int = Field(..., ge=0, le=10, title="Contract term years")
    billing_frequency: ContractBillingFrequencyEnum = Field(...)
    implementation_period: int = Field(...)
    signed_at: datetime = Field(...)
    commissioned_at: datetime = Field(...)
    end_at: datetime = Field(..., title="Contract end date")
    efl_rate: Optional[float] = Field(default=None, ge=0, le=1)

    # system mode (On-grid) specific
    system_size_kwp: Optional[float] = Field(default=None)
    guaranteed_production_kwh_per_kwp: Optional[float] = Field(default=None)
    grid_meter_reading_at_commissioning: Optional[float] = Field(default=None)

    # On Grid Lease specific
    equipment_lease_amount: Optional[Decimal] = Field(default=None)
    maintenance_amount: Optional[Decimal] = Field(default=None)
    total: Optional[Decimal] = Field(default=None)

    # PPA specific
    monthly_baseline_consumption_kwh: Optional[float] = Field(default=None)
    minimum_consumption_monthly_kwh: Optional[float] = Field(default=None)
    minimum_spend: Optional[float] = Field(default=None)
    tariff_periods: Optional[int] = Field(default=None, le=4, ge=2)
    tariffs: Optional[list[TariffSlotModel]] = Field(default=None)
    estimated_utility: Optional[int] = Field(default=None)

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
                raise BadRequest("end_at must be after commissioned_at")

            if self.term_years:
                expected_end = commissioned + relativedelta(years=self.term_years)
                delta_days = abs((end - expected_end).days)
                if delta_days > 1:
                    raise BadRequest(
                        f"end_at ({end.date()}) does not match "
                        f"commissioned_at + {self.term_years} years "
                        f"(expected ~{expected_end.date()})"
                    )

        if signed and commissioned:
            if signed > commissioned:
                raise BadRequest("signed_at must be before or on commissioned_at")

    def _validate_tariffs_align_with_periods(self):
        """
        If tariff_period and tariffs are both provided:
        - Each period must have exactly 2 tariff slots (A and B)
        - So total tariff rows must equal tariff_period × 2
        - Each period number must be represented (1 through tariff_period)
        - Each period must have both slot A and slot B
        """
        if not self.tariff_periods or not self.tariffs:
            return

        expected_count = self.tariff_periods * 2  # A + B per period
        if len(self.tariffs) != expected_count:
            raise BadRequest(
                f"Expected {expected_count} tariffs for {self.tariff_periods} "
                f"period(s) (A + B per period), got {len(self.tariffs)}"
            )

        # Check every period 1..N has exactly one A and one B
        from collections import defaultdict

        period_slots: dict[int, set[str]] = defaultdict(set)

        for tariff in self.tariffs:
            period_slots[tariff.period_number].add(tariff.slot.value)

        for period_num in range(1, self.tariff_periods + 1):
            slots = period_slots.get(period_num, set())
            if slots != {"A", "B"}:
                raise BadRequest(
                    f"Tariff period {period_num} must have both slot A and slot B, got: {slots or 'nothing'}"
                )


class UpdateDetailsRespModel:
    pass


class ContractDetailsRespModel(DBModel):
    contract_uid: UUID
    term_years: Optional[int] = None
    term_months: Optional[int] = None
    months_per_period: Optional[int] = None
    status: ContractDetailsStatus
    billing_frequency: Optional[ContractBillingFrequencyEnum] = None
    implementation_period: Optional[int] = None
    signed_at: Optional[datetime] = None
    commissioned_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    efl_rate: Optional[float] = None

    # On-grid specific
    system_size_kwp: Optional[float] = None
    guaranteed_production_kwh_per_kwp: Optional[float] = None
    grid_meter_reading_at_commissioning: Optional[float] = None

    # On Grid Lease specific
    equipment_lease_amount: Optional[Decimal] = None
    maintenance_amount: Optional[Decimal] = None
    total: Optional[Decimal] = None

    # PPA specific
    monthly_baseline_consumption_kwh: Optional[float] = None
    minimum_consumption_monthly_kwh: Optional[float] = None
    minimum_spend: Optional[float] = None
    tariff_periods: Optional[int] = None
    tariff_slots: Optional[str] = None
    estimated_utility: Optional[int] = None

    @field_serializer("signed_at", "commissioned_at", "end_at")
    def serialize_contract_dt(self, value: datetime):
        if value:
            return value.isoformat()

    @field_serializer("contract_uid")
    def serialize_other_uuid(self, value: UUID):
        return uuid_serializer(value)

    model_config = ConfigDict(from_attributes=True)


class ContractRespModel(DBModel):
    user_uid: UUID
    client_uid: UUID
    site_uid: UUID
    contract_ref: str
    contract_type: ContractTypeEnum
    system_mode: ContractSystemModeEnum
    currency: CurrencyEnum

    @field_serializer("user_uid", "client_uid", "site_uid")
    def serialize_contracts_uuid(self, value: UUID):
        return uuid_serializer(value)

    model_config = ConfigDict(from_attributes=True)


class ContractDetailedRespModel(ContractRespModel):
    client: ClientRespModel
    # site: SiteRespModel
    details: Optional[ContractDetailsRespModel]
