# Backend API

Base URL: http://localhost:8000. Interactive documentation: /docs; live OpenAPI schema: /openapi.json.

The current API is a local single-user service without authentication. Chat returns a complete JSON response; there is no /chat/stream endpoint.

## Documents and jobs

| Endpoint | Behavior |
|---|---|
| POST /documents | Multipart file upload (field: file); PDF, DOCX, TXT, MD. Returns document_id, job_id, status with HTTP 200. |
| GET /documents | Returns {"items":[{"id":"doc_...","name":"paper.pdf","status":"indexed"}]}. |
| POST /documents/{doc_id}/reindex | Reprocesses the stored upload, preserving the document ID. Returns a new job ID. An active ingestion job is rejected. |
| DELETE /documents/{doc_id} | Deletes vectors and relational document/chunk/job records. Returns {"status":"deleted"}. |
| GET /jobs/{job_id} | Returns job_id, document_id, status, error, updated_at. |
| GET /health | Reports SQLite, Qdrant, and Redis connectivity; does not test Groq inference. |

Job statuses: queued, processing, completed, failed.
Document statuses: queued, parsing, embedding, indexed, failed.
A duplicate checksum returns HTTP 409 `DOCUMENT_ALREADY_EXISTS`, with the existing
`document_id` and `document_name` in `details`. This also covers concurrent uploads
and renamed copies. No new document or ingestion job is created. Use reindex to
retry failed ingestion or upgrade old metadata. Different bytes with the same name
are allowed; PDF and DOCX versions are not treated as byte-identical uploads.

## POST /chat

First question:

    {
      "message": "Compare accuracy in Chapter 4 of paper.pdf.",
      "filters": {"document_name": "paper.pdf", "chapter": "4"}
    }

Follow-up: send the conversation_id returned by the first response.

    {
      "message": "Which model is best?",
      "conversation_id": "conv_..."
    }

Filters are optional and strictly validated:

| Field | Type |
|---|---|
| doc_id | string |
| doc_ids | list of strings; empty list intentionally matches nothing |
| document_name | string; exact filename, case-insensitive |
| page | positive integer |
| chapter | string, e.g. "4" |
| section | section title or numeric section identifier |
| author | string; exact metadata value, case-insensitive |
| date | string; metadata date, normally YYYY-MM-DD |
| file_type | string: pdf, docx, txt, md |

Explicit filters remain active through retries. Supported natural-language forms include filenames, "Chapter 4", "page 2", "Section 2.1", dated/published dates, quoted author names, and "PDF documents". Unknown named files match no documents rather than widening the search. Metadata must actually exist in the source; absent author/date/headings are not invented.

Response fields:

    {
      "answer": "A formatted answer with document/location citations and a Sources list",
      "state": "answer_ready",
      "loops": 0,
      "evidence_count": 3,
      "sources": [
        {
          "chunk_id": "chunk_...",
          "document_id": "doc_...",
          "document_name": "paper.pdf",
          "page": 4,
          "section": "Chapter 4",
          "location": null,
          "quote": "Exact source text"
        }
      ],
      "tool_results": [
        {
          "name": "calculator",
          "output": {"expression":"(a+b+c)/3","inputs":{"a":"92","b":"95","c":"89"},"result":"92"},
          "chunk_ids": ["chunk_...", "chunk_...", "chunk_..."]
        }
      ],
      "conversation_id": "conv_..."
    }

state is answer_ready or insufficient_evidence. loops counts additional retrieval rounds (0 to 2).
Successful chat responses additionally include `question_id` and `usage` (token totals,
provider attempts, retry waits, per-call records and stage timings). `X-Question-ID`
is also returned as a header. Each turn gets its own ID, independent of conversation ID.
Provider/application failures include these diagnostics in `details`; 422 validation
responses include the header. See [question diagnostics](observability.md) for fields
and log-filtering commands. Missing provider usage is flagged as unknown rather than
assumed to be zero.
Insufficient evidence or rejected answer validation produces an explicit refusal with no sources.
For DOCX/TXT/Markdown, location is the citation locator; page=1 is an internal logical container, not a rendered physical page.

## Errors

Application errors contain code, message, and details. Missing resources return 404;
duplicate uploads return 409; upload/reindex validation returns 400; queue submission
failure returns 503. FastAPI request/schema validation uses its standard 422 detail response.

Provider failures are service errors, not `200 insufficient_evidence` answers:

- `429 LLM_RATE_LIMITED`: the LLM provider rejected the request due to a request/token limit. If the provider supplies a valid wait duration, the response includes a `Retry-After` header (seconds) and `details.retry_after_seconds`.
- `503 LLM_UNAVAILABLE`: a provider connection or availability failure after bounded retries.
- `503 LLM_CONFIGURATION_ERROR`: the provider rejected its credentials, model, or request configuration.

For example, a rate-limited chat can return:

```json
{
  "code": "LLM_RATE_LIMITED",
  "message": "Groq has reached a request or token limit. Please try again later.",
  "details": { "provider": "Groq", "retry_after_seconds": 879 }
}
```

These failures do not save a fabricated insufficient-evidence answer to conversation history. A provider wait hint is not a guarantee that all remaining LLM calls for an answer will fit the quota. Genuine missing evidence and exhausted answer-verification attempts still return the normal `insufficient_evidence` result.

Malformed or ungrounded analysis output receives at most one correction per analysis
pass, shared between tool planning and the evidence verdict. The correction uses the
same evidence; a verdict correction reuses already executed tool results. If validation
still fails, `/chat` returns HTTP 503 `ANALYSIS_OUTPUT_INVALID` instead of retrieving
again or claiming the documents lack evidence. Its `details` include `analysis_stage`,
`correction_attempts`, `question_id`, and the accumulated `usage`. No failed turn is
saved. The frontend displays the service-error message with its existing retry action.
Provider errors and unexpected application errors keep their existing error handling.

Do not interpret health=ok as proof that a particular document, model, provider key, or answer is correct. Poll jobs and inspect their errors.
