from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class CreateInvoiceModel(BaseModel):
    period_start_at: datetime = Field(...)
    period_end_at: datetime = Field(...)
    subtotal: Decimal = Field(default=Decimal("0.00"))
    vat_rate: Decimal = Field(default=Decimal("0.00"))
    energy_mix: Optional[str] = Field(default=None)


class CreateInvoiceLineItemModel(BaseModel):
    invoice_uid: UUID = Field(...)
    description: str = Field(...)
    energy_kwh: Optional[Decimal] = Field(default=None)
    tariff_rate: Optional[Decimal] = Field(default=None)
    tariff_period: Optional[int] = Field(default=None)
    tariff_slot: Optional[str] = Field(default=None)
    amount: Decimal = Field(...)


class CreateInvoiceMeterDataModel(BaseModel):
    invoice_uid: UUID = Field(...)
    deviice_uid: Optional[UUID] = Field(default=None)
    label: str = Field(...)
    period_start_reading: Decimal = Field(...)
    period_end_reading: Decimal = Field(...)


class CreateInvoiceHistoryModel(BaseModel):
    invoice_uid: UUID = Field(...)
    sent_to: str = Field(...)
    sent_at: datetime = Field(...)
    was_successful: bool = Field(...)
    failure_reason: Optional[str] = Field(default=None)
