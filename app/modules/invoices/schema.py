from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_serializer

from app.modules.contracts.schema import ContractRespModel
from app.shared.schema import DBModel, TwoDP
from app.utils import uuid_serializer


class CreateInvoiceModel(BaseModel):
    period_start_at: datetime = Field(...)
    period_end_at: datetime = Field(...)
    subtotal: TwoDP = Field(default=TwoDP("0.00"))
    vat_rate: TwoDP = Field(default=TwoDP("0.00"))
    energy_mix: Optional[str] = Field(default=None)


class CreateInvoiceLineItemModel(BaseModel):
    invoice_uid: UUID = Field(...)
    description: str = Field(...)
    energy_kwh: Optional[TwoDP] = Field(default=None)
    tariff_rate: Optional[TwoDP] = Field(default=None)
    tariff_period: Optional[int] = Field(default=None)
    tariff_slot: Optional[str] = Field(default=None)
    amount: TwoDP = Field(...)


class CreateInvoiceMeterDataModel(BaseModel):
    invoice_uid: UUID = Field(...)
    device_uid: Optional[UUID] = Field(default=None)
    label: str = Field(...)
    period_start_reading: TwoDP = Field(...)
    period_end_reading: TwoDP = Field(...)


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
    energy_kwh: Optional[TwoDP]
    tariff_rate: Optional[TwoDP]
    tariff_period: Optional[int]
    tariff_slot: Optional[str]
    amount: TwoDP

    @field_serializer("invoice_uid")
    def serialize_invoice_uuid(self, value: UUID):
        return uuid_serializer(value)


class InvoiceMeterDataRespModel(DBModel):
    invoice_uid: UUID = Field(...)
    device_uid: Optional[UUID] = Field(default=None)
    label: str = Field(...)
    period_start_reading: TwoDP = Field(...)
    period_end_reading: TwoDP = Field(...)
    vat_amount: TwoDP = Field(...)
    total: TwoDP = Field(...)

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
    subtotal: TwoDP
    vat_rate: TwoDP
    energy_mix: Optional[str]
    contract: ContractRespModel
    line_items: list[InvoiceLineItemRespModel]
    meter_data: list[InvoiceMeterDataRespModel]
    history: list[InvoiceHistoryRespModel]
