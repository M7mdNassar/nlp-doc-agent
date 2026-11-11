from src.application.agents.orchestrator.orchestrator import Orchestrator
from src.application.agents.retriever.metadata_filter import MetadataFilterResolver
from src.core.errors import NotFoundError
from src.core.observability import stage
from src.domain.entities.answer import ChatResult
from src.domain.entities.conversation import Conversation
from src.domain.ports.conversation_repository import ConversationRepository
from src.domain.ports.document_repository import DocumentRepository
from src.domain.value_objects.metadata_filters import MetadataFilters


class AskQuestionUseCase:
    def __init__(
        self,
        orchestrator: Orchestrator,
        conversations: ConversationRepository,
        documents: DocumentRepository,
    ):
        self.orchestrator = orchestrator
        self.conversations = conversations
        self.documents = documents
        self.filter_resolver = MetadataFilterResolver()

    async def execute(
        self,
        question: str,
        conversation_id: str | None = None,
        filters: MetadataFilters | None = None,
    ) -> ChatResult:
        if conversation_id:
            with stage("conversation_load"):
                existing = await self.conversations.get(conversation_id)
            if existing is None:
                raise NotFoundError("Conversation", conversation_id)
            conversation = existing
        else:
            # Local single-user backend; authentication/tenant isolation is not claimed.
            conversation = Conversation.create("local")
        # Bound history independently of retrieved evidence.
        history = [f"{m.role}: {m.content[:2000]}" for m in conversation.messages[-8:]]
        with stage("document_lookup") as metrics:
            documents = await self.documents.list_all()
            metrics["document_count"] = len(documents)
        resolved = self.filter_resolver.resolve(question, documents, filters)
        result = await self.orchestrator.process(
            question, resolved.model_dump(exclude_none=True), history, documents
        )
        conversation.add_message("user", question)
        conversation.add_message("assistant", result["answer"])
        with stage("conversation_save"):
            await self.conversations.save(conversation)
        result["conversation_id"] = conversation.id
        return result
