"""Redis is authoritative; Qdrant stores only expiring semantic lookup pointers."""

import asyncio
import time
import uuid
from typing import Any

from qdrant_client import AsyncQdrantClient, models

from src.core.config import settings

from .redis_client import get_redis_client

COLLECTION = "verified_answers_v1"
PREFIX = "folio:verified:v1:"
LEASE_SECONDS = 120


class RedisQdrantAnswerStore:
    def __init__(self) -> None:
        self.redis = get_redis_client()
        self.qdrant = AsyncQdrantClient(url=settings.QDRANT_URL, timeout=5)
        self.ready = False
        self.initializing = asyncio.Lock()

    async def get(self, key: str) -> dict[str, Any] | None:
        import json

        value = await self.redis.get(PREFIX + key)
        return json.loads(value) if value else None

    async def set(self, key: str, entry: dict[str, Any], ttl: int) -> None:
        import json

        await self.redis.setex(PREFIX + key, ttl, json.dumps(entry, ensure_ascii=False))

    async def claim(self, key: str) -> str | None:
        token = uuid.uuid4().hex
        acquired = await self.redis.set(PREFIX + "lock:" + key, token, nx=True, ex=LEASE_SECONDS)
        return token if acquired else None

    async def renew(self, key: str, token: str) -> None:
        await self.redis.eval(
            "if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('expire',KEYS[1],ARGV[2]) else return 0 end",
            1,
            PREFIX + "lock:" + key,
            token,
            LEASE_SECONDS,
        )

    async def release(self, key: str, token: str) -> None:
        await self.redis.eval(
            "if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('del',KEYS[1]) else return 0 end",
            1,
            PREFIX + "lock:" + key,
            token,
        )

    async def _ensure(self, dimensions: int) -> None:
        if self.ready:
            return
        async with self.initializing:
            if not await self.qdrant.collection_exists(COLLECTION):
                try:
                    await self.qdrant.create_collection(
                        COLLECTION,
                        vectors_config=models.VectorParams(
                            size=dimensions, distance=models.Distance.COSINE
                        ),
                    )
                except Exception:
                    # A different process may have created the collection concurrently.
                    if not await self.qdrant.collection_exists(COLLECTION):
                        raise
            self.ready = True

    async def find(
        self, vector: list[float], scope: str, guard: str, threshold: float
    ) -> list[tuple[str, float]]:
        await self._ensure(len(vector))
        response = await self.qdrant.query_points(
            COLLECTION,
            query=vector,
            score_threshold=threshold,
            limit=3,
            with_payload=True,
            query_filter=models.Filter(
                must=[
                    models.FieldCondition(key="scope", match=models.MatchValue(value=scope)),
                    models.FieldCondition(key="guard", match=models.MatchValue(value=guard)),
                    models.FieldCondition(key="expires", range=models.Range(gt=time.time())),
                ]
            ),
        )
        return [
            (str(point.payload["key"]), float(point.score))
            for point in response.points
            if point.payload
        ]

    async def index(
        self, key: str, vector: list[float], scope: str, guard: str, expires: float
    ) -> None:
        await self._ensure(len(vector))
        await self.qdrant.delete(
            COLLECTION,
            points_selector=models.Filter(
                must=[models.FieldCondition(key="expires", range=models.Range(lte=time.time()))]
            ),
            wait=True,
        )
        await self.qdrant.upsert(
            COLLECTION,
            points=[
                models.PointStruct(
                    id=str(uuid.uuid5(uuid.NAMESPACE_URL, PREFIX + key)),
                    vector=vector,
                    payload={"key": key, "scope": scope, "guard": guard, "expires": expires},
                )
            ],
            wait=True,
        )
