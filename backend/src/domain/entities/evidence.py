from dataclasses import dataclass, field

from .chunk import Chunk
from .table import Table


@dataclass
class EvidencePackage:
    """The contract passed from Retriever to Analyst."""

    chunks: list[Chunk] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)
    diagnostics: dict[str, str] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return len(self.chunks) == 0 and len(self.tables) == 0
