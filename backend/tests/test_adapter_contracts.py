from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from qdrant_client import AsyncQdrantClient, models

from src.domain.entities.chunk import Chunk
from src.domain.value_objects.chunk_id import ChunkId
from src.domain.value_objects.document_id import DocumentId
from src.domain.value_objects.sparse_vector import SparseVector
from src.domain.value_objects.token_budget import TokenBudget
from src.infrastructure.llm import groq_adapter
from src.infrastructure.vector_store import qdrant_adapter
from src.infrastructure.vector_store.schema import (
    COLLECTION_NAME,
    DENSE_VECTOR_NAME,
    SPARSE_VECTOR_NAME,
)

pytest.importorskip("sentence_transformers")


def make_chunk() -> Chunk:
    return Chunk(ChunkId.generate(), DocumentId.generate(), "test passage", 1)


async def test_groq_stream_is_directly_async_iterable(monkeypatch):
    async def response():
        for token in (None, "Hello", " world"):
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=token))])

    create = AsyncMock(return_value=response())
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(groq_adapter, "AsyncGroq", lambda **kwargs: client)

    adapter = groq_adapter.GroqAdapter()
    tokens = [token async for token in adapter.stream("q", "s", TokenBudget(10))]

    assert tokens == ["Hello", " world"]


async def test_qdrant_round_trip_preserves_domain_ids(monkeypatch):
    client = AsyncQdrantClient(location=":memory:")
    monkeypatch.setattr(qdrant_adapter, "AsyncQdrantClient", lambda **kwargs: client)
    adapter = qdrant_adapter.QdrantAdapter()

    try:
        await client.create_collection(
            COLLECTION_NAME,
            vectors_config={
                DENSE_VECTOR_NAME: models.VectorParams(size=3, distance=models.Distance.COSINE)
            },
            sparse_vectors_config={SPARSE_VECTOR_NAME: models.SparseVectorParams()},
        )
        chunk = make_chunk()
        dense = [1.0, 0.0, 0.0]
        sparse = SparseVector([2], [1.0])

        # Upsert and check search
        await adapter.upsert([chunk], [dense], [sparse])
        evidence = await adapter.hybrid_search(dense, sparse, {"doc_id": str(chunk.document_id)})

        assert evidence.chunks == [chunk]

        # Delete and check
        await adapter.delete_by_document(str(chunk.document_id))
        assert (await client.count(COLLECTION_NAME)).count == 0
    finally:
        await client.close()


def test_sparse_vector_rejects_unpaired_values():
    with pytest.raises(ValueError, match="equal lengths"):
        SparseVector([1, 2], [1.0])
