import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import numpy as np
import pytest
from qdrant_client import AsyncQdrantClient, models
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.application.use_cases.upload_document import UploadDocumentUseCase
from src.core.config import settings
from src.core.errors import ValidationError
from src.domain.entities.chunk import Chunk
from src.domain.entities.conversation import Conversation
from src.domain.entities.document import Document, DocumentStatus
from src.domain.entities.job import Job, JobStatus
from src.domain.value_objects.chunk_id import ChunkId
from src.domain.value_objects.document_id import DocumentId
from src.domain.value_objects.sparse_vector import SparseVector
from src.infrastructure.relational.models import Base, JobModel
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


@pytest.fixture
async def database(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def local_vectors(monkeypatch):
    client = AsyncQdrantClient(location=":memory:")
    monkeypatch.setattr(qdrant_adapter, "AsyncQdrantClient", lambda **kwargs: client)
    adapter = qdrant_adapter.QdrantAdapter()
    await client.create_collection(
        COLLECTION_NAME,
        vectors_config={
            DENSE_VECTOR_NAME: models.VectorParams(size=3, distance=models.Distance.COSINE)
        },
        sparse_vectors_config={SPARSE_VECTOR_NAME: models.SparseVectorParams()},
    )
    return adapter


def structured_chunk(doc):
    return Chunk(
        ChunkId.generate(),
        doc.id,
        "| Metric | Value |\n|---|---|\n| Accuracy | 92 |",
        4,
        section="Section 2 Results",
        document_name=doc.name,
        file_type="pdf",
        author="Ada Lovelace",
        date="2026-11-07",
        chapter="4",
        table_data={"headers": ["Metric", "Value"], "rows": [["Accuracy", "92"]]},
    )


async def test_metadata_and_tables_round_trip_through_sqlite_and_qdrant(database, monkeypatch):
    vectors = await local_vectors(monkeypatch)
    doc = Document(DocumentId.generate(), "paper.pdf", "pdf", "unique")
    chunk = structured_chunk(doc)
    try:
        async with database() as session:
            await DocumentRepository(session).save(doc)
            await ChunkRepository(session).save_batch([chunk])
        async with database() as session:
            stored = await ChunkRepository(session).get_by_document(doc.id)
            assert stored == [chunk]
        await vectors.upsert(stored, [[1.0, 0.0, 0.0]], [SparseVector([1], [1.0])])
        filters = {
            "document_name": "PAPER.PDF",
            "chapter": "4",
            "page": 4,
            "section": "2",
            "author": "ada lovelace",
            "date": "2026-11-07",
            "file_type": "pdf",
        }
        evidence = await vectors.hybrid_search([1.0, 0.0, 0.0], SparseVector([1], [1.0]), filters)
        assert evidence.chunks == [chunk]
        assert evidence.tables[0].rows == [["Accuracy", "92"]]
        assert (
            await vectors.hybrid_search([1.0, 0.0, 0.0], SparseVector([1], [1.0]), {"chapter": "5"})
        ).is_empty
        assert (
            await vectors.hybrid_search([1.0, 0.0, 0.0], SparseVector([1], [1.0]), {"doc_ids": []})
        ).is_empty
    finally:
        await vectors.client.close()


async def test_conversation_survives_new_database_session(database):
    conversation = Conversation.create("local")
    conversation.add_message("user", "What is RAG?")
    async with database() as session:
        await ConversationRepository(session).save(conversation)
    async with database() as session:
        loaded = await ConversationRepository(session).get(conversation.id)
        assert loaded == conversation
        loaded.add_message("assistant", "Retrieval augmented generation.")
        await ConversationRepository(session).save(loaded)
    async with database() as session:
        assert len((await ConversationRepository(session).get(conversation.id)).messages) == 2


async def test_upload_deduplicates_and_reindex_preserves_document_id(
    database, monkeypatch, tmp_path
):
    from src.application.use_cases import upload_document

    monkeypatch.setattr(settings, "DATA_DIR", str(tmp_path))
    send = []
    monkeypatch.setattr(
        upload_document.celery_app, "send_task", lambda *args, **kwargs: send.append(kwargs)
    )
    async with database() as session:
        documents, jobs = DocumentRepository(session), JobRepository(session)
        use_case = UploadDocumentUseCase(documents, jobs)
        doc, job = await use_case.execute("sample.txt", "txt", b"Example content")
        same_doc, same_job = await use_case.execute("copy.txt", "txt", b"Example content")
        assert same_doc.id == doc.id and same_job.job_id == job.job_id
        assert len(send) == 1 and send[0]["args"][2] == job.job_id
        # Pre-upgrade jobs could remain queued even though their documents were indexed.
        doc.status = DocumentStatus.INDEXED
        await documents.save(doc)
        reindexed, new_job = await use_case.reindex(doc.id)
        assert reindexed.id == doc.id and new_job.job_id != job.job_id
        assert len(send) == 2


@pytest.mark.parametrize(("file_type", "content"), [("exe", b"x"), ("txt", b"")])
async def test_unsupported_and_empty_uploads_rejected_before_writing(
    database, monkeypatch, tmp_path, file_type, content
):
    monkeypatch.setattr(settings, "DATA_DIR", str(tmp_path))
    async with database() as session:
        use_case = UploadDocumentUseCase(DocumentRepository(session), JobRepository(session))
        with pytest.raises(ValidationError):
            await use_case.execute("bad." + file_type, file_type, content)
        assert not (tmp_path / "uploads").exists()


async def test_ingestion_uses_real_parsers_sqlite_and_vector_storage(
    database, monkeypatch, tmp_path
):
    from docx import Document as WordDocument

    from src.application.ingestion import pipeline

    document = WordDocument()
    document.add_heading("Chapter 4 Findings", 1)
    document.add_paragraph("Accuracy is 92%.")
    table = document.add_table(rows=2, cols=2)
    for row, values in zip(table.rows, [("Metric", "Value"), ("Accuracy", "92")], strict=True):
        for cell, value in zip(row.cells, values, strict=True):
            cell.text = value
    path = tmp_path / "sample.docx"
    document.save(path)
    doc = Document(DocumentId.generate(), path.name, "docx", "checksum")
    vectors = await local_vectors(monkeypatch)
    embedder = SimpleNamespace(
        max_tokens=512,
        count_tokens=len,
        embed_documents=AsyncMock(side_effect=lambda texts: [[1.0, 0.0, 0.0] for _ in texts]),
    )
    sparse = SimpleNamespace(
        embed=lambda texts: [
            SimpleNamespace(indices=np.array([1]), values=np.array([1.0])) for _ in texts
        ]
    )
    monkeypatch.setattr(pipeline, "SparseTextEmbedding", lambda **kwargs: sparse)
    try:
        async with database() as session:
            documents, chunks = DocumentRepository(session), ChunkRepository(session)
            await documents.save(doc)
            ingestion = pipeline.IngestionPipeline(documents, chunks, vectors, embedder)
            await ingestion.run(doc.id, str(path))
            count_before = (await vectors.client.count(COLLECTION_NAME)).count
            await ingestion.run(doc.id, str(path))
            assert (await vectors.client.count(COLLECTION_NAME)).count == count_before
            assert (await documents.get(doc.id)).status == DocumentStatus.INDEXED
            evidence = await vectors.hybrid_search(
                [1.0, 0.0, 0.0], SparseVector([1], [1.0]), {"chapter": "4"}
            )
            assert evidence.tables and evidence.tables[0].rows == [["Accuracy", "92"]]
            assert all(c.document_name == "sample.docx" for c in evidence.chunks)
    finally:
        await vectors.client.close()


@pytest.mark.parametrize("failed", [False, True])
async def test_worker_updates_job_status_and_propagates_failures(database, monkeypatch, failed):
    from src.infrastructure.queue import tasks

    doc = Document(DocumentId.generate(), "test.txt", "txt", "checksum")
    job = Job("job-test", doc.id)
    async with database() as session:
        await DocumentRepository(session).save(doc)
        await JobRepository(session).save(job)
    monkeypatch.setattr(tasks, "AsyncSessionLocal", database)
    monkeypatch.setattr(tasks, "BGEAdapter", lambda: object())
    close = AsyncMock()
    monkeypatch.setattr(
        tasks, "QdrantAdapter", lambda: SimpleNamespace(client=SimpleNamespace(close=close))
    )

    class Pipeline:
        def __init__(self, *args):
            self.documents = args[0]

        async def run(self, doc_id, path):
            async with database() as session:
                assert (await JobRepository(session).get(job.job_id)).status == JobStatus.PROCESSING
            if failed:
                raise ValueError("Broken PDF")
            document = await self.documents.get(doc_id)
            document.status = DocumentStatus.INDEXED
            await self.documents.save(document)

    monkeypatch.setattr(tasks, "IngestionPipeline", Pipeline)
    if failed:
        with pytest.raises(ValueError, match="Broken PDF"):
            await tasks._ingest_document_async(str(doc.id), "unused.txt", job.job_id)
    else:
        await tasks._ingest_document_async(str(doc.id), "unused.txt", job.job_id)
    async with database() as session:
        loaded = await JobRepository(session).get(job.job_id)
        assert loaded.status == (JobStatus.FAILED if failed else JobStatus.COMPLETED)
        assert loaded.error == ("Broken PDF" if failed else None)
    close.assert_awaited_once()


async def test_deleting_document_removes_related_jobs_and_chunks(database):
    doc = Document(DocumentId.generate(), "delete.pdf", "pdf", "delete")
    async with database() as session:
        repo = DocumentRepository(session)
        await repo.save(doc)
        await JobRepository(session).save(Job("job-delete", doc.id))
        await ChunkRepository(session).save_batch([structured_chunk(doc)])
        await repo.delete(doc.id)
        assert not (await session.scalars(select(JobModel))).all()
        assert await ChunkRepository(session).get_by_document(doc.id) == []


def test_database_upgrade_preserves_existing_documents_and_adds_new_fields(tmp_path):
    path = tmp_path / "migration.db"
    environment = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{path}"}
    backend = Path(__file__).resolve().parents[1]

    def migrate(revision):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", revision],
            cwd=backend,
            env=environment,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr

    migrate("158962a00ee8")
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO documents (id,name,file_type,checksum,status,page_count,access_tags,created_at) VALUES (?,?,?,?,?,?,?,?)",
            ("doc_existing", "original.pdf", "pdf", "sum", "indexed", 1, "", "2026-11-07"),
        )
    migrate("head")
    migrate("head")
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT name FROM documents").fetchone() == ("original.pdf",)
        assert "metadata_json" in {
            row[1] for row in connection.execute("PRAGMA table_info(chunks)")
        }
        assert connection.execute("SELECT COUNT(*) FROM conversations").fetchone() == (0,)
