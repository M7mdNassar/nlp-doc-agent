# Folio

A document research workspace for the Task-7 backend, built with Next.js 16, React, TypeScript, Radix Dialog, and custom CSS. Fonts are bundled locally. No external font service is required.

## Run with Docker

With the backend already running, from the repository root:

```sh
docker compose -f docker-compose.yml up -d --build --no-deps frontend
```

Open http://localhost:3000. Compose sets the server-only `BACKEND_URL` to `http://backend:8000`. No frontend provider key is needed. The root `.env` is not loaded into this container.

## Develop locally

Install Node.js 22 and start the backend stack. Then, from `frontend`:

```sh
npm ci
npm run dev
```

Open http://127.0.0.1:3000. On Windows, use `npm.cmd` / `npx.cmd` if PowerShell blocks the `.ps1` wrappers. If the backend is not at http://127.0.0.1:8000, copy `.env.example` to `.env.local` and set `BACKEND_URL`. This variable stays on the Next.js server. Stop the frontend container first if it occupies port 3000.

## Features and boundaries

- Upload PDF, DOCX, TXT, and Markdown files (up to 50 MiB each), with per-file progress and polling of real processing jobs.
- Search and filter the library, inspect job errors and identifiers, reindex documents, and confirm deletions.
- Chat with all ready documents or an explicit selection. An empty/unavailable selection cannot silently expand to all documents.
- Continue conversations with the backend's conversation ID; show source excerpts, verified citations, calculator results, and insufficient-evidence responses.
- Copy or export answers as Markdown. Switch themes and use the full interface on a phone or keyboard.
- Keep up to 30 conversations and 100 messages per conversation in browser storage, with storage-failure feedback and an explicit local-history reset. Backend documents are shared by this single-user installation. Browser history is not synchronized between devices or imported from Swagger.

Chat uses the backend's complete JSON response, not SSE. The waiting indicator represents a pending request, not fabricated agent progress. Stop waiting aborts the browser request; work may still finish on the server. The source drawer shows returned text and native locations; the backend does not serve original-file previews. Service health checks SQLite, Redis, and Qdrant, not LLM quota or credentials.

The server proxy allows only the supported methods and paths, limits upload buffering, checks request origins for mutations, and forwards no browser cookies or credentials. Markdown renders without raw HTML. This is still a local single-user app, not an authentication layer for public deployment.

## Checks

```sh
npm run lint
npm run typecheck
npm run build
npx playwright install chromium
npm test
```

Tests cover actual browser interactions with a mocked API, strict document filters, follow-up IDs, persistence, uploads and processing failures, deletion/reindex, errors and cancellation, unsafe Markdown, mobile layout, WCAG accessibility checks, and proxy boundaries. No LLM key is needed for this suite. Real indexing and Groq calls must be checked separately against a running backend.

For an optional live check, start the full stack and run `node scripts/smoke-live.mjs` from `frontend`. It uploads a uniquely named synthetic text document, waits for indexing, asks one real LLM question scoped to that document, checks the citation, and deletes its own fixture. It uses your configured backend provider quota and saves screenshots under `test-results/live`. A conversation record remains on the backend. It never removes pre-existing documents. Set `FRONTEND_URL` to test a different local frontend address.

CI installs Chromium and runs these checks. Browser traces and screenshots are saved on failures; use `npx playwright show-report` to inspect the report. Build output, dependencies, and test artifacts are ignored by Git.
