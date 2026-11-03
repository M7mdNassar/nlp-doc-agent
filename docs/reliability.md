# Reliability Invariants

These invariants define the contract between the system and its users. They are enforced in code and must not be relaxed without a decision record.

## Invariants

1. **No unsupported answer.** Every answer either contains citations or explicitly states that evidence is insufficient.
2. **No fabricated citation.** Every citation is resolved to a real chunk in the evidence package by the post-generation verifier. Unresolved citations are stripped or downgraded.
3. **No LLM arithmetic.** All numerical computation goes through the Calculator tool. The LLM never performs arithmetic.
4. **No LLM-enforced access control.** Metadata filters proposed by the LLM are validated server-side against the user’s document access. The retrieval layer enforces authorization, not the model.
5. **Bounded autonomy.** Every question runs under hard limits on retrieval rounds (max 2 feedback loops), clarification turns (max 1), tool calls per turn, and total latency.
6. **Bounded context.** Every LLM call has a pre-computed token budget. Requests exceeding the budget are truncated or rejected before they reach the provider.
7. **Idempotent ingestion.** Re-uploading an identical document is a no-op. Concurrent ingestion of the same document is serialized by a per-document lock.
8. **Atomic upserts.** Dense and sparse vectors for a chunk are written together. A partial write cannot occur.
9. **Traceable.** Every request carries a `trace_id` propagated across all stages, log entries, and OTel spans.
10. **Graceful degradation.** Every external dependency has a documented fallback and a visible state in the UI.
11. **Cache correctness over hit rate.** The semantic cache uses a strict similarity threshold. False positives are worse than misses.
12. **Reproducible builds.** Lockfiles are committed. Container images are pinned to specific versions.
13. **Reversible ingestion.** Deleting a document cascades to chunks, vectors, and every cached answer that cited it.

## Failure Handling

| Failure | Handling |
|---|---|
| Encrypted PDF | Rejected at validation, status `failed`, user notified |
| Corrupted file | Quarantined, ingestion job moves to dead-letter, user notified |
| Duplicate upload | Short-circuits via checksum, returns existing document ID |
| Scanned PDF with low OCR confidence | OCR fallback runs, per-page confidence stored, Analyst warned |
| Empty retrieval | Answer returns explicit “no evidence” with search diagnostics |
| Conflicting evidence | Analyst flags conflict, Answer surfaces both sides with citations |
| Feedback loop runaway | Hard cap at 2 rounds, then explicit insufficiency |
| Groq rate limit | Fallback model, then fallback provider, then partial answer with notice |
| Groq outage | Degraded mode: retrieval-only response with cached or partial evidence |
| Qdrant unavailable | Retrieval fails closed, no hallucination; explicit error to user |
| Redis unavailable | Degraded mode: no cache, ingestion pauses, health endpoint reports degraded |
| Embedding model upgraded | Version mismatch triggers full re-embed job; old vectors marked stale |
| Prompt injection in a document | Sanitized before LLM; Analyst system prompt explicitly ignores embedded instructions |
| Invalid citation placeholder | Verifier strips or downgrades before response |
| Ambiguous query | Max one clarification turn, then best-effort with explicit assumption |
| Duplicate concurrent queries | Redis lock coalesces into a single computation |
| Stale cache after document update | Citation-based invalidation evicts affected entries |
| Interrupted ingestion | Worker task is idempotent and resumes from last completed step |

## Degraded Modes

The `/health` endpoint reports the state of each dependency. The UI shows a banner when the system is degraded. A degraded system is **still honest**: it does not pretend to be healthy by returning answers it cannot support.

| Dependency | Degraded behavior |
|---|---|
| Groq | Serve cached answers only; reject new questions with a clear message |
| Qdrant | Serve cached answers only; ingestion continues queueing |
| Redis | No caching, no locks; ingestion paused; chat continues at reduced rate |
| SQLite | System unavailable; fail loud |

## Testing for Reliability

- Unit tests cover every invariant that can be tested in isolation.
- Integration tests cover adapter behavior against real Qdrant, Redis, and SQLite.
- Contract tests enforce that every adapter honors its port.
- A golden evaluation set is run in CI to catch regressions in retrieval recall and citation precision.