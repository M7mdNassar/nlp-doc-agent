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
            self._model = SentenceTransformer(
                settings.EMBEDDING_MODEL, device=settings.EMBEDDING_DEVICE
            )
            logger.info(
                "embedding_device",
                model=settings.EMBEDDING_MODEL,
                requested_device=settings.EMBEDDING_DEVICE,
                actual_device=str(self._model.device),
                batch_size=settings.EMBEDDING_BATCH_SIZE,
            )
        return self._model


embedding_loader = EmbeddingModelLoader()
