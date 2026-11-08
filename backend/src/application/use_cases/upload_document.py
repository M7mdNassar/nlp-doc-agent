import hashlib
import uuid
from pathlib import Path

from src.core.config import settings
from src.core.errors import AppError, NotFoundError, ValidationError
from src.domain.entities.document import Document, DocumentStatus
from src.domain.entities.job import Job, JobStatus
from src.domain.ports.document_repository import DocumentRepository
from src.domain.ports.job_repository import JobRepository
from src.domain.value_objects.document_id import DocumentId
from src.infrastructure.parsers.factory import parser_factory
from src.infrastructure.queue.celery_app import celery_app


class UploadDocumentUseCase:
    def __init__(self, doc_repo: DocumentRepository, job_repo: JobRepository):
        self.doc_repo = doc_repo
        self.job_repo = job_repo

    async def execute(
        self, file_name: str, file_type: str, file_bytes: bytes
    ) -> tuple[Document, Job]:
        file_type = file_type.lower()
        try:
            parser_factory.get_parser(file_type)
        except ValueError as exc:
            raise ValidationError("Supported file types are PDF, DOCX, TXT, and Markdown.") from exc
        if not file_bytes or len(file_bytes) > settings.MAX_UPLOAD_BYTES:
            raise ValidationError(f"Upload must contain 1 to {settings.MAX_UPLOAD_BYTES} bytes.")
        checksum = hashlib.sha256(file_bytes).hexdigest()
        existing = await self.doc_repo.get_by_checksum(checksum)
        if existing:
            job = await self.job_repo.latest_for_document(str(existing.id))
            if job:
                return existing, job
        doc = Document(
            id=DocumentId.generate(),
            name=Path(file_name).name,
            file_type=file_type,
            checksum=checksum,
        )
        save_path = self._path(doc)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_bytes(file_bytes)
        await self.doc_repo.save(doc)
        return doc, await self._enqueue(doc, save_path)

    def _path(self, doc: Document) -> Path:
        return Path(settings.DATA_DIR) / "uploads" / f"{doc.id}.{doc.file_type}"

    async def reindex(self, doc_id: DocumentId) -> tuple[Document, Job]:
        doc = await self.doc_repo.get(doc_id)
        if doc is None:
            raise NotFoundError("Document", str(doc_id))
        latest = await self.job_repo.latest_for_document(str(doc_id))
        if (
            latest
            and latest.status in {JobStatus.QUEUED, JobStatus.PROCESSING}
            and doc.status
            in {DocumentStatus.QUEUED, DocumentStatus.PARSING, DocumentStatus.EMBEDDING}
        ):
            raise ValidationError("This document already has an active ingestion job.")
        path = self._path(doc)
        if not path.is_file():
            raise NotFoundError("Uploaded file", str(doc_id))
        doc.status = DocumentStatus.QUEUED
        doc.error_message = None
        await self.doc_repo.save(doc)
        return doc, await self._enqueue(doc, path)

    async def _enqueue(self, doc: Document, path: Path) -> Job:
        job = Job(job_id=str(uuid.uuid4()), document_id=doc.id)
        await self.job_repo.save(job)
        try:
            celery_app.send_task(
                "ingest_document", args=[str(doc.id), str(path), job.job_id], task_id=job.job_id
            )
        except Exception as exc:
            job.status = JobStatus.FAILED
            job.error = "Could not enqueue ingestion. Check Redis and retry reindexing."
            doc.mark_failed(job.error)
            await self.job_repo.save(job)
            await self.doc_repo.save(doc)
            raise AppError("QUEUE_UNAVAILABLE", job.error, 503) from exc
        return job
