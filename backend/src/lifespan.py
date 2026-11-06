from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from src.infrastructure.embeddings.model_loader import embedding_loader
from src.infrastructure.rerankers.model_loader import reranker_loader
from src.infrastructure.vector_store.collections import init_qdrant_collections
from src.infrastructure.vector_store.qdrant_adapter import QdrantAdapter

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Starting up application...")

    # 1. Warm up ML models
    embedding_loader.load()
    reranker_loader.load()

    # 2. Initialize Qdrant Collections
    qdrant = QdrantAdapter()
    await init_qdrant_collections(qdrant.client)

    logger.info("Application startup complete.")
    yield
    logger.info("Shutting down application...")
