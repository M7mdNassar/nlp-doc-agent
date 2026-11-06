from typing import Any

import structlog
from qdrant_client import AsyncQdrantClient, models

from src.core.config import settings
from src.domain.entities.chunk import Chunk
from src.domain.entities.evidence import EvidencePackage
from src.domain.ports.vector_store import VectorStore
from src.domain.value_objects.chunk_id import ChunkId
from src.domain.value_objects.document_id import DocumentId
from src.domain.value_objects.sparse_vector import SparseVector as DomainSparseVector

from .schema import (
    COLLECTION_NAME,
    DENSE_VECTOR_NAME,
    PAYLOAD_ACCESS_TAGS,
    PAYLOAD_DOC_ID,
    PAYLOAD_PAGE,
    SPARSE_VECTOR_NAME,
)

logger = structlog.get_logger(__name__)


class QdrantAdapter(VectorStore):
    def __init__(self) -> None:
        self.client = AsyncQdrantClient(url=settings.QDRANT_URL)

    async def upsert(
        self,
        chunks: list[Chunk],
        dense_vectors: list[list[float]],
        sparse_vectors: list[DomainSparseVector],
    ) -> None:
        # Explicit validation to catch mismatches early
        if len(chunks) != len(dense_vectors) or len(chunks) != len(sparse_vectors):
            raise ValueError("Lists must have equal lengths")

        if not chunks:
            return

        points = []
        for chunk, dense, sparse in zip(chunks, dense_vectors, sparse_vectors, strict=True):
            # Qdrant requires valid UUIDs or integers. We strip the "chunk_" prefix.
            safe_point_id = str(chunk.id).replace("chunk_", "")

            points.append(
                models.PointStruct(
                    id=safe_point_id,
                    vector={
                        DENSE_VECTOR_NAME: dense,
                        SPARSE_VECTOR_NAME: models.SparseVector(
                            indices=sparse.indices, values=sparse.values
                        ),
                    },
                    payload={
                        "chunk_id": str(chunk.id),  # Save the original ID in payload
                        PAYLOAD_DOC_ID: str(chunk.document_id),
                        PAYLOAD_PAGE: chunk.page,
                        "section": chunk.section,
                        "text": chunk.text,
                        "parent_id": chunk.parent_id,
                        PAYLOAD_ACCESS_TAGS: [],
                    },
                )
            )

        await self.client.upsert(collection_name=COLLECTION_NAME, points=points, wait=True)

    async def hybrid_search(
        self,
        query_dense: list[float],
        query_sparse: DomainSparseVector,
        filters: dict[str, Any],
        limit: int = 20,
    ) -> EvidencePackage:

        qdrant_filter = None
        if filters:
            must_conditions = []
            if "doc_id" in filters:
                must_conditions.append(
                    models.FieldCondition(
                        key=PAYLOAD_DOC_ID, match=models.MatchValue(value=filters["doc_id"])
                    )
                )
            if "page" in filters:
                must_conditions.append(
                    models.FieldCondition(
                        key=PAYLOAD_PAGE, match=models.MatchValue(value=filters["page"])
                    )
                )
            if "access_tags" in filters:
                must_conditions.append(
                    models.FieldCondition(
                        key=PAYLOAD_ACCESS_TAGS, match=models.MatchAny(any=filters["access_tags"])
                    )
                )

            if must_conditions:
                qdrant_filter = models.Filter(must=must_conditions)

        # Convert domain SparseVector to Qdrant SparseVector for the query
        qdrant_sparse_query = models.SparseVector(
            indices=query_sparse.indices, values=query_sparse.values
        )

        try:
            response = await self.client.query_points(
                collection_name=COLLECTION_NAME,
                prefetch=[
                    models.Prefetch(
                        query=query_dense,
                        using=DENSE_VECTOR_NAME,
                        limit=limit,
                        filter=qdrant_filter,
                    ),
                    models.Prefetch(
                        query=qdrant_sparse_query,  # Use converted vector
                        using=SPARSE_VECTOR_NAME,
                        limit=limit,
                        filter=qdrant_filter,
                    ),
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=limit,
                with_payload=True,
            )
        except Exception as e:
            logger.error(f"Qdrant hybrid search failed: {e}")
            return EvidencePackage(diagnostics={"error": str(e)})

        chunks = []
        for point in response.points:
            payload = point.payload or {}
            # Restore the original ChunkId from the payload
            original_chunk_id = payload.get("chunk_id", f"chunk_{point.id}")

            chunks.append(
                Chunk(
                    id=ChunkId(original_chunk_id),
                    document_id=DocumentId(payload.get(PAYLOAD_DOC_ID, "")),
                    text=payload.get("text", ""),
                    page=payload.get(PAYLOAD_PAGE, 0),
                    section=payload.get("section"),
                    parent_id=payload.get("parent_id"),
                )
            )

        return EvidencePackage(chunks=chunks, diagnostics={"raw_results": len(chunks)})

    async def delete_by_document(self, document_id: str) -> None:
        await self.client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=models.Filter(
                must=[
                    models.FieldCondition(
                        key=PAYLOAD_DOC_ID, match=models.MatchValue(value=document_id)
                    )
                ]
            ),
        )
