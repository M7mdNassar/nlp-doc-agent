from importlib import import_module
from unittest.mock import Mock, call

import pytest

from src.core.config import Settings, settings


@pytest.mark.parametrize("device", ["cpu", "cuda"])
@pytest.mark.parametrize(
    "module_path,loader_name,constructor_name,setting_name",
    [
        (
            "src.infrastructure.embeddings.model_loader",
            "EmbeddingModelLoader",
            "SentenceTransformer",
            "EMBEDDING_DEVICE",
        ),
        (
            "src.infrastructure.rerankers.model_loader",
            "RerankerModelLoader",
            "CrossEncoder",
            "RERANKER_DEVICE",
        ),
    ],
)
def test_models_use_explicit_device_and_load_once(
    monkeypatch, device, module_path, loader_name, constructor_name, setting_name
):
    module = import_module(module_path)
    loader = getattr(module, loader_name)()
    monkeypatch.setattr(loader, "_model", None)
    monkeypatch.setattr(settings, setting_name, device)
    constructor = Mock(return_value=Mock(device=device))
    monkeypatch.setattr(module, constructor_name, constructor)
    assert loader.load() is loader.load()
    constructor.assert_called_once()
    assert constructor.call_args.kwargs["device"] == device


async def test_configured_batches_reach_both_local_models(monkeypatch):
    from src.infrastructure.embeddings import bge_adapter
    from src.infrastructure.rerankers import cross_encoder_adapter

    monkeypatch.setattr(settings, "EMBEDDING_BATCH_SIZE", 2)
    monkeypatch.setattr(settings, "RERANKER_BATCH_SIZE", 3)
    embedding = Mock()
    embedding.encode.side_effect = [[1.0], [[1.0], [2.0]]]
    monkeypatch.setattr(bge_adapter.embedding_loader, "load", lambda: embedding)
    adapter = bge_adapter.BGEAdapter()
    await adapter.embed_query("query")
    await adapter.embed_documents(["a", "b"])
    assert embedding.encode.call_args_list == [
        call("query", normalize_embeddings=True, batch_size=2),
        call(["a", "b"], normalize_embeddings=True, batch_size=2),
    ]
    reranker = Mock()
    reranker.predict.return_value = [0.5]
    monkeypatch.setattr(cross_encoder_adapter.reranker_loader, "load", lambda: reranker)
    from tests.test_adapter_contracts import make_chunk

    chunk = make_chunk()
    assert await cross_encoder_adapter.CrossEncoderAdapter().rerank("q", [chunk]) == [chunk]
    reranker.predict.assert_called_once_with([("q", chunk.text)], batch_size=3)


def test_fallback_settings_parse_from_env_and_reject_invalid_batches(monkeypatch):
    monkeypatch.setenv("LLM_FALLBACK_MODELS", '["openai/gpt-oss-20b"]')
    assert Settings(_env_file=None).LLM_FALLBACK_MODELS == ["openai/gpt-oss-20b"]
    monkeypatch.setenv("LLM_FALLBACK_MODELS", "[]")
    assert Settings(_env_file=None).LLM_FALLBACK_MODELS == []
    with pytest.raises(ValueError):
        Settings(_env_file=None, EMBEDDING_BATCH_SIZE=0)
