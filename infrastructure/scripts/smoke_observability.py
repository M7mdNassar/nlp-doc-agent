"""Live Groq/API check with synthetic in-memory evidence; no user-document or DB writes.

Run with backend's PYTHONPATH and configured GROQ_API_KEY. This consumes provider tokens.
Retrieval is fixed to isolate the changed prompts, verification, and usage accounting.
"""

import asyncio
import json
from types import SimpleNamespace

import httpx
from src.api.dependencies.providers import get_ask_question_uc
from src.application.agents.analyst.analyst_agent import AnalystAgent
from src.application.agents.answer.answer_agent import AnswerAgent
from src.application.agents.orchestrator.orchestrator import Orchestrator
from src.application.agents.retriever.query_rewriter import QueryRewriter
from src.application.citations.verifier import CitationVerifier
from src.application.use_cases.ask_question import AskQuestionUseCase
from src.core.observability import question_scope, stage
from src.domain.entities.analysis import AnalysisResult
from src.domain.entities.answer import AnswerBlock, AnswerDraft, EvidenceReference
from src.domain.entities.chunk import Chunk
from src.domain.entities.document import Document
from src.domain.entities.evidence import EvidencePackage
from src.domain.value_objects.chunk_id import ChunkId
from src.domain.value_objects.document_id import DocumentId
from src.infrastructure.llm.router import LLMRouter
from src.main import create_app


async def main() -> None:
    text = (
        "Trial A completed 18 of 20 checks. The evaluation was conducted in simulation. "
        "Real-world deployment performance was not measured."
    )
    documents = [
        Document(DocumentId("doc_diagnostics_a"), "Synthetic report.pdf", "pdf", "a"),
        Document(DocumentId("doc_diagnostics_b"), "Synthetic copy.docx", "docx", "b"),
    ]
    chunks = [
        Chunk(
            ChunkId(f"chunk_diagnostics_{i}"), doc.id, text, 1, document_name=doc.name
        )
        for i, doc in enumerate(documents)
    ]
    evidence = EvidencePackage.from_chunks(chunks)
    llm = LLMRouter()
    answer = AnswerAgent(llm)

    async def retrieve(*args):
        return evidence

    async def list_documents():
        return documents

    async def save(conversation):
        pass

    uc = AskQuestionUseCase(
        Orchestrator(
            QueryRewriter(llm),
            SimpleNamespace(retrieve=retrieve),
            AnalystAgent(llm),
            answer,
            CitationVerifier(),
        ),
        SimpleNamespace(save=save),
        SimpleNamespace(list_all=list_documents),
    )
    app = create_app()
    app.dependency_overrides[get_ask_question_uc] = lambda: uc
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/chat",
            json={
                "message": "What percentage of checks did Trial A complete, and in what evaluation setting?"
            },
        )
    result = response.json()
    assert response.status_code == 200, result
    assert result["state"] == "answer_ready", result
    assert "90" in result["answer"] and "simulation" in result["answer"].lower(), result
    assert result["sources"] and result["tool_results"], result
    assert result["question_id"] == response.headers["x-question-id"]
    usage = result["usage"]
    assert usage["usage_reported_requests"] >= 5 and usage["total_tokens"] > 0, usage
    assert usage["total_tokens"] == sum(
        call["total_tokens"] or 0 for call in usage["calls"]
    )
    assert {
        "query_rewrite",
        "tool_plan",
        "analysis_verdict",
        "answer_generation",
        "answer_verification",
    } <= {call["stage"] for call in usage["calls"]}
    print(
        json.dumps(
            {
                "case": "live_question",
                "status": "passed",
                "question_id": result["question_id"],
                "usage": usage,
                "answer": result["answer"],
            }
        ),
        flush=True,
    )

    # A real citation must not authorize a false deployment claim.
    incorrect = AnswerDraft(
        blocks=[
            AnswerBlock(
                text="Trial A completed 90% of checks in real-world deployment.",
                citations=[EvidenceReference(chunk_id=str(chunks[0].id), quote=text)],
            )
        ]
    )
    with question_scope() as trace, stage("answer_verification"):
        verdict = await answer.review(incorrect, evidence, AnalysisResult(True, ""))
        assert not verdict.accepts(1), verdict
    print(
        json.dumps(
            {
                "case": "unsupported_deployment_rejected",
                "status": "passed",
                "question_id": trace.question_id,
                "usage": trace.summary(),
            }
        ),
        flush=True,
    )
    print(json.dumps({"status": "passed", "checks": 2}), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
