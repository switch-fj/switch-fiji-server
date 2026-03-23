from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlmodel import DateTime, Field, Relationship

from app.modules.contracts.schema import (
    ContractBillingFrequencyEnum,
    ContractDetailsStatus,
    ContractSystemModeEnum,
    ContractTypeEnum,
    TariffSlotEnum,
    TariffTypeEnum,
)
from app.shared.model import MyAbstractSQLModel
from app.shared.schema import CurrencyEnum

if TYPE_CHECKING:
    from app.modules.clients.model import Client
    from app.modules.sites.model import Site


class Contract(MyAbstractSQLModel, table=True):
    __tablename__ = "contracts"

    user_uid: UUID = Field(foreign_key="users.uid", index=True, nullable=False)
    client_uid: UUID = Field(foreign_key="clients.uid", index=True, nullable=False)
    site_uid: UUID = Field(foreign_key="sites.uid", index=True, nullable=False)
    contract_ref: str = Field(nullable=False)
    contract_type: ContractTypeEnum = Field(nullable=False)
    system_mode: ContractSystemModeEnum = Field(nullable=False)
    currency: CurrencyEnum = Field(nullable=False)

    client: "Client" = Relationship(sa_relationship_kwargs={"foreign_keys": "[Contract.client_uid]"})
    site: "Site" = Relationship(sa_relationship_kwargs={"foreign_keys": "[Contract.site_uid]"})
    details: Optional["ContractDetails"] = Relationship(back_populates="contract")


class ContractDetails(MyAbstractSQLModel, table=True):
    __tablename__ = "contract_details"

    contract_uid: UUID = Field(foreign_key="contracts.uid", index=True, nullable=False)
    status: ContractDetailsStatus = Field(default=ContractDetailsStatus.DRAFT.value, sa_type=ContractDetailsStatus)
    # applies to all contract types
    term_years: Optional[int] = Field(nullable=True)
    billing_frequency: Optional[ContractBillingFrequencyEnum] = Field(
        nullable=True, sa_type=ContractBillingFrequencyEnum
    )
    implementation_period: Optional[int] = Field(nullable=True)
    signed_at: Optional[datetime] = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"nullable": True},
    )
    commissioned_at: Optional[datetime] = Field(
        default=None,
        description="""
        Date the system was commissioned.
        This is also the contract start date.
        All tariff periods run sequentially from this date.
        """,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"nullable": True},
    )
    end_at: Optional[datetime] = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"nullable": True},
    )
    monthly_baseline_consumption_kwh: Optional[float] = Field(nullable=True)
    minimum_consumption_monthly_kwh: Optional[float] = Field(nullable=True)
    minimum_spend: Optional[float] = Field(nullable=True)
    # EFL rate (global, entered once — variable tariffs are pegged to this)
    efl_rate: Optional[float] = Field(nullable=True)

    # PPA / On-grid specific
    system_size_kwp: Optional[float] = Field(nullable=True)
    guaranteed_production_kwh_per_kwp: Optional[float] = Field(nullable=True)
    grid_meter_reading_at_commissioning: Optional[float] = Field(nullable=True)

    # On Grid Lease specific
    equipment_lease_amount: Optional[float] = Field(nullable=True)
    maintenance_amount: Optional[float] = Field(nullable=True)

    contract: Optional["Contract"] = Relationship(back_populates="details")
    tariff_periods: list["TariffPeriod"] = Relationship(back_populates="contract_details")


class TariffPeriod(MyAbstractSQLModel, table=True):
    """
    One row per tariff period (max 4 per contract).
    Period number is 1-indexed: 1, 2, 3, 4.
    Duration is in years, always sequential from commissioning date.
    """

    __tablename__ = "tariff_periods"

    contract_details_uid: UUID = Field(foreign_key="contract_details.uid", index=True, nullable=False)
    period_number: int = Field(nullable=False)  # 1, 2, 3, 4
    duration_years: int = Field(nullable=False)  # e.g. 5

    contract_details: Optional["ContractDetails"] = Relationship(back_populates="tariff_periods")
    tariffs: list["Tariff"] = Relationship(back_populates="tariff_period")


class Tariff(MyAbstractSQLModel, table=True):
    """
    One row per tariff slot within a period.
    Each period has two slots: A and B (e.g. Tariff 1/A and Tariff 1/B).
    """

    __tablename__ = "tariffs"

    tariff_period_uid: UUID = Field(foreign_key="tariff_periods.uid", index=True, nullable=False)
    slot: TariffSlotEnum = Field(nullable=False)  # A | B
    tariff_type: TariffTypeEnum = Field(nullable=False)  # Fixed | Variable
    rate: float = Field(...)
    start_time: str = Field(nullable=True)  # "07:30"
    end_time: str = Field(nullable=True)  # "16:30"

    tariff_period: Optional["TariffPeriod"] = Relationship(back_populates="tariffs")
