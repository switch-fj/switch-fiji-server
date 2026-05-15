from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.modules.contracts.schema import ContractRespModel
from app.shared.schema import DBModel, TwoDP
from app.utils import uuid_serializer


class InvoiceMeterLabelEnum(StrEnum):
    """Enumeration of standardised labels for invoice meter data records."""

    SITE_METER_DAY = "Site Meter - Day"
    SITE_METER_NIGHT = "Site Meter - Night"
    GEN_METER_DAY = "Generator Meter - Day"
    GEN_METER_NIGHT = "Generator Meter - Night"
    SOLAR_GENRATION = "Solar Generation"
    ESSENTIAL_LOAD_GENRATION = "Essential Load Generation"
    NON_ESSENTIAL_LOAD_GENRATION = "Non Essential Load Generation"
    SELF_CONSUMPTION = "Self Consumption"
    FED_TO_GRID = "Fed to Grid"
    GRID_ENERGY = "Grid Energy"


class InvoiceLineItemEnum(StrEnum):
    """Enumeration of standardised descriptions for invoice line items."""

    ON_SOLAR_ENERGY_SUPPLIED = "On Solar Energy Supplied"
    OFF_SOLAR_ENERGY_SUPPLIED = "Off Solar Energy Supplied"
    FIXED_ASSET_LEASE = "Fixed Asset Lease"
    MONTHLY_MAINTENANCE_FEE = "Monthly Maintenance Fee"
    ESSENTIAL_ENERGY_SUPPLIED = "Essential Energy Supplied"
    NON_ESSENTIAL_ENERGY_SUPPLIED = "Non Essential Energy Supplied"
    GENERATOR_ENERGY_SUPPLIED = "Generator Energy Supplied"


class BaseInvoiceLineItemModel(BaseModel):
    description: str = Field(...)
    energy_kwh: Optional[TwoDP] = Field(default=None)
    tariff_rate: Optional[TwoDP] = Field(default=None)
    tariff_period: Optional[int] = Field(default=None)
    tariff_slot: Optional[str] = Field(default=None)
    amount: TwoDP = Field(...)


class BaseInvoiceMeterDataModel(BaseModel):
    device_uid: Optional[UUID] = Field(default=None)
    label: str = Field(...)
    period_start_reading: TwoDP = Field(...)
    period_end_reading: TwoDP = Field(...)


class CreateInvoiceModel(BaseModel):
    """Request model for creating a new invoice record."""

    period_start_at: datetime = Field(...)
    period_end_at: datetime = Field(...)
    period_start_telemetry_data: str = Field(nullable=False)
    period_end_telemetry_data: str = Field(nullable=False)
    subtotal: TwoDP = Field(default=Decimal("0.00"))
    vat_rate: TwoDP = Field(default=Decimal("0.00"))
    efl_standard_rate_kwh: TwoDP = Field(default=Decimal("0.00"))
    energy_mix: Optional[str] = Field(default=None)


class CreateInvoiceLineItemModel(BaseInvoiceLineItemModel):
    """Request model for creating a single invoice line item."""

    invoice_uid: UUID = Field(...)


class CreateInvoiceMeterDataModel(BaseInvoiceMeterDataModel):
    """Request model for creating an invoice meter data record."""

    invoice_uid: UUID = Field(...)


class CreateInvoiceHistoryModel(BaseModel):
    """Request model for recording an invoice delivery attempt."""

    invoice_uid: UUID = Field(...)
    sent_to: str = Field(...)
    sent_at: datetime = Field(...)
    was_successful: bool = Field(...)
    failure_reason: Optional[str] = Field(default=None)


class CreateInvoiceSnapshotLineItemModel(BaseInvoiceLineItemModel):
    """Request model for creating a single invoice snapshot line item."""

    snapshot_uid: UUID = Field(...)


class CreateInvoiceSnapshotMeterDataModel(BaseInvoiceMeterDataModel):
    """Request model for creating an invoice snapshot meter data record."""

    snapshot_uid: UUID = Field(...)


class InvoiceRespModel(DBModel):
    """Response model for a basic invoice record."""

    invoice_ref: str
    period_start_at: datetime
    period_end_at: datetime
    period_start_telemetry_data: str
    period_end_telemetry_data: str
    subtotal: Decimal
    vat_rate: Decimal
    efl_standard_rate_kwh: Decimal
    vat_amount: Decimal
    total: Decimal
    energy_mix: Optional[str]

    @field_serializer("period_start_at", "period_end_at")
    def serialize_period_dt(self, value: datetime):
        """Serialise billing period datetime fields to ISO-8601 strings.

        Args:
            value: The datetime value to serialise.

        Returns:
            ISO-8601 formatted string, or None if value is falsy.
        """
        if value:
            return value.isoformat()

    @field_serializer("subtotal", "vat_rate", "efl_standard_rate_kwh", "vat_amount", "total")
    def serialize_decimals(self, value: Decimal):
        """Serialise Decimal financial fields to two-decimal-place strings.

        Args:
            value: The Decimal value to serialise.

        Returns:
            A string formatted to two decimal places, or None if value is falsy.
        """
        if value:
            return f"{value:.2f}"


class InvoiceHistoryRespModel(DBModel):
    """Response model for an invoice delivery history record."""

    invoice_uid: UUID
    sent_to: str
    sent_at: datetime
    was_successful: bool
    failure_reason: Optional[str]
    invoice: InvoiceRespModel

    @field_serializer("sent_at")
    def serialize_sent_at_dt(self, value: datetime):
        """Serialise the sent_at datetime to an ISO-8601 string.

        Args:
            value: The datetime value to serialise.

        Returns:
            ISO-8601 formatted string, or None if value is falsy.
        """
        if value:
            return value.isoformat()

    @field_serializer("invoice_uid")
    def serialize_invoice_uuid(self, value: UUID):
        """Serialise the invoice_uid UUID to a plain string.

        Args:
            value: The UUID value to serialise.

        Returns:
            A string representation of the UUID.
        """
        return uuid_serializer(value)


class InvoiceLineItemRespModel(DBModel):
    """Response model for a single invoice line item."""

    invoice_uid: UUID
    description: str
    energy_kwh: Optional[Decimal]
    tariff_rate: Optional[Decimal]
    tariff_period: Optional[int]
    tariff_slot: Optional[str]
    amount: Decimal

    @field_serializer("invoice_uid")
    def serialize_invoice_uuid(self, value: UUID):
        """Serialise the invoice_uid UUID to a plain string.

        Args:
            value: The UUID value to serialise.

        Returns:
            A string representation of the UUID.
        """
        return uuid_serializer(value)

    @field_serializer("amount", "tariff_rate", "energy_kwh")
    def serialize_decimals(self, value: Decimal):
        """Serialise Decimal fields to two-decimal-place strings.

        Args:
            value: The Decimal value to serialise.

        Returns:
            A string formatted to two decimal places, or None if value is falsy.
        """
        if value:
            return f"{value:.2f}"


class InvoiceMeterDataRespModel(DBModel):
    """Response model for an invoice meter data record."""

    invoice_uid: UUID
    device_uid: Optional[UUID]
    label: str
    period_start_reading: Decimal
    period_end_reading: Decimal

    @field_serializer("invoice_uid", "device_uid")
    def serialize_invoice_uuid(self, value: UUID):
        """Serialise UUID fields to plain strings.

        Args:
            value: The UUID value to serialise.

        Returns:
            A string representation of the UUID.
        """
        return uuid_serializer(value)

    @field_serializer("period_start_reading", "period_end_reading")
    def serialize_decimals(self, value: Decimal):
        """Serialise Decimal meter reading fields to two-decimal-place strings.

        Args:
            value: The Decimal value to serialise.

        Returns:
            A string formatted to two decimal places, or None if value is falsy.
        """
        if value:
            return f"{value:.2f}"


class InvoiceDetailedRespModel(InvoiceRespModel):
    """Extended invoice response model including the contract, line items, and meter data."""

    contract: ContractRespModel
    line_items: list[InvoiceLineItemRespModel]
    meter_data: list[InvoiceMeterDataRespModel]


class InvoiceDetailsDict(BaseModel):
    subtotal: Decimal
    vat_rate: Decimal
    efl_standard_rate_kwh: Decimal
    invoice_line_items: list[BaseInvoiceLineItemModel]
    invoice_meter_data: list[BaseInvoiceMeterDataModel]
    energy_mix: str

    model_config = ConfigDict(from_attributes=True)


class InvoiceSnapshotLineItemRespModel(DBModel):
    """Response model for a single invoice snapshot line item."""

    snapshot_uid: UUID
    description: str
    energy_kwh: Optional[Decimal]
    tariff_rate: Optional[Decimal]
    tariff_period: Optional[int]
    tariff_slot: Optional[str]
    amount: Decimal

    @field_serializer("snapshot_uid")
    def serialize_snapshot_uuid(self, value: UUID):
        return uuid_serializer(value)

    @field_serializer("amount", "tariff_rate", "energy_kwh")
    def serialize_decimals(self, value: Decimal):
        if value:
            return f"{value:.2f}"


class InvoiceSnapshotMeterDataRespModel(DBModel):
    """Response model for an invoice snapshot meter data record."""

    snapshot_uid: UUID
    device_uid: Optional[UUID]
    label: str
    period_start_reading: Decimal
    period_end_reading: Decimal

    @field_serializer("snapshot_uid", "device_uid")
    def serialize_uuids(self, value: UUID):
        return uuid_serializer(value)

    @field_serializer("period_start_reading", "period_end_reading")
    def serialize_decimals(self, value: Decimal):
        if value:
            return f"{value:.2f}"


class InvoiceSnapshotRespModel(DBModel):
    """Response model for a live invoice snapshot."""

    period_start_at: datetime
    period_end_at: datetime
    period_start_telemetry_data: str
    period_end_telemetry_data: str
    subtotal: Decimal
    vat_rate: Decimal
    efl_standard_rate_kwh: Decimal
    energy_mix: Optional[str]
    vat_amount: Decimal
    total: Decimal
    snapshotted_at: datetime
    line_items: list[InvoiceSnapshotLineItemRespModel]
    meter_data: list[InvoiceSnapshotMeterDataRespModel]

    @field_serializer("period_start_at", "period_end_at", "snapshotted_at")
    def serialize_period_dt(self, value: datetime):
        if value:
            return value.isoformat()

    @field_serializer("subtotal", "vat_rate", "vat_amount", "total")
    def serialize_decimals(self, value: Decimal):
        if value:
            return f"{value:.2f}"
