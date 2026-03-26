from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlmodel import DateTime, Enum, Field, Relationship

from app.modules.contracts.schema import (
    ContractBillingFrequencyEnum,
    ContractDetailsStatus,
    ContractSystemModeEnum,
    ContractTypeEnum,
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
    contract_type: ContractTypeEnum = Field(sa_type=Enum(ContractTypeEnum), nullable=False)
    system_mode: ContractSystemModeEnum = Field(
        sa_type=Enum(ContractSystemModeEnum),
        nullable=False,
    )
    currency: CurrencyEnum = Field(sa_type=Enum(CurrencyEnum), nullable=False)

    client: "Client" = Relationship(sa_relationship_kwargs={"foreign_keys": "[Contract.client_uid]"})
    site: "Site" = Relationship(sa_relationship_kwargs={"foreign_keys": "[Contract.site_uid]"})
    details: Optional["ContractDetails"] = Relationship(back_populates="contract")


class ContractDetails(MyAbstractSQLModel, table=True):
    __tablename__ = "contract_details"

    contract_uid: UUID = Field(foreign_key="contracts.uid", index=True, nullable=False)
    status: ContractDetailsStatus = Field(
        default=ContractDetailsStatus.DRAFT.value, sa_type=Enum(ContractDetailsStatus)
    )
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
        default=None,
        description="""
        Date the system was commissioned.
        This is also the contract start date.
        All tariff periods run sequentially from this date.
        """,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"nullable": False},
    )
    end_at: datetime = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"nullable": False},
    )

    # EFL rate (global, entered once — variable tariffs are pegged to this)
    efl_rate: Optional[float] = Field(nullable=True)

    # ppa specific
    tariff_periods: Optional[int] = Field(nullable=True)  # 1, 2, 3, 4
    tariff_slots: Optional[str] = Field(nullable=True)
    monthly_baseline_consumption_kwh: Optional[float] = Field(nullable=True)
    minimum_consumption_monthly_kwh: Optional[float] = Field(nullable=True)
    minimum_spend: Optional[float] = Field(nullable=True)

    # ppa (on-grid) specific
    estimated_utility: Optional[int] = Field(nullable=True)

    # system mode (On-grid) specific
    system_size_kwp: Optional[float] = Field(nullable=True)
    guaranteed_production_kwh_per_kwp: Optional[float] = Field(nullable=True)
    grid_meter_reading_at_commissioning: Optional[float] = Field(nullable=True)

    # Lease (off-grid) specific
    equipment_lease_amount: Optional[Decimal] = Field(nullable=True)
    maintenance_amount: Optional[Decimal] = Field(nullable=True)
    total: Optional[Decimal] = Field(nullable=True)

    contract: "Contract" = Relationship(
        back_populates="details",
        sa_relationship_kwargs={"foreign_keys": "[ContractDetails.contract_uid]"},
    )

    @property
    def term_months(self):
        if not self.term_years:
            return None
        return self.term_years * 12

    @property
    def months_per_period(self) -> Optional[int]:
        if not self.tariff_periods:
            return None
        return self.term_months // self.tariff_periods
