import hashlib
import uuid
from pathlib import Path

import aiofiles

from src.core.config import settings
from src.domain.entities.document import Document, DocumentStatus
from src.domain.entities.job import Job, JobStatus
from src.domain.ports.document_repository import DocumentRepository
from src.domain.ports.job_repository import JobRepository
from src.domain.value_objects.document_id import DocumentId


class UploadDocumentUseCase:
    def __init__(self, doc_repo: DocumentRepository, job_repo: JobRepository):
        self.doc_repo = doc_repo
        self.job_repo = job_repo

    async def execute(
        self, file_name: str, file_type: str, file_bytes: bytes
    ) -> tuple[Document, Job]:
        # 1. Checksum & Deduplication Check
        checksum = hashlib.sha256(file_bytes).hexdigest()

        existing_doc = await self.doc_repo.get_by_checksum(checksum)
        if existing_doc:
            # If the document already exists, return it and create a completed job
            # so the frontend knows it's ready to use.
            dummy_job = Job(
                job_id=str(uuid.uuid4()), document_id=existing_doc.id, status=JobStatus.COMPLETED
            )
            await self.job_repo.save(dummy_job)
            return existing_doc, dummy_job

        # 2. Save file to disk
        doc_id = DocumentId.generate()
        save_path = Path(settings.DATA_DIR) / "uploads" / f"{doc_id}.{file_type}"
        save_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(save_path, "wb") as f:
            await f.write(file_bytes)

        # 3. Create Domain Entities
        doc = Document(
            id=doc_id,
            name=file_name,
            file_type=file_type,
            checksum=checksum,
            status=DocumentStatus.QUEUED,
        )
        job = Job(job_id=str(uuid.uuid4()), document_id=doc_id, status=JobStatus.QUEUED)

        # 4. Persist to DB
        await self.doc_repo.save(doc)
        await self.job_repo.save(job)

        # 5. Enqueue Task
        from src.infrastructure.queue.tasks import ingest_document_task

        ingest_document_task.delay(str(doc_id), str(save_path))

        return doc, job
