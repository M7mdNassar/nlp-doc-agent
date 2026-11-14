from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.chunk import Chunk
from src.domain.entities.document import Document
from src.domain.ports.chunk_repository import ChunkRepository as IChunkRepository
from src.domain.value_objects.chunk_id import ChunkId
from src.domain.value_objects.document_id import DocumentId
from src.infrastructure.relational.models import ChunkModel, DocumentModel


class ChunkRepository(IChunkRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def publish(self, document: Document, chunks: list[Chunk]) -> None:
        """The SQL chunk set is the atomic publication pointer for staged vectors."""
        try:
            result = await self.session.execute(
                update(DocumentModel)
                .where(DocumentModel.id == str(document.id))
                .values(status="indexed", page_count=document.page_count, error_message=None)
                .returning(DocumentModel.id)
            )
            if result.scalar_one_or_none() is None:
                raise ValueError("Document was removed during ingestion")
            await self.session.execute(
                delete(ChunkModel).where(ChunkModel.document_id == str(document.id))
            )
            self.session.add_all(
                [
                    ChunkModel(
                        id=str(c.id),
                        document_id=str(c.document_id),
                        text=c.text,
                        page=c.page,
                        section=c.section,
                        parent_id=c.parent_id,
                        metadata_json=c.metadata(),
                    )
                    for c in chunks
                ]
            )
            await self.session.commit()
        except BaseException:
            await self.session.rollback()
            raise

    async def save_batch(self, chunks: list[Chunk]) -> None:
        models = [
            ChunkModel(
                id=str(c.id),
                document_id=str(c.document_id),
                text=c.text,
                page=c.page,
                section=c.section,
                parent_id=c.parent_id,
                metadata_json=c.metadata(),
            )
            for c in chunks
        ]
        self.session.add_all(models)
        await self.session.commit()

    async def get_by_document(self, doc_id: DocumentId) -> list[Chunk]:
        stmt = select(ChunkModel).where(ChunkModel.document_id == str(doc_id))
        result = await self.session.execute(stmt)
        return [
            Chunk(
                id=ChunkId(m.id),
                document_id=DocumentId(m.document_id),
                text=m.text,
                page=m.page,
                section=m.section,
                parent_id=m.parent_id,
                **m.metadata_json,
            )
            for m in result.scalars().all()
        ]

    async def delete_by_document(self, doc_id: DocumentId) -> None:
        stmt = delete(ChunkModel).where(ChunkModel.document_id == str(doc_id))
        await self.session.execute(stmt)
        await self.session.commit()
