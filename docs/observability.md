# Question diagnostics and token usage

Every `POST /chat` gets a server-generated `question_id` (`q_...`). Each turn in the
same conversation gets a different question ID. The API returns it in the
`X-Question-ID` header, alongside `usage` in successful response bodies, and in
`details` on application/provider failures. Schema-validation failures retain
FastAPI's usual 422 body and include the header. The frontend proxy passes the JSON
body through; inspect its Network response or use Swagger to see these fields.

## Find a slow or expensive question

From the repository root, follow detailed application logs:

```powershell
docker compose -f docker-compose.yml logs --follow --since=5m backend
```

After a question completes, copy `question_id` from its response and filter:

```powershell
$questionId = 'q_REPLACE_WITH_THE_RETURNED_ID'
docker compose -f docker-compose.yml logs --since=1h backend | Select-String -SimpleMatch $questionId
```

For a new test using the API (this makes Groq calls):

```powershell
$body = @{ message = "Summarize the selected document."; filters = @{ doc_ids = @('doc_REPLACE_WITH_YOUR_DOCUMENT_ID') } } | ConvertTo-Json -Depth 4
$reply = Invoke-RestMethod -Method Post http://localhost:8000/chat -ContentType 'application/json' -Body $body
$reply.question_id
$reply.usage | Select-Object llm_calls,provider_requests,retries,rate_limit_responses,input_tokens,output_tokens,total_tokens,cached_input_tokens,usage_complete,duration_ms,retry_wait_ms
$reply.usage.stages | Format-Table stage,status,duration_ms
$reply.usage.calls | Format-Table stage,attempt,status,status_code,input_tokens,output_tokens,total_tokens,duration_ms,provider_request_id
```

`GET /documents` lists document IDs. Selecting the PDF and DOCX versions of the same
content can increase retrieval work; select the intended sources for the question.

## Events and fields

| Event | What it explains |
| --- | --- |
| `question_started` / `question_completed` | Correlation ID, overall duration, final HTTP status, usage and stage summaries. |
| `stage_started` / `stage_completed` | Dependency initialization, conversation/document lookup, rewriting, retrieval, embeddings, vector search, reranking, context selection, tool planning/execution, analysis, generation, citation checks, verification, and conversation storage. |
| `llm_request_started` / `llm_request_completed` | Stage, logical call ID, actual attempt number, model, output limit, provider response ID, HTTP status, finish reason, duration and provider-reported tokens. |
| `llm_retry_wait_started` / `llm_retry_wait_completed` | Planned and actual wait, separated into provider rate limits, existing local cooldowns and transient failures. |
| `llm_retry_stopped` | Provider attempts and rate-limit wait budget at the point a retry cannot proceed. |
| `document_upload_duplicate` / `document_upload_queued` | An existing document was detected, or a new document/job was queued. Concurrent duplicate conflicts also produce `application_error` with code `DOCUMENT_ALREADY_EXISTS`. |

Large `reranking` or embedding durations indicate local model work. Large provider
durations indicate time spent awaiting Groq. Large `retry_wait_ms` indicates backoff,
not retrieval latency. Repeated generation/verification stages indicate rejected
answers being corrected. A rate-limit record includes the provider's quota type
(TPM/TPD/RPM/RPD) and limit/used/requested numbers when its error supplies them.

Stage durations are **inclusive**: `retrieval` contains embedding/search/reranking,
and `analysis` contains tool planning/verdict calls. Do not add parent and child
durations together. Stage timings describe elapsed wall time, not CPU utilization.

## Counting rules

- `llm_calls` counts logical generation operations, including ones stopped by a local cooldown.
- `provider_requests` counts actual SDK requests, not local cooldown checks or sleeps.
- `retries` counts additional provider attempts within the same logical call. A separate
  corrected answer is a new call, not a transport retry.
- Usage is captured immediately after a provider response, before content/JSON/answer
  validation. Discarded or truncated completions still contribute to totals.
- `input_tokens`, `output_tokens`, and `total_tokens` are provider-reported totals for
  requests with accounting available. Cached input is already included in input totals;
  reasoning tokens are part of output totals. Do not add either again.
- A 429, connection failure or interrupted stream may not report usage. Its per-call
  fields remain `null`, and `usage_unreported_requests` increases. `usage_complete=false`
  means totals are partial, not that missing calls consumed zero tokens.
- `cached_usage_reported_requests` distinguishes a reported cache count from omitted
  cache metadata. Cache hits are not guaranteed.
- Summaries are available for failed questions too. Usage for earlier successful
  stages survives a later failure; no failed answer is saved as a successful turn.

Question and call tracking is request-local, so simultaneous questions do not mix
their counters. Logs contain metadata and counts, not questions, answers, source
text, API keys, or raw provider error bodies. Routine successful health/document
polling and HTTP-client INFO lines are suppressed; `LOG_LEVEL=debug` restores them.

These diagnostics are in responses and application logs, not a new database table
or historical usage endpoint. Docker log retention applies; export needed logs
before recreating containers. They describe this application's calls, not all
usage by other applications sharing the Groq organization.

## Analysis validation and correction

`analysis_output_invalid` records the question ID, `analysis_stage`, `analysis_attempt`,
and `correction_remaining`. Diagnostics distinguish:

- `category=json`: invalid JSON.
- `category=schema`: invalid fields/types, with up to eight `issues` containing a safe
  field path and validation type, e.g. `has_enough_evidence` / `bool_type`.
- `category=grounding`: `unknown_chunk_reference` or `missing_grounded_findings`.
- `category=tool_validation`: deterministic tool arguments or evidence checks failed.

Unknown field names and dynamic dictionary keys are redacted; exception messages,
input values, invalid completions, questions and document text are not logged.
Stage records include `output_valid` and `correction`. A stage with `status=ok` and
`output_valid=false` means the validation failure was caught for bounded recovery,
not that the output was accepted.

`analysis_correction_requested` starts a single correction using the same evidence.
`analysis_output_corrected` records successful correction. The budget is one correction
shared across planning/tool execution and verdict validation per analysis pass, so
there are at most three logical analysis calls instead of the usual two. Correcting
a verdict does not repeat successful tool planning or deterministic execution.
Corrections are separate logical calls, included in token totals under the original
question ID; provider transport retries retain their existing separate bounds.

`analysis_correction_exhausted` ends the question with HTTP 503
`ANALYSIS_OUTPUT_INVALID`. Invalid analysis is never a retrieval query. Only a
validated insufficient-evidence verdict (or no retrieved evidence) requests more
evidence. A successful correction must still pass the normal citation and answer
verification checks. This can reduce wasted work, but does not eliminate rate limits
or guarantee that the model's next output is valid.

## Source sharing and duplicate files

Uploading identical bytes again, even under another filename, returns HTTP 409
`DOCUMENT_ALREADY_EXISTS` with the existing document ID/name. No new job is queued.
The existing unique checksum index also resolves concurrent uploads; a rejected
request's temporary file is removed. Reindex the existing document to retry ingestion.
Different content with the same filename is allowed. A PDF and DOCX with similar
visible content are different files and can both be stored.

Prompts now keep exact source strings in a shared `texts` map. Chunk IDs, document
metadata, excerpt IDs, and per-block citation references stay separate. Verification
retains both the selected quote and its full surrounding context and may use only
the sources cited by that block. Identical strings are shared; differing numbers,
punctuation, caveats, tables, or wording are not silently merged. The deterministic
citation checks and independent semantic review remain in place.

This reduces repeated text within prompts; it does not eliminate the need to send
evidence to separate analysis/answer/review calls. It does not reset provider quotas
or guarantee that every question fits the provider's per-minute limit.

## Optional live verification

The following smoke test uses synthetic evidence and in-memory conversation storage.
It sends real Groq requests, but does not read uploaded documents or modify SQLite,
Qdrant, or ingestion jobs. Retrieval is fixed, so this check isolates the API,
prompts, tools, citations, verification, and usage reporting rather than exercising
embedding/reranking quality.

```powershell
docker compose -f docker-compose.yml cp infrastructure/scripts/smoke_observability.py backend:/tmp/smoke_observability.py
docker compose -f docker-compose.yml exec -T -e PYTHONPATH=/app backend python /tmp/smoke_observability.py
```

It checks a calculated answer with a simulation qualification and rejects an
unsupported deployment claim. A successful run prints `{"status":"passed","checks":2}`.
Its synthetic answer is printed explicitly by the test script; normal application
diagnostic events do not print answer/source content.
