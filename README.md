# NLP Doc Agent

A full-stack implementation of the Task-7 document-chat workflow: Retriever, Analyst, and Answer agents coordinated by a bounded orchestrator, with **Folio**, a responsive document research workspace.

- Upload PDF, DOCX, TXT, or Markdown files.
- Clean and chunk text, retain source locations and structured PDF/DOCX tables, and index dense and sparse vectors in Qdrant.
- Search with dense embeddings and BM25, apply metadata filters, rerank, and select context within a token budget.
- Run source-backed arithmetic, document comparisons, and table/statistical analysis.
- Retrieve additional evidence when needed; refuse to generate a final answer if evidence remains insufficient.
- Return verified source references, readable citations, tool results, and a persistent conversation ID.
- Upload and manage documents, follow indexing jobs, ask questions, and inspect cited excerpts through the browser.
- Choose specific sources, continue conversations, export answers, and switch between light and dark themes.

## Open the workspace

If the backend is already running, add the frontend without rebuilding the Python services:

```sh
docker compose -f docker-compose.yml up -d --build --no-deps frontend
```

Open **http://localhost:3000**. The frontend uses your existing backend, uploaded documents, and provider configuration. No extra API key or database migration is needed for the frontend.

For a fresh installation, configure the root `.env` as described below, then start all services:

```sh
docker compose -f docker-compose.yml up -d --build qdrant redis migrate backend worker frontend
```

See [frontend development and tests](frontend/README.md) for running Next.js locally. Conversation history is stored in the current browser; the backend API does not expose a history-list endpoint. Uploaded files and processing jobs remain in the backend volumes.

## Run the backend

Requires Docker Desktop/Engine and Docker Compose. From the repository root, create .env from .env.example **only if you do not already have one**, then configure GROQ_API_KEY.

PowerShell:

    if (-not (Test-Path .env)) { Copy-Item .env.example .env }
    docker compose -f docker-compose.yml up -d --build qdrant redis migrate backend worker
    docker compose -f docker-compose.yml logs --tail=100 migrate backend worker

The migrate service upgrades SQLite before the API and worker start. Open http://localhost:8000/docs to upload files and send questions. Poll GET /jobs/{job_id} until completed before querying new documents.

For existing installations, read [the upgrade instructions](docs/deployment.md). Existing documents need reindexing to populate the new metadata and structured table fields.

## Tests

From backend, after installing uv:

    uv sync --frozen --all-extras
    uv run --no-sync ruff check .
    uv run --no-sync mypy src
    uv run --no-sync pytest -q

The default suite uses isolated SQLite and in-memory Qdrant, generated PDF/DOCX fixtures, and mocked provider/model calls. It does not require a Groq key or running Docker services.

An optional live ML/Groq smoke test is available at infrastructure/scripts/smoke_backend.py. It creates synthetic documents and uses isolated in-memory databases; it makes real Groq requests. See [deployment and verification](docs/deployment.md).

## Documentation

- [Task-7 implementation and before/after changes](docs/task7-implementation.md)
- [API reference](docs/api-reference.md)
- [Architecture](docs/architecture.md)
- [Data model](docs/data-model.md)
- [Reliability and limitations](docs/reliability.md)
- [Deployment and upgrade commands](docs/deployment.md)

## Scope

This is a local, single-user application. Authentication, SSE chat, automatic OCR, and production multi-tenant isolation are not implemented. Chat displays the completed, reviewed backend answer rather than streamed tokens. Image-only PDFs must be OCRed before upload. DOCX/TXT/Markdown citations use native block/line locations rather than invented physical page numbers. Grounding review uses an LLM and is not a mathematical guarantee of factual correctness.
