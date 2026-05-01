import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from dateutil.relativedelta import relativedelta
from sqlmodel import Column, DateTime, Enum, Field, Relationship, String

from app.modules.contracts.schema import (
    ContractBillingFrequencyEnum,
    ContractDetailsStatus,
    ContractSystemModeEnum,
    ContractTypeEnum,
    TariffIndexedRuleTypeEnum,
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
    tariff_slots: Optional[str] = Field(nullable=True)
    tariff_indexed_rule_type: TariffIndexedRuleTypeEnum = Field(
        sa_column=Column(
            String,
            nullable=False,
            server_default=TariffIndexedRuleTypeEnum.EFL_LINKED.value,
        )
    )
    monthly_baseline_consumption_kwh: Optional[float] = Field(nullable=True)
    minimum_consumption_monthly_kwh: Optional[float] = Field(nullable=True)
    minimum_spend: Optional[float] = Field(nullable=True)

    # ppa (on-grid) specific
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
    grid_meter_reading_at_commissioning: Optional[float] = Field(nullable=True)

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
    def active_tariff_slots(self) -> Optional[list[dict]]:
        """Determine the currently active tariff slots based on the elapsed contract time.

        Returns:
            A list of tariff slot dicts for the current period, or None if the required fields are missing.
        """
        if not self.tariff_slots or not self.commissioned_at or not self.months_per_period:
            return None

        tz = ZoneInfo(self.contract.timezone)

        now = datetime.now(tz=tz)
        commissioned_local = (self.actual_commissioned_at or self.commissioned_at).astimezone(tz)

        diff = relativedelta(now, commissioned_local)
        months_elapsed = diff.years * 12 + diff.months
        current_period = (months_elapsed // self.months_per_period) + 1

        slots = json.loads(self.tariff_slots)
        active = [s for s in slots if s["period_number"] == current_period]
        return active if active else None

    @property
    def tariff_fixed_to_indexed_at(self) -> Optional[datetime]:
        """Derive the exact date the tariff switched from fixed to indexed

        Returns:
            A datetime value.
        """

        if not self.tariff_periods or not self.months_per_period:
            return None

        tz = ZoneInfo(self.contract.timezone)
        start = (self.actual_commissioned_at or self.commissioned_at).astimezone(tz)
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        switch_date = start + relativedelta(months=self.months_per_period)

        return switch_date.astimezone(timezone.utc)

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
