import json
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlmodel import (
    Column,
    DateTime,
    Field,
    Identity,
    Integer,
    String,
    UniqueConstraint,
)

from app.modules.job_run.schema import JobReferenceType, JobRunStatus, JobType
from app.shared.model import MyAbstractSQLModel


class JobRun(MyAbstractSQLModel, table=True):
    """ORM model representing an on-demand job run."""

    __tablename__ = "job_runs"
    __table_args__ = (
        UniqueConstraint(
            "reference_uid",
            "job_type",
            "reference_type",
            "meta",
            "triggered_by_uid",
            name="uq_job_run_dedup",
        ),
    )

    id: int = Field(
        sa_column=Column(
            Integer,
            Identity(always=True),
            unique=True,
            nullable=False,
        )
    )
    task_id: str = Field(index=True, nullable=False)
    job_type: JobType = Field(nullable=False, sa_type=String)
    reference_type: JobReferenceType = Field(nullable=False, sa_type=String)
    reference_uid: UUID = Field(nullable=False, index=True)
    status: JobRunStatus = Field(default=JobRunStatus.PENDING, sa_type=String)
    triggered_by_uid: Optional[UUID] = Field(default=None, nullable=True)
    meta: Optional[str] = Field(
        default=None,
        nullable=True,
        description="JSON blob for job-specific context.",
    )
    result_uid: Optional[UUID] = Field(default=None, nullable=True)
    error: Optional[str] = Field(default=None, nullable=True)
    started_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))
    completed_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))

    @property
    def meta_parsed(self) -> Optional[dict]:
        if not self.meta:
            return None
        return json.loads(self.meta)
