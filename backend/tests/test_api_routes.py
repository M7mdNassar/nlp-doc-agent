from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from httpx import ASGITransport, AsyncClient

from src.domain.entities.document import Document
from src.domain.entities.job import Job, JobStatus
from src.domain.value_objects.document_id import DocumentId


@pytest.fixture
def api(monkeypatch):
    pytest.importorskip("sentence_transformers")
    from src.api.dependencies import providers
    from src.main import create_app

    return create_app(), providers


@pytest.fixture
async def client(api):
    app, _ = api
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
    uc.execute.assert_awaited_once_with("Question?")


async def test_document_upload_uses_multipart(api, client):
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


async def test_job_status_injects_database_session(api, client, monkeypatch):
    app, providers = api
    session = object()

    async def fake_session():
        yield session

    job = Job("job-test", DocumentId.generate(), JobStatus.QUEUED)
    repo = SimpleNamespace(get=AsyncMock(return_value=job))
    repository_factory = Mock(return_value=repo)
    monkeypatch.setattr(providers, "JobRepository", repository_factory)
    app.dependency_overrides[providers.get_db_session] = fake_session

    response = await client.get("/jobs/job-test")

    assert response.status_code == 200
    assert response.json()["job_id"] == job.job_id
    repo.get.assert_awaited_once_with("job-test")


async def test_missing_job_returns_404(api, client):
    app, providers = api
    uc = SimpleNamespace(execute=AsyncMock(return_value=None))
    app.dependency_overrides[providers.get_job_status_uc] = lambda: uc

    response = await client.get("/jobs/missing")
    assert response.status_code == 404
