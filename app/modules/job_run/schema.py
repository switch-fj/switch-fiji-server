from datetime import datetime
from enum import StrEnum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

from app.core.exceptions import BadRequest
from app.shared.schema import DBModel
from app.utils import uuid_serializer


class JobRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INVALID = "invalid"


class JobType(StrEnum):
    COMPUTE_INVOICE = "compute_invoice"
    COMPUTE_PV_DEGRADATION = "compute_pv_degradation"
    COMPUTE_STRING_WIRING = "COMPUTE_STRING_WIRING"


class JobReferenceType(StrEnum):
    CONTRACT = "contract"
    PV_DEGRADATION = "pv_degradation"
    STRING_WIRING = "string_wiring"


class JobComputeContractInvoice(BaseModel):
    contract_uid: UUID = Field(...)
    period_start: datetime = Field(...)
    period_end: datetime = Field(...)

    @model_validator(mode="after")
    def validate(self):
        self._validate_date()
        return self

    def _validate_date(self):
        if self.period_end <= self.period_start:
            raise BadRequest("Period end must be after period start")


class JobComputeContractInvoiceResp(BaseModel):
    task_id: str

    model_config = ConfigDict(from_attributes=True)


class JobRunResp(DBModel):
    task_id: str
    job_type: JobType
    reference_type: JobReferenceType
    status: JobRunStatus
    reference_uid: UUID
    triggered_by_uid: Optional[UUID]
    result_uid: Optional[UUID]
    meta: Optional[str]
    error: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    @field_serializer("started_at", "completed_at")
    def serialize_job_run_dt(self, value: datetime):
        """Serialise datetime fields to ISO-8601 strings.

        Args:
            value: The datetime value to serialise.

        Returns:
            ISO-8601 formatted string, or None if value is falsy.
        """
        if value:
            return value.isoformat()

    @field_serializer("triggered_by_uid", "reference_uid", "result_uid")
    def serialize_job_run_uuid(self, value: UUID):
        """Serialise the uid UUID to a plain string.

        Args:
            value: The UUID value to serialise.

        Returns:
            A string representation of the UUID.
        """
        return uuid_serializer(value)
