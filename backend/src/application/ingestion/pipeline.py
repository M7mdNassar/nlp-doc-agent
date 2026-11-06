from pathlib import Path

import structlog
from fastembed import SparseTextEmbedding

from src.domain.ports.chunk_repository import ChunkRepository
from src.domain.ports.document_repository import DocumentRepository
from src.domain.ports.embedder import Embedder
from src.domain.ports.vector_store import VectorStore
from src.domain.value_objects.document_id import DocumentId
from src.domain.value_objects.sparse_vector import SparseVector
from src.infrastructure.parsers.factory import parser_factory

from .chunker import Chunker

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
        self.chunker = Chunker()
        # BM25 sparse embedding model
        self.sparse_model = SparseTextEmbedding(model_name="Qdrant/bm25")

    async def run(self, doc_id: DocumentId, file_path: str) -> None:
        doc = await self.doc_repo.get(doc_id)
        if not doc:
            logger.error(f"Document {doc_id} not found.")
            return

        try:
            # 1. Update Status: PARSING
            doc.mark_parsing()
            await self.doc_repo.save(doc)

            # 2. Parse
            path = Path(file_path)
            parser = parser_factory.get_parser(doc.file_type)
            elements = await parser.parse(path)  # Type is now list[ParsedElement]

            # 3. Update Status: EMBEDDING
            page_count = max([e.page for e in elements]) if elements else 1
            doc.mark_embedding(page_count)
            await self.doc_repo.save(doc)

            # 4. Chunk
            chunks = self.chunker.chunk(doc_id, elements)

            # 5. Embed (Dense & Sparse)
            texts = [c.text for c in chunks]
            dense_vectors = await self.embedder.embed_documents(texts)

            sparse_embeddings = list(self.sparse_model.embed(texts))
            sparse_vectors = [
                SparseVector(indices=e.indices.tolist(), values=e.values.tolist())
                for e in sparse_embeddings
            ]

            # 6. Store
            await self.chunk_repo.save_batch(chunks)
            await self.vector_store.upsert(chunks, dense_vectors, sparse_vectors)

            # 7. Update Status: INDEXED
            doc.mark_indexed()
            await self.doc_repo.save(doc)

        except Exception as e:
            logger.error(f"Ingestion failed for {doc_id}: {e}")
            doc.mark_failed(str(e))
            await self.doc_repo.save(doc)
