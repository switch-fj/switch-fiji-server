from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlmodel import DateTime, Field, Numeric, Relationship

from app.shared.model import MyAbstractSQLModel

if TYPE_CHECKING:
    from app.modules.sites.model import Site
    from app.modules.users.model import User


class PVSummary(MyAbstractSQLModel, table=True):
    """
    PV Summary for sites. The "Generate PV Summary" modal writes here
    """

    __tablename__ = "pv_summary"

    site_uid: UUID = Field(foreign_key="sites.uid", nullable=False, index=True, unique=True)
    user_uid: UUID = Field(foreign_key="users.uid", nullable=False, index=True)
    commissioned_at: datetime = Field(
        default=None,
        sa_type=DateTime(timezone=True),
    )
    expected_production_kwh: Decimal = Field(...)
    system_size_kwp: Decimal = Field(...)
    year1_degradation: float = Field(Numeric(precision=1, scale=2))
    year2plus_degradation: float = Field(Numeric(precision=1, scale=2))

    # Relationships
    site: "Site" = Relationship(back_populates="pv_summary")
    user: "User" = Relationship(back_populates="pv_summary")
