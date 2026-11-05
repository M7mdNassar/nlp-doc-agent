from dataclasses import dataclass

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
