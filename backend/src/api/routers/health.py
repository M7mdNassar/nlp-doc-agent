from typing import TypedDict

from fastapi import APIRouter
from sqlalchemy import text

from src.infrastructure.cache.redis_client import get_redis_client
from src.infrastructure.relational.db import engine
from src.infrastructure.vector_store.qdrant_adapter import QdrantAdapter

router = APIRouter()


class HealthResponse(TypedDict):
    status: str
    dependencies: dict[str, str]


@router.get("/health")
async def health_check() -> HealthResponse:
    status: HealthResponse = {"status": "ok", "dependencies": {}}

    # Check DB
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        status["dependencies"]["sqlite"] = "ok"
    except Exception:
        status["dependencies"]["sqlite"] = "down"
        status["status"] = "degraded"

    # Check Qdrant
    try:
        client = QdrantAdapter().client
        await client.get_collections()
        status["dependencies"]["qdrant"] = "ok"
    except Exception:
        status["dependencies"]["qdrant"] = "down"
        status["status"] = "degraded"

    # Check Redis
    try:
        redis = get_redis_client()
        await redis.ping()
        status["dependencies"]["redis"] = "ok"
    except Exception:
        status["dependencies"]["redis"] = "down"
        status["status"] = "degraded"

    return status
