from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI
import structlog

logger = structlog.get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Handles startup and shutdown events.
    We will connect to Qdrant, Redis, and load ML models here later.
    """
    logger.info("Starting up application...")
    
    # TODO: Initialize Database
    # TODO: Initialize Qdrant Client
    # TODO: Initialize Redis Client
    # TODO: Warm up Embedding & Reranker Models
    
    yield
    
    logger.info("Shutting down application...")
    # TODO: Close connections gracefully