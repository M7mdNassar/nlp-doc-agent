from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from qdrant_client import AsyncQdrantClient, models

from src.domain.entities.chunk import Chunk
from src.domain.value_objects.chunk_id import ChunkId
from src.domain.value_objects.document_id import DocumentId
from src.domain.value_objects.sparse_vector import SparseVector
from src.domain.value_objects.token_budget import TokenBudget
from src.infrastructure.llm import groq_adapter, router
from src.infrastructure.vector_store import qdrant_adapter
from src.infrastructure.vector_store.schema import (
    COLLECTION_NAME,
    DENSE_VECTOR_NAME,
    SPARSE_VECTOR_NAME,
)


def make_chunk():
    return Chunk(ChunkId.generate(), DocumentId.generate(), "test passage", 1)


async def test_groq_stream_is_directly_async_iterable(monkeypatch):
    async def response():
        for token in (None, "Hello", " world"):
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=token))])

    create = AsyncMock(return_value=response())
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(groq_adapter, "AsyncGroq", lambda **kwargs: client)
    adapter = groq_adapter.GroqAdapter()
    monkeypatch.setattr(router, "GroqAdapter", lambda: adapter)

    tokens = [token async for token in router.LLMRouter().stream("q", "s", TokenBudget(10))]

    assert tokens == ["Hello", " world"]
    assert create.await_args.kwargs["stream"] is True


async def test_stream_failure_propagates_without_replaying_tokens(monkeypatch):
    async def response():
        yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="first"))])
        raise RuntimeError("connection lost")

    create = AsyncMock(return_value=response())
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(groq_adapter, "AsyncGroq", lambda **kwargs: client)
    adapter = groq_adapter.GroqAdapter()
    tokens = []
    with pytest.raises(RuntimeError, match="connection lost"):
        async for token in adapter.stream("q", "s", TokenBudget(10)):
            tokens.append(token)

    assert tokens == ["first"]
    create.assert_awaited_once()


@pytest.mark.parametrize("counts", [(1, 0, 1), (1, 1, 0), (0, 1, 1)])
async def test_vector_count_mismatch_is_rejected_before_upload(monkeypatch, counts):
    client = SimpleNamespace(upsert=AsyncMock())
    monkeypatch.setattr(qdrant_adapter, "AsyncQdrantClient", lambda **kwargs: client)
    adapter = qdrant_adapter.QdrantAdapter()

    with pytest.raises(ValueError, match="equal lengths"):
        await adapter.upsert(
            [make_chunk()] * counts[0], [[1.0]] * counts[1], [SparseVector([1], [1.0])] * counts[2]
        )

    client.upsert.assert_not_awaited()


async def test_qdrant_round_trip_preserves_domain_ids_and_is_idempotent(monkeypatch):
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
        await adapter.upsert([chunk], [dense], [sparse])
        await adapter.upsert([chunk], [dense], [sparse])
        assert (await client.count(COLLECTION_NAME)).count == 1

        evidence = await adapter.hybrid_search(dense, sparse, {"doc_id": str(chunk.document_id)})
        assert evidence.chunks == [chunk]
        assert evidence.diagnostics == {"raw_results": "1"}

        await adapter.delete_by_document(str(chunk.document_id))
        assert (await client.count(COLLECTION_NAME)).count == 0
    finally:
        await client.close()


def test_sparse_vector_rejects_unpaired_values():
    with pytest.raises(ValueError, match="equal lengths"):
        SparseVector([1, 2], [1.0])


async def test_embeddings_return_python_float_lists(monkeypatch):
    import numpy as np

    from src.infrastructure.embeddings import bge_adapter

    model = Mock()
    model.encode.side_effect = [np.array([1, 2]), np.array([[1, 2], [3, 4]])]
    monkeypatch.setattr(bge_adapter.embedding_loader, "load", lambda: model)
    adapter = bge_adapter.BGEAdapter()

    query = await adapter.embed_query("q")
    documents = await adapter.embed_documents(["a", "b"])
    assert query == [1.0, 2.0]
    assert documents == [[1.0, 2.0], [3.0, 4.0]]
    assert all(type(value) is float for value in query)
    assert all(type(value) is float for row in documents for value in row)


async def test_reranker_preserves_score_alignment_and_rejects_missing_scores(monkeypatch):
    from src.infrastructure.rerankers import cross_encoder_adapter

    model = Mock()
    model.predict.side_effect = [[0.1, 0.9], [0.1]]
    monkeypatch.setattr(cross_encoder_adapter.reranker_loader, "load", lambda: model)
    adapter = cross_encoder_adapter.CrossEncoderAdapter()
    chunks = [make_chunk(), make_chunk()]

    assert await adapter.rerank("q", chunks, top_k=1) == [chunks[1]]
    model.predict.assert_called_once_with([("q", chunk.text) for chunk in chunks])
    with pytest.raises(ValueError):
        await adapter.rerank("q", chunks)


@pytest.mark.parametrize(
    "module_path,loader_name,model_name",
    [
        (
            "src.infrastructure.embeddings.model_loader",
            "EmbeddingModelLoader",
            "SentenceTransformer",
        ),
        ("src.infrastructure.rerankers.model_loader", "RerankerModelLoader", "CrossEncoder"),
    ],
)
def test_model_loaders_cache_one_model(monkeypatch, module_path, loader_name, model_name):
    from importlib import import_module

    module = import_module(module_path)
    loader_type = getattr(module, loader_name)
    loader = loader_type()
    monkeypatch.setattr(loader, "_model", None)
    model = Mock()
    constructor = Mock(return_value=model)
    monkeypatch.setattr(module, model_name, constructor)

    assert loader_type() is loader
    assert loader.load() is model
    assert loader.load() is model
    constructor.assert_called_once()
