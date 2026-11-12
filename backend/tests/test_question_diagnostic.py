import importlib.util
import json
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from structlog.testing import capture_logs

from src.application.agents.analyst.analyst_agent import AnalystAgent
from src.application.agents.answer.answer_agent import AnswerAgent
from src.application.agents.retriever.query_rewriter import QueryRewriter
from src.core.observability import question_scope, stage
from src.domain.entities.document import DocumentStatus
from src.domain.exceptions.llm_provider_error import LLMRateLimitError
from src.domain.value_objects.token_budget import TokenBudget
from tests.test_llm_provider_errors import adapter_with
from tests.test_observability import completion
from tests.unit.application.test_orchestrator import make_orchestrator


@pytest.fixture
def diagnostic():
    path = Path(__file__).resolve().parents[2] / "infrastructure/scripts/diagnose_question.py"
    spec = importlib.util.spec_from_file_location("question_diagnostic", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_capture_keeps_exact_review_evidence_and_feedback_without_extra_calls(
    diagnostic,
    tmp_path,
    sample_chunks,
    monkeypatch,
):
    replies = [
        "Model X accuracy?",
        '{"tools":[]}',
        json.dumps(
            {
                "has_enough_evidence": True,
                "missing_info": "",
                "findings": [
                    {"text": "Model X is 95% accurate.", "chunk_ids": ["chunk_1"]},
                ],
            }
        ),
        json.dumps(
            {"blocks": [{"text": "PRIVATE_UNSUPPORTED", "citations": [{"quote_id": "quote_1"}]}]}
        ),
        json.dumps(
            {
                "supported": [False],
                "qualifications_preserved": [True],
                "no_added_details": [False],
                "feedback": ["Block 1: PRIVATE_UNSUPPORTED is absent from the cited quote."],
            }
        ),
        json.dumps(
            {"blocks": [{"text": sample_chunks[0].text, "citations": [{"quote_id": "quote_1"}]}]}
        ),
        json.dumps(
            {"supported": [True], "qualifications_preserved": [True], "no_added_details": [True]}
        ),
    ]
    adapter, create, _ = adapter_with(monkeypatch, [completion(content=r) for r in replies])
    orchestrator = make_orchestrator(sample_chunks, [])
    orchestrator.rewriter = QueryRewriter(adapter)
    orchestrator.analyst = AnalystAgent(adapter)
    orchestrator.answer_agent = AnswerAgent(adapter)
    output = tmp_path / "capture.json"
    with capture_logs() as logs, question_scope() as trace:
        capture = diagnostic.Capture(output, "PRIVATE_QUESTION")
        diagnostic.attach_capture(orchestrator, capture)
        try:
            capture.data["result"] = await orchestrator.process(
                "PRIVATE_QUESTION", {"doc_ids": ["doc_123456789"]}
            )
        finally:
            capture.close()
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["result"]["state"] == "answer_ready"
    assert data["question_id"] == trace.question_id
    assert data["usage"]["llm_calls"] == create.await_count == 7
    assert data["usage"]["total_tokens"] == 875
    assert len(data["retrievals"]) == 1
    assert data["retrievals"][0]["chunks"][0]["id"] == "chunk_1"
    assert data["retrievals"][0]["chunks"][0]["text"] == sample_chunks[0].text
    first, corrected = data["answer_attempts"]
    assert first["draft"]["blocks"][0]["text"] == "PRIVATE_UNSUPPORTED"
    assert first["review"]["feedback"] == [
        "Block 1: PRIVATE_UNSUPPORTED is absent from the cited quote."
    ]
    assert not first["accepted"] and corrected["accepted"]
    assert "PRIVATE_UNSUPPORTED" in corrected["correction_feedback_received"]
    review_calls = [c for c in data["llm_calls"] if c["stage"] == "answer_verification"]
    assert len(review_calls) == 2
    payload = json.loads(review_calls[0]["user_prompt"])
    source = payload["sources"][payload["blocks"][0]["source_ids"][0]]
    assert payload["texts"][source["quote_text_id"]] == sample_chunks[0].text
    assert [c["response"] for c in data["llm_calls"]] == replies
    assert "PRIVATE_" not in json.dumps(logs)
    assert sample_chunks[0].text not in json.dumps(logs)


async def test_failure_flushes_partial_capture_without_provider_error_message(diagnostic, tmp_path):
    error = LLMRateLimitError("Groq", 120)
    error.args = ("PRIVATE_CREDENTIAL",)
    llm = SimpleNamespace(generate=AsyncMock(side_effect=error))
    path = tmp_path / "partial.json"
    with question_scope():
        capture = diagnostic.Capture(path, "question")
        try:
            with stage("answer_verification"), pytest.raises(LLMRateLimitError):
                await diagnostic.RecordingLLM(llm, capture).generate(
                    "SOURCE", "SYSTEM", TokenBudget(100)
                )
            saved = json.loads(path.read_text(encoding="utf-8"))
            assert saved["llm_calls"][0]["user_prompt"] == "SOURCE"
        finally:
            capture.close()
    saved = path.read_text(encoding="utf-8")
    assert "LLMRateLimitError" in saved and "PRIVATE_CREDENTIAL" not in saved
    llm.generate.assert_awaited_once()


def test_existing_artifact_is_never_overwritten(diagnostic, tmp_path):
    path = tmp_path / "existing.json"
    path.write_text("existing evidence", encoding="utf-8")
    with pytest.raises(FileExistsError):
        diagnostic.Capture(path, "q")
    assert path.read_text(encoding="utf-8") == "existing evidence"


@pytest.mark.parametrize(
    "status,count",
    [(DocumentStatus.QUEUED, 1), (DocumentStatus.INDEXED, 0), (DocumentStatus.INDEXED, 2)],
)
def test_requires_one_ready_document(diagnostic, sample_document, status, count):
    sample_document.status = status
    with pytest.raises(ValueError):
        diagnostic.select_document([sample_document] * count, sample_document.name)


@pytest.mark.parametrize("fails", [False, True])
async def test_run_uses_existing_index_without_saving_a_conversation(
    diagnostic,
    monkeypatch,
    tmp_path,
    sample_document,
    fails,
):
    from src.api.dependencies import providers
    from src.infrastructure.relational import db
    from src.infrastructure.relational.repositories import document_repository

    sample_document.status = DocumentStatus.INDEXED
    session = SimpleNamespace(commit=AsyncMock())

    @asynccontextmanager
    async def session_factory():
        yield session

    monkeypatch.setattr(db, "AsyncSessionLocal", session_factory)
    engine = SimpleNamespace(dispose=AsyncMock())
    monkeypatch.setattr(db, "engine", engine)
    repository = SimpleNamespace(
        list_all=AsyncMock(return_value=[sample_document]), save=AsyncMock()
    )
    monkeypatch.setattr(document_repository, "DocumentRepository", Mock(return_value=repository))

    def agent():
        return SimpleNamespace(llm=SimpleNamespace(generate=AsyncMock()))

    orchestrator = SimpleNamespace(
        rewriter=agent(),
        analyst=agent(),
        answer_agent=agent(),
        retriever=SimpleNamespace(reranker=SimpleNamespace(model=SimpleNamespace(device="cpu"))),
        process=AsyncMock(return_value={"state": "insufficient_evidence"}),
    )
    uc = SimpleNamespace(orchestrator=orchestrator, execute=AsyncMock())
    if fails:
        orchestrator.process.side_effect = RuntimeError("PRIVATE_EXCEPTION")
    monkeypatch.setattr(providers, "get_ask_question_uc", Mock(return_value=uc))
    path = tmp_path / "run.json"
    assert await diagnostic.run(path, "q", sample_document.name) == int(fails)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["document"]["id"] == str(sample_document.id)
    assert data["actual_reranker_device"] == "cpu"
    orchestrator.process.assert_awaited_once_with(
        "q",
        filters={"doc_ids": [str(sample_document.id)]},
        history=[],
        documents=[sample_document],
    )
    uc.execute.assert_not_awaited()
    repository.save.assert_not_awaited()
    session.commit.assert_not_awaited()
    engine.dispose.assert_awaited_once()
    assert "GROQ_API_KEY" not in data["settings"]
    assert "PRIVATE_EXCEPTION" not in path.read_text(encoding="utf-8")
