import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.agents.analyst.analyst_agent import AnalystAgent
from src.application.agents.answer.answer_agent import AnswerAgent
from src.application.agents.orchestrator.orchestrator import Orchestrator
from src.application.agents.retriever.context_selector import ContextSelector
from src.application.agents.retriever.query_rewriter import QueryRewriter
from src.application.agents.retriever.retriever_agent import RetrieverAgent
from src.application.answer_cache import AnswerCache
from src.application.citations.verifier import CitationVerifier
from src.application.tools.calculator import Calculator
from src.application.tools.document_comparison import DocumentComparison
from src.application.tools.registry import ToolRegistry
from src.application.use_cases.ask_question import AskQuestionUseCase
from src.application.use_cases.delete_document import DeleteDocumentUseCase
from src.application.use_cases.get_job_status import GetJobStatusUseCase
from src.application.use_cases.list_documents import ListDocumentsUseCase
from src.application.use_cases.upload_document import UploadDocumentUseCase
from src.core.config import settings
from src.core.observability import stage
from src.domain.ports.answer_cache import AnswerCacheStore
from src.infrastructure.relational.db import get_db_session
from src.infrastructure.relational.repositories.conversation_repository import (
    ConversationRepository,
)
from src.infrastructure.relational.repositories.document_repository import DocumentRepository
from src.infrastructure.relational.repositories.job_repository import JobRepository

if TYPE_CHECKING:
    from src.infrastructure.embeddings.bge_adapter import BGEAdapter
    from src.infrastructure.llm.router import LLMRouter
    from src.infrastructure.rerankers.cross_encoder_adapter import CrossEncoderAdapter
    from src.infrastructure.vector_store.qdrant_adapter import QdrantAdapter


@lru_cache
def get_llm() -> "LLMRouter":
    from src.infrastructure.llm.router import LLMRouter

    return LLMRouter()


@lru_cache
def get_embedder() -> "BGEAdapter":
    from src.infrastructure.embeddings.bge_adapter import BGEAdapter

    return BGEAdapter()


@lru_cache
def get_reranker() -> "CrossEncoderAdapter":
    from src.infrastructure.rerankers.cross_encoder_adapter import CrossEncoderAdapter

    return CrossEncoderAdapter()


@lru_cache
def get_vector_store() -> "QdrantAdapter":
    from src.infrastructure.vector_store.qdrant_adapter import QdrantAdapter

    return QdrantAdapter()


@lru_cache
def get_answer_cache_store() -> AnswerCacheStore:
    from src.infrastructure.cache.answer_store import RedisQdrantAnswerStore

    return RedisQdrantAnswerStore()


@lru_cache
def answer_cache_parameters() -> str:
    digest = hashlib.sha256()
    # A changed backend invalidates saved approvals, including prompt/parser changes.
    for path in sorted(Path(__file__).resolve().parents[2].rglob("*.py")):
        digest.update(str(path.relative_to(Path(__file__).resolve().parents[2])).encode())
        digest.update(path.read_bytes())
    digest.update(
        json.dumps(
            {
                key: getattr(settings, key)
                for key in (
                    "ANSWER_CACHE_VERSION",
                    "LLM_MODEL",
                    "LLM_FALLBACK_MODELS",
                    "OPENROUTER_FALLBACK_MODELS",
                    "EMBEDDING_MODEL",
                    "RERANKER_MODEL",
                )
            },
            sort_keys=True,
        ).encode()
    )
    return digest.hexdigest()


# --- Database Dependency ---

DBSession = Annotated[AsyncSession, Depends(get_db_session)]


def get_upload_doc_uc(session: DBSession) -> UploadDocumentUseCase:
    return UploadDocumentUseCase(DocumentRepository(session), JobRepository(session))


def get_list_docs_uc(session: DBSession) -> ListDocumentsUseCase:
    return ListDocumentsUseCase(DocumentRepository(session))


def get_delete_doc_uc(session: DBSession) -> DeleteDocumentUseCase:
    return DeleteDocumentUseCase(DocumentRepository(session), get_vector_store())


def get_job_status_uc(session: DBSession) -> GetJobStatusUseCase:
    return GetJobStatusUseCase(JobRepository(session))


def get_ask_question_uc(session: DBSession) -> AskQuestionUseCase:
    with stage("dependency_setup"):
        return _build_ask_question_uc(session)


def _build_ask_question_uc(session: AsyncSession) -> AskQuestionUseCase:
    rewriter = QueryRewriter(get_llm())
    retriever = RetrieverAgent(get_embedder(), get_vector_store(), get_reranker())

    # Setup Tools
    registry = ToolRegistry()
    registry.register(Calculator())
    registry.register(DocumentComparison())
    # Table Extractor needs evidence, so it's registered dynamically in a real ReAct,
    # but for our simplified tool loop, the Analyst prompt will handle context.

    analyst = AnalystAgent(get_llm(), registry)
    answer = AnswerAgent(get_llm())
    verifier = CitationVerifier()

    orchestrator = Orchestrator(
        rewriter,
        retriever,
        analyst,
        answer,
        verifier,
        ContextSelector(
            get_embedder().count_tokens, max_tokens=6000, max_chunks=16, per_document=12
        ),
    )

    cache = None
    if settings.ANSWER_CACHE_ENABLED:
        from src.infrastructure.cache.corpus import SqlCacheCorpus

        cache = AnswerCache(
            get_answer_cache_store(),
            SqlCacheCorpus(session),
            get_embedder(),
            answer_cache_parameters(),
            ttl=settings.ANSWER_CACHE_TTL_SECONDS,
            semantic=settings.ANSWER_CACHE_SEMANTIC_ENABLED,
            threshold=settings.ANSWER_CACHE_SIMILARITY_THRESHOLD,
            wait_seconds=settings.ANSWER_CACHE_WAIT_SECONDS,
        )
    return AskQuestionUseCase(
        orchestrator, ConversationRepository(session), DocumentRepository(session), cache
    )
