from dataclasses import dataclass

from ..value_objects.chunk_id import ChunkId
from ..value_objects.document_id import DocumentId


@dataclass
class Citation:
    document_id: DocumentId
    document_name: str
    chunk_id: ChunkId
    page: int
    quote: str
    section: str | None = None
