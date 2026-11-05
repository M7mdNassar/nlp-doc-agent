from typing import Any, Protocol


class JobQueue(Protocol):
    async def enqueue(self, task_name: str, payload: dict[str, Any]) -> str:
        """Returns a Job ID."""
        ...
