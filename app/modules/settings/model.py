from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlmodel import DateTime, Field, Relationship

from app.shared.model import MyAbstractSQLModel
from app.shared.schema import CurrencyEnum, DateFormatEnum, TimeFormatEnum


class ContractSettingsRateHistory(MyAbstractSQLModel, table=True):
    """Tracks historical changes to EFL rate and VAT rate."""

    __tablename__ = "contract_settings_rate_history"

    contract_settings_uid: UUID = Field(foreign_key="contract_settings.uid", nullable=False)
    efl_standard_rate_kwh: Optional[Decimal] = Field(nullable=True, default=None)
    vat_rate: Optional[int] = Field(nullable=True, default=None)
    effective_from: datetime = Field(
        nullable=False,
        sa_type=DateTime(timezone=True),
    )
    effective_to: Optional[datetime] = Field(
        nullable=True,
        default=None,
        sa_column_kwargs={"nullable": True},
        sa_type=DateTime(timezone=True),
    )
    created_by_uid: Optional[UUID] = Field(foreign_key="users.uid", nullable=True, default=None)

    settings: "ContractSettings" = Relationship(
        back_populates="rate_history",
        sa_relationship_kwargs={"foreign_keys": "[ContractSettingsRateHistory.contract_settings_uid]"},
    )


class ContractSettings(MyAbstractSQLModel, table=True):
    """ORM model representing global configuration settings for contract management."""

    __tablename__ = "contract_settings"

    # general
    primary_currency: str = Field(nullable=False, default=CurrencyEnum.USD.value)

    # date, time format
    time_format: str = Field(nullable=False, default=TimeFormatEnum.TWENTY_FOUR.value)
    date_format: str = Field(nullable=False, default=DateFormatEnum.DMY)

    # notifications
    asset_performance: bool = Field(nullable=False, default=False)
    invoice_generated: bool = Field(nullable=False, default=False)
    invoice_emailed: bool = Field(nullable=False, default=False)

    updated_by_uid: Optional[UUID] = Field(foreign_key="users.uid", nullable=True, default=None)

    # Relationships
    rate_history: Optional[list["ContractSettingsRateHistory"]] = Relationship(back_populates="settings")

    @property
    def efl_standard_rate_kwh(self) -> Decimal | None:
        """Return the active EFL rate or None if no active rate exists."""
        active = next((r for r in self.rate_history if r.effective_to is None), None)
        return active.efl_standard_rate_kwh if active else None

    @property
    def vat_rate(self) -> int | None:
        """Return the active VAT rate or None if no active rate exists."""
        active = next((r for r in self.rate_history if r.effective_to is None), None)
        return active.vat_rate if active else None
