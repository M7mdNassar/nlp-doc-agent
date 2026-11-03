# Architecture Decision Records (ADRs)

This directory contains the project's **Architecture Decision Records (ADRs)**. Each record documents an important technical decision, including **what was decided, why it was chosen, and which alternatives were considered**.

ADRs give contributors a shared place to understand the reasoning behind the architecture without having to reconstruct it from code or old discussions.

## Contents

- [When to write an ADR](#when-to-write-an-adr)
- [ADR format](#adr-format)
- [Decision records](#decision-records)
- [Process](#process)

## When to write an ADR

Create an ADR when a decision:

- Changes the system's architecture or overall structure.
- Would be difficult or expensive to reverse later.
- Is likely to raise questions for future contributors.
- Involves trade-offs that are not clear from the code alone.

Routine implementation details do not need an ADR.

## ADR format

Every decision record should use the following structure:

```markdown
# <Short title>

## Status

Proposed | Accepted | Superseded by [<new record>](<relative-link>)

## Context

Describe the situation, the problem, and the factors that influenced the decision.

## Decision

Explain what was decided.

## Consequences

Describe what becomes easier, what becomes harder, and which risks or trade-offs are accepted.

## Alternatives considered

List the other options considered and explain why they were not selected.
```

### Status meanings

| Status | Meaning |
|---|---|
| `Proposed` | The decision is still under discussion. |
| `Accepted` | The decision has been reviewed and agreed upon. |
| `Superseded` | A newer ADR replaces this decision. Link to the newer record. |

## Decision records

| Record | Topic |
|---|---|
| [vector-store.md](vector-store.md) | Selection of the vector database. |
| [orchestrator.md](orchestrator.md) | Using a deterministic state machine for the orchestrator. |
| [caching.md](caching.md) | The caching strategy. |
| [frontend.md](frontend.md) | Frontend technology stack and streaming approach. |

## Process

1. **Create a draft:** Add the ADR in the same pull request (PR) that introduces the decision.
2. **Discuss:** Review the decision and its trade-offs as part of the PR discussion.
3. **Accept:** Once the PR is merged, update the ADR status to `Accepted`.
4. **Supersede when needed:** If a later decision replaces an accepted one, create a new ADR and update the old record's status to `Superseded`, linking to the new record.

Do not rewrite an accepted ADR to reflect new thinking. Keep its original reasoning as a historical record; document the new decision in a separate ADR.
