from typing import Any

from fastembed import SparseTextEmbedding

from src.core.observability import stage
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
        with stage("dense_embedding"):
            dense_vector = await self.embedder.embed_query(query)

        # 2. Embed Query (Sparse)
        with stage("sparse_embedding"):
            sparse_embedding = list(self.sparse_model.query_embed(query))[0]
            sparse_vector = SparseVector(
                indices=sparse_embedding.indices.tolist(), values=sparse_embedding.values.tolist()
            )

        # 3. Hybrid Search in Qdrant
        with stage("vector_search") as metrics:
            evidence = await self.vector_store.hybrid_search(
                query_dense=dense_vector,
                query_sparse=sparse_vector,
                filters=filters or {},
                limit=20,  # Get top 20 candidates
            )
            metrics["candidate_chunks"] = len(evidence.chunks)

        if evidence.is_empty:
            return evidence

        # Keep the full ranking until the orchestrator applies the shared context budget.
        with stage("reranking", candidate_chunks=len(evidence.chunks)):
            reranked_chunks = await self.reranker.rerank(query, evidence.chunks, top_k=20)

        return EvidencePackage.from_chunks(reranked_chunks, evidence.diagnostics)
