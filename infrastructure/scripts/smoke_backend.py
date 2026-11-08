"""Live ML/Groq smoke test using synthetic documents and isolated in-memory stores.

Run with the backend environment and GROQ_API_KEY configured. No application database
or Qdrant collection is read or modified. This makes real Groq inference requests.
"""

import asyncio
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

script_path = Path(__file__).resolve()
if len(script_path.parents) > 2:
    repository_backend = script_path.parents[2] / "backend"
    if (repository_backend / "src").is_dir():
        sys.path.insert(0, str(repository_backend))


async def main() -> None:
    from qdrant_client import AsyncQdrantClient, models
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from src.api.dependencies.providers import get_embedder, get_llm, get_reranker
    from src.application.agents.analyst.analyst_agent import AnalystAgent
    from src.application.agents.answer.answer_agent import AnswerAgent
    from src.application.agents.orchestrator.orchestrator import Orchestrator
    from src.application.agents.retriever.context_selector import ContextSelector
    from src.application.agents.retriever.query_rewriter import QueryRewriter
    from src.application.agents.retriever.retriever_agent import RetrieverAgent
    from src.application.citations.verifier import CitationVerifier
    from src.application.ingestion.pipeline import IngestionPipeline
    from src.application.use_cases.ask_question import AskQuestionUseCase
    from src.core.config import settings
    from src.domain.entities.document import Document
    from src.domain.value_objects.document_id import DocumentId
    from src.infrastructure.relational.models import Base
    from src.infrastructure.relational.repositories.chunk_repository import ChunkRepository
    from src.infrastructure.relational.repositories.conversation_repository import (
        ConversationRepository,
    )
    from src.infrastructure.relational.repositories.document_repository import DocumentRepository
    from src.infrastructure.vector_store.qdrant_adapter import QdrantAdapter
    from src.infrastructure.vector_store.schema import (
        COLLECTION_NAME,
        DENSE_VECTOR_NAME,
        SPARSE_VECTOR_NAME,
    )

    if not settings.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is required for this live smoke test")
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    client = AsyncQdrantClient(location=":memory:")
    await client.create_collection(
        COLLECTION_NAME,
        vectors_config={
            DENSE_VECTOR_NAME: models.VectorParams(size=384, distance=models.Distance.COSINE)
        },
        sparse_vectors_config={SPARSE_VECTOR_NAME: models.SparseVectorParams()},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        with patch(
            "src.infrastructure.vector_store.qdrant_adapter.AsyncQdrantClient", return_value=client
        ):
            vectors = QdrantAdapter()
        embedder, reranker, llm = get_embedder(), get_reranker(), get_llm()
        async with sessions() as session:
            documents = DocumentRepository(session)
            pipeline = IngestionPipeline(documents, ChunkRepository(session), vectors, embedder)
            with tempfile.TemporaryDirectory(prefix="task7-smoke-") as directory:
                for model, accuracy in [("A", 92), ("B", 95), ("C", 89)]:
                    path = Path(directory) / f"model-{model}.txt"
                    path.write_text(
                        f"Model {model} has accuracy {accuracy}%. All three models were evaluated on the same benchmark.",
                        encoding="utf-8",
                    )
                    doc = Document(DocumentId.generate(), path.name, "txt", f"synthetic-{model}")
                    await documents.save(doc)
                    await pipeline.run(doc.id, str(path))
            orchestrator = Orchestrator(
                QueryRewriter(llm),
                RetrieverAgent(embedder, vectors, reranker),
                AnalystAgent(llm),
                AnswerAgent(llm),
                CitationVerifier(),
                ContextSelector(
                    embedder.count_tokens, max_tokens=6000, max_chunks=16, per_document=8
                ),
            )
            use_case = AskQuestionUseCase(orchestrator, ConversationRepository(session), documents)
            result = await use_case.execute(
                "What is the average accuracy across Model A, Model B, and Model C? Show the calculation."
            )
            assert result["state"] == "answer_ready", result
            assert len(result["sources"]) == 3, result
            assert any(tool["output"].get("result") == "92" for tool in result["tool_results"]), (
                result
            )
            followup = await use_case.execute(
                "Which of them has the highest accuracy?", result["conversation_id"]
            )
            assert followup["state"] == "answer_ready", followup
            assert "95" in followup["answer"] and "B" in followup["answer"], followup
            print(
                json.dumps(
                    {
                        "status": "passed",
                        "mean": 92,
                        "sources": len(result["sources"]),
                        "followup_state": followup["state"],
                        "model": settings.LLM_MODEL,
                    }
                )
            )
    finally:
        await client.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
