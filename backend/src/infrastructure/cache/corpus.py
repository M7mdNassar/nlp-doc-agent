import hashlib
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.citations.verifier import normalized
from src.domain.entities.answer import Source
from src.infrastructure.relational.models import ChunkModel, DocumentModel, JobModel


class SqlCacheCorpus:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def revision(self) -> str:
        # Content fingerprints avoid a migration and catch updates, additions,
        # deletions and same-file reindexing, including transitions during ingestion.
        digest = hashlib.sha256()
        for model in (DocumentModel, ChunkModel, JobModel):
            rows = (
                await self.session.execute(
                    select(model.__table__).order_by(list(model.__table__.primary_key)[0])
                )
            ).all()
            for row in rows:
                digest.update(json.dumps(dict(row._mapping), sort_keys=True, default=str).encode())
        return digest.hexdigest()

    async def supports(self, sources: list[Source]) -> bool:
        rows = (
            await self.session.execute(
                select(ChunkModel, DocumentModel)
                .join(DocumentModel, ChunkModel.document_id == DocumentModel.id)
                .where(ChunkModel.id.in_([source["chunk_id"] for source in sources]))
            )
        ).all()
        chunks = {chunk.id: (chunk, document) for chunk, document in rows}
        for source in sources:
            if source["chunk_id"] not in chunks:
                return False
            chunk, document = chunks[source["chunk_id"]]
            if (
                document.status != "indexed"
                or document.id != source["document_id"]
                or document.name != source["document_name"]
                or chunk.page != source["page"]
                or chunk.section != source["section"]
                or (chunk.metadata_json or {}).get("location") != source["location"]
                or not normalized(source["quote"])
                or normalized(source["quote"]) not in normalized(chunk.text)
            ):
                return False
        return bool(sources)
