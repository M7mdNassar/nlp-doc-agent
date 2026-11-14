from collections import OrderedDict

from src.core.config import settings
from src.core.observability import stage
from src.domain.ports.embedder import Embedder

from .model_loader import embedding_loader


class BGEAdapter(Embedder):
    QUERY_CACHE_SIZE = 128

    def __init__(self) -> None:
        self.model = embedding_loader.load()
        # Exact model inputs only; this stores vectors, never answers or approvals.
        self._query_embeddings: OrderedDict[str, tuple[float, ...]] = OrderedDict()

    @property
    def max_tokens(self) -> int:
        return int(self.model.max_seq_length or 512)

    def count_tokens(self, text: str) -> int:
        return len(self.model.tokenizer.encode(text, add_special_tokens=True))

    async def embed_query(self, text: str) -> list[float]:
        with stage("query_embedding") as metrics:
            cached = self._query_embeddings.get(text)
            metrics["cache_hit"] = cached is not None
            if cached is not None:
                self._query_embeddings.move_to_end(text)
                return list(cached)
            embedding = self.model.encode(
                text, normalize_embeddings=True, batch_size=settings.EMBEDDING_BATCH_SIZE
            )
            vector = tuple(float(value) for value in embedding)
            self._query_embeddings[text] = vector
            if len(self._query_embeddings) > self.QUERY_CACHE_SIZE:
                self._query_embeddings.popitem(last=False)
            return list(vector)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        embeddings = self.model.encode(
            texts, normalize_embeddings=True, batch_size=settings.EMBEDDING_BATCH_SIZE
        )
        return [[float(value) for value in embedding] for embedding in embeddings]
