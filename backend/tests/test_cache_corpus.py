import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from src.domain.entities.answer import Source
from src.infrastructure.cache.corpus import SqlCacheCorpus
from src.infrastructure.relational.models import Base, ChunkModel, DocumentModel, JobModel


@pytest.fixture
async def corpus_db(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/cache.db")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        doc = DocumentModel(
            id="doc_a", name="paper.pdf", file_type="pdf", checksum="abc", status="indexed"
        )
        chunk = ChunkModel(
            id="chunk_a", document_id="doc_a", text="Attention uses a weighted sum.", page=1
        )
        session.add_all([doc, chunk])
        await session.commit()
        source = Source(
            chunk_id="chunk_a",
            document_id="doc_a",
            document_name="paper.pdf",
            quote="Attention uses a weighted sum.",
            page=1,
            section=None,
            location=None,
        )
        yield SqlCacheCorpus(session), session, doc, chunk, source
    await engine.dispose()


@pytest.mark.parametrize(
    "change",
    ["add_document", "delete_document", "edit_content", "reindex", "metadata", "status", "job"],
)
async def test_lifecycle_and_content_changes_invalidate_revision(corpus_db, change):
    corpus, session, doc, chunk, _ = corpus_db
    before = await corpus.revision()
    if change == "add_document":
        session.add(
            DocumentModel(
                id="doc_b", name="other.pdf", file_type="pdf", checksum="xyz", status="indexed"
            )
        )
    elif change == "delete_document":
        await session.delete(doc)
    elif change == "edit_content":
        chunk.text = "Contradictory new result."
    elif change == "reindex":
        chunk.id = "chunk_reindexed"
    elif change == "metadata":
        doc.access_tags = "restricted"
    elif change == "status":
        doc.status = "parsing"
    else:
        session.add(JobModel(job_id="job_a", document_id="doc_a", status="queued"))
    await session.commit()
    assert before != await corpus.revision()


@pytest.mark.parametrize(
    "damage",
    ["quote", "document_id", "page", "section", "location", "document_name", "deleted", "status"],
)
async def test_cached_sources_are_checked_against_actual_indexed_content(corpus_db, damage):
    corpus, session, doc, chunk, source = corpus_db
    assert await corpus.supports([source])
    if damage == "deleted":
        await session.delete(chunk)
    elif damage == "status":
        doc.status = "failed"
    else:
        source[damage] = 99 if damage == "page" else "invalid"
    await session.commit()
    assert not await corpus.supports([source])
