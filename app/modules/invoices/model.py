from datetime import datetime
from uuid import UUID

from sqlmodel import DateTime, Field

from app.shared.model import MyAbstractSQLModel


class Invoice(MyAbstractSQLModel, table=True):
    __tablename__ = "invoices"

    contract_uid: UUID = Field(foreign_key="contracts.uid")
    invoice_ref: str = Field(nullable=False)
    start_at: datetime = Field(
        sa_type=DateTime(timezone=True),
    )
    end_at: datetime = Field(
        sa_type=DateTime(timezone=True),
    )
