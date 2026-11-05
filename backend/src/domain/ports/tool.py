from typing import Any, Protocol


class Tool(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    @property
    def schema(self) -> dict[str, Any]: ...

    async def execute(self, **kwargs: Any) -> Any: ...
