from functools import lru_cache
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.agents.analyst.analyst_agent import AnalystAgent
from src.application.agents.answer.answer_agent import AnswerAgent
from src.application.agents.orchestrator.orchestrator import Orchestrator
from src.application.agents.retriever.context_selector import ContextSelector
from src.application.agents.retriever.query_rewriter import QueryRewriter
from src.application.agents.retriever.retriever_agent import RetrieverAgent
from src.application.citations.verifier import CitationVerifier
from src.application.use_cases.ask_question import AskQuestionUseCase
from src.application.use_cases.delete_document import DeleteDocumentUseCase
from src.application.use_cases.get_job_status import GetJobStatusUseCase
from src.application.use_cases.list_documents import ListDocumentsUseCase
from src.application.use_cases.upload_document import UploadDocumentUseCase
from src.infrastructure.relational.db import get_db_session
from src.infrastructure.relational.repositories.conversation_repository import (
    ConversationRepository,
)
from src.infrastructure.relational.repositories.document_repository import DocumentRepository
from src.infrastructure.relational.repositories.job_repository import JobRepository

# 1. Import the heavy types ONLY during type checking
if TYPE_CHECKING:
    from src.infrastructure.embeddings.bge_adapter import BGEAdapter
    from src.infrastructure.llm.router import LLMRouter
    from src.infrastructure.rerankers.cross_encoder_adapter import CrossEncoderAdapter
    from src.infrastructure.vector_store.qdrant_adapter import QdrantAdapter

# --- Lazy Singletons ---
# lru_cache ensures they are only initialized once, AND only when needed.


@lru_cache
def get_llm() -> "LLMRouter":  # 2. Add return type hint
    from src.infrastructure.llm.router import LLMRouter

    return LLMRouter()


@lru_cache
def get_embedder() -> "BGEAdapter":  # 2. Add return type hint
    from src.infrastructure.embeddings.bge_adapter import BGEAdapter

    return BGEAdapter()


@lru_cache
def get_reranker() -> "CrossEncoderAdapter":  # 2. Add return type hint
    from src.infrastructure.rerankers.cross_encoder_adapter import CrossEncoderAdapter

    return CrossEncoderAdapter()


@lru_cache
def get_vector_store() -> "QdrantAdapter":  # 2. Add return type hint
    from src.infrastructure.vector_store.qdrant_adapter import QdrantAdapter

    return QdrantAdapter()


# --- Database Dependency ---

DBSession = Annotated[AsyncSession, Depends(get_db_session)]


# --- Use Case Wiring ---


def get_upload_doc_uc(session: DBSession) -> UploadDocumentUseCase:
    return UploadDocumentUseCase(
        DocumentRepository(session),
        JobRepository(session),
    )


def get_list_docs_uc(session: DBSession) -> ListDocumentsUseCase:
    return ListDocumentsUseCase(DocumentRepository(session))


def get_delete_doc_uc(session: DBSession) -> DeleteDocumentUseCase:
    return DeleteDocumentUseCase(
        DocumentRepository(session),
        get_vector_store(),
    )


def get_job_status_uc(session: DBSession) -> GetJobStatusUseCase:
    return GetJobStatusUseCase(JobRepository(session))


def get_ask_question_uc(session: DBSession) -> AskQuestionUseCase:
    rewriter = QueryRewriter(get_llm())
    retriever = RetrieverAgent(
        get_embedder(),
        get_vector_store(),
        get_reranker(),
    )
    analyst = AnalystAgent(get_llm())
    answer = AnswerAgent(get_llm())
    verifier = CitationVerifier()

    orchestrator = Orchestrator(
        rewriter,
        retriever,
        analyst,
        answer,
        verifier,
        ContextSelector(
            get_embedder().count_tokens, max_tokens=6000, max_chunks=16, per_document=8
        ),
    )

    return AskQuestionUseCase(
        orchestrator, ConversationRepository(session), DocumentRepository(session)
    )
