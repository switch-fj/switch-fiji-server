from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from app.shared.schema import CurrencyEnum, DBModel


class UpdateContractSettingsModel(BaseModel):
    vat_rate: Optional[int] = Field(default=None)
    efl_standard_rate: Optional[Decimal] = Field(default=None)
    primary_currency: Optional[CurrencyEnum] = Field(default=None)

    time_format: Optional[str] = Field(default=None)
    date_format: Optional[str] = Field(default=None)

    asset_perfomance: Optional[bool] = Field(default=None)
    invoice_generated: Optional[bool] = Field(default=None)
    invoice_emailed: Optional[bool] = Field(default=None)


class ContractSettingsModel(DBModel):
    vat_rate: Optional[int]
    efl_standard_rate: Optional[Decimal]
    primary_currency: Optional[CurrencyEnum]

    time_format: Optional[str]
    date_format: Optional[str]

    asset_perfomance: Optional[bool]
    invoice_generated: Optional[bool]
    invoice_emailed: Optional[bool]
