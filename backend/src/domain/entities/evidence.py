from dataclasses import dataclass, field

from ..value_objects.confidence import Confidence
from ..value_objects.page_range import PageRange
from .chunk import Chunk
from .table import Table


@dataclass
class EvidencePackage:
    """The contract passed from Retriever to Analyst."""

    chunks: list[Chunk] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)
    diagnostics: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_chunks(
        cls, chunks: list[Chunk], diagnostics: dict[str, str] | None = None
    ) -> "EvidencePackage":
        tables = [
            Table(
                c.document_id,
                PageRange(c.page, c.page),
                c.text,
                Confidence(1.0),
                section=c.section,
                chunk_id=str(c.id),
                headers=c.table_data["headers"],
                rows=c.table_data["rows"],
            )
            for c in chunks
            if c.table_data
        ]
        return cls(chunks=chunks, tables=tables, diagnostics=diagnostics or {})

    @property
    def is_empty(self) -> bool:
        return len(self.chunks) == 0 and len(self.tables) == 0
