from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlmodel import DateTime, Field, Index, Relationship, text

from app.shared.model import MyAbstractSQLModel

if TYPE_CHECKING:
    from app.modules.contracts.model import Contract
    from app.modules.devices.model import Device


class Invoice(MyAbstractSQLModel, table=True):
    __tablename__ = "invoices"

    __table_args__ = (
        Index("ix_invoices_contract_uid", "contract_uid"),
        Index("ix_invoices_created_at", text("created_at DESC")),
        Index("ix_invoices_period_start_at", "period_start_at"),
    )

    contract_uid: UUID = Field(foreign_key="contracts.uid")
    invoice_ref: str = Field(nullable=False, unique=True)

    # billing period
    period_start_at: datetime = Field(
        sa_type=DateTime(timezone=True),
    )
    period_end_at: datetime = Field(
        sa_type=DateTime(timezone=True),
    )

    # financials
    subtotal: Decimal = Field(nullable=False)
    vat_rate: Decimal = Field(nullable=False)

    # energy mix snapshot (computed once at generation time)
    energy_mix: Optional[str] = Field(nullable=True)  # Json Data will be stored here.

    pdf_s3_key: Optional[str] = Field(default=None)

    # relationships
    contract: "Contract" = Relationship(back_populates="invoices")
    line_items: list["InvoiceLineItem"] = Relationship(back_populates="invoice")
    meter_data: list["InvoiceMeterData"] = Relationship(back_populates="invoice")
    history: list["InvoiceHistory"] = Relationship(back_populates="invoice")

    @property
    def vat_amount(self) -> Decimal:
        return self.subtotal * (self.vat_rate / Decimal(100))

    @property
    def total(self) -> Decimal:
        return self.subtotal + self.vat_amount


class InvoiceLineItem(MyAbstractSQLModel, table=True):
    __tablename__ = "invoice_line_items"

    invoice_uid: UUID = Field(foreign_key="invoices.uid", index=True, nullable=False)
    description: str = Field(nullable=False, description="e.g enums of InvoiceLineItemEnum")

    # PPA specific (null for Lease)
    energy_kwh: Optional[Decimal] = Field(nullable=True)
    tariff_rate: Optional[Decimal] = Field(nullable=True)
    tariff_period: Optional[int] = Field(nullable=True, description="active tariff for the specific billing period")
    tariff_slot: Optional[str] = Field(nullable=True)  # A or B

    amount: Decimal = Field(nullable=False)

    # relationships
    invoice: "Invoice" = Relationship(back_populates="line_items")


class InvoiceMeterData(MyAbstractSQLModel, table=True):
    __tablename__ = "invoice_meter_data"

    invoice_uid: UUID = Field(foreign_key="invoices.uid", index=True, nullable=False)
    device_uid: Optional[UUID] = Field(foreign_key="devices.uid", index=True, nullable=True, default=None)

    label: str = Field(nullable=False, description="e.g Enums of InvoiceMeterLabelEnum")
    period_start_reading: Decimal = Field(nullable=False)
    period_end_reading: Decimal = Field(nullable=False)

    # relationships
    invoice: "Invoice" = Relationship(back_populates="meter_data")
    device: Optional["Device"] = Relationship()

    @property
    def usage(self):
        return self.period_end_reading - self.period_start_reading


class InvoiceHistory(MyAbstractSQLModel, table=True):
    __tablename__ = "invoice_history"

    invoice_uid: UUID = Field(foreign_key="invoices.uid", index=True, nullable=False)

    sent_to: str = Field(nullable=False)
    sent_at: datetime = Field(nullable=False)
    was_successful: bool = Field(default=False)
    failure_reason: Optional[str] = Field(nullable=True)

    # relationships
    invoice: "Invoice" = Relationship(back_populates="history")
