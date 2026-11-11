# Deployment and upgrade

Run commands from the repository root unless stated otherwise. The backend upgrade sections below retain the API-only commands; the frontend can be added independently.

## Add the Folio frontend to an existing backend

```sh
docker compose -f docker-compose.yml up -d --build --no-deps frontend
docker compose -f docker-compose.yml logs --tail=100 frontend
```

Open **http://localhost:3000**. No backend rebuild, database migration, reindex, or volume reset is needed for this frontend addition. Existing uploaded documents appear automatically. Swagger remains at http://localhost:8000/docs and Qdrant at http://localhost:6333/dashboard.

The new frontend image uses Node 22 and runs as an unprivileged user. Compose publishes it on the local machine only (`127.0.0.1:3000`). Its server forwards allowed API requests to `BACKEND_URL=http://backend:8000`. The browser uses same-origin `/api/backend/...` URLs. The frontend does not load the root `.env`, and needs no Groq key, JWT secret, or `NEXT_PUBLIC_API_URL`. Keep provider credentials in the backend's existing configuration.

For a completely fresh installation, configure `.env` first, then run:

```sh
docker compose -f docker-compose.yml up -d --build qdrant redis migrate backend worker frontend
```

Use **Upload documents** in the UI, wait for **Ready**, then ask a question. Click a citation to see the actual retrieved excerpt. The library exposes processing errors, job IDs, reindex, and deletion. Conversations and theme preferences are saved in the current browser. The frontend cannot import earlier Swagger conversations because the backend has no conversation-list endpoint.

For local development, run the backend stack with Docker, then follow [frontend/README.md](../frontend/README.md). Stop a locally running Next.js server before starting the frontend container because both use port 3000. These services remain intended for local single-user use; this update does not add authentication or authorize public exposure.

## Configuration

Keep your existing .env. If starting fresh, PowerShell:

    if (-not (Test-Path .env)) { Copy-Item .env.example .env }

Set GROQ_API_KEY in .env. The existing key remains usable; no new provider account is required.
LLM_MODEL defaults to openai/gpt-oss-120b.
Docker uses QDRANT_URL=http://qdrant:6333, REDIS_URL=redis://redis:6379/0,
DATABASE_URL=sqlite+aiosqlite:///./data/app.db, and DATA_DIR=/app/data.

## Existing installation

The update changes Python source, the database schema, and production image dependencies. Rebuild/recreate the backend and worker. The new one-shot migrate service runs Alembic before they start.

Preserve a database copy before upgrading. After stopping API/worker writes, this command creates a timestamped backup inside the persistent data volume:

    docker compose -f docker-compose.yml stop backend worker
    docker compose -f docker-compose.yml run --rm --no-deps --entrypoint python backend -c "import datetime,sqlite3; from src.core.config import settings; from sqlalchemy.engine import make_url; p=make_url(settings.DATABASE_URL).database; s=sqlite3.connect(p); d=sqlite3.connect(p+'.backup-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')); s.backup(d); d.close(); s.close()"
    docker compose -f docker-compose.yml up -d --build qdrant redis migrate backend worker

No volume reset is needed. Do not run docker compose down -v or make reset for this upgrade.

Check startup:

    docker compose -f docker-compose.yml ps -a
    docker compose -f docker-compose.yml logs --tail=100 migrate backend worker
    Invoke-RestMethod http://localhost:8000/health

A successful migrate container exits with code 0; that is expected.
The health response should report SQLite/Qdrant/Redis as ok, but it does not verify Groq credentials.

If you intentionally used a custom SQLite URL or upload directory, retain it consistently in .env for migrate/backend/worker. The migration now respects DATABASE_URL in online mode.

## Reindex existing uploads

Old indexed chunks lack the new metadata/table fields. Reindex existing documents after startup; uploading the same bytes again returns the existing document rather than reprocessing it.

    $documents = Invoke-RestMethod http://localhost:8000/documents
    $documents.items | Format-Table id,name,status
    $job = Invoke-RestMethod -Method Post "http://localhost:8000/documents/<document-id>/reindex"
    Invoke-RestMethod "http://localhost:8000/jobs/$($job.job_id)"

Replace <document-id> with an actual ID. Repeat for existing documents. Wait for completed before chatting. If failed, inspect error and the worker logs. The stored upload must still be present in the shared uploads volume. An active job must finish before another reindex is accepted.

Reindexing changes chunk IDs, so old answers in conversation history retain historical references. New questions use newly retrieved evidence.

## Start a new installation

    docker compose -f docker-compose.yml up -d --build qdrant redis migrate backend worker

The migration service creates the schema on first run. Use http://localhost:8000/docs to upload a PDF/DOCX/TXT/Markdown file. Poll the returned job until completed, then POST /chat.

## Development with source mounts

    docker compose -f docker-compose.yml -f docker-compose.override.yml up -d --build qdrant redis migrate backend worker

Plain docker compose automatically includes the override file. Use the explicit base-file command above when you want production stages without source mounts.

## Local tests

    cd backend
    uv sync --frozen --all-extras
    uv run --no-sync ruff check .
    uv run --no-sync mypy src
    uv run --no-sync pytest -q

No database migration or Docker stack is needed for the default test suite: it creates isolated test databases and runs the migrations itself.

For a host-based backend, set DATABASE_URL to your SQLite file, DATA_DIR to a writable local directory, and QDRANT_URL/REDIS_URL to localhost. Set GROQ_API_KEY in the process environment or a backend/.env file, then:

    uv run --no-sync alembic upgrade head
    uv run --no-sync uvicorn src.main:app --host 127.0.0.1 --port 8000

Run the Celery worker in a separate terminal with the same settings. Docker is recommended for the worker on Windows.

## Optional live smoke test

After the Docker stack is running, copy and run the synthetic smoke script:

    docker compose -f docker-compose.yml cp infrastructure/scripts/smoke_backend.py backend:/tmp/task7-smoke.py
    docker compose -f docker-compose.yml exec -e PYTHONPATH=/app backend python /tmp/task7-smoke.py

This uses actual embedding/reranking models and the configured Groq key, and therefore makes provider requests. All document/vector/SQL data for this test is temporary or in memory. It does not upload to or modify your application corpus. A successful run prints status=passed, mean=92, and a successful follow-up state.

## LLM credentials and answer-quality check

Compose reads GROQ_API_KEY from the repository-root .env and injects it into backend/worker.
The backend's Settings reads that process environment; a backend/.env is only relevant when
running Python directly from backend on the host. The application does not use a key from Codex.
GroqAdapter calls AsyncGroq.chat.completions.create with settings.GROQ_API_KEY and LLM_MODEL
(default openai/gpt-oss-120b). Embedding and reranking models run locally and do not need that key.

To run the optional synthetic qualification/unsupported-detail checks against Groq:

    docker compose -f docker-compose.yml cp infrastructure/scripts/smoke_answer_quality.py backend:/tmp/task7-quality-smoke.py
    docker compose -f docker-compose.yml exec -e PYTHONPATH=/app backend python /tmp/task7-quality-smoke.py

This makes provider requests using synthetic text only. It does not read uploaded documents or
change the database. It checks incorrect drafts as well as a newly generated summary.

## Container changes

### Duplicate uploads, question diagnostics, and source sharing

Rebuild the backend to install these changes:

```powershell
docker compose -f docker-compose.yml up -d --build --no-deps backend
```

Wait for [backend health](http://localhost:8000/health) to respond after model warmup.
Then open [Swagger](http://localhost:8000/docs) or refresh Folio. There are no new
dependencies, environment variables, schema migrations, or volume changes. No worker
or frontend rebuild, document reupload, or reindex is required. Existing documents
and conversations remain available. Leave sufficient free disk space for the image
build and model cache; do not reset Docker volumes to install this update.

Duplicate uploads now display the API's "already uploaded" message through the
existing frontend error handling. Chat response JSON includes `question_id` and
`usage`, and application logs contain correlated timing/token events. See
[observability](observability.md) for commands to investigate one question and
interpret partial usage after provider failures.

### Provider error reporting update

If upgrading from a version that displayed Groq quota errors as "Not enough verified evidence", rebuild only the API and frontend:

```sh
docker compose -f docker-compose.yml up -d --build --no-deps backend frontend
```

No dependency, schema, environment variable, worker, or vector-index changes are required for this fix. Refresh Folio after the containers start and send a new question; older saved responses are historical and are not rewritten.

The UI now displays a provider-limit error with an approximate wait when Groq supplies one. The API returns HTTP 429 rather than a successful evidence-refusal response. Wait before retrying and check your account's [Groq limits](https://console.groq.com/settings/limits) if the quota remains exhausted. Limits apply to the organization, so creating another key in the same organization does not create more quota. See [Groq's rate-limit documentation](https://console.groq.com/docs/rate-limits).

Choosing just the relevant CV can reduce unrelated retrieval context, but cannot bypass provider limits. Keep the existing key and model unless you intentionally choose a different provider/model configuration or plan. Database resets and reuploads do not replenish Groq quota. The green connection indicator checks backend dependencies, not the provider's remaining token allowance.

### Cooldown retry correction

If the provider-error update is already installed, this follow-up only needs the backend:

```sh
docker compose -f docker-compose.yml up -d --build --no-deps backend
```

Local cooldown waits no longer consume the three provider attempts. An early wakeup waits
out the remaining cooldown within the same 60-second rate-limit wait budget. Citation and
answer-quality verification still run, and genuine quota exhaustion still returns HTTP 429.
No frontend/worker rebuild, dependency update, environment change, migration, reindex, or
volume reset is required. Wait for backend startup/model warmup before retrying in Folio.

### Existing image configuration

- Production backend and worker install uv sync --frozen --no-dev --extra ml --no-cache.
- Development stages install all extras with the frozen lockfile and --no-cache.
- Linux and Windows use CPU-only PyTorch from the official PyTorch CPU index. The refreshed lockfile excludes CUDA/NVIDIA dependencies; no GPU is required. macOS retains its PyPI source.
- Disabling uv's download cache during image builds avoids retaining package archives in the image layers. Docker layer caching still works normally.
- The migrate service runs alembic upgrade head and gates API/worker startup.
- .env.example documents the existing required settings and optional LLM_MODEL/MAX_UPLOAD_BYTES.
- The lockfile was regenerated for CPU-only PyTorch; use the committed pyproject.toml and uv.lock together.
