from typing import Any, Protocol

from ..entities.chunk import Chunk
from ..entities.evidence import EvidencePackage


class VectorStore(Protocol):
    async def upsert(self, chunks: list[Chunk]) -> None: ...
    async def hybrid_search(
        self, query: str, filters: dict[str, Any], limit: int
    ) -> EvidencePackage: ...
    async def delete_by_document(self, document_id: str) -> None: ...
