from datetime import date, time
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlmodel import Date, Field, Index, Relationship, Time, UniqueConstraint

from app.shared.model import MyAbstractSQLModel

if TYPE_CHECKING:
    from app.modules.sites.model import Site
    from app.modules.users.model import User


class SiteMPPTFunctionCheck(MyAbstractSQLModel, table=True):
    """
    MPPT Function check table for sites. Updated by telemetry data from dynamodb
    """

    __tablename__ = "site_mppt_function_check"
    __table_args__ = (
        UniqueConstraint(
            "site_uid",
            "date_at",
            "from_",
            "to",
            "interval_in_minutes",
            name="uq_site_mppt_fn_check",
        ),
        Index("ix_site_mppt_fn_check_site_date", "site_uid", "date_at"),
    )

    site_uid: UUID = Field(foreign_key="sites.uid", nullable=False, index=True)
    user_uid: UUID = Field(foreign_key="users.uid", nullable=False, index=True)
    date_at: date = Field(sa_column_kwargs={"nullable": False}, sa_type=Date)
    from_: time = Field(sa_type=Time)
    to: time = Field(sa_type=Time)
    interval_in_minutes: int = Field(default=30)
    telemetry_reading_str: Optional[str] = Field(default=None)
    mppt_fn_check_table_str: Optional[str] = Field(default=None, description="JSON-serialized object")
    is_completed: bool = Field(default=False, index=True)

    # Relationships
    site: "Site" = Relationship(back_populates="site_mppt_fn_check")
    user: "User" = Relationship(back_populates="site_mppt_fn_check")
