from src.core.config import settings
from src.core.retrieval_diagnostics import record_candidates
from src.domain.entities.chunk import Chunk
from src.domain.ports.reranker import Reranker

from .model_loader import reranker_loader


class CrossEncoderAdapter(Reranker):
    def __init__(self) -> None:
        self.model = reranker_loader.load()

    async def rerank(self, query: str, chunks: list[Chunk], top_k: int = 8) -> list[Chunk]:
        if not chunks:
            return []

        # Create pairs for the cross-encoder
        pairs = [(query, chunk.retrieval_text()) for chunk in chunks]

        # Predict scores
        scores = self.model.predict(pairs, batch_size=settings.RERANKER_BATCH_SIZE)

        # Attach scores to chunks and sort
        scored_chunks = list(zip(chunks, scores, strict=True))
        scored_chunks.sort(key=lambda x: x[1], reverse=True)
        record_candidates(
            "reranking",
            [chunk for chunk, _ in scored_chunks],
            [float(score) for _, score in scored_chunks],
        )

        # Return top_k
        return [chunk for chunk, score in scored_chunks[:top_k]]
