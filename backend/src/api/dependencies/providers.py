from functools import lru_cache
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.agents.analyst.analyst_agent import AnalystAgent
from src.application.agents.answer.answer_agent import AnswerAgent
from src.application.agents.orchestrator.orchestrator import Orchestrator
from src.application.agents.retriever.query_rewriter import QueryRewriter
from src.application.agents.retriever.retriever_agent import RetrieverAgent
from src.application.citations.verifier import CitationVerifier
from src.application.tools.calculator import Calculator
from src.application.tools.document_comparison import DocumentComparison
from src.application.tools.registry import ToolRegistry
from src.application.use_cases.ask_question import AskQuestionUseCase
from src.application.use_cases.delete_document import DeleteDocumentUseCase
from src.application.use_cases.get_job_status import GetJobStatusUseCase
from src.application.use_cases.list_documents import ListDocumentsUseCase
from src.application.use_cases.upload_document import UploadDocumentUseCase
from src.infrastructure.relational.db import get_db_session
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

    orchestrator = Orchestrator(rewriter, retriever, analyst, answer, verifier)
    return AskQuestionUseCase(orchestrator)
