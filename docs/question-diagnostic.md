# Capture one attention question

This tool asks one question using the existing indexed `attention.pdf` and captures
the normal retrieval, analysis, draft, correction and verification calls. It consumes
the configured provider's tokens. It does not add extra LLM calls, change prompts,
reindex documents or save a conversation. Do not reindex before capturing the failure.

On the GPU laptop, bring these two files over from the updated branch:

- `infrastructure/scripts/diagnose-attention.ps1`
- `infrastructure/scripts/diagnose_question.py`

Also retain the updated `.gitignore` and `.dockerignore` to exclude private captures.
No image rebuild or new environment setting is required if the backend already has
the analysis-correction update. Docker Desktop, Qdrant and Redis must be running,
and `attention.pdf` must show Ready in the document library.

From the repository root in PowerShell, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\infrastructure\scripts\diagnose-attention.ps1
```

The launcher pauses the backend to free its model/GPU memory, runs the diagnostic
in a temporary container using the same image, environment and data volumes, then
restarts the backend if it was running. Do not send other questions during the run.
The website cannot answer questions while the backend is paused. Model loading
and provider cooldowns can make this command take several minutes. The final path is
printed, e.g. `.diagnostics/attention-20261112-013000-ab12cd34.json`.

Send that JSON file for inspection. It contains document excerpts, questions and
model replies; review it before sharing. Normal application logs still omit these
contents. Credentials/environment values and raw provider exception messages are
not collected. The launcher always tries to restore the original running backend
after a normal completion or command failure. A forced process/PC shutdown can
interrupt cleanup; restart the backend manually if necessary.

For a CPU installation, append `-Cpu` to the same command. For another question,
the Python script also accepts `--question` and `--document-name` arguments.

The capture has these sections:

| Section | Contents |
|---|---|
| `retrievals` | Search queries, filters, returned chunks, original page numbers and document IDs. |
| `retrieval_events` | Complete hybrid-search and reranker candidate lists with scores, followed by context selection decisions. Exclusions identify duplicate text, document limits, chunk limits, or token budget. Available in format version 2 captures. |
| `answer_attempts` | Each draft, exact selected evidence, analysis, feedback received for correction, reviewer verdict/feedback, and acceptance. |
| `llm_calls` | Exact system/user prompts and returned text, including the reviewer's source-text mapping; associated provider-request metadata. |
| `usage` | Actual reported tokens, waits, calls and stage durations under one question ID. |
| `result` / `error` | Final answer/state or safe exception type if the question failed. |

The file is updated after each call, so failures normally leave useful partial
evidence. Each run has a unique name and cannot overwrite an earlier artifact.
Runtime settings are restricted to model names and device information.

This is a fresh empty-history question in a separate process. It cannot recover
the drafts from an earlier request. Model startup is included in dependency setup,
and writing the capture adds overhead, so use it to diagnose content first, then
measure normal API latency after the correction. Provider responses may vary.

If the artifact shows a `ValueError` before any LLM calls, check that exactly one
document is named `attention.pdf` and its status is indexed. Other failures include
missing provider configuration, provider rate limits, or unavailable database/vector
services; the partial artifact and normal logs help identify the failing stage.
