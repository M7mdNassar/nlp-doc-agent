import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError as SchemaError
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from qdrant_client import AsyncQdrantClient, models
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.api.chat_stream import stream_error
from src.api.dependencies.providers import get_ask_question_uc
from src.application.agents.analyst.analyst_agent import AnalystAgent
from src.application.agents.answer.answer_agent import AnswerAgent
from src.application.agents.orchestrator.orchestrator import Orchestrator
from src.application.agents.retriever.metadata_filter import MetadataFilterResolver
from src.application.citations.verifier import CitationVerifier
from src.application.ingestion import pipeline
from src.application.tools.analyst_tools import AnalystTools
from src.application.use_cases.ask_question import AskQuestionUseCase
from src.application.use_cases.upload_document import UploadDocumentUseCase
from src.core.config import settings
from src.core.errors import AppError, ValidationError
from src.domain.entities.analysis import AnalysisResult, ToolRequest
from src.domain.entities.answer import AnswerBlock, AnswerDraft, EvidenceReference, GroundingVerdict
from src.domain.entities.chunk import Chunk
from src.domain.entities.conversation import Conversation
from src.domain.entities.document import Document, DocumentStatus
from src.domain.entities.evidence import EvidencePackage
from src.domain.entities.job import JobStatus
from src.domain.exceptions.llm_provider_error import LLMOutputError
from src.domain.value_objects.chunk_id import ChunkId
from src.domain.value_objects.document_id import DocumentId
from src.domain.value_objects.metadata_filters import MetadataFilters
from src.domain.value_objects.parsed_element import ParsedElement
from src.domain.value_objects.sparse_vector import SparseVector
from src.infrastructure.llm.retry import async_retry
from src.infrastructure.parsers.pdf_parser import PDFParser
from src.infrastructure.relational.models import Base, ChunkModel, IngestionClaimModel
from src.infrastructure.relational.repositories.chunk_repository import ChunkRepository
from src.infrastructure.relational.repositories.conversation_repository import (
    ConversationRepository,
)
from src.infrastructure.relational.repositories.document_repository import DocumentRepository
from src.infrastructure.relational.repositories.job_repository import JobRepository
from src.infrastructure.vector_store import qdrant_adapter
from src.infrastructure.vector_store.schema import (
    COLLECTION_NAME,
    DENSE_VECTOR_NAME,
    SPARSE_VECTOR_NAME,
)
from src.main import create_app


@pytest.fixture
async def sessions(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'qa.db'}")
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def refusal():
    return {
        "answer": "Not enough evidence.",
        "state": "insufficient_evidence",
        "loops": 0,
        "evidence_count": 0,
        "sources": [],
        "tool_results": [],
        "conversation_id": "",
    }


async def test_concurrent_conversation_conflict_is_explicit_and_retry_preserves_both(sessions):
    initial = Conversation.create("qa")
    initial.add_message("user", "seed")
    initial.add_message("assistant", "seed answer")
    async with sessions() as s:
        await ConversationRepository(s).save(initial)
    barrier = asyncio.Barrier(2)
    seen = []

    async def process(question, *_):
        await barrier.wait()
        return refusal()

    async def ask(question):
        async with sessions() as s:
            uc = AskQuestionUseCase(
                SimpleNamespace(process=process),
                ConversationRepository(s),
                SimpleNamespace(list_all=AsyncMock(return_value=[])),
            )
            try:
                await uc.execute(question, initial.id, MetadataFilters(doc_ids=[]))
                return "ok", question
            except AppError as exc:
                return exc.code, question

    outcomes = await asyncio.gather(ask("turn A"), ask("turn B"))
    assert sorted(code for code, _ in outcomes) == ["CONVERSATION_CHANGED", "ok"]
    retry = next(q for code, q in outcomes if code != "ok")
    async with sessions() as s:
        repo = ConversationRepository(s)
        loaded = await repo.get(initial.id)
        assert len(loaded.messages) == 4
        seen.extend(m.content for m in loaded.messages)
        uc = AskQuestionUseCase(
            SimpleNamespace(process=AsyncMock(return_value=refusal())),
            repo,
            SimpleNamespace(list_all=AsyncMock(return_value=[])),
        )
        await uc.execute(retry, initial.id, MetadataFilters(doc_ids=[]))
    async with sessions() as s:
        final = await ConversationRepository(s).get(initial.id)
        assert len(final.messages) == 6
        assert sum(m.content == "turn A" for m in final.messages) == 1
        assert sum(m.content == "turn B" for m in final.messages) == 1


@pytest.mark.parametrize("failure", ["none", "parse", "embed", "upsert", "sql_commit"])
async def test_reindex_stages_vectors_and_atomically_publishes(sessions, monkeypatch, failure):
    client = AsyncQdrantClient(location=":memory:")
    monkeypatch.setattr(qdrant_adapter, "AsyncQdrantClient", lambda **_: client)

    async def active(_):
        async with sessions() as s:
            return list((await s.scalars(select(ChunkModel.id))).all())

    vectors = qdrant_adapter.QdrantAdapter(published_ids=active)
    await client.create_collection(
        COLLECTION_NAME,
        vectors_config={
            DENSE_VECTOR_NAME: models.VectorParams(size=3, distance=models.Distance.COSINE)
        },
        sparse_vectors_config={SPARSE_VECTOR_NAME: models.SparseVectorParams()},
    )
    doc = Document(
        DocumentId.generate(), "qa.txt", "txt", "original", status=DocumentStatus.INDEXED
    )
    old = Chunk(ChunkId.generate(), doc.id, "Old evidence 10.", 1, document_name=doc.name)
    async with sessions() as s:
        await DocumentRepository(s).save(doc)
        await ChunkRepository(s).save_batch([old])
    await vectors.upsert([old], [[1.0, 0.0, 0.0]], [SparseVector([1], [1.0])])
    original_upsert = vectors.upsert

    async def stage(*args):
        await original_upsert(*args)
        # Before SQL publication, staged points must not displace the old answer.
        before = await vectors.hybrid_search([1.0, 0.0, 0.0], SparseVector([1], [1.0]), {})
        assert [c.id for c in before.chunks] == [old.id]
        if failure == "upsert":
            raise RuntimeError("Injected partial upsert failure")

    monkeypatch.setattr(vectors, "upsert", stage)
    parser = SimpleNamespace(parse=AsyncMock(return_value=[ParsedElement("New evidence 20.", 1)]))
    if failure == "parse":
        parser.parse.side_effect = RuntimeError("Injected parse failure")
    monkeypatch.setattr(pipeline.parser_factory, "get_parser", lambda _: parser)
    sparse = SimpleNamespace(
        embed=lambda texts: [
            SimpleNamespace(indices=np.array([1]), values=np.array([1.0])) for _ in texts
        ]
    )
    monkeypatch.setattr(pipeline, "SparseTextEmbedding", lambda **_: sparse)
    embedder = SimpleNamespace(
        max_tokens=512, count_tokens=len, embed_documents=AsyncMock(return_value=[[1.0, 0.0, 0.0]])
    )
    if failure == "embed":
        embedder.embed_documents.side_effect = RuntimeError("Injected embedding failure")
    try:
        async with sessions() as s:
            chunks = ChunkRepository(s)
            if failure == "sql_commit":

                async def fail_commit():
                    await s.flush()
                    raise RuntimeError("Injected commit failure")

                monkeypatch.setattr(s, "commit", fail_commit)
            ingestion = pipeline.IngestionPipeline(DocumentRepository(s), chunks, vectors, embedder)
            if failure == "none":
                await ingestion.run(doc.id, "not-read-by-fixture")
            else:
                with pytest.raises(RuntimeError, match="Injected"):
                    await ingestion.run(doc.id, "not-read-by-fixture")
        async with sessions() as s:
            saved = await ChunkRepository(s).get_by_document(doc.id)
            assert (await DocumentRepository(s).get(doc.id)).status == DocumentStatus.INDEXED
            assert [c.text for c in saved] == [
                "New evidence 20." if failure == "none" else old.text
            ]
        found = await vectors.hybrid_search([1.0, 0.0, 0.0], SparseVector([1], [1.0]), {})
        assert [c.text for c in found.chunks] == [saved[0].text]
    finally:
        await client.close()


async def test_concurrent_reindex_claim_and_terminal_release(sessions, monkeypatch, tmp_path):
    from src.application.use_cases import upload_document

    monkeypatch.setattr(settings, "DATA_DIR", str(tmp_path))
    doc = Document(DocumentId.generate(), "qa.txt", "txt", "claim", status=DocumentStatus.INDEXED)
    path = tmp_path / "uploads" / f"{doc.id}.txt"
    path.parent.mkdir()
    path.write_text("data")
    async with sessions() as s:
        await DocumentRepository(s).save(doc)
    barrier = asyncio.Barrier(2)
    send = []
    monkeypatch.setattr(upload_document.celery_app, "send_task", lambda *a, **k: send.append(k))

    async def reindex():
        async with sessions() as s:
            jobs = JobRepository(s)

            async def latest(_):
                await barrier.wait()
                return None

            monkeypatch.setattr(jobs, "latest_for_document", latest)
            uc = UploadDocumentUseCase(DocumentRepository(s), jobs)
            try:
                return (await uc.reindex(doc.id))[1]
            except ValidationError:
                return None

    results = await asyncio.gather(reindex(), reindex())
    assert len(send) == 1 and sum(r is not None for r in results) == 1
    job = next(r for r in results if r is not None)
    async with sessions() as s:
        job.status = JobStatus.COMPLETED
        await JobRepository(s).save(job)
        assert not list((await s.scalars(select(IngestionClaimModel))).all())
        # A later legitimate reindex is admitted and keeps the current document usable.
        await UploadDocumentUseCase(DocumentRepository(s), JobRepository(s)).reindex(doc.id)
        assert (await DocumentRepository(s).get(doc.id)).status == DocumentStatus.INDEXED


async def test_queue_failure_releases_claim_and_keeps_working_document(
    sessions, monkeypatch, tmp_path
):
    from src.application.use_cases import upload_document

    monkeypatch.setattr(settings, "DATA_DIR", str(tmp_path))
    doc = Document(DocumentId.generate(), "qa.txt", "txt", "queue", status=DocumentStatus.INDEXED)
    path = tmp_path / "uploads" / f"{doc.id}.txt"
    path.parent.mkdir()
    path.write_text("data")

    def fail(*a, **k):
        raise RuntimeError("queue down")

    monkeypatch.setattr(upload_document.celery_app, "send_task", fail)
    async with sessions() as s:
        await DocumentRepository(s).save(doc)
        with pytest.raises(AppError) as raised:
            await UploadDocumentUseCase(DocumentRepository(s), JobRepository(s)).reindex(doc.id)
        assert raised.value.code == "QUEUE_UNAVAILABLE"
        assert (await DocumentRepository(s).get(doc.id)).status == DocumentStatus.INDEXED
        assert not list((await s.scalars(select(IngestionClaimModel))).all())
        assert path.read_text() == "data"


def numbered_pdf(path: Path):
    writer = PdfWriter()
    page = writer.add_blank_page(612, 792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    stream = DecodedStreamObject()
    stream.set_data(
        b"BT /F1 12 Tf 50 730 Td (4. Main results) Tj 0 -20 Td "
        b"(Accuracy is 0.914.) Tj 0 -30 Td (5. Operational performance) Tj "
        b"0 -20 Td (Median latency is 18.6 ms.) Tj ET"
    )
    page[NameObject("/Contents")] = writer._add_object(stream)
    writer.write(path)


async def test_numbered_pdf_headings_populate_following_sections(tmp_path):
    p = tmp_path / "numbered.pdf"
    numbered_pdf(p)
    elements = await PDFParser().parse(p)
    assert any(e.section == "4. Main results" and "0.914" in e.text for e in elements)
    assert any(e.section == "5. Operational performance" and "18.6 ms" in e.text for e in elements)


@pytest.mark.parametrize(
    "question,field,expected",
    [
        ("Compare page 2 and page 3", "pages", [2, 3]),
        ("Compare pages 2, 4 and 6", "pages", [2, 4, 6]),
        ("Read pages 2-4", "pages", [2, 3, 4]),
        ("Compare section 4 and section 5", "sections", ["4", "5"]),
        ("Read sections 4.1 to 4.3", "sections", ["4.1", "4.2", "4.3"]),
    ],
)
def test_multiple_constraints(question, field, expected):
    result = MetadataFilterResolver().resolve(question, []).model_dump(exclude_none=True)
    assert result[field] == expected


def test_constraints_intersect_hard_scope_and_bound_ranges():
    r = MetadataFilterResolver()
    assert r.resolve("Read pages 2-4", [], MetadataFilters(page=9)).pages == []
    assert r.resolve("Read sections 2 and 4", [], MetadataFilters(sections=["4"])).sections == ["4"]
    with pytest.raises(ValidationError):
        r.resolve("Read pages 1-10000000", [])


@pytest.mark.parametrize("allowed", [["doc_11111111", "doc_22222222"], ["doc_22222222"]])
async def test_followup_resolves_against_original_user_selection(allowed):
    docs = [
        Document(DocumentId("doc_11111111"), "paper1_ml.pdf", "pdf", "a"),
        Document(DocumentId("doc_22222222"), "paper2_ml.pdf", "pdf", "b"),
    ]
    conversation = Conversation.create("qa")
    conversation.add_message("user", "Explain paper1_ml.pdf")
    retriever = SimpleNamespace(retrieve=AsyncMock(return_value=EvidencePackage()))
    orch = Orchestrator(
        SimpleNamespace(rewrite=AsyncMock(return_value="Compare paper1_ml.pdf and paper2_ml.pdf")),
        retriever,
        SimpleNamespace(analyze=AsyncMock(return_value=AnalysisResult(False, "missing"))),
        SimpleNamespace(),
        CitationVerifier(),
    )
    uc = AskQuestionUseCase(
        orch,
        SimpleNamespace(get=AsyncMock(return_value=conversation), save=AsyncMock()),
        SimpleNamespace(list_all=AsyncMock(return_value=docs)),
    )
    await uc.execute(
        "Now compare that model with paper2_ml.pdf",
        conversation.id,
        MetadataFilters(doc_ids=allowed),
    )
    assert retriever.retrieve.await_args.args[1]["doc_ids"] == allowed


@pytest.mark.parametrize("expression,value", [("a +", "18.6"), ("a ** 0", "0")])
async def test_tool_input_failures_use_the_existing_single_correction(expression, value):
    chunk = Chunk(ChunkId.generate(), DocumentId.generate(), f"Value is {value}.", 1)
    plan = {
        "tools": [
            {
                "name": "calculator",
                "arguments": {
                    "expression": expression,
                    "values": {
                        "a": {"chunk_id": str(chunk.id), "quote": chunk.text, "value": value}
                    },
                },
            }
        ],
        "verdict": None,
    }
    corrected = {
        "tools": [],
        "verdict": {
            "has_enough_evidence": True,
            "missing_info": "",
            "conflict_detected": False,
            "findings": [{"text": chunk.text, "quote_ids": ["quote_1"]}],
        },
    }
    llm = SimpleNamespace(generate=AsyncMock(side_effect=[json.dumps(plan), json.dumps(corrected)]))
    result = await AnalystAgent(llm).analyze(
        "Find the supplied value", EvidencePackage.from_chunks([chunk])
    )
    assert result.has_enough_evidence
    assert llm.generate.await_count == 2
    assert (
        "correction" in llm.generate.await_args.args[0].lower()
        or "failed validation" in llm.generate.await_args.args[0]
    )


def test_sentence_punctuation_quote_is_valid_but_decimal_substrings_are_not():
    chunk = Chunk(ChunkId.generate(), DocumentId.generate(), "Latency is 18.6 ms. Count 192.", 1)
    tools = AnalystTools(EvidencePackage.from_chunks([chunk]))

    def request(quote, value):
        return ToolRequest(
            name="calculator",
            arguments={
                "expression": "a*2",
                "values": {"a": {"chunk_id": str(chunk.id), "quote": quote, "value": value}},
            },
        )

    assert tools.execute(request("18.6 ms", "18.6")).output["result"] == "37.2"
    for quote, value in [("92", "92"), ("18", "18"), ("18.60", "18.60")]:
        with pytest.raises(ValueError):
            tools.execute(request(quote, value))


async def test_review_receives_question_and_rejects_grounded_wrong_metric():
    chunk = Chunk(ChunkId.generate(), DocumentId.generate(), "Median 18.6 ms. P95 31.4 ms.", 1)
    draft = AnswerDraft(
        blocks=[
            AnswerBlock(
                text="Median is 18.6 ms.",
                citations=[EvidenceReference(chunk_id=str(chunk.id), quote=chunk.text)],
            )
        ]
    )
    llm = SimpleNamespace(
        generate=AsyncMock(
            return_value=json.dumps(
                {
                    "answers_question": False,
                    "supported": [True],
                    "qualifications_preserved": [True],
                    "no_added_details": [True],
                    "feedback": ["P95 requested; median answered"],
                    "missing_info": "",
                }
            )
        )
    )
    verdict = await AnswerAgent(llm).review(
        draft,
        EvidencePackage.from_chunks([chunk]),
        AnalysisResult(True, ""),
        question="What is P95?",
    )
    assert not verdict.accepts(1)
    assert json.loads(llm.generate.await_args.args[0])["question"] == "What is P95?"
    with pytest.raises(SchemaError):
        GroundingVerdict(supported=[True], qualifications_preserved=[True], no_added_details=[True])


async def test_truncated_provider_output_is_not_retried_as_transport():
    calls = 0

    @async_retry(max_retries=3, base_delay=0)
    async def incomplete():
        nonlocal calls
        calls += 1
        raise LLMOutputError("test")

    with pytest.raises(LLMOutputError):
        await incomplete()
    assert calls == 1
    assert stream_error(LLMOutputError("test"))["code"] == "LLM_OUTPUT_INVALID"


@pytest.mark.parametrize("stream", [False, True])
async def test_json_and_stream_expose_output_errors_without_fabricated_answers(stream):
    app = create_app()
    app.dependency_overrides[get_ask_question_uc] = lambda: SimpleNamespace(
        execute=AsyncMock(side_effect=LLMOutputError("test"))
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/chat/stream" if stream else "/chat", json={"message": "question"})
    if stream:
        events = [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")]
        assert [e["type"] for e in events] == ["error"]
        assert events[0]["error"]["code"] == "LLM_OUTPUT_INVALID"
    else:
        assert r.status_code == 503 and r.json()["code"] == "LLM_OUTPUT_INVALID"


async def test_question_deadline_cancels_generation_without_saving_turn(monkeypatch):
    monkeypatch.setattr(settings, "QUESTION_TIMEOUT_SECONDS", 0.02)
    cancelled = asyncio.Event()

    async def wait(*_):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    conversations = SimpleNamespace(save=AsyncMock())
    uc = AskQuestionUseCase(
        SimpleNamespace(process=wait),
        conversations,
        SimpleNamespace(list_all=AsyncMock(return_value=[])),
    )
    with pytest.raises(AppError) as exc:
        await uc.execute("question", filters=MetadataFilters(doc_ids=[]))
    assert exc.value.code == "QUESTION_TIMEOUT" and exc.value.status_code == 504
    assert cancelled.is_set()
    conversations.save.assert_not_awaited()


async def test_unchanged_evidence_does_not_repeat_the_same_insufficient_analysis():
    chunk = Chunk(ChunkId.generate(), DocumentId.generate(), "Known evidence.", 1)
    analyst = SimpleNamespace(
        analyze=AsyncMock(return_value=AnalysisResult(False, "Missing salary"))
    )
    answer = SimpleNamespace(generate=AsyncMock())
    retrieval = SimpleNamespace(
        retrieve=AsyncMock(return_value=EvidencePackage.from_chunks([chunk]))
    )
    orch = Orchestrator(
        SimpleNamespace(rewrite=AsyncMock(return_value="salary")),
        retrieval,
        analyst,
        answer,
        CitationVerifier(),
    )
    result = await orch.process("What is the salary?")
    assert result["state"] == "insufficient_evidence"
    assert retrieval.retrieve.await_count == 2
    assert analyst.analyze.await_count == 1
    answer.generate.assert_not_awaited()
