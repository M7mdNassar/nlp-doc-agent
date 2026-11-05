from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from src.domain.entities.chunk import Chunk
from src.domain.value_objects.document_id import DocumentId
from src.domain.value_objects.chunk_id import ChunkId
from src.domain.ports.chunk_repository import ChunkRepository as IChunkRepository
from src.infrastructure.relational.models import ChunkModel

class ChunkRepository(IChunkRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_batch(self, chunks: list[Chunk]) -> None:
        models = [
            ChunkModel(
                id=str(c.id),
                document_id=str(c.document_id),
                text=c.text,
                page=c.page,
                section=c.section,
                parent_id=c.parent_id
            ) for c in chunks
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
                parent_id=m.parent_id
            ) for m in result.scalars().all()
        ]

    async def delete_by_document(self, doc_id: DocumentId) -> None:
        stmt = delete(ChunkModel).where(ChunkModel.document_id == str(doc_id))
        await self.session.execute(stmt)
        await self.session.commit()