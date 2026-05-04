from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.shared.schema import (
    CurrencyEnum,
    DateFormatEnum,
    DBModel,
    TimeFormatEnum,
)
from app.utils import uuid_serializer


class UpdateContractSettingsModel(BaseModel):
    """Request model for partially updating contract settings fields."""

    primary_currency: Optional[CurrencyEnum] = Field(default=None)
    time_format: Optional[TimeFormatEnum] = Field(default=None)
    date_format: Optional[DateFormatEnum] = Field(default=None)

    efl_standard_rate_kwh: Optional[Decimal] = Field(default=None)
    vat_rate: Optional[int] = Field(default=None)

    asset_performance: Optional[bool] = Field(default=None)
    invoice_generated: Optional[bool] = Field(default=None)
    invoice_emailed: Optional[bool] = Field(default=None)


class CreateContractEFLRateModel(BaseModel):
    """Request model for setting a new EFL rate (time-series, never overwritten)."""

    efl_standard_rate_kwh: Optional[Decimal] = Field(default=None)
    effective_from: datetime = Field(...)


class CreateContractVATRateModel(BaseModel):
    """Request model for setting a new VAT rate (time-series, never overwritten)."""

    vat_rate: Optional[int] = Field(default=None)
    effective_from: datetime = Field(...)


class ContractSettingsModel(DBModel):
    """Response model for the current contract settings configuration."""

    primary_currency: CurrencyEnum
    time_format: str
    date_format: str

    efl_standard_rate_kwh: Optional[Decimal]
    vat_rate: Optional[int]

    asset_performance: bool
    invoice_generated: bool
    invoice_emailed: bool

    model_config = ConfigDict(from_attributes=True)


class EFLRateHistoryRespModel(DBModel):
    """Response model for a single EFL rate history entry."""

    contract_settings_uid: UUID
    efl_standard_rate_kwh: Optional[Decimal]
    effective_from: datetime
    effective_to: Optional[datetime]
    created_by_uid: Optional[UUID]

    @field_serializer("contract_settings_uid", "created_by_uid")
    def serialize_rate_uuid(self, value: UUID):
        return uuid_serializer(value)


class VATRateHistoryRespModel(DBModel):
    """Response model for a single VAT rate history entry."""

    contract_settings_uid: UUID
    vat_rate: Optional[int]
    effective_from: datetime
    effective_to: Optional[datetime]
    created_by_uid: Optional[UUID]

    @field_serializer("contract_settings_uid", "created_by_uid")
    def serialize_rate_uuid(self, value: UUID):
        return uuid_serializer(value)
