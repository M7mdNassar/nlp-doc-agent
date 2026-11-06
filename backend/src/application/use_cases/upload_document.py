import hashlib
import uuid
from pathlib import Path

from src.core.config import settings
from src.domain.entities.document import Document, DocumentStatus
from src.domain.entities.job import Job, JobStatus
from src.domain.ports.document_repository import DocumentRepository
from src.domain.ports.job_repository import JobRepository
from src.domain.value_objects.document_id import DocumentId
from src.infrastructure.queue.tasks import ingest_document_task


class UploadDocumentUseCase:
    def __init__(self, doc_repo: DocumentRepository, job_repo: JobRepository):
        self.doc_repo = doc_repo
        self.job_repo = job_repo

    async def execute(
        self, file_name: str, file_type: str, file_bytes: bytes
    ) -> tuple[Document, Job]:
        # 1. Checksum & Deduplication
        checksum = hashlib.sha256(file_bytes).hexdigest()
        # (In a real app, check if checksum exists in doc_repo and short-circuit)

        # 2. Save file to disk
        doc_id = DocumentId.generate()
        save_path = Path(settings.DATA_DIR) / "uploads" / f"{doc_id}.{file_type}"
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "wb") as f:
            f.write(file_bytes)

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
        ingest_document_task.delay(str(doc_id), str(save_path))

        return doc, job
