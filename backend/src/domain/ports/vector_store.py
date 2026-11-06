from typing import Any, Protocol

from ..entities.chunk import Chunk
from ..entities.evidence import EvidencePackage
from ..value_objects.sparse_vector import SparseVector


class VectorStore(Protocol):
    async def upsert(
        self,
        chunks: list[Chunk],
        dense_vectors: list[list[float]],
        sparse_vectors: list[SparseVector],
    ) -> None: ...
    async def hybrid_search(
        self,
        query_dense: list[float],
        query_sparse: SparseVector,
        filters: dict[str, Any],
        limit: int = 20,
    ) -> EvidencePackage: ...
    async def delete_by_document(self, document_id: str) -> None: ...
