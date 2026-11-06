from src.domain.entities.document import Document
from src.domain.ports.document_repository import DocumentRepository


class ListDocumentsUseCase:
    def __init__(self, doc_repo: DocumentRepository):
        self.doc_repo = doc_repo

    async def execute(self) -> list[Document]:
        return await self.doc_repo.list_all()
