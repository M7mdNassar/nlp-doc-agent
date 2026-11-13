from dataclasses import dataclass
from typing import Any

from ..value_objects.chunk_id import ChunkId
from ..value_objects.document_id import DocumentId


@dataclass
class Chunk:
    id: ChunkId
    document_id: DocumentId
    text: str
    page: int
    section: str | None = None
    parent_id: str | None = None
    document_name: str = ""
    file_type: str = ""
    author: str = ""
    date: str = ""
    chapter: str | None = None
    location: str | None = None
    table_data: dict[str, Any] | None = None

    def retrieval_text(self) -> str:
        """Include the source heading for ranking without altering citation text."""
        if self.section and not self.text.startswith(self.section):
            return f"{self.section}\n{self.text}"
        return self.text

    def metadata(self) -> dict[str, Any]:
        return {
            key: getattr(self, key)
            for key in (
                "document_name",
                "file_type",
                "author",
                "date",
                "chapter",
                "location",
                "table_data",
            )
        }
