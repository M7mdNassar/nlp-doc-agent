from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4


@dataclass
class Message:
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class Conversation:
    id: str
    user_id: str
    messages: list[Message] = field(default_factory=list)

    @classmethod
    def create(cls, user_id: str) -> "Conversation":
        return cls(id=f"conv_{uuid4().hex}", user_id=user_id)

    def add_message(self, role: str, content: str) -> None:
        self.messages.append(Message(role=role, content=content))
