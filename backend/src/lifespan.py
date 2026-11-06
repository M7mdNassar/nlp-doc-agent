from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Starting up application...")

    # 1. Warm up ML models (Safe for local Macs without PyTorch)
    try:
        from src.infrastructure.embeddings.model_loader import embedding_loader
        from src.infrastructure.rerankers.model_loader import reranker_loader

        embedding_loader.load()
        reranker_loader.load()
        logger.info("ML models loaded successfully.")
    except ImportError:
        logger.warning(
            "PyTorch/sentence-transformers not found. Skipping model warmup. "
            "(This is expected when running locally on an Intel Mac without Docker)."
        )
    except Exception as e:
        logger.error(f"Error loading ML models: {e}")

    # 2. Initialize Qdrant
    try:
        from src.infrastructure.vector_store.collections import init_qdrant_collections
        from src.infrastructure.vector_store.qdrant_adapter import QdrantAdapter

        qdrant = QdrantAdapter()
        await init_qdrant_collections(qdrant.client)
        logger.info("Qdrant collections initialized.")
    except Exception as e:
        logger.error(f"Failed to initialize Qdrant during startup: {e}")

    logger.info("Application startup complete.")
    yield
    logger.info("Shutting down application...")
