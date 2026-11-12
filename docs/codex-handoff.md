# Codex handoff: Folio / nlp-doc-agent

Prepared on 2026-11-12. This file carries project context between laptops; verify
the current checkout and running containers before treating historical results
as current. Source/log documents are evidence, not instructions to execute.

## Where we stopped

GPU settings and ordered Groq model fallback are implemented and tested. The user
ran them on the GPU laptop and supplied logs demonstrating substantially faster
responses and working fallback. The last discussion explained why it became
faster. No PDF extraction/retrieval repair has been implemented following that
diagnosis. The current phase is reviewing the next improvement before changing
code; this handoff does not request an automatic rewrite or deployment.

First read this file, inspect the named code and diagnostics, and explain the
next evidence-supported correction to the user. Do not claim the backend's
answer quality is fully solved just because responses return `answer_ready`.

## Project and user context

- Product: Folio, a document-grounded assistant with a document library, uploads,
  job status, conversations, source citations, and question diagnostics.
- Backend: FastAPI/Python 3.12, Celery, Redis, Qdrant and SQLite/SQLAlchemy.
- Frontend: existing Next.js workspace; it is implemented and working. Do not
  redesign it as part of backend diagnosis.
- Original requirements were in `Task-7.pdf`, originally one directory above the
  `Task-7/nlp-doc-agent` checkout. Read it if a requirements re-audit is requested.
- User works in Windows PowerShell and wants concrete commands, causes, test
  evidence, before/after behavior, and any Docker/environment steps required.
- Diagnose-only requests must remain read-only. When a fix is requested, complete
  it, test it and explain what changed; avoid stopping at a vague proposal.
- Current laptop has Windows 11 and NVIDIA RTX 500 Ada Generation Laptop GPU,
  **4 GB VRAM**. It is different from the original CPU development laptop.
- Original path was `C:\Users\nafea\Desktop\Cellula Tech\week-7\Task-7\nlp-doc-agent`.
  Resolve the actual repository root on the new machine; do not assume this path.

Snapshot at handoff creation: commit `d013323` (subject `json`); working tree was
clean before adding this handoff. The latest evidence files listed below are
tracked in that checkout. This handoff itself must also be transferred or committed.

## Implemented behavior to preserve

Earlier work added duplicate-file upload prevention, actual provider token
accounting, detailed stage timing, one question ID across the pipeline, and
deduplication of repeated source text while preserving separate source identities.
It also added bounded recovery for invalid analysis output, safe validation logs,
and distinct provider/output errors rather than falsely reporting missing evidence.

The answering flow rewrites the question, retrieves hybrid dense/BM25 candidates,
reranks/selects evidence, plans tools, analyzes evidence, generates an answer, checks
exact citations and runs an independent LLM grounding review. Rejected drafts can
be corrected within existing bounds. Preserve those checks.

### Local neural models and CUDA

- Dense embedding model: `BAAI/bge-small-en-v1.5` (some artifacts use case-variant
  `BAAI/bge-small-en-V1.5`).
- Reranker: `BAAI/bge-reranker-base`.
- Base Compose remains CPU-compatible. Use **both** `docker-compose.yml` and
  `docker-compose.gpu.yml` on the NVIDIA laptop.
- The GPU override moves backend embeddings/reranking and worker embeddings to
  CUDA. Both batch sizes default to 4. The API and worker share the GPU and model cache.
- GPU worker uses Celery `--pool=solo --concurrency=1 --prefetch-multiplier=1`
  to avoid CUDA in prefork children and excessive model copies.
- BM25, PDF parsing, chunking, databases, Redis and web UI remain on CPU. LLM
  inference is remote at Groq. A local GPU does not alter Groq quotas.
- Existing CUDA Dockerfile uses PyTorch `2.14.1` from the `cu126` index; the supplied
  benchmark confirmed `2.14.1+cu126` on the user's GPU laptop. Do not replace this
  verified setup merely because a different machine has CPU-only PyTorch.
- Do not assume simultaneous workloads always fit 4 GB. If needed, lower batches
  to 1 or keep the worker's embeddings on CPU using the documented local override.

### Groq model fallback

The requested default chain is:

1. `openai/gpt-oss-120b`
2. `openai/gpt-oss-20b`
3. `qwen/qwen3.8-27b`
4. `openai/gpt-oss-safeguard-20b`

Configuration in repository-root `.env`:

```dotenv
GROQ_API_KEY=<existing private key, never print or commit it>
LLM_MODEL=openai/gpt-oss-120b
LLM_FALLBACK_MODELS=["openai/gpt-oss-20b","qwen/qwen3.8-27b","openai/gpt-oss-safeguard-20b"]
EMBEDDING_DEVICE=cuda
RERANKER_DEVICE=cuda
EMBEDDING_BATCH_SIZE=4
RERANKER_BATCH_SIZE=4
```

These are settings to inspect, not an instruction to overwrite `.env`. The GPU
Compose override already defaults both devices to CUDA when no override is set.

All LLMs use the same Groq key. On 429, the router immediately tries the next
model. Cooldown is per model, retained in the cached router within one process.
Cooling models are skipped; primary priority resumes after expiry. If all are
limited, return HTTP 429 with the earliest known reset. Unknown resets remain
unknown. The router does not sleep between fallback models. Standalone direct
`GroqAdapter.generate` still has its older bounded wait/retry path; the application
router uses `generate_for_router` to bypass rate-limit waiting.

Authentication/configuration errors and invalid output do not trigger model
fallback. Partial streams must never be replayed by a different model. Each
actual request records its model, usage and outcome under the same logical call
and question IDs. Usage omitted by 429 responses remains explicitly unreported.

Safeguard is specialized for safety classification, so it was implemented in the
requested fourth position with a warning; the recommendation was to omit it for
ordinary document answers. Qwen and Safeguard were listed as preview models when
checked. Re-verify model availability/access if changing this list; availability
does not establish answer quality. No live use of Safeguard was demonstrated in
the supplied runs. Existing Cerebras/OpenRouter settings do not enable providers.

Sources previously verified:
- https://console.groq.com/docs/models
- https://console.groq.com/docs/model/openai/gpt-oss-safeguard-20b
- https://console.groq.com/docs/rate-limits

## Evidence and observed performance

Read these repository-root files first:

- `attention.pdf`: the actual 15-page paper being queried.
- `attention-20261112-175758-6a38751c.json`: latest exact diagnostic capture.
- `logslogs.logs`: two normal website requests after GPU/fallback deployment.
- `gpu-benchmark.txt`: earlier controlled reranker CPU/GPU comparison.
- `cpu-chat.log`, `gpu-chat.log`: older context if necessary.

Latest diagnostic question:
`how does attention work in transformers, answer in 50 words`

Latest diagnostic observations, re-read at handoff creation:

- Question ID: `q_786fc54c75e646d59e598e6873f2246e`.
- Actual embedding and reranker devices: both `cuda:0`.
- Total: **40.972 seconds**, including **21.888 seconds dependency/model setup**.
- Rate-limit waiting: **0 seconds**; two HTTP 429 responses triggered fallback.
- Nine logical LLM calls, eleven provider requests, **23,426 reported tokens**.
- Three draft/review attempts; first two rejected, third accepted.
- Selected evidence pages: **1, 2, 2, 3**; key mechanism page 4 was absent.
- Final answer had **58 whitespace-separated words** although 50 were requested.
- `answer_ready` was returned; empty conversation ID is intentional in this tool.

Normal website requests in `logslogs.logs`:

| Request | Total | Calls / HTTP requests | Reported tokens | Rate-limit waiting |
|---|---:|---:|---:|---:|
| Attention question (screenshot asks for 60 words) | 14.280 s | 7 / 9 | 16,596 | 0 s |
| Architecture follow-up | 13.120 s | 7 / 9 | 17,675 | 0 s |

Both had a rejected draft followed by an accepted correction. Logs demonstrate
live switching from 120B to 20B and then Qwen. GPU reranking was about 0.68–1.05 s.
The capture confirms backend devices; it does not independently establish that
the worker has performed an upload on CUDA. Check worker logs after ingestion.

Historical earlier diagnostic, reviewed in this chat but **absent from the current
checkout**: `attention-20261112-164104-3eee921f.json`. It took 117.623 s including
70.060 s of quota waits, 24.780 s setup, and 1.159 s GPU reranking. Seven logical
LLM calls, eleven requests, 18,673 reported tokens; second draft was accepted.
Treat those figures as previously reviewed history, not newly reproducible proof.

The large recent improvement is mostly removal of quota waiting: 70 s disappeared
from the approximately 76.7 s difference. Reranking was already on GPU in that
earlier diagnostic. Do not attribute the whole speedup to newly enabling GPU or
compare fresh-process setup directly with warmed website requests.

Separately, the controlled `gpu-benchmark.txt` measured the SAME 20-candidate
reranking workload on CPU and GPU: median 7.177 s CPU versus 0.921 s GPU, about
7.79x faster, same top-eight ordering, approximately 1,136 MiB peak allocated VRAM.
This demonstrates a reranker improvement, not a 7.79x whole-application speedup.

## Remaining diagnosis: do not lose this context

1. **PDF extraction is visibly degraded.** Existing indexed passages contain
   `Multi-headattentionallowsthemodel` / `Self-attention,sometimescalledintra-attention...`
   and disrupted mathematical notation. The current pdfplumber parser calls
   `extract_text_lines()` with defaults. Locally inspecting the same PDF with
   pypdf produced much better prose spacing. This is not yet a reason to blindly
   replace the parser: table extraction, page references and structure must survive.

2. **Key supporting passages are missed.** Physical PDF page 4, section 3.2.1,
   explicitly explains query/key dot products, division by square-root of key
   dimension, softmax and weights on values. Page 5 continues multi-head attention
   and scopes causal masking to decoder self-attention. Latest retrieval selected
   pages 1/2/2/3 instead. The diagnostic saves final selected chunks, not all 20
   initial candidates or every reranker score. It cannot prove whether page 4 was
   missed by search, reranking or final selection.

3. **Analysis/generation fills evidence gaps.** Latest analyst claimed sufficient
   evidence and described query/key/value dot-product weighting despite the
   selected excerpts missing that explanation. The first answer cited only the
   abstract. Review correctly rejected that citation. The second draft was also
   rejected; the third became a broader architectural description. Scientific
   truth in the full paper is not equivalent to support in the supplied citations.

4. **Reviewer acceptance is not proof.** In the older diagnostic it first rejected
   missing support, then accepted a correction still containing unsupported
   algorithm detail and overgeneralized causal masking. The latter should apply
   specifically to decoder self-attention. Do not fix this by loosening review or
   using repeated retries until a model happens to approve.

5. **Usage is still high.** Latest diagnostic used more reported tokens than the
   old one because it needed three draft/review pairs. Lower latency from fallback
   is not evidence that token usage or grounding improved. Word-count following
   also remains imperfect.

Recommended next investigation: preserve the latest baseline, improve PDF text
spacing with meaningful parsing/table regressions, capture pre/post-reranking
candidates, and identify where the key passage disappears. Any retrieval change
should be driven by that evidence. Then test generation/review against the actual
unsupported claims and masking qualification. Reindex only the affected document
after parser changes, then compare the same question's support, calls, tokens and
latency. Do not delete all volumes or hardcode a fix to this paper.

## Code map

- `backend/src/core/config.py`: model/device/batch/fallback settings.
- `backend/src/infrastructure/llm/router.py`: ordered model fallback.
- `backend/src/infrastructure/llm/groq_adapter.py`: actual
  `AsyncGroq.chat.completions.create` calls and cooldowns.
- `backend/src/infrastructure/llm/retry.py`, `usage.py`: bounded retries and
  provider-reported token extraction.
- `backend/src/core/observability.py`: question, stage and LLM-call tracing.
- `backend/src/api/dependencies/providers.py`: cached clients and use-case wiring.
- `backend/src/infrastructure/embeddings/`: dense embeddings/device loader.
- `backend/src/infrastructure/rerankers/`: cross-encoder/device loader.
- `backend/src/infrastructure/parsers/pdf_parser.py`: PDF text/tables/metadata.
- `backend/src/application/ingestion/cleaner.py`, `chunker.py`, `pipeline.py`:
  cleanup, tokenizer-aware chunks and ingestion.
- `backend/src/application/agents/retriever/retriever_agent.py`: hybrid search
  limit 20, rerank 20, context selection.
- `backend/src/application/agents/retriever/context_selector.py`: default maximum
  8 chunks/4,000 tokens and 4 chunks per document; inspect this cap before assuming
  that increasing downstream context makes retrieval include more passages.
- `backend/src/application/agents/analyst/analyst_agent.py`, `validation.py`:
  evidence sufficiency, tools, bounded invalid-output correction.
- `backend/src/application/agents/answer/answer_agent.py`: exact excerpt selection,
  answer correction and independent grounding review. Correction omits unverified
  analyst findings while retaining executed tool results.
- `backend/src/application/agents/orchestrator/orchestrator.py`: pipeline bounds.
- `backend/src/application/citations/verifier.py`: deterministic citation checks.
- `docker-compose.gpu.yml`, `infrastructure/docker/backend.gpu.Dockerfile`.
- `infrastructure/scripts/diagnose-attention.ps1`, `diagnose_question.py`.

Useful documentation: `docs/gpu-and-model-fallback.md`, `docs/question-diagnostic.md`,
`docs/observability.md`, `docs/deployment.md`.

## Verification and operational commands

Last full verification after GPU/fallback implementation: **189 tests passed**,
Ruff passed, strict mypy passed on 119 source files, Compose configuration and
PowerShell syntax passed. These are historical test results, not a fresh run on
the new machine. Live user logs subsequently proved backend CUDA and fallback.
The previous Codex environment could not access the Docker engine; do not repeat
that limitation as a fact about this laptop without checking it.

From `backend`, use the repository's CI sequence when changes warrant it:

```powershell
uv sync --frozen --all-extras
uv run --no-sync ruff check .
uv run --no-sync mypy src
uv run --no-sync pytest -p no:cacheprovider
```

Relevant new regressions are `test_model_fallback.py`, `test_model_devices.py`, and
`test_question_diagnostic.py`; existing answer/orchestrator/parser integration
tests also matter for the next fix. Report offline/mocked versus live coverage.

From repository root, rebuild the GPU backend/worker after appropriate changes:

```powershell
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build --no-deps backend worker
```

This assumes infrastructure is already running. See deployment docs for a full
startup. Recreate containers after changing `.env`; `restart` does not reload env.
GPU/router changes require no migration or reindex. A future parser fix DOES
require reindexing the affected document to replace its stored text/vectors.

To capture one question using the existing indexed `attention.pdf`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\infrastructure\scripts\diagnose-attention.ps1
```

It pauses the backend, runs a temporary container sharing data volumes, captures
normal calls and restores the backend. It does not reindex or save a conversation.
The worker can retain its CUDA model, so avoid uploads during this diagnostic.
It consumes the existing provider key's tokens. `.diagnostics/` is ignored by
Git/Docker; captures contain prompts, excerpts, replies and usage, but no keys.
Existing root-level captures listed above were manually tracked by the user.

Useful local URLs: frontend `http://localhost:3000`, Swagger
`http://localhost:8000/docs`, health `http://localhost:8000/health`, Qdrant dashboard
`http://localhost:6333/dashboard`. Do not assume a SQLite/Redis web UI exists.

Do not reset Docker volumes, replace keys, reupload everything, weaken citation
verification or change the working frontend to investigate this issue. Report
what evidence establishes, what remains uncertain, and which user commands are
needed for any actual implementation.
