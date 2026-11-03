# Deployment

This document explains how to run NLP Doc Chat with Docker Compose, configure its environment, manage persistent data, and understand the current deployment and scaling approach.

## Table of Contents

- [Overview](#overview)
- [Services](#services)
- [Persistent Volumes](#persistent-volumes)
- [Local Development](#local-development)
- [Production Profile](#production-profile)
- [Environment Variables](#environment-variables)
- [Healthchecks and Startup Order](#healthchecks-and-startup-order)
- [Backups](#backups)
- [First Run](#first-run)
- [Resetting the Environment](#resetting-the-environment)
- [Scaling Considerations](#scaling-considerations)

## Overview

NLP Doc Chat runs under a single Docker Compose stack. The stack contains five services:

1. `frontend` — the Next.js user interface and SSE bridge.
2. `backend` — the FastAPI application.
3. `worker` — the Celery worker that processes document ingestion tasks.
4. `qdrant` — the vector store.
5. `redis` — the cache, lock manager, and Celery message broker.

## Services

| Service | Image | Purpose |
|---|---|---|
| `frontend` | Built from `infrastructure/docker/frontend.Dockerfile` | Next.js UI and SSE bridge. |
| `backend` | Built from `infrastructure/docker/backend.Dockerfile` | FastAPI application. |
| `worker` | Built from `infrastructure/docker/worker.Dockerfile` | Celery worker for asynchronous document ingestion. |
| `qdrant` | Official `qdrant/qdrant` image | Vector store. |
| `redis` | Official `redis` image | Cache, locks, and message broker. |

## Persistent Volumes

Persistent data is stored in named Docker volumes:

| Volume | Container path | Purpose |
|---|---|---|
| `qdrant_data` | `/qdrant/storage` | Qdrant vector-store data. |
| `redis_data` | `/data` | Redis data. |
| `data_uploads` | `/app/data/uploads` | Uploaded files. |
| `data_sqlite` | `/app/data/sqlite` | SQLite database files. |

## Local Development

Start the services with:

```bash
cp .env.example .env
make up
```

Use the development target to enable hot reload:

```bash
make dev
```

`make dev` loads `docker-compose.override.yml`, which mounts source directories and exposes additional ports.

## Production Profile

The production profile differs from the development setup in the following ways:

- Source directories are not mounted into containers. Images are built once and deployed.
- Qdrant, Redis, and the backend are bound to loopback only.
- The frontend is the only externally reachable service.
- Images are pinned to specific tags and digests in `docker-compose.yml`.
- Secrets are injected through environment variables from a secret manager, not from a file.

## Environment Variables

The `.env.example` file is the canonical list of environment variables. Keep it up to date whenever configuration changes.

| Variable | Purpose | Default or notes |
|---|---|---|
| `GROQ_API_KEY` | Groq API key. | Backend only. |
| `CEREBRAS_API_KEY` | Fallback LLM provider API key. | — |
| `OPENROUTER_API_KEY` | Secondary fallback provider API key. | — |
| `JWT_SECRET` | Signing key for user sessions. | — |
| `QDRANT_URL` | Qdrant endpoint. | `http://qdrant:6333` |
| `REDIS_URL` | Redis connection URL. | `redis://redis:6379/0` |
| `SQLITE_PATH` | Path to the SQLite database file. | — |
| `DATA_DIR` | Root directory for uploads and parsed files. | — |
| `EMBEDDING_MODEL` | Embedding model identifier. | `BAAI/bge-small-en-v1.5` |
| `RERANKER_MODEL` | Reranker model identifier. | `BAAI/bge-reranker-base` |
| `LOG_LEVEL` | Backend logging level. | `info` |
| `NEXT_PUBLIC_API_URL` | API base URL exposed to the browser. | — |

> **Important:** Variables prefixed with `NEXT_PUBLIC_` are exposed to the browser. Do not place secrets in these variables.

## Healthchecks and Startup Order

Each service has a healthcheck or readiness condition:

| Service | Healthcheck or readiness condition |
|---|---|
| `qdrant` | TCP probe on port `6333`. |
| `redis` | `redis-cli ping`. |
| `backend` | `GET /health` reports the status of each dependency. |
| `frontend` | Readiness depends on the backend health endpoint. |

Docker Compose uses `depends_on` with `condition: service_healthy` to enforce this startup order:

```text
redis → qdrant → backend → worker → frontend
```

## Backups

The current backup approach for each persistent volume is:

| Volume | Backup guidance |
|---|---|
| `qdrant_data` | Back up using Qdrant snapshots. |
| `redis_data` | Contains cache data only; backups are not required. |
| `data_uploads` | Back up the raw uploaded files. |
| `data_sqlite` | Back up the SQLite database using `sqlite3 .backup`. |

Backups are not automated in v1. The `infrastructure/scripts/` directory is intended to host backup scripts as the system matures.

## First Run

Start the stack, check its health, and optionally load sample documents:

```bash
make up
make health
make seed  # Optional: load sample documents
```

If `make health` reports `degraded`, inspect the failing dependency in the health response and check the relevant container logs:

```bash
make logs
```

## Resetting the Environment

To reset the local environment, run:

```bash
make reset
```

> **Warning:** This command stops the stack, removes all named volumes, and starts the environment again from a clean state. It is destructive and intended for development only. Persistent data stored in those volumes will be removed.

## Scaling Considerations

The current setup is designed for a single developer or a small team running the system on one machine.

Scaling to multiple backend instances will require:

- Moving SQLite to a network database such as PostgreSQL.
- Making the frontend and backend horizontally scalable behind a load balancer.
- Ensuring Qdrant and Redis are reachable by all backend instances.
- Moving session state out of individual backend processes.

These changes are deferred until there is a concrete need. The intended direction is documented in the decision records.
