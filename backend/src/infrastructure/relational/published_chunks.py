from typing import Any

from sqlalchemy import select

from src.infrastructure.relational.db import AsyncSessionLocal
from src.infrastructure.relational.models import ChunkModel, DocumentModel


async def published_chunk_ids(filters: dict[str, Any]) -> list[str]:
    stmt = select(ChunkModel.id).join(DocumentModel).where(DocumentModel.status == "indexed")
    if "doc_ids" in filters:
        stmt = stmt.where(ChunkModel.document_id.in_(filters["doc_ids"]))
    if "doc_id" in filters:
        stmt = stmt.where(ChunkModel.document_id == filters["doc_id"])
    async with AsyncSessionLocal() as session:
        return list((await session.scalars(stmt)).all())
