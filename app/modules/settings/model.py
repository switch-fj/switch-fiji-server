from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlmodel import Field

from app.shared.model import MyAbstractSQLModel
from app.shared.schema import CurrencyEnum, DateFormatEnum, TimeFormatEnum


class ContractSettings(MyAbstractSQLModel, table=True):
    __tablename__ = "contract_settings"

    # general
    vat_rate: Optional[int] = Field(nullable=True, default=None)
    efl_standard_rate_kwh: Optional[Decimal] = Field(nullable=True, default=None)
    primary_currency: str = Field(nullable=False, default=CurrencyEnum.USD.value)

    # date, time format
    time_format: str = Field(nullable=False, default=TimeFormatEnum.TWENTY_FOUR.value)
    date_format: str = Field(nullable=False, default=DateFormatEnum.DMY)

    # notifications
    asset_performance: bool = Field(nullable=False, default=False)
    invoice_generated: bool = Field(nullable=False, default=False)
    invoice_emailed: bool = Field(nullable=False, default=False)

    updated_by_uid: Optional[UUID] = Field(foreign_key="users.uid", nullable=True, default=None)
