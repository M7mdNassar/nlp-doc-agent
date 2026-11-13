from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.conversation import Conversation, Message
from src.infrastructure.relational.models import ConversationModel


class ConversationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, conversation_id: str) -> Conversation | None:
        model = await self.session.get(ConversationModel, conversation_id)
        if model is None:
            return None
        return Conversation(
            model.id,
            model.user_id,
            [
                Message(
                    message["role"],
                    message["content"],
                    datetime.fromisoformat(message["timestamp"]),
                )
                for message in model.messages
            ],
        )

    async def save(self, conversation: Conversation) -> None:
        model = await self.session.get(ConversationModel, conversation.id)
        if model is None:
            model = ConversationModel(id=conversation.id, user_id=conversation.user_id)
            self.session.add(model)
        model.messages = [
            {"role": m.role, "content": m.content, "timestamp": m.timestamp.isoformat()}
            for m in conversation.messages
        ]
        await self.session.commit()
