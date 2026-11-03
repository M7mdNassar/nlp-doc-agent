# Frontend Stack and Streaming

## Status

Accepted.

## Context

The frontend must:

- Stream tokens from an SSE endpoint to the browser.
- Render inline citations as interactive chips that open the exact source chunk.
- Manage a document library with async ingestion status.
- Look and behave like a production application, not an internal tool.

Candidate approaches included Streamlit, a React SPA with a custom streaming layer, and Next.js with the Vercel AI SDK.

## Decision

The frontend is built with **Next.js 14 (App Router)**, **TypeScript**, **Tailwind CSS**, **shadcn/ui**, and the **Vercel AI SDK**.

The frontend and backend live in the **same repository** but are built as separate Docker images and run as separate containers. The browser talks only to Next.js. A Next.js route handler bridges the backend’s SSE stream to the Vercel AI SDK protocol. Business logic — retrieval, agents, citations — never moves into Next.js.

The TypeScript client for the backend is generated from the FastAPI OpenAPI schema and committed to the repository.

## Consequences

Easier:

- Streaming chat is implemented with a well-supported hook and protocol, not a hand-rolled parser.
- Citations can be rendered as first-class components with their own navigation.
- The UI is a real product surface, not a prototyping surface.
- Type safety across the API boundary is enforced at build time.

Harder:

- Two services to build and deploy instead of one.
- The frontend requires a codegen step whenever the backend API changes. This is enforced in CI.

## Alternatives considered

- **Streamlit.** Rejected. It cannot render interactive citation chips, cannot stream tokens with the control the UI needs, and is a prototyping tool, not a production frontend.
- **React SPA with a custom streaming client.** Rejected. It duplicates the protocol handling that the Vercel AI SDK already solves, and it loses the App Router’s conventions for routing, layout, and server components.
- **Monolithic Next.js with business logic inside route handlers.** Rejected. It would move retrieval, orchestration, and citation verification into TypeScript, losing the Python ML ecosystem and the strict layering enforced on the backend.