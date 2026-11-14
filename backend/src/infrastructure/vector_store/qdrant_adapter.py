from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from qdrant_client import AsyncQdrantClient, models

from src.core.config import settings
from src.core.retrieval_diagnostics import record_candidates
from src.domain.entities.chunk import Chunk
from src.domain.entities.evidence import EvidencePackage
from src.domain.ports.vector_store import VectorStore
from src.domain.value_objects.chunk_id import ChunkId
from src.domain.value_objects.document_id import DocumentId
from src.domain.value_objects.metadata_filters import section_key
from src.domain.value_objects.sparse_vector import SparseVector as DomainSparseVector
from src.infrastructure.relational.published_chunks import published_chunk_ids

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
    def __init__(
        self,
        published_ids: Callable[[dict[str, Any]], Awaitable[list[str]]] | None = published_chunk_ids,
    ) -> None:
        self.client = AsyncQdrantClient(url=settings.QDRANT_URL)
        self.published_ids = published_ids

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
                        **chunk.metadata(),
                        "name_key": chunk.document_name.casefold(),
                        "author_key": chunk.author.casefold(),
                        "section_key": self._section_key(chunk.section or ""),
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

        if any(filters.get(key) == [] for key in ("doc_ids", "pages", "sections")):
            return EvidencePackage()
        qdrant_filter = self._build_filter(filters)
        if self.published_ids is not None:
            active = await self.published_ids(filters)
            if not active:
                return EvidencePackage()
            published = models.HasIdCondition(
                has_id=[chunk_id.removeprefix("chunk_") for chunk_id in active]
            )
            qdrant_filter = models.Filter(
                must=[qdrant_filter, published] if qdrant_filter else [published]
            )

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
            raise RuntimeError("Document retrieval is unavailable") from e

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
                    page=int(payload.get(PAYLOAD_PAGE, 0)),
                    section=payload.get("section"),
                    parent_id=payload.get("parent_id"),
                    **{
                        key: payload[key]
                        for key in (
                            "document_name",
                            "file_type",
                            "author",
                            "date",
                            "chapter",
                            "location",
                            "table_data",
                        )
                        if key in payload
                    },
                )
            )

        record_candidates("hybrid_search", chunks, [float(p.score) for p in response.points])
        return EvidencePackage.from_chunks(chunks, diagnostics={"raw_results": str(len(chunks))})

    @staticmethod
    def _build_filter(filters: dict[str, Any]) -> models.Filter | None:
        conditions = []
        fields = {"doc_id": PAYLOAD_DOC_ID, "document_name": "name_key", "author": "author_key",
                  "file_type": "file_type", "date": "date", "chapter": "chapter",
                  "section": "section_key", "page": PAYLOAD_PAGE}
        for field, key in fields.items():
            if field in filters:
                conditions.append(models.FieldCondition(
                    key=key, match=models.MatchValue(value=QdrantAdapter._filter_value(field, filters[field]))
                ))
        for field, key in {"doc_ids": PAYLOAD_DOC_ID, "pages": PAYLOAD_PAGE,
                           "sections": "section_key", "access_tags": PAYLOAD_ACCESS_TAGS}.items():
            if field in filters:
                values = filters[field]
                if field == "sections":
                    values = [section_key(v) for v in values]
                conditions.append(models.FieldCondition(key=key, match=models.MatchAny(any=values)))
        return models.Filter(must=conditions) if conditions else None

    @staticmethod
    def _filter_value(field: str, value: Any) -> Any:
        if field in {"page", "doc_id"}:
            return value
        return section_key(str(value)) if field == "section" else str(value).casefold()

    @staticmethod
    def _section_key(value: str) -> str:
        return section_key(value)

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
