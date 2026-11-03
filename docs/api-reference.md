# API Reference

This document describes the local API for **NLP Doc Chat**, including authentication, error responses, endpoints, streaming behavior, and rate limits.

## Base URL

```text
http://localhost:8000
```

All endpoints use JSON for requests and responses unless stated otherwise. File uploads use `multipart/form-data`, and the streaming chat endpoint uses Server-Sent Events (SSE).

The OpenAPI schema is generated at `docs/api/openapi.json`. It is the source of truth for the generated TypeScript client.

## Table of Contents

- [Authentication](#authentication)
- [Error Contract](#error-contract)
  - [Common Error Codes](#common-error-codes)
- [Endpoints](#endpoints)
  - [`GET /health`](#get-health)
  - [`POST /documents`](#post-documents)
  - [`GET /documents`](#get-documents)
  - [`DELETE /documentsdocument_id`](#delete-documentsdocument_id)
  - [`GET /jobsjob_id`](#get-jobsjob_id)
  - [`POST /chat`](#post-chat)
  - [`POST /chat/stream`](#post-chatstream)
- [Rate Limits](#rate-limits)

---

## Authentication

Version 1 uses a **JWT stored in an HttpOnly cookie**.

The frontend obtains the token through the login route and forwards it automatically with API requests. All API routes require a valid session except `GET /health`.

## Error Contract

All error responses use the same JSON structure:

```json
{
  "code": "RETRIEVAL_UNAVAILABLE",
  "message": "Human-readable description.",
  "details": {
    "dependency": "qdrant"
  },
  "trace_id": "01HX..."
}
```

### Common Error Codes

| Code | Meaning |
|---|---|
| `VALIDATION_ERROR` | The request body or parameters are invalid. |
| `UNAUTHORIZED` | The session is missing or invalid. |
| `FORBIDDEN` | Access to the requested document is denied. |
| `NOT_FOUND` | The requested resource does not exist. |
| `DOCUMENT_FAILED` | Document ingestion failed. See `details.reason` for the reason. |
| `INSUFFICIENT_EVIDENCE` | The pipeline completed but could not find enough evidence to answer. |
| `RETRIEVAL_UNAVAILABLE` | The vector store is unavailable. |
| `LLM_UNAVAILABLE` | All LLM providers are unavailable. |
| `RATE_LIMITED` | A provider or API rate limit has been reached. |
| `INTERNAL_ERROR` | An unexpected failure occurred. The error is logged with its `trace_id`. |

## Endpoints

### `GET /health`

Returns the status of the API's dependencies.

**Authentication:** Not required.

**Example response:**

```json
{
  "status": "ok",
  "dependencies": {
    "qdrant": "ok",
    "redis": "ok",
    "sqlite": "ok",
    "groq": "ok"
  }
}
```

The overall `status` can be one of:

- `ok` — all dependencies are available.
- `degraded` — one or more dependencies are experiencing issues.
- `down` — the service is unavailable.

### `POST /documents`

Uploads a document and queues it for asynchronous ingestion. The response contains a document ID and an ingestion job ID.

**Content type:** `multipart/form-data`

**Fields:**

| Field | Required | Description |
|---|---:|---|
| `file` | Yes | The document to upload. |
| `tags` | No | Comma-separated tags for the document. |

**Success response:** `202 Accepted`

```json
{
  "document_id": "doc_01HX...",
  "job_id": "job_01HX...",
  "status": "queued"
}
```

### `GET /documents`

Returns the documents that the authenticated user is allowed to access.

**Example response:**

```json
{
  "items": [
    {
      "document_id": "doc_01HX...",
      "name": "paper.pdf",
      "type": "pdf",
      "pages": 42,
      "chunks": 187,
      "status": "ready",
      "uploaded_at": "2026-01-12T10:00:00Z"
    }
  ]
}
```

### `DELETE /documents/{document_id}`

Deletes the specified document and its related data. This includes its chunks, vectors, and cached answers that cite the document.

**Success response:** `204 No Content`

### `GET /jobs/{job_id}`

Returns the current status of a document ingestion job.

The `status` field can be one of:

- `queued`
- `parsing`
- `embedding`
- `indexed`
- `failed`

When ingestion fails, the response includes an `error` field containing the reason for the failure.

### `POST /chat`

Sends a question and returns the complete answer in a single JSON response.

**Example request:**

```json
{
  "message": "What is the accuracy of Model X in Chapter 4?",
  "conversation_id": "conv_01HX...",
  "document_ids": [
    "doc_01HX..."
  ]
}
```

**Example response:**

```json
{
  "conversation_id": "conv_01HX...",
  "answer": "Model X achieves 92.4% accuracy [paper.pdf, p. 12].",
  "citations": [
    {
      "doc_id": "doc_01HX...",
      "doc_name": "paper.pdf",
      "page": 12,
      "section": "4.2",
      "chunk_id": "chunk_01HX...",
      "quote": "Model X achieves 92.4% accuracy on the test split."
    }
  ],
  "assumptions": [],
  "conflicts": [],
  "insufficient": false,
  "trace_id": "01HX..."
}
```

The response includes the answer, resolved citations, any assumptions or conflicts, an indicator of whether the evidence was insufficient, and a trace ID for debugging.

### `POST /chat/stream`

Sends a question and streams the answer using **Server-Sent Events (SSE)**.

The stream emits events in the following order:

| Order | Event | Purpose |
|---:|---|---|
| 1 | `meta` | Provides the conversation ID and trace ID. |
| 2 | `token` | Sends text deltas as the answer is generated. This event can occur multiple times. |
| 3 | `citations` | Provides the final list of resolved citations. |
| 4 | `assumptions` | Provides assumptions and conflicts, if any. |
| 5 | `done` | Marks the end of the stream. |

If an error occurs, the stream emits an `error` event containing the standard error object, then closes.

The frontend uses a Next.js route handler to bridge this SSE protocol to the Vercel AI SDK. The backend does not communicate directly with the browser.

## Rate Limits

The API enforces the following limits on the server:

| Operation | Limit |
|---|---|
| Chat requests | 10 requests per minute per user. |
| Document uploads | 5 documents per minute per user. |
| Ingestion concurrency | 1 document per user at a time. |

When a rate limit is exceeded, the API returns **`429 Too Many Requests`** with the error code `RATE_LIMITED`.
