import os
from typing import ClassVar, Self

import structlog
from sentence_transformers import CrossEncoder

from src.core.config import settings

logger = structlog.get_logger(__name__)


class RerankerModelLoader:
    _instance: ClassVar[Self | None] = None
    _model: CrossEncoder | None = None

    def __new__(cls) -> Self:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def load(self) -> CrossEncoder:
        if self._model is None:
            logger.info(f"Loading reranker model: {settings.RERANKER_MODEL}")

            device = os.environ.get("RERANKER_DEVICE", "cpu")
            self._model = CrossEncoder(settings.RERANKER_MODEL, device=device)
            logger.info(
                "reranker_device",
                requested_device=device,
                actual_device=str(self._model.device),
            )
            
            logger.info("Reranker model loaded successfully.")
        return self._model


reranker_loader = RerankerModelLoader()
