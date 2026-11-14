from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import numpy as np
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import providers
from src.application.agents.retriever.context_selector import ContextSelector
from src.application.answer_cache import AnswerCache
from src.core.observability import question_scope
from src.domain.entities.chunk import Chunk
from src.domain.value_objects.chunk_id import ChunkId
from src.domain.value_objects.document_id import DocumentId
from src.infrastructure.embeddings import bge_adapter
from tests.test_answer_cache import MemoryStore


def test_reuse_retriever_without_reusing_request_database_sessions(monkeypatch):
    embedder = SimpleNamespace(count_tokens=len)
    factory = Mock(return_value=SimpleNamespace())
    monkeypatch.setattr(providers, "get_embedder", lambda: embedder)
    monkeypatch.setattr(providers, "get_vector_store", lambda: object())
    monkeypatch.setattr(providers, "get_reranker", lambda: object())
    monkeypatch.setattr(providers, "get_llm", lambda: object())
    monkeypatch.setattr(providers, "RetrieverAgent", factory)
    monkeypatch.setattr(providers.settings, "ANSWER_CACHE_ENABLED", False)
    providers.get_retriever.cache_clear()
    try:
        first_session, second_session = AsyncSession(), AsyncSession()
        first = providers.get_ask_question_uc(first_session)
        second = providers.get_ask_question_uc(second_session)
        assert first is not second and first.orchestrator is not second.orchestrator
        assert first.orchestrator.retriever is second.orchestrator.retriever
        assert first.documents.session is first_session
        assert second.documents.session is second_session
        assert first.conversations.session is not second.conversations.session
        factory.assert_called_once()
    finally:
        providers.get_retriever.cache_clear()


def test_selector_tokenizes_each_candidate_once_and_keeps_conflicting_sources():
    chunks = [
        Chunk(ChunkId("chunk_a"), DocumentId("doc_model_a"), "Median latency is 18.6 ms.", 2),
        Chunk(ChunkId("chunk_b"), DocumentId("doc_model_b"), "Median latency is 2.8 ms.", 2),
        Chunk(ChunkId("chunk_duplicate"), DocumentId("doc_model_a"), "Median latency is 18.6 ms.", 2),
        Chunk(ChunkId("chunk_c"), DocumentId("doc_model_a"), "P95 latency is 31.4 ms.", 2),
    ]
    count = Mock(side_effect=len)
    selected = ContextSelector(count, max_tokens=1000, max_chunks=4).select(chunks)
    assert [c.id for c in selected] == [chunks[i].id for i in (0, 1, 3)]
    assert count.call_count == len(chunks)
    limited = ContextSelector(len, max_tokens=100, max_chunks=4).select(chunks)
    assert limited == chunks[:1]


async def test_query_embeddings_are_exact_and_return_independent_vectors(monkeypatch):
    model = SimpleNamespace(encode=Mock(return_value=np.array([0.25, 0.75])))
    monkeypatch.setattr(bge_adapter.embedding_loader, "load", lambda: model)
    adapter = bge_adapter.BGEAdapter()
    first = await adapter.embed_query("Median latency?")
    first[0] = 999.0
    assert await adapter.embed_query("Median latency?") == [0.25, 0.75]
    model.encode.assert_called_once()
    for different in ["P95 latency?", "median latency?", "Median latency? "]:
        await adapter.embed_query(different)
    assert model.encode.call_count == 4
    # An adapter with another model lifecycle cannot reuse an earlier vector.
    await bge_adapter.BGEAdapter().embed_query("Median latency?")
    assert model.encode.call_count == 5


async def test_query_embedding_cache_is_bounded_and_failed_encodes_are_retried(monkeypatch):
    model = SimpleNamespace(encode=Mock(return_value=np.array([1.0, 0.0])))
    monkeypatch.setattr(bge_adapter.embedding_loader, "load", lambda: model)
    adapter = bge_adapter.BGEAdapter()
    for i in range(adapter.QUERY_CACHE_SIZE):
        await adapter.embed_query(str(i))
    await adapter.embed_query("0")  # Touch the oldest entry before inserting another.
    await adapter.embed_query("new")
    await adapter.embed_query("0")
    assert model.encode.call_count == adapter.QUERY_CACHE_SIZE + 1
    await adapter.embed_query("1")  # Least recently used entry was evicted.
    assert model.encode.call_count == adapter.QUERY_CACHE_SIZE + 2
    model.encode.side_effect = [RuntimeError("temporary encode error"), np.array([2.0, 3.0])]
    with pytest.raises(RuntimeError, match="temporary"):
        await adapter.embed_query("retry")
    assert await adapter.embed_query("retry") == [2.0, 3.0]


async def test_semantic_miss_reuses_query_vector_for_normal_retrieval(monkeypatch):
    model = SimpleNamespace(encode=Mock(return_value=np.array([1.0, 0.0])))
    monkeypatch.setattr(bge_adapter.embedding_loader, "load", lambda: model)
    embedder = bge_adapter.BGEAdapter()
    corpus = SimpleNamespace(revision=AsyncMock(return_value="unchanged"))
    cache = AnswerCache(MemoryStore(), corpus, embedder, "same-pipeline")

    async def retrieve_and_answer():
        assert await embedder.embed_query("What is scaled dot-product attention?") == [1.0, 0.0]
        return {"state": "insufficient_evidence", "answer": "Not enough evidence.", "sources": []}

    with question_scope() as trace:
        result = await cache.run(
            "What is scaled dot-product attention?", {}, [], retrieve_and_answer
        )
    assert result["cache"]["status"] == "miss"
    assert result["state"] == "insufficient_evidence"
    assert [s["cache_hit"] for s in trace.stages if s["stage"] == "query_embedding"] == [
        False,
        True,
    ]
    model.encode.assert_called_once()
