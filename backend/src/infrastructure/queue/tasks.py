import asyncio

import structlog

from src.application.ingestion.pipeline import IngestionPipeline
from src.domain.entities.job import JobStatus
from src.domain.value_objects.document_id import DocumentId
from src.infrastructure.embeddings.bge_adapter import BGEAdapter
from src.infrastructure.queue.celery_app import celery_app
from src.infrastructure.relational.db import AsyncSessionLocal
from src.infrastructure.relational.repositories.chunk_repository import ChunkRepository
from src.infrastructure.relational.repositories.document_repository import DocumentRepository
from src.infrastructure.relational.repositories.job_repository import JobRepository
from src.infrastructure.vector_store.qdrant_adapter import QdrantAdapter

logger = structlog.get_logger(__name__)


@celery_app.task(name="ingest_document")  # type: ignore
def ingest_document_task(document_id: str, file_path: str, job_id: str | None = None) -> None:
    asyncio.run(_ingest_document_async(document_id, file_path, job_id))


async def _ingest_document_async(
    document_id: str, file_path: str, job_id: str | None = None
) -> None:
    async with AsyncSessionLocal() as session:
        jobs = JobRepository(session)
        job = await jobs.get(job_id) if job_id else await jobs.latest_for_document(document_id)
        if job is None:
            raise ValueError("Ingestion job not found")
        if str(job.document_id) != document_id:
            raise ValueError("Job does not belong to this document")
        if job.status == JobStatus.COMPLETED:
            return
        documents = DocumentRepository(session)
        vector_store = None
        try:
            job.status, job.error = JobStatus.PROCESSING, None
            await jobs.save(job)
            vector_store = QdrantAdapter()
            pipeline = IngestionPipeline(
                documents, ChunkRepository(session), vector_store, BGEAdapter()
            )
            await pipeline.run(DocumentId(document_id), file_path)
            job.status = JobStatus.COMPLETED
            await jobs.save(job)
        except Exception as exc:
            await session.rollback()
            job.status, job.error = JobStatus.FAILED, str(exc)
            await jobs.save(job)
            doc = await documents.get(DocumentId(document_id))
            if doc:
                doc.mark_failed(str(exc))
                await documents.save(doc)
            logger.exception("ingestion_job_failed", job_id=job.job_id)
            raise
        finally:
            if vector_store is not None:
                await vector_store.client.close()
