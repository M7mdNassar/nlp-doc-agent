# Contributing to NLP Doc Agent

This document is the single source of truth for how we work on this project. Read it end-to-end before your first commit. It covers project setup, Git workflow, branching, commits, pull requests, code review, code style, testing, and security rules.

If something here is unclear or missing, open an issue or propose a change in a pull request. Do not silently deviate from these guidelines.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [First-time Setup](#2-first-time-setup)
3. [Environment Variables](#3-environment-variables)
4. [Branching Model](#4-branching-model)
5. [Commit Messages](#5-commit-messages)
6. [Push Rules](#6-push-rules)
7. [Pull Requests](#7-pull-requests)
8. [Code Review](#8-code-review)
9. [Code Style](#9-code-style)
10. [Architecture Rules](#10-architecture-rules)
11. [Testing](#11-testing)
12. [Security Rules](#12-security-rules)
13. [Adding New Components](#13-adding-new-components)
14. [Release Process](#14-release-process)
15. [Reporting Issues](#15-reporting-issues)
16. [Questions](#16-questions)

---

## 1. Prerequisites

Install the following before starting:

| Tool | Requirement / Purpose |
|---|---|
| **Docker** | Docker with Compose v2. This is the primary way to run the project. |
| **Python** | Python 3.12 for backend development outside Docker. |
| **Node.js** | Node.js 20 LTS with npm for frontend development. |
| **uv** | Python package manager used by the backend. Install with `pip install uv` or use the official installer. |
| **make** | Convenience commands. Optional, but recommended. |
| **Git** | Configure your Git name and email before contributing. |

### Platform-specific notes

- **Windows:** Use WSL2 for the best experience.
- **macOS:** Use Docker Desktop with at least 8 GB of RAM allocated.
- **Linux:** Use Docker Engine with the Compose plugin.

---

## 2. First-time Setup

### 2.1 Clone the repository

```bash
git clone <repo-url>
cd nlp-doc-chat
```

### 2.2 Configure the environment

```bash
cp .env
```

Fill in the required values. See [Environment Variables](#3-environment-variables) for the rules. **Never commit your `.env` file.**

### 2.3 Start the application

```bash
make up
```

### 2.4 Verify the services

```bash
make health
```

Expected local endpoints:

| Service | URL |
|---|---|
| Frontend | <http://localhost:3000> |
| Backend API documentation | <http://localhost:8000/docs> |
| Qdrant dashboard | <http://localhost:6333/dashboard> |

The health endpoint should return:

```json
{"status": "ok"}
```

### 2.5 Common Make commands

| Command | Purpose |
|---|---|
| `make up` | Start all services in the background. |
| `make down` | Stop all services. |
| `make logs` | Tail logs from all services. |
| `make dev` | Start services with hot reload (uses `docker-compose.override.yml`). |
| `make test` | Run backend and frontend test suites. |
| `make test-backend` | Run backend tests only. |
| `make test-frontend` | Run frontend tests only. |
| `make lint` | Run all linters. |
| `make format` | Auto-format backend and frontend code. |
| `make typecheck` | Run `mypy` and `tsc --noEmit`. |
| `make codegen` | Regenerate the TypeScript API client from FastAPI's OpenAPI schema. |
| `make seed` | Load sample documents into a fresh instance. |
| `make reset` | Stop services, wipe volumes, and restart from a fresh state. |

---

## 3. Environment Variables

All environment variables live in `.env`, which is ignored by Git. The `.env.example` file is the source of truth for the variables required by the project.

### Rules

- Never commit `.env`, API keys, or other secrets.
- Always update `.env.example` when introducing a new environment variable.
- Production secrets must come from a secret manager, not from files.
- The frontend may only receive variables prefixed with `NEXT_PUBLIC_`.
- **Never place secrets in `NEXT_PUBLIC_*` variables.** These variables are included in the browser bundle and are therefore public.

---

## 4. Branching Model

We use **trunk-based development** with short-lived feature branches.

### Core rules

- `main` is always deployable and is the only long-lived branch.
- Create short-lived branches from `main` for all work.
- Merge branches back into `main` through pull requests using squash merge.
- Branches should live for hours to a couple of days, not weeks. Split large features into smaller pieces.

### Branch naming

Use this format:

```text
<type>/<short-description>
```

Allowed branch types:

| Type | Use for |
|---|---|
| `feat/` | New user-facing feature. |
| `fix/` | Bug fix. |
| `refactor/` | Internal restructuring with no behavior change. |
| `perf/` | Performance improvement. |
| `docs/` | Documentation-only changes. |
| `test/` | Adding or fixing tests. |
| `chore/` | Tooling, dependencies, or CI maintenance. |
| `ci/` | CI/CD changes. |

Examples:

```text
feat/document-upload
fix/citation-mapping
refactor/orchestrator-state-machine
docs/architecture-overview
```

Branch descriptions must be lowercase, hyphen-separated, and short (2–5 words).

---

## 5. Commit Messages

We follow **[Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/)**.

### Format

```text
<type>(<scope>): <subject>

<body>

<footer>
```

### Fields

- **`type`** — One of `feat`, `fix`, `refactor`, `perf`, `docs`, `test`, `chore`, `ci`, `build`, or `style`.
- **`scope`** — Optional. Identifies the affected area, such as `orchestrator`, `retrieval`, `ui`, `ingestion`, `caching`, or `citations`.
- **`subject`** — Use the imperative mood, lowercase, with no trailing period. Maximum 72 characters.
- **`body`** — Optional. Explain what changed and why, not how.
- **`footer`** — Optional. Reference issues (for example, `Closes #42` or `Refs #17`) or describe breaking changes (`BREAKING CHANGE: ...`).

### Examples

Simple feature commit:

```text
feat(ingestion): add PDF table extraction with page provenance
```

Bug-fix commit with a body:

```text
fix(citations): map answer placeholders to chunk IDs before returning

The Answer agent emitted placeholders in the format [doc, p. X] but the
verifier only matched on doc ID. Now it resolves page numbers to the
exact chunk so unreachable citations are downgraded instead of shipped.
```

Refactoring commit:

```text
refactor(orchestrator): extract budget enforcement into BudgetPolicy class
```

### Rules

- Make one logical change per commit. Do not mix a refactor and a feature in one commit.
- Do not commit commented-out code or debugging prints.
- Do not commit generated files, except for the OpenAPI client, which is explicitly committed.
- Commits must pass local hooks (`pre-commit`) before they are accepted.

---

## 6. Push Rules

### General rules

- Never push directly to `main`. Branch protection blocks direct pushes.
- Always push to your own branch and open a pull request.
- Push early and often to your branch. Work-in-progress (WIP) branches are fine.
- If your branch is behind `main`, rebase on `main` and force-push **only to your own branch**, using `git push --force-with-lease`.
- Never force-push to `main`.
- Delete your branch after it has been merged.

### Branch protection on `main`

The following settings are enforced at the repository level:

- Direct pushes are disabled.
- Merges require a pull request.
- Merges require at least one approving review.
- Merges require all CI checks to pass.
- Merges require the branch to be up to date with `main`.
- Force pushes and branch deletions are disabled.
- Signed commits are recommended, but not required for v1.

---

## 7. Pull Requests

### 7.1 Opening a pull request

1. Make sure your branch is up to date with `main`:
   ```bash
   git rebase main
   ```
2. Push your branch.
3. Open a pull request against `main`.
4. Fill in the pull request template completely.
5. Link related issues in the description.
6. Request a review from at least one teammate.
7. Keep the pull request small. Aim for fewer than 400 changed lines; split larger changes into multiple pull requests.

### 7.2 Pull request title

Use the same format as commit messages:

```text
type(scope): subject
```

### 7.3 Pull request description template

Use this template when opening a pull request:

```markdown
## Summary
Briefly describe what this PR does and why.

## Changes
- Bullet list of concrete changes.
- Group by area if large.

## Testing
- How was this tested? (unit, integration, manual)
- Commands run.
- Screenshots or recordings for UI changes.

## Checklist
- [ ] Tests added or updated
- [ ] Docs updated (if behavior, API, or config changed)
- [ ] `.env.example` updated (if new env vars)
- [ ] OpenAPI client regenerated (if API changed)
- [ ] No secrets committed
- [ ] Follows the layering rules (see `docs/architecture.md`)

## Related issues
Closes #...
```

### 7.4 Merge strategy

- Use **squash merge** into `main`. The pull request title becomes the commit message.
- Never merge using **Create a merge commit** or **Rebase and merge**.
- The pull request author merges after approval and successful CI checks.

### 7.5 Definition of Done

A pull request is ready to merge only when all of the following are true:

- [ ] CI is green (linting, type checking, and tests).
- [ ] At least one approving review has been received.
- [ ] The pull request description is complete.
- [ ] New or changed behavior is covered by tests.
- [ ] Documentation is updated when behavior, API, configuration, or architecture changes.
- [ ] No TODOs remain without a linked issue.
- [ ] No debug logs, commented-out code, or dead code remain.

---

## 8. Code Review

### Reviewer responsibilities

Reviewers are expected to:

- Review pull requests within one business day.
- Focus on correctness, clarity, test coverage, and adherence to invariants.
- Leave actionable comments. Distinguish blocking comments (must fix) from non-blocking comments (nit, optional, or question).
- Approve only when they would be comfortable shipping the change.

### Author responsibilities

Authors are expected to:

- Respond to every review comment by resolving it or discussing it.
- Push fixes as new commits until approval. The squash merge will collapse those commits.
- Avoid force-pushing after review has started unless a reviewer explicitly asks for a rebase.
- Never approve their own pull requests.
- Never merge without a review unless the change is trivial (for example, a typo or dependency bump) and a maintainer explicitly allows it.

---

## 9. Code Style

Style is enforced by tooling, not opinion. When a linter reports a problem, fix the code. Do not disable a rule without a documented reason.

### Backend (Python)

| Area | Standard |
|---|---|
| Formatter | `ruff format` |
| Linter | `ruff check` |
| Type checker | `mypy` in strict mode for `domain/` and `application/` |
| Import ordering | Enforced by Ruff. |
| Line length | 100 characters. |
| Function and variable naming | `snake_case` |
| Class naming | `PascalCase` |
| Constant naming | `UPPER_SNAKE_CASE` |

### Frontend (TypeScript)

| Area | Standard |
|---|---|
| Formatter | Prettier |
| Linter | ESLint with the Next.js and TypeScript presets. |
| Type checker | `tsc --noEmit` in strict mode. |
| Variable and function naming | `camelCase` |
| Component and type naming | `PascalCase` |
| File naming (non-component files) | `kebab-case` |
| Component file naming | `PascalCase` |

### General guidelines

- Prefer clarity over cleverness.
- Keep functions small and single-purpose.
- Name things by what they do, not by how they are implemented.
- Avoid magic numbers; use named constants.
- Do not introduce side effects in pure functions in the domain layer.

---

## 10. Architecture Rules

These rules are enforced. The backend follows a layered architecture with a strict dependency direction.

### Dependency direction

```text
api → application → domain
api → infrastructure → domain
```

### Layer responsibilities and dependencies

- `domain/` imports nothing from other layers.
- `application/` imports from `domain/` only.
- `infrastructure/` implements ports defined in `domain/ports/`.
- `api/` wires everything together through `dependencies/providers.py`.

### Architecture rules

- Do not put business logic in `api/routers/`.
- Do not perform I/O in `domain/`.
- Do not directly import third-party libraries (such as the Qdrant client, Redis, or Groq SDK) inside `application/` or `domain/`. Use ports instead.
- Do not add cross-imports between sibling modules in `application/` unless explicitly allowed.
- Architecture violations fail CI through `import-linter`.
- If you genuinely need a new dependency, propose it in a decision record (see `docs/decisions/`).

---

## 11. Testing

### Test types

- **Unit tests:** Test domain and application logic with ports mocked.
- **Integration tests:** Test adapters against real Qdrant, Redis, and SQLite instances running through Docker.
- **Contract tests:** Every adapter must pass the port compliance tests.
- **End-to-end tests:** Test the full chat flow through the API.

### Testing rules

- New logic requires new tests.
- Bug fixes require a regression test.
- The coverage gate is **80%** for `domain/` and `application/`.
- Tests must be deterministic. Do not make network calls in unit tests.
- Test files must mirror the source tree.

### Run tests locally

```bash
make test
```

---

## 12. Security Rules

- Never commit secrets. Use `.env` locally and a secret manager in every deployed environment.
- Never log secrets, tokens, or full document content. Log identifiers and lengths only.
- Validate all user input at the API boundary with Pydantic.
- Enforce access control on the server side. Never trust an LLM-generated filter to authorize access to a document.
- Sanitize extracted document text before passing it to an LLM. Prompt injection inside documents is an expected threat.
- Report vulnerabilities privately to the maintainers. Do not open a public issue.

---

## 13. Adding New Components

Use this quick reference to determine where new functionality belongs. See [`docs/architecture.md`](docs/architecture.md) for the full explanation.

| Task | Location |
|---|---|
| Add a new file parser (e.g., PPTX) | `backend/src/infrastructure/parsers/`; register it in `factory.py`. |
| Add a new LLM provider | `backend/src/infrastructure/llm/`; register it in `router.py`. |
| Add a new Analyst tool | `backend/src/application/tools/`; register it in `registry.py`. |
| Add a new retrieval step | `backend/src/application/agents/retriever/` |
| Add a new API endpoint | `backend/src/api/routers/` + `schemas/` + a use case in `application/use_cases/`. |
| Add a new UI page | `frontend/src/app/<route>/page.tsx` |
| Add a reusable UI component | `frontend/src/components/ui/` for primitives; `frontend/src/components/<area>/` for feature components. |
| Add a cache layer or change invalidation | `backend/src/application/caching/` |
| Change citation behavior | `backend/src/application/citations/` |
| Change prompts | `backend/src/application/agents/<agent>/prompt_builder.py` |

### After changing the API

After adding an endpoint or changing a schema, regenerate the TypeScript client:

```bash
make codegen
```

Commit the generated files.

---

## 14. Release Process

The release process is **not yet defined for v1**. Until it is defined:

- Treat `main` as always deployable.
- Any tag on `main` is a release candidate.
- Do not create a tag without a maintainer's approval.

---

## 15. Reporting Issues

- Use the issue templates in `.github/ISSUE_TEMPLATE/`.
- Bug reports must include:
  - Expected behavior.
  - Actual behavior.
  - Steps to reproduce.
  - Environment.
- Feature requests must explain the problem being solved, not just the proposed solution.

---

## 16. Questions

If anything in this document is unclear, ask in the team channel before making assumptions. This document evolves over time; propose improvements through a pull request.
