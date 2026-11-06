from src.domain.entities.chunk import Chunk
from src.domain.ports.reranker import Reranker

from .model_loader import reranker_loader


class CrossEncoderAdapter(Reranker):
    def __init__(self):
        self.model = reranker_loader.load()

    async def rerank(self, query: str, chunks: list[Chunk], top_k: int = 8) -> list[Chunk]:
        if not chunks:
            return []

        # Create pairs for the cross-encoder
        pairs = [[query, chunk.text] for chunk in chunks]

        # Predict scores
        scores = self.model.predict(pairs)

        # Attach scores to chunks and sort
        scored_chunks = list(zip(chunks, scores, strict=True))
        scored_chunks.sort(key=lambda x: x[1], reverse=True)

        # Return top_k
        return [chunk for chunk, score in scored_chunks[:top_k]]
