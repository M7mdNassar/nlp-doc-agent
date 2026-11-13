from pathlib import Path

import structlog
from fastembed import SparseTextEmbedding

from src.domain.entities.document import DocumentStatus
from src.domain.ports.chunk_repository import ChunkRepository
from src.domain.ports.document_repository import DocumentRepository
from src.domain.ports.embedder import Embedder
from src.domain.ports.vector_store import VectorStore
from src.domain.value_objects.document_id import DocumentId
from src.domain.value_objects.sparse_vector import SparseVector
from src.infrastructure.parsers.factory import parser_factory

from .chunker import Chunker
from .cleaner import clean_elements

logger = structlog.get_logger(__name__)


class IngestionPipeline:
    def __init__(
        self,
        doc_repo: DocumentRepository,
        chunk_repo: ChunkRepository,
        vector_store: VectorStore,
        embedder: Embedder,
    ):
        self.doc_repo = doc_repo
        self.chunk_repo = chunk_repo
        self.vector_store = vector_store
        self.embedder = embedder
        self.chunker = Chunker(
            chunk_size=min(384, embedder.max_tokens - 2), count_tokens=embedder.count_tokens
        )
        self.sparse_model = SparseTextEmbedding(model_name="Qdrant/bm25")

    async def run(self, doc_id: DocumentId, file_path: str) -> None:
        doc = await self.doc_repo.get(doc_id)
        if not doc:
            raise ValueError(f"Document {doc_id} not found")
        try:
            # Retrying/reindexing uses the same document ID.
            doc.status = DocumentStatus.QUEUED
            doc.error_message = None
            doc.mark_parsing()
            await self.doc_repo.save(doc)
            parser = parser_factory.get_parser(doc.file_type)
            elements = clean_elements(await parser.parse(Path(file_path)))
            if not elements:
                raise ValueError(
                    "No readable content found. Image-only PDFs require OCR before upload."
                )
            doc.mark_embedding(max(e.page for e in elements))
            await self.doc_repo.save(doc)
            chunks = self.chunker.chunk(doc_id, elements)
            for chunk in chunks:
                chunk.document_name = doc.name
                chunk.file_type = doc.file_type
            texts = [c.retrieval_text() for c in chunks]
            dense_vectors = await self.embedder.embed_documents(texts)
            sparse_embeddings = list(self.sparse_model.embed(texts))
            sparse_vectors = [
                SparseVector(indices=e.indices.tolist(), values=e.values.tolist())
                for e in sparse_embeddings
            ]
            # Compute successfully before replacing old data. A failed replacement is retryable.
            await self.vector_store.delete_by_document(str(doc_id))
            await self.chunk_repo.delete_by_document(doc_id)
            await self.chunk_repo.save_batch(chunks)
            await self.vector_store.upsert(chunks, dense_vectors, sparse_vectors)
            doc.mark_indexed()
            await self.doc_repo.save(doc)
        except Exception as exc:
            logger.error("ingestion_failed", document_id=str(doc_id), error=str(exc))
            doc.mark_failed(str(exc))
            await self.doc_repo.save(doc)
            raise
