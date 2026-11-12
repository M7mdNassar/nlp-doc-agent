# GPU inference and Groq model fallback

The GPU Compose override enables CUDA for dense embeddings in both the API and
ingestion worker, and for cross-encoder reranking in the API. It uses the existing
CUDA image and shared model cache. Base Compose continues to work on CPU.

BM25 is a lexical tokenizer/scorer and stays on CPU, together with PDF parsing,
chunking, Qdrant, Redis, SQLite and the web application. Groq serves LLM inference
remotely. A local GPU does not change Groq quotas or accelerate provider waits.

## Apply on the NVIDIA Windows laptop

Docker Desktop must be running Linux containers with WSL2 GPU support. From the
repository root, update the root `.env` with the following lines; keep your
existing `GROQ_API_KEY` and infrastructure settings:

```dotenv
LLM_MODEL=openai/gpt-oss-120b
LLM_FALLBACK_MODELS=["openai/gpt-oss-20b","qwen/qwen3.8-27b","openai/gpt-oss-safeguard-20b"]
EMBEDDING_BATCH_SIZE=4
RERANKER_BATCH_SIZE=4
```

Remove any existing `EMBEDDING_DEVICE=cpu` or `RERANKER_DEVICE=cpu` overrides from
the root `.env`, or set those overrides to `cuda`. The GPU Compose file defaults
both to `cuda`. Batch sizes are capped by configuration rather than CPU count.

Run these commands one at a time in PowerShell:

```powershell
nvidia-smi
```

```powershell
docker compose -f docker-compose.yml -f docker-compose.gpu.yml config --quiet
```

For an existing installation whose migrations and infrastructure already work:

```powershell
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build --no-deps backend worker
```

If the infrastructure has been stopped, use this instead of the preceding command:

```powershell
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build qdrant redis migrate backend worker frontend
```

```powershell
docker compose -f docker-compose.yml -f docker-compose.gpu.yml exec backend python -c "import torch; assert torch.cuda.is_available(), 'CUDA unavailable'; print(torch.__version__, torch.cuda.get_device_name(0))"
```

```powershell
docker compose -f docker-compose.yml -f docker-compose.gpu.yml exec worker python -c "import torch; assert torch.cuda.is_available(), 'CUDA unavailable'; print(torch.__version__, torch.cuda.get_device_name(0))"
```

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Refresh Folio at <http://localhost:3000> or Swagger at <http://localhost:8000/docs>.
Send one question and upload one new document, waiting for it to finish indexing.
Model loading happens on first use, so the CUDA availability commands alone do
not prove that embedding/reranking inference has run on CUDA.

```powershell
docker compose -f docker-compose.yml -f docker-compose.gpu.yml logs --since=10m backend worker | Select-String 'embedding_device|reranker_device|llm_model_selected|llm_model_rate_limited|llm_models_exhausted|llm_request_completed'
```

After those actions, expect `embedding_device` with `actual_device` `cuda:0` in
both backend and worker logs, and `reranker_device` with `cuda:0` in backend logs.
Run `nvidia-smi` during a request or upload to observe the GPU's live memory use.

No migration, volume reset, document reupload or reindex is required just to move
the same embedding model to CUDA. Existing model IDs, vector dimensions and
normalization remain the same. Small floating-point differences across devices
are possible. These changes do not repair previously extracted PDF text.

## Memory on a 4 GB GPU

The worker runs Celery with `--pool=solo --concurrency=1`, which avoids CUDA use in
forked worker children and multiple copies per CPU core. GPU memory is still
shared by the backend, worker, Windows and other applications. Batch size four is
a starting point, not a guarantee that every workload fits.

If CUDA runs out of memory, set both batch sizes to `1` and recreate backend and
worker with the same GPU Compose command. If memory remains insufficient, keep
the ingestion worker on CPU by adding a local override file:

```yaml
# docker-compose.worker-cpu.local.yml
services:
  worker:
    environment:
      EMBEDDING_DEVICE: cpu
```

```powershell
docker compose -f docker-compose.yml -f docker-compose.gpu.yml -f docker-compose.worker-cpu.local.yml up -d --no-deps worker
```

This retains CUDA in the backend and the same embedding model for uploads. Do
not use `EMBEDDING_DEVICE=cpu` in root `.env` for this purpose: that override
affects both services. To return both services to GPU, run the normal GPU command
without the local worker override. Use `up`, rather than `restart`, after changing
environment variables so Docker recreates containers with the new values.

## Fallback behavior

The requested default order is:

1. `openai/gpt-oss-120b`
2. `openai/gpt-oss-20b`
3. `qwen/qwen3.8-27b`
4. `openai/gpt-oss-safeguard-20b`

All models use the same `GROQ_API_KEY`. Each logical call starts with the primary,
skips any model whose known cooldown is still active, and immediately tries the
next on HTTP 429. Cooldowns are independent and retained by the cached router
within the backend process. They are not shared between backend replicas.
When a cooldown expires, the higher-priority model is eligible again. Each model
is tried at most once per logical call for rate limiting; there is no wait between
fallback models. Transient errors keep the existing bounded retry behavior.

If every configured model is limited, the API returns HTTP 429 with the earliest
known retry delay. Missing reset times remain unknown. A restart clears local
cooldown memory but does not reset provider quota. Authentication/configuration
errors, invalid output and verification failures do not trigger model fallback.
Streaming only falls back before any answer text has been emitted.

Every provider request records its actual model and reported usage under the
same question ID and logical call ID. Rate-limited requests without usage remain
explicitly unreported. Citation checking, schema validation and independent
answer review still run after fallback. Switching models can change answer
quality and does not guarantee success or fewer total tokens.

Groq currently lists Qwen and Safeguard as preview models. Safeguard is trained
for safety classification, so it is a poor general document-answer fallback. The
fourth option is included to match the requested order; the recommended document
configuration omits it:

```dotenv
LLM_FALLBACK_MODELS=["openai/gpt-oss-20b","qwen/qwen3.8-27b"]
```

For a chain using only the listed production models, use:

```dotenv
LLM_FALLBACK_MODELS=["openai/gpt-oss-20b"]
```

Set `LLM_FALLBACK_MODELS=[]` to disable fallback. Use a JSON array, not a comma
separated string. Duplicate/blank entries are ignored. Recreate the backend after
changing this setting. Your account must allow access to every configured model.
Per-model capacity can help with a model-specific limit; organization-wide limits
can affect the entire chain.

Sources: [Groq model list](https://console.groq.com/docs/models),
[Safeguard model purpose](https://console.groq.com/docs/model/openai/gpt-oss-safeguard-20b),
[Groq rate limits](https://console.groq.com/docs/rate-limits).

For a controlled question capture, the existing diagnostic launcher now records
both device settings, both actual devices and the fallback list. It still sends
one question through the normal pipeline, which may make several LLM requests.
The worker can retain its own CUDA model while the backend is paused; avoid
uploading documents during the diagnostic on a 4 GB GPU.
