from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import DuplicateDocumentError
from src.domain.entities.document import Document, DocumentStatus
from src.domain.ports.document_repository import DocumentRepository as IDocumentRepository
from src.domain.value_objects.document_id import DocumentId
from src.infrastructure.relational.models import DocumentModel


class DocumentRepository(IDocumentRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save(self, document: Document) -> None:
        # Upsert logic
        stmt = select(DocumentModel).where(DocumentModel.id == str(document.id))
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()

        if model:
            # Update
            model.name = document.name
            model.status = document.status.value
            model.page_count = document.page_count
            model.error_message = document.error_message
            model.access_tags = ",".join(document.access_tags)
        else:
            # Insert
            model = DocumentModel(
                id=str(document.id),
                name=document.name,
                file_type=document.file_type,
                checksum=document.checksum,
                status=document.status.value,
                page_count=document.page_count,
                error_message=document.error_message,
                access_tags=",".join(document.access_tags),
                created_at=document.created_at,
            )
            self.session.add(model)

        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            existing = await self.get_by_checksum(document.checksum)
            if existing is not None and existing.id != document.id:
                raise DuplicateDocumentError(str(existing.id), existing.name) from None
            raise

    async def get(self, doc_id: DocumentId) -> Document | None:
        stmt = select(DocumentModel).where(DocumentModel.id == str(doc_id))
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()

        if not model:
            return None

        return Document(
            id=DocumentId(model.id),
            name=model.name,
            file_type=model.file_type,
            checksum=model.checksum,
            status=DocumentStatus(model.status),
            page_count=model.page_count,
            error_message=model.error_message,
            access_tags=model.access_tags.split(",") if model.access_tags else [],
            created_at=model.created_at,
        )

    async def list_all(self) -> list[Document]:
        stmt = select(DocumentModel)
        result = await self.session.execute(stmt)
        models = result.scalars().all()
        return [
            Document(
                id=DocumentId(m.id),
                name=m.name,
                file_type=m.file_type,
                checksum=m.checksum,
                status=DocumentStatus(m.status),
                page_count=m.page_count,
                error_message=m.error_message,
                access_tags=m.access_tags.split(",") if m.access_tags else [],
                created_at=m.created_at,
            )
            for m in models
        ]

    async def get_by_checksum(self, checksum: str) -> Document | None:
        result = await self.session.execute(
            select(DocumentModel.id).where(DocumentModel.checksum == checksum)
        )
        doc_id = result.scalar_one_or_none()
        return await self.get(DocumentId(doc_id)) if doc_id else None

    async def delete(self, doc_id: DocumentId) -> None:
        stmt = select(DocumentModel).where(DocumentModel.id == str(doc_id))
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        if model:
            await self.session.delete(model)
            await self.session.commit()
