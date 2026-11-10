from contextlib import asynccontextmanager
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import UploadFile
from httpx import ASGITransport, AsyncClient

from src.core.errors import ValidationError
from src.domain.entities.document import Document
from src.domain.entities.job import Job, JobStatus
from src.domain.exceptions.llm_provider_error import (
    LLMConfigurationError,
    LLMProviderError,
    LLMRateLimitError,
)
from src.domain.value_objects.document_id import DocumentId


@pytest.fixture
def api(monkeypatch):
    pytest.importorskip("sentence_transformers")

    # Import the real routers without creating external clients or downloading models.
    from src.infrastructure.cache import exact_cache
    from src.infrastructure.embeddings import bge_adapter
    from src.infrastructure.llm import router
    from src.infrastructure.rerankers import cross_encoder_adapter
    from src.infrastructure.vector_store import qdrant_adapter

    for module, name in (
        (exact_cache, "RedisExactCache"),
        (bge_adapter, "BGEAdapter"),
        (router, "LLMRouter"),
        (cross_encoder_adapter, "CrossEncoderAdapter"),
        (qdrant_adapter, "QdrantAdapter"),
    ):
        monkeypatch.setattr(module, name, Mock())

    from src.api.dependencies import providers
    from src.main import create_app

    app = create_app()
    return app, providers


@pytest.fixture
async def client(api):
    app, _ = api
    # ASGITransport deliberately does not run the external-service startup lifespan.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def test_chat_dependency_and_response(api, client):
    app, providers = api
    result = {"answer": "Test answer", "state": "answer_ready", "loops": 0, "evidence_count": 1}
    uc = SimpleNamespace(execute=AsyncMock(return_value=result))
    app.dependency_overrides[providers.get_ask_question_uc] = lambda: uc

    response = await client.post("/chat", json={"message": "Question?"})

    assert response.status_code == 200
    assert response.json() == result
    uc.execute.assert_awaited_once_with("Question?", None, None)


async def test_document_upload_uses_multipart_and_injected_use_case(api, client):
    app, providers = api
    doc = Document(DocumentId.generate(), "sample.txt", "txt", "checksum")
    job = Job("job-test", doc.id)
    uc = SimpleNamespace(execute=AsyncMock(return_value=(doc, job)))
    app.dependency_overrides[providers.get_upload_doc_uc] = lambda: uc

    response = await client.post(
        "/documents", files={"file": ("sample.txt", b"contents", "text/plain")}
    )

    assert response.status_code == 200
    assert response.json() == {"document_id": str(doc.id), "job_id": job.job_id, "status": "queued"}
    uc.execute.assert_awaited_once_with("sample.txt", "txt", b"contents")


@pytest.mark.parametrize("filename", [None, ""])
async def test_upload_without_filename_is_rejected_before_use_case(api, filename):
    from src.api.routers.documents import upload_document

    uc = SimpleNamespace(execute=AsyncMock())
    upload = UploadFile(file=BytesIO(b"contents"), filename=filename)
    try:
        with pytest.raises(ValidationError, match="filename") as error:
            await upload_document(upload, uc)
        assert error.value.status_code == 400
        uc.execute.assert_not_awaited()
    finally:
        await upload.close()


async def test_list_and_delete_document_dependencies(api, client):
    app, providers = api
    doc = Document(DocumentId.generate(), "sample.txt", "txt", "checksum")
    list_uc = SimpleNamespace(execute=AsyncMock(return_value=[doc]))
    delete_uc = SimpleNamespace(execute=AsyncMock())
    app.dependency_overrides[providers.get_list_docs_uc] = lambda: list_uc
    app.dependency_overrides[providers.get_delete_doc_uc] = lambda: delete_uc

    response = await client.get("/documents")
    assert response.status_code == 200
    assert response.json() == {"items": [{"id": str(doc.id), "name": doc.name, "status": "queued"}]}
    response = await client.delete(f"/documents/{doc.id}")
    assert response.status_code == 200
    assert response.json() == {"status": "deleted"}
    delete_uc.execute.assert_awaited_once_with(doc.id)


@pytest.mark.parametrize("status", [JobStatus.QUEUED, JobStatus.FAILED])
async def test_job_status_injects_database_session(api, client, monkeypatch, status):
    app, providers = api
    session = object()

    async def fake_session():
        yield session

    job = Job(
        "job-test",
        DocumentId.generate(),
        status,
        "parse failed" if status == JobStatus.FAILED else None,
    )
    repo = SimpleNamespace(get=AsyncMock(return_value=job))
    repository_factory = Mock(return_value=repo)
    monkeypatch.setattr(providers, "JobRepository", repository_factory)
    app.dependency_overrides[providers.get_db_session] = fake_session

    response = await client.get("/jobs/job-test")

    assert response.status_code == 200
    assert response.json() == {
        "job_id": job.job_id,
        "document_id": str(job.document_id),
        "status": status.value,
        "error": job.error,
        "updated_at": job.updated_at.isoformat(),
    }
    repository_factory.assert_called_once_with(session)
    repo.get.assert_awaited_once_with("job-test")


async def test_missing_job_returns_404(api, client):
    app, providers = api
    uc = SimpleNamespace(execute=AsyncMock(return_value=None))
    app.dependency_overrides[providers.get_job_status_uc] = lambda: uc

    response = await client.get("/jobs/missing")

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"
    uc.execute.assert_awaited_once_with("missing")


@pytest.mark.parametrize("failed", [None, "sqlite", "qdrant", "redis"])
async def test_health_response_preserves_dependency_statuses(api, client, monkeypatch, failed):
    from src.api.routers import health

    def operation(name):
        return AsyncMock(side_effect=RuntimeError("offline") if failed == name else None)

    @asynccontextmanager
    async def connection():
        yield SimpleNamespace(execute=operation("sqlite"))

    monkeypatch.setattr(health, "engine", SimpleNamespace(connect=connection))
    monkeypatch.setattr(
        health,
        "QdrantAdapter",
        lambda: SimpleNamespace(client=SimpleNamespace(get_collections=operation("qdrant"))),
    )
    monkeypatch.setattr(
        health, "get_redis_client", lambda: SimpleNamespace(ping=operation("redis"))
    )

    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "degraded" if failed else "ok",
        "dependencies": {
            name: "down" if name == failed else "ok" for name in ("sqlite", "qdrant", "redis")
        },
    }


def test_openapi_registers_jobs_and_required_file(api):
    app, _ = api
    schema = app.openapi()
    assert "/jobs/{job_id}" in schema["paths"]
    upload = schema["paths"]["/documents"]["post"]
    assert upload["requestBody"]["required"] is True
    assert "multipart/form-data" in upload["requestBody"]["content"]


async def test_chat_forwards_conversation_and_validated_filters(api, client):
    app, providers = api
    uc = SimpleNamespace(execute=AsyncMock(return_value={"answer": "ok"}))
    app.dependency_overrides[providers.get_ask_question_uc] = lambda: uc
    response = await client.post(
        "/chat",
        json={
            "message": "Question",
            "conversation_id": "conv_test",
            "filters": {"chapter": "4", "page": 2},
        },
    )
    assert response.status_code == 200
    args = uc.execute.await_args.args
    assert args[:2] == ("Question", "conv_test")
    assert args[2].model_dump(exclude_none=True) == {"chapter": "4", "page": 2}


@pytest.mark.parametrize(
    "body",
    [
        {"message": "   "},
        {"message": "q", "filters": {"page": 0}},
        {"message": "q", "filters": {"page": "2"}},
        {"message": "q", "filters": {"unknown": "ignored?"}},
    ],
)
async def test_chat_rejects_invalid_input_instead_of_ignoring_filters(api, client, body):
    app, providers = api
    uc = SimpleNamespace(execute=AsyncMock())
    app.dependency_overrides[providers.get_ask_question_uc] = lambda: uc
    assert (await client.post("/chat", json=body)).status_code == 422
    uc.execute.assert_not_awaited()


async def test_reindex_endpoint_returns_new_job(api, client):
    app, providers = api
    doc = Document(DocumentId.generate(), "existing.pdf", "pdf", "sum")
    job = Job("job-reindex", doc.id)
    uc = SimpleNamespace(reindex=AsyncMock(return_value=(doc, job)))
    app.dependency_overrides[providers.get_upload_doc_uc] = lambda: uc
    response = await client.post(f"/documents/{doc.id}/reindex")
    assert response.status_code == 200
    assert response.json()["job_id"] == "job-reindex"
    uc.reindex.assert_awaited_once_with(doc.id)


@pytest.mark.parametrize(
    "error,status,code,retry_after",
    [
        (LLMRateLimitError("Groq", 879), 429, "LLM_RATE_LIMITED", "879"),
        (LLMRateLimitError("Groq"), 429, "LLM_RATE_LIMITED", None),
        (LLMProviderError("Groq"), 503, "LLM_UNAVAILABLE", None),
        (LLMConfigurationError("Groq"), 503, "LLM_CONFIGURATION_ERROR", None),
    ],
)
async def test_chat_provider_failures_are_service_errors(
    api, client, error, status, code, retry_after
):
    app, providers = api
    uc = SimpleNamespace(execute=AsyncMock(side_effect=error))
    app.dependency_overrides[providers.get_ask_question_uc] = lambda: uc
    response = await client.post("/chat", json={"message": "Projects?"})
    assert response.status_code == status
    body = response.json()
    assert body["code"] == code
    assert body["message"] == str(error)
    assert body["details"]["provider"] == "Groq"
    assert "state" not in body
    assert response.headers.get("retry-after") == retry_after
    assert body["details"].get("retry_after_seconds") == (int(retry_after) if retry_after else None)
    assert response.headers["cache-control"] == "no-store"
