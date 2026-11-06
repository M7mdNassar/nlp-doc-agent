import asyncio

import structlog

from src.application.ingestion.pipeline import IngestionPipeline
from src.domain.value_objects.document_id import DocumentId
from src.infrastructure.embeddings.bge_adapter import BGEAdapter
from src.infrastructure.queue.celery_app import celery_app
from src.infrastructure.relational.db import AsyncSessionLocal
from src.infrastructure.relational.repositories.chunk_repository import ChunkRepository
from src.infrastructure.relational.repositories.document_repository import DocumentRepository
from src.infrastructure.vector_store.qdrant_adapter import QdrantAdapter

logger = structlog.get_logger(__name__)


@celery_app.task(name="ingest_document")
def ingest_document_task(document_id: str, file_path: str) -> None:
    """Celery task to run the async pipeline."""
    asyncio.run(_ingest_document_async(document_id, file_path))


async def _ingest_document_async(document_id: str, file_path: str) -> None:
    logger.info(f"Starting ingestion for {document_id}")
    async with AsyncSessionLocal() as session:
        doc_repo = DocumentRepository(session)
        chunk_repo = ChunkRepository(session)
        vector_store = QdrantAdapter()
        embedder = BGEAdapter()

        pipeline = IngestionPipeline(
            doc_repo=doc_repo,
            chunk_repo=chunk_repo,
            vector_store=vector_store,
            embedder=embedder,
        )

        await pipeline.run(DocumentId(document_id), file_path)
    logger.info(f"Finished ingestion for {document_id}")
