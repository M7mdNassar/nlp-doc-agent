"""Opt-in capture of ONE normal question against existing indexed documents.

Contains document text, drafts and reviewer feedback. Never enable globally or log
the artifact. Run through diagnose-attention.ps1; no conversation or document writes.
"""

import argparse
import asyncio
import json
import os
from collections.abc import AsyncGenerator
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from src.core.observability import current_trace, question_scope, stage
from src.domain.entities.document import DocumentStatus
from src.domain.entities.evidence import EvidencePackage
from src.domain.ports.llm import LLMClient
from src.domain.value_objects.token_budget import TokenBudget


def evidence_data(evidence: EvidencePackage) -> list[dict[str, Any]]:
    return [
        {
            **asdict(chunk),
            "id": str(chunk.id),
            "document_id": str(chunk.document_id),
            "parent_id": str(chunk.parent_id) if chunk.parent_id else None,
        }
        for chunk in evidence.chunks
    ]


class Capture:
    def __init__(self, output: Path, question: str):
        # Reserve the output before any provider calls; do not overwrite older evidence.
        descriptor = os.open(output, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        self.file = os.fdopen(descriptor, "w+", encoding="utf-8")
        self.data: dict[str, Any] = {
            "format_version": 1,
            "created_at": datetime.now(UTC).isoformat(),
            "contains_document_content": True,
            "question": question,
            "history": [],
            "llm_calls": [],
            "retrievals": [],
            "answer_attempts": [],
        }
        self.flush()

    def flush(self) -> None:
        trace = current_trace()
        if trace:
            self.data["question_id"] = trace.question_id
            self.data["usage"] = trace.summary()
        encoded = json.dumps(self.data, ensure_ascii=False, indent=2)
        self.file.seek(0)
        self.file.write(encoded)
        self.file.truncate()
        self.file.flush()

    def close(self) -> None:
        try:
            self.flush()
        finally:
            self.file.close()


class RecordingLLM:
    def __init__(self, inner: LLMClient, capture: Capture):
        self.inner, self.capture = inner, capture

    async def generate(self, prompt: str, system: str, budget: TokenBudget) -> str:
        trace = current_trace()
        start = len(trace.requests) if trace else 0
        record = {
            "stage": structlog.contextvars.get_contextvars().get("stage", "unclassified"),
            "system_prompt": system,
            "user_prompt": prompt,
        }
        self.capture.data["llm_calls"].append(record)
        self.capture.flush()
        try:
            response = await self.inner.generate(prompt, system, budget)
            record["response"] = response
            return response
        except BaseException as exc:
            # Do not capture exception messages, headers or provider/account credentials.
            record["error_type"] = type(exc).__name__
            raise
        finally:
            if trace:
                record["provider_requests"] = [asdict(r) for r in trace.requests[start:]]
            self.capture.flush()

    async def stream(
        self, prompt: str, system: str, budget: TokenBudget
    ) -> AsyncGenerator[str, None]:
        raise NotImplementedError("This diagnostic captures the non-streaming chat pipeline")
        yield ""  # pragma: no cover


class RecordingRetriever:
    def __init__(self, inner: Any, capture: Capture):
        self.inner, self.capture = inner, capture

    async def retrieve(self, query: str, filters: dict[str, Any] | None = None) -> EvidencePackage:
        evidence = await self.inner.retrieve(query, filters)
        self.capture.data["retrievals"].append(
            {
                "query": query,
                "filters": filters,
                "chunks": evidence_data(evidence),
            }
        )
        self.capture.flush()
        return evidence


class RecordingAnswer:
    def __init__(self, inner: Any, capture: Capture):
        self.inner, self.capture = inner, capture

    async def generate(
        self, question: str, evidence: EvidencePackage, analysis: Any, **kwargs: Any
    ) -> Any:
        record = {
            "attempt": len(self.capture.data["answer_attempts"]) + 1,
            "selected_evidence": evidence_data(evidence),
            "analysis": {
                "has_enough_evidence": analysis.has_enough_evidence,
                "missing_info": analysis.missing_info,
                "conflict_detected": analysis.conflict_detected,
                "findings": [finding.model_dump() for finding in analysis.findings],
                "tool_results": [asdict(result) for result in analysis.tool_results],
            },
            "correction_feedback_received": kwargs.get("review_feedback"),
        }
        self.capture.data["answer_attempts"].append(record)
        self.capture.flush()
        try:
            draft = await self.inner.generate(question, evidence, analysis, **kwargs)
            record["draft"] = draft.model_dump()
            return draft
        except BaseException as exc:
            record["generation_error_type"] = type(exc).__name__
            raise
        finally:
            self.capture.flush()

    async def review(self, draft: Any, evidence: EvidencePackage, analysis: Any) -> Any:
        record = self.capture.data["answer_attempts"][-1]
        try:
            review = await self.inner.review(draft, evidence, analysis)
            record["review"] = review.model_dump()
            record["accepted"] = review.accepts(len(draft.blocks))
            return review
        except BaseException as exc:
            record["review_error_type"] = type(exc).__name__
            raise
        finally:
            self.capture.flush()


def attach_capture(orchestrator: Any, capture: Capture) -> None:
    for agent in (orchestrator.rewriter, orchestrator.analyst, orchestrator.answer_agent):
        agent.llm = RecordingLLM(agent.llm, capture)
    orchestrator.retriever = RecordingRetriever(orchestrator.retriever, capture)
    orchestrator.answer_agent = RecordingAnswer(orchestrator.answer_agent, capture)


def select_document(documents: list[Any], name: str) -> Any:
    matches = [d for d in documents if d.name.casefold() == name.casefold()]
    if len(matches) != 1:
        raise ValueError("Expected exactly one document with the requested filename")
    if matches[0].status != DocumentStatus.INDEXED:
        raise ValueError("The requested document must finish indexing first")
    return matches[0]


async def run(output: Path, question: str, document_name: str) -> int:
    capture = Capture(output, question)
    database_engine = None
    with question_scope():
        try:
            # Lazy imports keep --help usable without creating clients/loading models.
            from src.api.dependencies.providers import get_ask_question_uc
            from src.core.config import settings
            from src.infrastructure.relational.db import AsyncSessionLocal, engine
            from src.infrastructure.relational.repositories.document_repository import (
                DocumentRepository,
            )

            database_engine = engine
            capture.data["settings"] = {
                "llm_model": settings.LLM_MODEL,
                "llm_fallback_models": settings.LLM_FALLBACK_MODELS,
                "embedding_model": settings.EMBEDDING_MODEL,
                "requested_embedding_device": settings.EMBEDDING_DEVICE,
                "embedding_batch_size": settings.EMBEDDING_BATCH_SIZE,
                "reranker_model": settings.RERANKER_MODEL,
                "requested_reranker_device": settings.RERANKER_DEVICE,
                "reranker_batch_size": settings.RERANKER_BATCH_SIZE,
            }
            async with AsyncSessionLocal() as session:
                with stage("document_lookup"):
                    documents = await DocumentRepository(session).list_all()
                    document = select_document(documents, document_name)
                capture.data["document"] = {
                    "id": str(document.id),
                    "name": document.name,
                    "checksum": document.checksum,
                }
                uc = get_ask_question_uc(session)
                capture.data["actual_reranker_device"] = str(
                    uc.orchestrator.retriever.reranker.model.device
                )
                capture.data["actual_embedding_device"] = str(
                    uc.orchestrator.retriever.embedder.model.device
                )
                attach_capture(uc.orchestrator, capture)
                # Call the same orchestrator directly to avoid saving a conversation.
                capture.data["result"] = await uc.orchestrator.process(
                    question,
                    filters={"doc_ids": [str(document.id)]},
                    history=[],
                    documents=[document],
                )
            return 0
        except Exception as exc:
            capture.data["error"] = {"type": type(exc).__name__}
            return 1
        finally:
            # Close aiosqlite's pooled connections/background threads so this
            # process exits and the launcher can restart the backend.
            if database_engine is not None:
                try:
                    await database_engine.dispose()
                except Exception as exc:
                    capture.data["cleanup_error_type"] = type(exc).__name__
            capture.close()
            print(
                json.dumps(
                    {
                        "diagnostic_file": str(output),
                        "question_id": capture.data.get("question_id"),
                        "state": capture.data.get("result", {}).get("state"),
                        "error": capture.data.get("error"),
                    }
                ),
                flush=True,
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document-name", default="attention.pdf")
    parser.add_argument(
        "--question", default="how does attention work in transformers, answer in 50 words"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    return asyncio.run(run(args.output, args.question, args.document_name))


if __name__ == "__main__":
    raise SystemExit(main())
