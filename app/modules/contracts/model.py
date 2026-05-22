import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from dateutil.relativedelta import relativedelta
from sqlmodel import Column, DateTime, Enum, Field, Integer, Relationship, String

from app.modules.contracts.schema import (
    ContractBillingFrequencyEnum,
    ContractDetailsStatus,
    ContractSystemModeEnum,
    ContractTypeEnum,
    DayOfWeekEnum,
    TariffIndexedRuleTypeEnum,
    TariffSlotModel,
    TariffSlotTypeEnum,
)
from app.shared.model import MyAbstractSQLModel
from app.shared.schema import CurrencyEnum

if TYPE_CHECKING:
    from app.modules.clients.model import Client
    from app.modules.invoices.model import Invoice, InvoiceSnapshot
    from app.modules.sites.model import Site


class Contract(MyAbstractSQLModel, table=True):
    """ORM model representing a billing contract between the platform and a client site."""

    __tablename__ = "contracts"

    user_uid: UUID = Field(foreign_key="users.uid", index=True, nullable=False)
    client_uid: UUID = Field(foreign_key="clients.uid", index=True, nullable=False)
    site_uid: UUID = Field(foreign_key="sites.uid", index=True, nullable=False)
    contract_ref: str = Field(nullable=False)
    contract_type: ContractTypeEnum = Field(sa_type=Enum(ContractTypeEnum), nullable=False)
    system_mode: ContractSystemModeEnum = Field(
        sa_type=Enum(ContractSystemModeEnum),
        nullable=False,
    )
    timezone: str = Field(
        default="Pacific/Fiji",
        sa_column_kwargs={"server_default": "Pacific/Fiji"},
    )
    currency: CurrencyEnum = Field(sa_type=Enum(CurrencyEnum), nullable=False)
    client: "Client" = Relationship(sa_relationship_kwargs={"foreign_keys": "[Contract.client_uid]"})
    site: "Site" = Relationship(sa_relationship_kwargs={"foreign_keys": "[Contract.site_uid]"})
    details: Optional["ContractDetails"] = Relationship(back_populates="contract")
    invoices: list["Invoice"] = Relationship(
        back_populates="contract",
        sa_relationship_kwargs={"foreign_keys": "[Invoice.contract_uid]"},
    )
    snapshots: list["InvoiceSnapshot"] = Relationship(
        back_populates="contract",
        sa_relationship_kwargs={"foreign_keys": "[InvoiceSnapshot.contract_uid]"},
    )


class ContractDetails(MyAbstractSQLModel, table=True):
    """ORM model storing the financial and scheduling details of a contract."""

    __tablename__ = "contract_details"

    contract_uid: UUID = Field(foreign_key="contracts.uid", index=True, nullable=False)

    # applies to all contract types
    term_years: int = Field()
    billing_frequency: ContractBillingFrequencyEnum = Field(sa_type=Enum(ContractBillingFrequencyEnum))
    weekly_billing_start_day: Optional[DayOfWeekEnum] = Field(
        default=DayOfWeekEnum.MONDAY,
        sa_column=Column(Integer, nullable=True),
        description="""
            Required when billing_frequency is WEEKLY.
            The day of the week the billing period starts (e.g. WEDNESDAY = 2).
            The period always ends on Sunday, and the invoice is dispatched the following Monday.
        """,
    )
    implementation_period: int = Field()
    signed_at: datetime = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"nullable": False},
    )
    commissioned_at: datetime = Field(
        description="""
        Date the system is expected to get commissioned.
        This is also the contract expected start date.
        All tariff periods run sequentially from this date.
        """,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"nullable": False},
    )
    end_at: datetime = Field(
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"nullable": False},
    )
    actual_commissioned_at: Optional[datetime] = Field(
        default=None,
        description="""
        Date the contract is actually get's commissioned.
        This is also the contract actual start date.
        All tariff periods run sequentially from this date is it exists.
        """,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"nullable": True},
    )
    actual_end_at: Optional[datetime] = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"nullable": True},
    )

    # EFL rate (global, entered once — variable tariffs are pegged to this)
    efl_standard_rate_kwh: Optional[Decimal] = Field(nullable=False)

    # ppa specific
    tariff_periods: Optional[int] = Field(nullable=True)  # 1, 2, 3, 4
    tariff_indexed_rule_type: Optional[TariffIndexedRuleTypeEnum] = Field(
        sa_column=Column(
            String,
            nullable=True,
            server_default=TariffIndexedRuleTypeEnum.EFL_LINKED.value,
        )
    )
    monthly_baseline_consumption_kwh: Optional[float] = Field(nullable=True)
    minimum_consumption_monthly_kwh: Optional[float] = Field(nullable=True)
    minimum_spend: Optional[float] = Field(nullable=True)

    # ppa (off-grid) specific
    tariff_slots: Optional[str] = Field(
        nullable=True,
        description="""
            This tariff slot applies to ppa off-grid, ppa on-grid no battery.
        """,
    )

    # ppa (on-grid) specific
    with_battery: Optional[str] = Field(nullable=True, default="no")
    ppa_on_grid_no_battery_tariffs: Optional[str] = Field(
        nullable=True,
        description="Tariff slots for PPA on-grid without battery (Utility/Solar structure).",
    )
    estimated_utility: Optional[int] = Field(nullable=True)
    grid_meter_offset_pair: Optional[str] = Field(
        nullable=True,
        description="""
            This constant offset lets the platform estimate the EFL meter reading at any point from our grid meter data.
            Clients use this to cross-check their EFL bills against Switch data.
            Most sites are three-phase — the structure should support up to three paired readings (one per phase),
            not just one. (Storing it as JSON).
            e.g
            [(efl_meter_1, grid_meter_1), (efl_meter_2, grid_meter_2), (efl_meter_3, grid_meter_3),]
        """,
    )

    # system mode (On-grid) specific
    system_size_kwp: Optional[float] = Field(nullable=True)
    guaranteed_production_kwh_per_kwp: Optional[float] = Field(nullable=True)
    grid_meter_reading_at_commissioning_kwh: Optional[float] = Field(nullable=True)
    grid_meter_reading_at_commissioning_kvar: Optional[float] = Field(nullable=True)

    # Lease (on-grid) specific
    equipment_lease_amount: Optional[Decimal] = Field(default=None, nullable=True)
    maintenance_amount: Optional[Decimal] = Field(default=None, nullable=True)
    total: Optional[Decimal] = Field(default=None, nullable=True)

    contract: "Contract" = Relationship(
        back_populates="details",
        sa_relationship_kwargs={"foreign_keys": "[ContractDetails.contract_uid]"},
    )

    @property
    def term_months(self):
        """Convert the contract term from years to months.

        Returns:
            Total contract duration in months, or None if term_years is not set.
        """
        if not self.term_years:
            return None
        return self.term_years * 12

    @property
    def months_per_period(self) -> Optional[int]:
        """Calculate the number of months in each tariff period.

        Returns:
            Months per tariff period, or None if tariff_periods is not set.
        """
        if not self.tariff_periods:
            return None

        return self.term_months // self.tariff_periods

    @property
    def slot_period_durations_in_months(self) -> dict[int, int]:
        """Return an ordered mapping of period_number -> duration_in_months.

        Only populated when *every* slot carries a ``duration_years`` value.
        Slots sharing the same ``period_number`` must have identical
        ``duration_years``; we deduplicate and take the first one encountered.

        Returns:
            ``{}`` when no ``duration_years`` values are present (callers should
            then fall back to ``months_per_period``).
        """
        if not self.tariff_slots:
            return {}

        slots = [TariffSlotModel.model_validate(slot) for slot in json.loads(self.tariff_slots)]

        seen: dict[int, int] = {}
        for slot in slots:
            if slot.duration_years is not None and slot.period_number not in seen:
                seen[slot.period_number] = slot.duration_years

        if not seen:
            return {}

        return {period: years * 12 for period, years in sorted(seen.items())}

    @property
    def active_tariff_slots(self) -> Optional[list[dict]]:
        """Determine the currently active tariff slots.

        Priority:
        1. ``duration_years`` path  — uses ``slot_period_durations_in_months``
        2. Uniform-period fallback  — uses ``months_per_period``

        Returns:
            List of :class:`TariffSlotModel` instances for the current period,
            or ``None`` when required fields are missing.
        """
        if not self.tariff_slots or not self.commissioned_at:
            return None

        tz = ZoneInfo(self.contract.timezone)
        now = datetime.now(tz=tz)
        commissioned_local = (self.actual_commissioned_at or self.commissioned_at).astimezone(tz)

        diff = relativedelta(now, commissioned_local)
        months_elapsed = diff.years * 12 + diff.months

        slots = [TariffSlotModel.model_validate(slot) for slot in json.loads(self.tariff_slots)]

        current_period = None
        period_durations = self.slot_period_durations_in_months
        if period_durations:
            running_months = 0
            for period_number, duration in period_durations.items():
                running_months += duration
                if months_elapsed < running_months:
                    current_period = period_number
                    break
            if current_period is None:
                current_period = max(period_durations.keys())

        elif self.months_per_period:
            current_period = (months_elapsed // self.months_per_period) + 1

        if current_period is None:
            return None

        active = [s for s in slots if s.period_number == current_period]
        return active if active else None

    @property
    def tariff_fixed_to_indexed_at(self) -> Optional[datetime]:
        """Derive the exact datetime the tariff switches from Fixed to Variable/Indexed.

        We walk the *full* period schedule (not just the active period) to find
        the end of the last consecutive Fixed period, which is the switch point.

        Priority:
        1. ``duration_years`` path  — uses ``slot_period_durations_in_months``
        2. Uniform-period fallback  — uses ``months_per_period`` (period 1 = Fixed)

        Returns:
            A UTC :class:`datetime`, or ``None`` when the contract has no
            multi-period tariff or has no battery (on-grid without battery has no
            fixed→indexed transition managed here).
        """
        if not self.tariff_periods:
            return None

        if self.with_battery == "no":
            return None

        tz = ZoneInfo(self.contract.timezone)
        start = (self.actual_commissioned_at or self.commissioned_at).astimezone(tz)
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)

        period_durations = self.slot_period_durations_in_months
        if period_durations and self.tariff_slots:
            slots = [TariffSlotModel.model_validate(slot) for slot in json.loads(self.tariff_slots)]

            representative: dict[int, TariffSlotModel] = {}
            for slot in slots:
                if slot.period_number not in representative:
                    representative[slot.period_number] = slot

            fixed_months = 0
            for period_number, duration in sorted(period_durations.items()):
                slot = representative.get(period_number)
                if slot and slot.slot_type == TariffSlotTypeEnum.FIXED:
                    fixed_months += duration
                else:
                    break

            if fixed_months == 0:
                return None

            switch_date = start + relativedelta(months=fixed_months)
            return switch_date.astimezone(timezone.utc)

        if self.months_per_period:
            switch_date = start + relativedelta(months=self.months_per_period)
            return switch_date.astimezone(timezone.utc)

        return None

    @property
    def status(self) -> ContractDetailsStatus:
        """Derive the current status of the contract based on dates relative to now.

        Returns:
            A ContractDetailsStatus value: DRAFT, PENDING, ACTIVE, or EXPIRED.
        """
        now = datetime.now(timezone.utc)

        if not self.commissioned_at:
            return ContractDetailsStatus.DRAFT

        if now < self.commissioned_at:
            return ContractDetailsStatus.PENDING

        if now > self.end_at:
            return ContractDetailsStatus.EXPIRED

        return ContractDetailsStatus.ACTIVE
