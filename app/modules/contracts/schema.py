from datetime import datetime, timezone
from decimal import Decimal
from enum import IntEnum, StrEnum
from typing import Optional
from uuid import UUID

from dateutil.relativedelta import relativedelta
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)
from typing_extensions import Literal

from app.core.exceptions import BadRequest
from app.modules.clients.schema import ClientRespWithoutSitesCountModel
from app.shared.schema import CurrencyEnum, DBModel
from app.utils import uuid_serializer

type YesNo = Literal["yes", "no"]


class ContractTypeEnum(StrEnum):
    """Enumeration of supported contract billing types."""

    PPA = "PPA"
    LEASE = "Lease"


class ContractSystemModeEnum(StrEnum):
    """Enumeration of solar system grid connection modes."""

    ON_GRID = "On Grid"
    OFF_GRID = "Off Grid"


class ContractDetailsStatus(StrEnum):
    """Enumeration of contract lifecycle statuses."""

    DRAFT = "draft"
    PENDING = "pending"
    ACTIVE = "active"
    EXPIRED = "expired"


class ContractBillingFrequencyEnum(StrEnum):
    """Enumeration of supported billing frequencies for a contract."""

    DAILY = "daily"
    WEEKLY = "weekly"
    BI_WEEKLY = "bi-weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    SEMI_ANNUALLY = "semi-annually"
    ANNUALLY = "annually"


class DayOfWeekEnum(IntEnum):
    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6


class TariffIndexedRuleTypeEnum(StrEnum):
    """Enumeration of supported rule type for indexed periods"""

    EFL_LINKED = "EFL_LINKED"
    FIXED_ANNUAL_ESCALATOR = "FIXED_ANNUAL_ESCALATOR"


class TariffSlotTypeEnum(StrEnum):
    """
    Enumeration indicating whether a tariff rate is fixed or indexed relative to the EFL rate.
    tariff slot is also tariff period
    """

    FIXED = "Fixed"
    VARIABLE = "Variable"


class TariffSlotEnum(StrEnum):
    """Enumeration of the two tariff time slots (A: on-solar and B: off-solar)."""

    A = "A"
    B = "B"


class OnGridNoBatterySlotEnum(StrEnum):
    """Enumeration of tariff slot types for PPA on-grid without battery."""

    UTILITY = "Utility"
    SOLAR = "Solar"


class OnGridNoBatteryTariffSlotModel(BaseModel):
    """Model representing a single tariff slot for PPA on-grid without battery (Utility or Solar)."""

    period_number: int = Field(ge=1, le=4)
    slot: OnGridNoBatterySlotEnum = Field(...)
    slot_type: TariffSlotTypeEnum = Field(...)
    rate: float = Field(...)
    start_time: str = Field(...)
    end_time: str = Field(...)

    @model_validator(mode="after")
    def validate(self):
        self._validate_rate()
        return self

    def _validate_rate(self):
        if self.slot_type == TariffSlotTypeEnum.FIXED:
            if not (0 <= self.rate <= 1):
                raise BadRequest(f"Slot {self.slot.value} (FIXED) rate must be between 0 and 1, got {self.rate}")
        elif self.slot_type == TariffSlotTypeEnum.VARIABLE:
            if not (-100 <= self.rate <= 100):
                raise BadRequest(
                    f"Slot {self.slot.value} (VARIABLE) rate must be between -100 and 100, got {self.rate}"
                )

    @staticmethod
    def _parse_time(field_name: str, value: str) -> datetime.time:
        try:
            return datetime.strptime(value, "%H:%M").time()
        except ValueError:
            raise BadRequest(f"'{field_name}' must be in HH:MM format (00:00–23:59), got '{value}'")


class TariffSlotModel(BaseModel):
    """Model representing a single tariff slot within a PPA contract period."""

    period_number: int = Field(ge=1, le=4)
    slot: TariffSlotEnum = Field(...)
    slot_type: TariffSlotTypeEnum = Field(...)
    rate: float = Field(...)
    start_time: str = Field(...)
    end_time: str = Field(...)
    duration_years: Optional[int] = Field(
        default=None,
        title="Tariff slot duration in years",
    )

    @model_validator(mode="after")
    def validate(self):
        self._validate_rate()
        return self

    def _validate_rate(self):
        if self.slot_type == TariffSlotTypeEnum.FIXED:
            if not (0 <= self.rate <= 1):
                raise BadRequest(f"Slot {self.slot.value} (FIXED) rate must be between 0 and 1, got {self.rate}")
        elif self.slot_type == TariffSlotTypeEnum.VARIABLE:
            if not (-100 <= self.rate <= 100):
                raise BadRequest(
                    f"Slot {self.slot.value} (VARIABLE) rate must be between -100 and 100, got {self.rate}"
                )

    @staticmethod
    def _parse_time(field_name: str, value: str) -> datetime.time:
        try:
            return datetime.strptime(value, "%H:%M").time()
        except ValueError:
            raise BadRequest(f"'{field_name}' must be in HH:MM format (00:00–23:59), got '{value}'")


class CreateContractModel(BaseModel):
    """Request model for creating a new contract."""

    client_uid: UUID = Field(...)
    site_uid: UUID = Field(...)
    contract_type: ContractTypeEnum = Field(...)
    system_mode: ContractSystemModeEnum = Field(...)
    currency: CurrencyEnum = Field(...)
    timezone: str = Field(...)

    @model_validator(mode="after")
    def validate_contract(self):
        """Ensure the contract type and system mode combination is valid.

        Returns:
            The validated CreateContractModel instance.

        Raises:
            BadRequest: If a Lease contract is paired with an Off Grid system mode.
        """
        contract_type = self.contract_type
        system_mode = self.system_mode

        if contract_type == ContractTypeEnum.LEASE and system_mode == ContractSystemModeEnum.OFF_GRID:
            raise BadRequest(f"Contract type of {contract_type} can't have system mode of {system_mode}")

        return self


class CreateContractDetailsModel(BaseModel):
    """Request model for creating or updating contract details."""

    term_years: int = Field(..., ge=0, le=10, title="Contract term years")
    billing_frequency: ContractBillingFrequencyEnum = Field(..., title="Billing Frequency")
    weekly_billing_start_day: Optional[DayOfWeekEnum] = Field(
        default=DayOfWeekEnum.MONDAY, title="Weekly billing start day"
    )
    implementation_period: int = Field(..., title="Contract Implementation")
    signed_at: datetime = Field(..., title="Contract signed at")
    commissioned_at: datetime = Field(..., title="expected commission date")
    end_at: datetime = Field(..., title="expected contract end date")
    actual_commissioned_at: Optional[datetime] = Field(default=None, title="Actual contract commission date")
    actual_end_at: Optional[datetime] = Field(default=None, title="Actual Contract end date")

    # system mode (On-grid) specific
    system_size_kwp: Optional[float] = Field(default=None, title="System size kwp")
    guaranteed_production_kwh_per_kwp: Optional[float] = Field(default=None, title="Guaranteed production kwh per kwp")
    grid_meter_reading_at_commissioning_kwh: Optional[float] = Field(
        default=None, title="Grid meter reading at commissioning KWH"
    )
    grid_meter_reading_at_commissioning_kvar: Optional[float] = Field(
        default=None, title="Grid meter reading at commissioning KVAR"
    )

    # On Grid Lease specific
    equipment_lease_amount: Optional[Decimal] = Field(default=None, title="Equipment lease amount")
    maintenance_amount: Optional[Decimal] = Field(default=None, title="Maintenance amount")
    total: Optional[Decimal] = Field(default=None, title="Total")

    # PPA specific
    monthly_baseline_consumption_kwh: Optional[float] = Field(default=None, title="Monthly baseline consumption kwh")
    minimum_consumption_monthly_kwh: Optional[float] = Field(default=None, title="Minimum consumptions monthly kwh")
    minimum_spend: Optional[float] = Field(default=None, title="Minimum spend")
    tariff_periods: Optional[int] = Field(default=None, le=4, ge=1, title="Tariff periods")

    tariff_indexed_rule_type: Optional[TariffIndexedRuleTypeEnum] = Field(default=None)
    tariffs: Optional[list[TariffSlotModel]] = Field(default=None, title="Tariffs")

    # PPA on-Grid
    with_battery: Optional[YesNo] = Field(default="no", title="PPA on grid battery availability")
    ppa_on_grid_no_battery_tariffs: Optional[list[OnGridNoBatteryTariffSlotModel]] = Field(
        default=None, title="PPA on-grid no-battery tariff slots"
    )
    estimated_utility: Optional[int] = Field(default=None, title="Estimated utility pair")
    grid_meter_offset_pair: Optional[list[tuple[float]]] = Field(default=None, title="Grid meter offset pair")

    @field_validator(
        "signed_at",
        "commissioned_at",
        "end_at",
        "actual_commissioned_at",
        "actual_end_at",
        mode="before",
    )
    @classmethod
    def parse_dates_as_utc(cls, value) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, str):
            value = datetime.fromisoformat(value)
        if isinstance(value, datetime):
            if value.tzinfo is None:
                raise ValueError("Datetime must be timezone-aware. Send UTC ISO strings e.g. '2024-01-01T00:00:00Z'")
            return value.astimezone(timezone.utc)
        return value

    @model_validator(mode="after")
    def validate_contract_details(self) -> "CreateContractDetailsModel":
        """Run date consistency and tariff alignment checks after all fields are populated.

        Returns:
            The validated CreateContractDetailsModel instance.
        """
        self._validate_weekly_start_day()
        self._validate_dates()
        self._validate_tariffs_align_with_periods()
        self._validate_ppa_on_grid_no_battery()
        return self

    def _validate_weekly_start_day(self):
        if self.billing_frequency == ContractBillingFrequencyEnum.WEEKLY:
            if self.weekly_billing_start_day is None:
                raise ValueError("weekly_billing_start_day is required when billing_frequency is WEEKLY.")
            if self.weekly_billing_start_day == DayOfWeekEnum.SUNDAY:
                raise ValueError("weekly_billing_start_day cannot be Sunday — periods always end on Sunday.")
        return self

    def _validate_dates(self):
        """
        Three rules:
        1. end_at must be after commissioned_at
        2. actual_end_at must be after actual_commissioned_at
        2. If term_years, commissioned_at and actual_commissioned_at are all set,
           end_at and actual_end_at must equal commissioned_at + term_years (±1 day tolerance)
           and actual_commissioned_at + term_years
        3. signed_at must be before or equal to commissioned_at or actual_end_date
        """
        commissioned = self.commissioned_at
        end = self.end_at
        actual_commissioned = self.actual_commissioned_at
        actual_end = self.actual_end_at
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

        if actual_commissioned and actual_end:
            if actual_end <= actual_commissioned:
                raise BadRequest("actual_end_at must be after actual_commissioned_at")

            if self.term_years:
                expected_end = actual_commissioned + relativedelta(years=self.term_years)
                delta_days = abs((actual_end - expected_end).days)
                if delta_days > 1:
                    raise BadRequest(
                        f"actual_end_at ({end.date()}) does not match "
                        f"actual_commissioned_at + {self.term_years} years "
                        f"(expected ~{expected_end.date()})"
                    )

        if signed and commissioned:
            if signed > commissioned:
                raise BadRequest("signed_at must be before or on commissioned_at")

        if signed and actual_commissioned:
            if signed > actual_commissioned:
                raise BadRequest("signed_at must be before or on actual_commissioned_at")

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
        seen: dict[int, int] = {}

        for tariff in self.tariffs:
            period_slots[tariff.period_number].add(tariff.slot.value)
            if tariff.duration_years is not None:
                if tariff.period_number not in seen:
                    seen[tariff.period_number] = tariff.duration_years
                elif seen[tariff.period_number] != tariff.duration_years:
                    raise BadRequest(f"Period {tariff.period_number} has conflicting durations in years")
            else:
                if tariff.period_number in seen:
                    raise BadRequest(f"Period {tariff.period_number} has tariffs with missing duration in years")

        if seen:
            if len(seen.keys()) != self.tariff_periods:
                raise BadRequest("Some tariffs have empty duration in years")

            if sum(seen.values()) != self.term_years:
                raise BadRequest("Sum of durations in years must equal term of years.")

        for period_num in range(1, self.tariff_periods + 1):
            slots = period_slots.get(period_num, set())
            if slots != {"A", "B"}:
                raise BadRequest(
                    f"Tariff period {period_num} must have both slot A and slot B, got: {slots or 'nothing'}"
                )

    def _validate_ppa_on_grid_no_battery(self):
        """
        PPA on-grid no battery always has exactly 2 tariff slots:
        one Utility and one Solar — regardless of tariff_periods.
        """
        if self.with_battery == "yes" or not self.ppa_on_grid_no_battery_tariffs:
            return

        slots = self.ppa_on_grid_no_battery_tariffs

        if len(slots) != 2:
            raise BadRequest(
                f"PPA on-grid without battery requires exactly 2 tariff slots (Utility + Solar), got {len(slots)}"
            )

        slot_types = {s.slot.value for s in slots}
        expected = {
            OnGridNoBatterySlotEnum.UTILITY.value,
            OnGridNoBatterySlotEnum.SOLAR.value,
        }
        if slot_types != expected:
            raise BadRequest(f"PPA on-grid without battery must have both Utility and Solar slots, got: {slot_types}")

        for slot in slots:
            if slot.period_number != 1:
                raise BadRequest(
                    f"PPA on-grid without battery tariff slots must have period_number=1, "
                    f"got period_number={slot.period_number} for slot {slot.slot.value}"
                )


class ContractDetailsRespModel(DBModel):
    """Response model for contract details including all financial and scheduling fields."""

    contract_uid: UUID
    term_years: Optional[int] = None
    term_months: Optional[int] = None
    status: ContractDetailsStatus
    billing_frequency: Optional[ContractBillingFrequencyEnum] = None
    implementation_period: Optional[int] = None
    signed_at: Optional[datetime] = None
    commissioned_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    actual_commissioned_at: Optional[datetime] = None
    actual_end_at: Optional[datetime] = None
    efl_standard_rate_kwh: Optional[float] = None

    # On-grid specific
    system_size_kwp: Optional[float] = None
    guaranteed_production_kwh_per_kwp: Optional[float] = None
    grid_meter_reading_at_commissioning_kwh: Optional[float] = None
    grid_meter_reading_at_commissioning_kvar: Optional[float] = None

    # On Grid Lease specific
    equipment_lease_amount: Optional[Decimal] = None
    maintenance_amount: Optional[Decimal] = None
    total: Optional[Decimal] = None

    # PPA specific
    monthly_baseline_consumption_kwh: Optional[float] = None
    minimum_consumption_monthly_kwh: Optional[float] = None
    minimum_spend: Optional[float] = None
    tariff_periods: Optional[int] = None
    tariff_indexed_rule_type: Optional[TariffIndexedRuleTypeEnum] = None
    tariff_slots: Optional[str] = None
    tariff_fixed_to_indexed_at: Optional[datetime] = None

    # ppa (on-grid) specific
    with_battery: Optional[str] = None
    ppa_on_grid_no_battery_tariffs: Optional[str] = None
    estimated_utility: Optional[int] = None
    grid_meter_offset_pair: Optional[str] = None

    @field_serializer(
        "signed_at",
        "commissioned_at",
        "end_at",
        "actual_commissioned_at",
        "actual_end_at",
        "tariff_fixed_to_indexed_at",
    )
    def serialize_contract_dt(self, value: datetime):
        """Serialise contract date fields to ISO-8601 strings.

        Args:
            value: The datetime value to serialise.

        Returns:
            ISO-8601 formatted string, or None if value is falsy.
        """
        if value:
            return value.isoformat()

    @field_serializer("contract_uid")
    def serialize_other_uuid(self, value: UUID):
        """Serialise the contract_uid UUID to a plain string.

        Args:
            value: The UUID value to serialise.

        Returns:
            A string representation of the UUID.
        """
        return uuid_serializer(value)

    @field_serializer("equipment_lease_amount", "maintenance_amount", "total")
    def serialize_decimals(self, value: Decimal):
        """Serialise Decimal financial fields to two-decimal-place strings.

        Args:
            value: The Decimal value to serialise.

        Returns:
            A string formatted to two decimal places, or None if value is falsy.
        """
        if value:
            return f"{value:.2f}"

    model_config = ConfigDict(from_attributes=True)


class ContractRespModel(DBModel):
    """Response model for a contract's core fields."""

    user_uid: UUID
    client_uid: UUID
    site_uid: UUID
    contract_ref: str
    contract_type: ContractTypeEnum
    system_mode: ContractSystemModeEnum
    currency: CurrencyEnum
    timezone: Optional[str]

    @field_serializer("user_uid", "client_uid", "site_uid")
    def serialize_contracts_uuid(self, value: UUID):
        """Serialise contract UUID fields to plain strings.

        Args:
            value: The UUID value to serialise.

        Returns:
            A string representation of the UUID.
        """
        return uuid_serializer(value)

    model_config = ConfigDict(from_attributes=True)


class ContractSiteRespModel(DBModel):
    """Slim site model embedded within contract responses."""

    client_uid: UUID
    site_id: Optional[str]
    site_name: Optional[str]
    gateway_id: Optional[str]
    firmware: Optional[str]


class ContractDetailedRespModel(ContractRespModel):
    """Extended contract response model including the associated client, site, and details."""

    client: ClientRespWithoutSitesCountModel
    site: ContractSiteRespModel
    details: Optional[ContractDetailsRespModel]


class EnergyPortfolioRespModel(BaseModel):
    produced_kwh: float
    baseline_kwh: float
    invoice_total: float
    invoice_count: int
