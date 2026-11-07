from typing import Any

from fastembed import SparseTextEmbedding

from src.domain.entities.evidence import EvidencePackage
from src.domain.ports.embedder import Embedder
from src.domain.ports.reranker import Reranker
from src.domain.ports.vector_store import VectorStore
from src.domain.value_objects.sparse_vector import SparseVector

from .context_selector import ContextSelector


class RetrieverAgent:
    def __init__(self, embedder: Embedder, vector_store: VectorStore, reranker: Reranker):
        self.embedder = embedder
        self.vector_store = vector_store
        self.reranker = reranker
        self.sparse_model = SparseTextEmbedding(model_name="Qdrant/bm25")
        self.context_selector = ContextSelector(max_chunks=5)

    async def retrieve(self, query: str, filters: dict[str, Any] | None = None) -> EvidencePackage:
        dense_vector = await self.embedder.embed_query(query)
        sparse_embedding = list(self.sparse_model.embed([query]))[0]
        sparse_vector = SparseVector(
            indices=sparse_embedding.indices.tolist(), values=sparse_embedding.values.tolist()
        )

        evidence = await self.vector_store.hybrid_search(
            query_dense=dense_vector,
            query_sparse=sparse_vector,
            filters=filters or {},
            limit=20,
        )

        if evidence.is_empty:
            return evidence

        # Rerank (Top 20 -> Top 8)
        reranked_chunks = await self.reranker.rerank(query, evidence.chunks, top_k=8)

        # Apply Context Selector (Top 8 -> Best 5 diverse)
        final_chunks = self.context_selector.select(reranked_chunks)

        return EvidencePackage(chunks=final_chunks, diagnostics=evidence.diagnostics)
