from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.shared.schema import CurrencyEnum, DateFormatEnum, TimeFormatEnum


class UpdateContractSettingsModel(BaseModel):
    vat_rate: Optional[int] = Field(default=None)
    efl_standard_rate_kwh: Optional[Decimal] = Field(default=None)
    primary_currency: Optional[CurrencyEnum] = Field(default=None)

    time_format: Optional[TimeFormatEnum] = Field(default=None)
    date_format: Optional[DateFormatEnum] = Field(default=None)

    asset_performance: Optional[bool] = Field(default=None)
    invoice_generated: Optional[bool] = Field(default=None)
    invoice_emailed: Optional[bool] = Field(default=None)


class ContractSettingsModel(BaseModel):
    vat_rate: int
    efl_standard_rate_kwh: Decimal
    primary_currency: CurrencyEnum

    time_format: str
    date_format: str

    asset_performance: bool
    invoice_generated: bool
    invoice_emailed: bool

    @field_serializer("efl_standard_rate_kwh")
    def serialize_decimals(self, value: Decimal):
        if value:
            return f"{value:.2f}"

    model_config = ConfigDict(from_attributes=True)
