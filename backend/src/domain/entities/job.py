from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from ..value_objects.document_id import DocumentId


class JobStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Job:
    job_id: str
    document_id: DocumentId
    status: JobStatus = JobStatus.QUEUED
    error: str | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
