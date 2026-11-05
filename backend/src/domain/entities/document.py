from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from ..exceptions.ingestion_error import IngestionError
from ..value_objects.document_id import DocumentId


class DocumentStatus(StrEnum):
    QUEUED = "queued"
    PARSING = "parsing"
    EMBEDDING = "embedding"
    INDEXED = "indexed"
    FAILED = "failed"


@dataclass
class Document:
    id: DocumentId
    name: str
    file_type: str
    checksum: str
    access_tags: list[str] = field(default_factory=list)
    status: DocumentStatus = DocumentStatus.QUEUED
    page_count: int = 0
    error_message: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def mark_parsing(self) -> None:
        if self.status != DocumentStatus.QUEUED:
            raise IngestionError(f"Cannot parse document in status {self.status}")
        self.status = DocumentStatus.PARSING

    def mark_embedding(self, page_count: int) -> None:
        if self.status != DocumentStatus.PARSING:
            raise IngestionError(f"Cannot embed document in status {self.status}")
        self.page_count = page_count
        self.status = DocumentStatus.EMBEDDING

    def mark_indexed(self) -> None:
        if self.status != DocumentStatus.EMBEDDING:
            raise IngestionError(f"Cannot index document in status {self.status}")
        self.status = DocumentStatus.INDEXED

    def mark_failed(self, reason: str) -> None:
        self.status = DocumentStatus.FAILED
        self.error_message = reason
