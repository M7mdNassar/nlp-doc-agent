from typing import Any

from fastembed import SparseTextEmbedding

from src.domain.entities.evidence import EvidencePackage
from src.domain.ports.embedder import Embedder
from src.domain.ports.reranker import Reranker
from src.domain.ports.vector_store import VectorStore
from src.domain.value_objects.sparse_vector import SparseVector


class RetrieverAgent:
    def __init__(self, embedder: Embedder, vector_store: VectorStore, reranker: Reranker):
        self.embedder = embedder
        self.vector_store = vector_store
        self.reranker = reranker
        self.sparse_model = SparseTextEmbedding(model_name="Qdrant/bm25")

    async def retrieve(self, query: str, filters: dict[str, Any] | None = None) -> EvidencePackage:
        # 1. Embed Query (Dense)
        dense_vector = await self.embedder.embed_query(query)

        # 2. Embed Query (Sparse)
        sparse_embedding = list(self.sparse_model.embed([query]))[0]
        sparse_vector = SparseVector(
            indices=sparse_embedding.indices.tolist(), values=sparse_embedding.values.tolist()
        )

        # 3. Hybrid Search in Qdrant
        evidence = await self.vector_store.hybrid_search(
            query_dense=dense_vector,
            query_sparse=sparse_vector,
            filters=filters or {},
            limit=20,  # Get top 20 candidates
        )

        if evidence.is_empty:
            return evidence

        # 4. Rerank (Top 20 -> Top 8)
        reranked_chunks = await self.reranker.rerank(query, evidence.chunks, top_k=8)

        return EvidencePackage(chunks=reranked_chunks, diagnostics=evidence.diagnostics)
