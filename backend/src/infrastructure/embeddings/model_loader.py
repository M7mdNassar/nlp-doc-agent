from typing import ClassVar, Self

import structlog
from sentence_transformers import SentenceTransformer

from src.core.config import settings

logger = structlog.get_logger(__name__)


class EmbeddingModelLoader:
    _instance: ClassVar[Self | None] = None
    _model: SentenceTransformer | None = None

    def __new__(cls) -> Self:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def load(self) -> SentenceTransformer:
        if self._model is None:
            logger.info(f"Loading embedding model: {settings.EMBEDDING_MODEL}")
            self._model = SentenceTransformer(settings.EMBEDDING_MODEL, device="cpu")
            logger.info("Embedding model loaded successfully.")
        return self._model


embedding_loader = EmbeddingModelLoader()
