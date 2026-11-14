from copy import deepcopy
from datetime import datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import AppError
from src.domain.entities.conversation import Conversation, Message
from src.infrastructure.relational.models import ConversationModel


class ConversationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, conversation_id: str) -> Conversation | None:
        model = await self.session.get(ConversationModel, conversation_id, populate_existing=True)
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
            persisted_messages=deepcopy(model.messages),
        )

    async def save(self, conversation: Conversation) -> None:
        messages = [
            {"role": m.role, "content": m.content, "timestamp": m.timestamp.isoformat()}
            for m in conversation.messages
        ]
        if conversation.persisted_messages is None:
            self.session.add(
                ConversationModel(
                    id=conversation.id, user_id=conversation.user_id, messages=messages
                )
            )
        else:
            result = await self.session.execute(
                update(ConversationModel)
                .where(
                    ConversationModel.id == conversation.id,
                    ConversationModel.messages == conversation.persisted_messages,
                )
                .values(messages=messages)
                .returning(ConversationModel.id)
                .execution_options(synchronize_session=False)
            )
            if result.scalar_one_or_none() is None:
                await self.session.rollback()
                raise AppError(
                    "CONVERSATION_CHANGED",
                    "Another question updated this conversation. Please retry your question "
                    "so it uses the latest context.",
                    409,
                )
        await self.session.commit()
        conversation.persisted_messages = deepcopy(messages)
