# Frontend workspace and API boundary

## Status

Implemented. This supersedes the earlier proposed Next.js 14 / Vercel AI SDK streaming design, which did not describe the actual backend contract.

## Decision

Folio uses **Next.js 16 App Router, React, TypeScript, custom CSS, and Radix Dialog**. It is a separate Node 22 container in the same repository. Locally bundled DM Sans and Lora fonts, semantic color tokens, responsive layouts, and light/dark themes define the visual system. There is no Tailwind or AI SDK dependency.

The browser talks to an allowlisted Next.js route handler at `/api/backend/...`; the server forwards to a server-only `BACKEND_URL`. Provider keys remain in the Python backend. The frontend container does not import the root environment file. The proxy checks mutation origins and body size, sets timeouts, and does not forward cookies or browser authorization headers.

The API client has TypeScript contracts with Zod validation for actual response payloads. These are maintained explicitly because the current chat route's OpenAPI response does not expose the complete typed answer schema. API-contract changes require updating the client schemas and fixtures.

## Interaction model

- The current backend returns a completed JSON answer. Chat waits for that result; it does not invent streamed tokens or internal agent stages. Cancelling stops waiting and does not promise that backend work has stopped.
- Document uploads return job IDs. The client polls jobs and the document library until processing reaches a terminal state, and preserves pending job IDs in browser storage across reloads.
- Specific document selections are explicit filters. Missing, unready, or empty selections disable sending instead of silently broadening the query.
- Citations open the actual source quote with document name and page or native block/line location. There is no original-file viewer because the backend does not offer a file-serving endpoint.
- Conversation IDs support backend follow-ups. Sidebar history is browser-local because there is no backend history-list API. Storage failures are visible rather than silently losing the persistence guarantee.
- Insufficient-evidence answers, API errors, and cancelled requests have distinct states. Model Markdown is rendered without raw HTML.

## Verification

ESLint, TypeScript, a production build, Playwright browser flows, axe accessibility checks, and proxy tests run in frontend CI. Browser tests use mocked API responses; a separate live smoke test verifies the running Python/Redis/Qdrant/Groq integration. Neither automated accessibility checks nor mocked tests alone establish complete production readiness.

## Boundaries

Retrieval, orchestration, grounding review, tool execution, and provider calls remain in Python. The UI adds no authentication, multi-tenant isolation, OCR, SSE protocol, or cross-device conversation sync. The application remains intended for local single-user use.
