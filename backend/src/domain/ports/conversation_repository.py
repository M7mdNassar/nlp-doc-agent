from typing import Protocol

from ..entities.conversation import Conversation


class ConversationRepository(Protocol):
    async def save(self, conversation: Conversation) -> None: ...

    async def get(self, conversation_id: str) -> Conversation | None: ...
