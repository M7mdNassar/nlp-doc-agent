import uuid
import asyncio
from src.infrastructure.cache.redis_client import get_redis_client
from src.domain.ports.lock import Lock as ILock


class RedisLock(ILock):
    def __init__(self):
        self.redis = get_redis_client()

    async def acquire(self, key: str, timeout: float = 10.0) -> str | None:
        """
        Acquires a lock. Returns a lock token if successful, else None.
        """
        token = str(uuid.uuid4())
        end_time = asyncio.get_event_loop().time() + timeout

        while asyncio.get_event_loop().time() < end_time:
            # SET NX PX (Set if Not Exists, with millisecond expiry)
            success = await self.redis.set(key, token, nx=True, px=int(timeout * 1000))
            if success:
                return token
            await asyncio.sleep(0.1)

        return None

    async def release(self, key: str, token: str) -> None:
        """
        Releases the lock only if the token matches (Lua script for atomicity).
        """
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        await self.redis.eval(lua_script, 1, key, token)