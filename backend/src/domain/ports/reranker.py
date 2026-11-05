from typing import Protocol

from ..entities.chunk import Chunk


class Reranker(Protocol):
    async def rerank(self, query: str, chunks: list[Chunk], top_k: int = 8) -> list[Chunk]: ...
