import json
from typing import Any, cast

from src.domain.ports.cache import ExactCache as IExactCache
from src.infrastructure.cache.redis_client import get_redis_client


class RedisExactCache(IExactCache):
    def __init__(self) -> None:
        self.redis = get_redis_client()

    async def get(self, key: str) -> dict[str, Any] | None:
        data = await self.redis.get(key)
        if data:
            return cast(dict[str, Any], json.loads(data))
        return None

    async def set(self, key: str, value: dict[str, Any], ttl: int = 86400) -> None:
        await self.redis.setex(key, ttl, json.dumps(value))
