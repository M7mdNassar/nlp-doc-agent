from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.agents.analyst.analyst_agent import AnalystAgent
from src.application.agents.answer.answer_agent import AnswerAgent
from src.application.agents.orchestrator.orchestrator import Orchestrator
from src.application.agents.retriever.query_rewriter import QueryRewriter
from src.application.agents.retriever.retriever_agent import RetrieverAgent
from src.application.citations.verifier import CitationVerifier
from src.application.use_cases.ask_question import AskQuestionUseCase
from src.application.use_cases.delete_document import DeleteDocumentUseCase
from src.application.use_cases.get_job_status import GetJobStatusUseCase
from src.application.use_cases.list_documents import ListDocumentsUseCase
from src.application.use_cases.upload_document import UploadDocumentUseCase
from src.infrastructure.cache.exact_cache import RedisExactCache
from src.infrastructure.embeddings.bge_adapter import BGEAdapter
from src.infrastructure.llm.router import LLMRouter
from src.infrastructure.relational.db import get_db_session
from src.infrastructure.relational.repositories.document_repository import DocumentRepository
from src.infrastructure.relational.repositories.job_repository import JobRepository
from src.infrastructure.rerankers.cross_encoder_adapter import CrossEncoderAdapter
from src.infrastructure.vector_store.qdrant_adapter import QdrantAdapter

# --- Infrastructure Singletons ---
# These are heavy and shouldn't be re-instantiated per request
_llm_router = LLMRouter()
_embedder = BGEAdapter()
_reranker = CrossEncoderAdapter()
_vector_store = QdrantAdapter()
_cache = RedisExactCache()

# --- Use Case Wiring ---


def get_upload_doc_uc(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UploadDocumentUseCase:
    return UploadDocumentUseCase(DocumentRepository(session), JobRepository(session))


def get_list_docs_uc(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ListDocumentsUseCase:
    return ListDocumentsUseCase(DocumentRepository(session))


def get_delete_doc_uc(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> DeleteDocumentUseCase:
    return DeleteDocumentUseCase(DocumentRepository(session), _vector_store)


def get_job_status_uc(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> GetJobStatusUseCase:
    return GetJobStatusUseCase(JobRepository(session))


def get_ask_question_uc() -> AskQuestionUseCase:
    rewriter = QueryRewriter(_llm_router)
    retriever = RetrieverAgent(_embedder, _vector_store, _reranker)
    analyst = AnalystAgent(_llm_router)
    answer = AnswerAgent(_llm_router)
    verifier = CitationVerifier()
    orchestrator = Orchestrator(rewriter, retriever, analyst, answer, verifier)
    return AskQuestionUseCase(orchestrator)
