import os
from pathlib import Path

import structlog

from src.core.config import settings
from src.domain.ports.document_repository import DocumentRepository
from src.domain.ports.vector_store import VectorStore
from src.domain.value_objects.document_id import DocumentId

logger = structlog.get_logger(__name__)


class DeleteDocumentUseCase:
    def __init__(self, doc_repo: DocumentRepository, vector_store: VectorStore):
        self.doc_repo = doc_repo
        self.vector_store = vector_store

    async def execute(self, doc_id: DocumentId) -> None:
        # 1. Get document to find file_type
        doc = await self.doc_repo.get(doc_id)

        # 2. Delete from Vector DB
        await self.vector_store.delete_by_document(str(doc_id))

        # 3. Delete from Relational DB (Cascade will delete chunks)
        await self.doc_repo.delete(doc_id)

        # 4. Delete raw file from disk
        if doc:
            file_path = Path(settings.DATA_DIR) / "uploads" / f"{doc_id}.{doc.file_type}"
            if file_path.exists():
                try:
                    os.remove(file_path)
                except Exception as e:
                    logger.error(f"Failed to delete raw file {file_path}: {e}")
