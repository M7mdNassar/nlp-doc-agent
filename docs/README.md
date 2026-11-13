# Documentation Index

This folder contains the technical documentation for NLP Doc Chat. It is intended for the whole team — engineers, reviewers, and anyone onboarding to the project.

## Contents

| Document | Purpose |
|---|---|
| [architecture.md](architecture.md) | High-level architecture, layers, components, agent pipeline, data flow |
| [reliability.md](reliability.md) | System invariants, failure handling, degraded modes, edge cases |
| [api-reference.md](api-reference.md) | Implemented HTTP endpoints, filters, citations, and error responses |
| [data-model.md](data-model.md) | Domain entities, value objects, ports, and schema conventions |
| [deployment.md](deployment.md) | Docker Compose services, environment variables, volumes, local operations |
| [decisions/](decisions/README.md) | Architecture Decision Records (ADRs) for significant choices |
| [Live OpenAPI schema](http://localhost:8000/openapi.json) | Schema served by the running backend |
| [task7-implementation.md](task7-implementation.md) | Task requirements, before/after behavior, and verification results |

## Conventions

- Documents describe **what the system is and why**, not how to implement it (implementation lives in code and inline comments).
- Every significant architectural choice gets a decision record in `decisions/`.
- If a document and the code disagree, the code is the source of truth — but the document must be fixed in the same PR.
- Keep documents concise and current. Delete stale sections instead of commenting them out.

## Audience

- **New teammates** — start with `architecture.md`, then `data-model.md`.
- **Reviewers** — read `reliability.md` before reviewing changes to retrieval, agents, or citations.
- **Operators** — read `deployment.md` before changing Docker Compose, volumes, or environment variables.
