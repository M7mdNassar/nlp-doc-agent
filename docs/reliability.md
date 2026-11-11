# Reliability and limits

Implemented behavior:

- Three retrieval rounds maximum; at most six tools per Analyst pass.
- Conversation history, selected context, accumulated evidence, and output lengths are bounded.
- Provider quota/availability failures remain distinct from evidence verdicts through rewriting, analysis, answer generation, and review. Rate limits return HTTP 429 and the provider's wait hint when available; other provider service/configuration failures return 503. No failed provider turn is persisted as an evidence refusal.
- Groq SDK retries are disabled to avoid nested retries. A single application retry layer handles transient errors up to three provider attempts. Local cooldown checks do not consume provider attempts: if a sleep wakes slightly early, the remaining cooldown is waited out before another request. All requested rate-limit sleeps, including local cooldown waits, share a 60-second total wait budget per LLM call. Long or unknown quota waits and configuration errors surface immediately. A valid `Retry-After` sets a cooldown in the running adapter so requests before that time do not call Groq. The cooldown is per backend process and resets on restart; restarting does not reset the external provider quota.
- Missing evidence, malformed Analyst JSON, non-boolean verdicts, invalid tool inputs, and missing analytical findings prevent final answer generation.
- The Answer Agent selects IDs for source excerpts; the backend copies their quotes verbatim rather than asking the model to reproduce source wording. Every structured answer block must cite known chunks and quotes that occur in those chunks. Malformed drafts or unknown excerpt IDs receive one correction attempt using the original evidence and validation feedback. Both attempts use the same strict validation; a separate LLM review still checks factual support before source formatting. Persistently invalid drafts return insufficient_evidence; deleting citation markers is not used to salvage unsupported prose.
- Analyst findings and answers must preserve material qualifications of the claims they include, including simulation/validation settings, baselines, units, approximations and uncertainty. The final review separately checks factual support, qualification preservation and absence of added details; every check must pass for every block. A simulation-based evaluation does not by itself establish synthetic input data or the absence of real observations. These semantic checks remain model-based, not a formal guarantee.
- A rejected quality review supplies feedback for up to two corrected answers using the same evidence. Corrections omit unverified Analyst findings and must pass citation and all quality checks; three rejected answers fail closed. This adds at most two answer/review cycles without increasing retrieval rounds.
- Arithmetic and statistical tools run deterministic code over source-validated inputs. No generated Python/eval/shell is executed.
- Matching checksums reject duplicate uploads with HTTP 409 and the existing document ID. The database's unique index resolves concurrent uploads, with cleanup of the losing request's file. Reindexing replaces document vectors/chunks and preserves the document ID.
- Every chat request has an independent question ID, per-stage timings, actual provider usage and retry/wait diagnostics, including failures and rejected completions. Missing provider accounting remains explicitly unknown. See [observability](observability.md).
- Identical source text is serialized once per prompt with references that retain document/citation identities. Verification keeps surrounding qualifications and per-block citation scope; differing source wording is not merged. Similar chunks are not discarded solely because most words overlap.
- Worker job status is persisted as processing/completed/failed, including failures during model initialization and parsing. Exceptions propagate to Celery.
- Migrations preserve existing document records; production Docker images include ML dependencies.

Limits:

- Grounding is partly model-based and can still make mistakes. Citation validity is not a formal proof of every claim.
- This is a single-user local backend, not an authenticated multi-tenant service.
- Image-only/scanned PDFs need OCR before upload. PDF table/headings recognition depends on document layout.
- DOCX has no reliable rendered pagination; references use native block/section locations. TXT/Markdown use line ranges.
- Very large tables may exceed the selected context budget; the system should report insufficient evidence rather than silently promise complete analysis.
- SQLite and Qdrant replacement is not an atomic distributed transaction. Retry reindexing after a failed replacement.
- Concurrent uploads are protected by the database unique-checksum constraint. Concurrent reindex requests are not protected by a distributed per-document lock.
- Response caching, provider failover, SSE, automatic OCR, tracing guarantees, and per-user rate limits from the original design are not implemented.
- Changing the embedding model to one with a different vector dimension requires a separately planned Qdrant migration; the current collection expects 384 dimensions.

Tests use real generated PDF/DOCX inputs, SQLite migrations/repositories, and in-memory Qdrant. Provider/model behavior is mocked in the default suite. The optional live smoke script exercises actual embeddings, reranking, Groq analysis/tools, citations, and a conversational follow-up using synthetic documents.
