from typing import Protocol


class Lock(Protocol):
    async def acquire(self, key: str, timeout: float = 10.0) -> str | None: ...

    async def release(self, key: str, token: str) -> None: ...
