import redis.asyncio as aioredis
from src.core.config import settings

# Global Redis connection pool
redis_pool = aioredis.ConnectionPool.from_url(
    settings.REDIS_URL,
    decode_responses=True
)

def get_redis_client() -> aioredis.Redis:
    return aioredis.Redis(connection_pool=redis_pool)