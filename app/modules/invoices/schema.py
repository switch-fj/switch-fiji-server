from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_serializer

from app.modules.contracts.schema import ContractRespModel
from app.shared.schema import DBModel, FourDP
from app.utils import uuid_serializer


class InvoiceMeterLabelEnum(StrEnum):
    SITE_METER_1_DAY = "Site Meter 1 - Day"
    SITE_METER_1_NIGHT = "Site Meter 1 - Night"
    GEN_METER_1_DAY = "Generator Meter 1 - Day"
    GEN_METER_1_NIGHT = "Generator Meter 1 - Night"
    SOLAR_GENRATION = "Solar Generation"
    SELF_CONSUMPTION = "Self Consumption"
    FED_TO_GRID = "Fed to Grid"
    GRID_ENERGY = "Grid Energy"


class InvoiceLineItemEnum(StrEnum):
    ON_SOLAR_ENERGY_SUPPLIED = "On Solar Energy Supplied"
    OFF_SOLAR_ENERGY_SUPPLIED = "Off Solar Energy Supplied"
    FIXED_ASSET_LEASE = "Fixed Asset Lease"
    MONTHLY_MAINTENANCE_FEE = "Monthly Maintenance Fee"


class CreateInvoiceModel(BaseModel):
    period_start_at: datetime = Field(...)
    period_end_at: datetime = Field(...)
    subtotal: FourDP = Field(default=Decimal("0.0000"))
    vat_rate: FourDP = Field(default=Decimal("0.0000"))
    energy_mix: Optional[str] = Field(default=None)


class CreateInvoiceLineItemModel(BaseModel):
    invoice_uid: UUID = Field(...)
    description: str = Field(...)
    energy_kwh: Optional[FourDP] = Field(default=None)
    tariff_rate: Optional[FourDP] = Field(default=None)
    tariff_period: Optional[int] = Field(default=None)
    tariff_slot: Optional[str] = Field(default=None)
    amount: FourDP = Field(...)


class CreateInvoiceMeterDataModel(BaseModel):
    invoice_uid: UUID = Field(...)
    device_uid: Optional[UUID] = Field(default=None)
    label: str = Field(...)
    period_start_reading: FourDP = Field(...)
    period_end_reading: FourDP = Field(...)


class CreateInvoiceHistoryModel(BaseModel):
    invoice_uid: UUID = Field(...)
    sent_to: str = Field(...)
    sent_at: datetime = Field(...)
    was_successful: bool = Field(...)
    failure_reason: Optional[str] = Field(default=None)


class InvoiceHistoryRespModel(DBModel):
    invoice_uid: UUID
    sent_to: str
    sent_at: datetime
    was_successful: bool
    failure_reason: Optional[str]

    @field_serializer("sent_at")
    def serialize_sent_at_dt(self, value: datetime):
        if value:
            return value.isoformat()

    @field_serializer("invoice_uid")
    def serialize_invoice_uuid(self, value: UUID):
        return uuid_serializer(value)


class InvoiceLineItemRespModel(DBModel):
    invoice_uid: UUID
    description: str
    energy_kwh: Optional[FourDP]
    tariff_rate: Optional[FourDP]
    tariff_period: Optional[int]
    tariff_slot: Optional[str]
    amount: FourDP

    @field_serializer("invoice_uid")
    def serialize_invoice_uuid(self, value: UUID):
        return uuid_serializer(value)


class InvoiceMeterDataRespModel(DBModel):
    invoice_uid: UUID = Field(...)
    device_uid: Optional[UUID] = Field(default=None)
    label: str = Field(...)
    period_start_reading: FourDP = Field(...)
    period_end_reading: FourDP = Field(...)
    vat_amount: FourDP = Field(...)
    total: FourDP = Field(...)

    @field_serializer("invoice_uid", "device_uid")
    def serialize_invoice_uuid(self, value: UUID):
        return uuid_serializer(value)

    @field_serializer("period_start_reading", "period_end_reading")
    def serialize_period_dt(self, value: datetime):
        if value:
            return value.isoformat()


class InvoiceRespModel(DBModel):
    invoice_ref: str
    period_start_at: datetime = Field(...)
    period_end_at: datetime = Field(...)
    subtotal: FourDP
    vat_rate: FourDP
    energy_mix: Optional[str]
    contract: ContractRespModel
    line_items: list[InvoiceLineItemRespModel]
    meter_data: list[InvoiceMeterDataRespModel]
    history: list[InvoiceHistoryRespModel]
