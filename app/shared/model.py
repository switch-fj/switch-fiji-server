from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, func
from sqlmodel import Field, SQLModel


class MyAbstractSQLModel(SQLModel):
    __abstract__ = True

    uid: UUID = Field(
        primary_key=True,
        default_factory=uuid4,
        index=True,
        unique=True,
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"nullable": False},
        sa_type=DateTime(timezone=True),
    )

    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={
            "nullable": False,
            "onupdate": func.now(),
            "server_default": func.now(),
        },
        sa_type=DateTime(timezone=True),
    )

    deleted_at: Optional[datetime] = Field(
        default=None,
        sa_column_kwargs={"nullable": True},
        sa_type=DateTime(timezone=True),
    )
