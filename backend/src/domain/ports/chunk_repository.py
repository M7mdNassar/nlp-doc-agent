from typing import Protocol

from ..entities.chunk import Chunk
from ..value_objects.document_id import DocumentId


class ChunkRepository(Protocol):
    async def save_batch(self, chunks: list[Chunk]) -> None: ...

    async def get_by_document(self, doc_id: DocumentId) -> list[Chunk]: ...

    async def delete_by_document(self, doc_id: DocumentId) -> None: ...
