# Orchestrator as a Deterministic State Machine

## Status

Accepted.

## Context

The system must coordinate three agents — Retriever, Analyst, and Answer — with feedback loops, budgets, retries, and explicit insufficiency handling. A straightforward option is to implement the Orchestrator as an LLM agent that decides which agent to call next based on the conversation.

That approach has serious drawbacks for this system:

- The set of legal next steps is small and well understood. Encoding it in a prompt wastes tokens and adds nondeterminism.
- Feedback loops can become unbounded if the model decides to keep calling the Retriever.
- Debugging failures requires reconstructing why the model chose a step, which is not reproducible.
- Enforcing token, latency, and tool-call budgets is unreliable when the model controls flow.

## Decision

The Orchestrator is a **deterministic state machine** implemented in Python. LLMs are used only for the bounded linguistic tasks inside each agent (query rewriting, analysis reasoning, answer generation).

The state machine:

- Defines explicit states (`received`, `rewritten`, `retrieved`, `analyzed`, `answer_ready`, `verified`, `returned`, `insufficient_evidence`).
- Declares legal transitions in `transitions.py`.
- Enforces budgets in `budget.py` (token, latency, tool-call, loop count).
- Applies policies in `policies.py` (retry, clarification, insufficiency).
- Emits structured events for tracing.

## Consequences

Easier:

- The workflow is reproducible and testable end-to-end with mocks.
- Budget enforcement is exact, not best-effort.
- Feedback loops are bounded by construction, not by prompt hope.
- Failures surface as specific states, not as model confusion.

Harder:

- Adding a new agent requires a code change, not a prompt edit. This is intentional.
- The workflow is less flexible than an open-ended agent. This is also intentional — the problem is a bounded pipeline, not an open-ended task.

## Alternatives considered

- **LLM-driven orchestrator.** Rejected for the reasons above. It trades determinism and debuggability for flexibility that this problem does not need.
- **LangGraph or a similar framework.** Rejected because the state machine is small enough to implement directly, and a framework would add a dependency and its own abstractions on top of a well-understood problem.