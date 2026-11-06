from src.domain.ports.document_repository import DocumentRepository
from src.domain.ports.vector_store import VectorStore
from src.domain.value_objects.document_id import DocumentId


class DeleteDocumentUseCase:
    def __init__(self, doc_repo: DocumentRepository, vector_store: VectorStore):
        self.doc_repo = doc_repo
        self.vector_store = vector_store

    async def execute(self, doc_id: DocumentId) -> None:
        # 1. Delete from Vector DB
        await self.vector_store.delete_by_document(str(doc_id))

        # 2. Delete from Relational DB (Cascade will delete chunks)
        await self.doc_repo.delete(doc_id)

        # 3. (Future) Delete raw file from disk
