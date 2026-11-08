from src.domain.ports.embedder import Embedder

from .model_loader import embedding_loader


class BGEAdapter(Embedder):
    def __init__(self) -> None:
        self.model = embedding_loader.load()

    @property
    def max_tokens(self) -> int:
        return int(self.model.max_seq_length or 512)

    def count_tokens(self, text: str) -> int:
        return len(self.model.tokenizer.encode(text, add_special_tokens=True))

    async def embed_query(self, text: str) -> list[float]:
        # sentence-transformers is synchronous, run in threadpool in production
        # For v1 local, we accept the slight block
        embedding = self.model.encode(text, normalize_embeddings=True)
        return [float(value) for value in embedding]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        embeddings = self.model.encode(texts, normalize_embeddings=True)
        return [[float(value) for value in embedding] for embedding in embeddings]
