import gc
import json
import statistics
import time

import torch
from pypdf import PdfReader
from sentence_transformers import CrossEncoder

MODEL = "BAAI/bge-reranker-base"
QUERY = "how does attention work in transformers, answer in 50 words"
BATCH_SIZE = 4
RUNS = 5

if not torch.cuda.is_available():
    raise SystemExit("CUDA is unavailable. Check Docker GPU access and PyTorch.")

reader = PdfReader("/bench/attention.pdf")
text = "\n".join(page.extract_text() or "" for page in reader.pages)
text = " ".join(text.split())

# Representative passages, identical for the CPU and GPU runs.
# These do not reproduce the application's exact retrieved chunks.
passages = [
    text[start:start + 1600]
    for start in range(0, len(text), 1400)
    if len(text[start:start + 1600]) >= 200
][:20]

if len(passages) < 20:
    raise SystemExit("Use the attention paper: this benchmark requires 20 passages.")

pairs = [(QUERY, passage) for passage in passages]
results = {}

print(json.dumps({
    "torch": torch.__version__,
    "cuda": torch.version.cuda,
    "gpu": torch.cuda.get_device_name(0),
    "model": MODEL,
    "candidates": len(pairs),
    "batch_size": BATCH_SIZE,
}), flush=True)

for device in ("cpu", "cuda"):
    model = CrossEncoder(MODEL, device=device, max_length=512)

    # Exclude model downloading, loading, and initial warmup from timing.
    model.predict(pairs, batch_size=BATCH_SIZE, show_progress_bar=False)
    if device == "cuda":
        torch.cuda.synchronize()
        torch.cuda.reset_peak_memory_stats()

    timings = []
    scores = None

    for _ in range(RUNS):
        if device == "cuda":
            torch.cuda.synchronize()

        started = time.perf_counter()
        scores = model.predict(
            pairs,
            batch_size=BATCH_SIZE,
            show_progress_bar=False,
        )

        if device == "cuda":
            torch.cuda.synchronize()

        timings.append(time.perf_counter() - started)

    ranking = sorted(
        range(len(scores)),
        key=lambda index: float(scores[index]),
        reverse=True,
    )
    results[device] = {
        "seconds": [round(value, 3) for value in timings],
        "median_seconds": round(statistics.median(timings), 3),
        "top_8_passage_indices": ranking[:8],
    }

    if device == "cuda":
        results[device]["peak_allocated_vram_mib"] = round(
            torch.cuda.max_memory_allocated() / (1024 ** 2), 1
        )

    print(json.dumps({device: results[device]}), flush=True)

    del model
    gc.collect()
    if device == "cuda":
        torch.cuda.empty_cache()

speedup = (
    results["cpu"]["median_seconds"]
    / results["cuda"]["median_seconds"]
)
print(json.dumps({"cpu_to_gpu_speedup": round(speedup, 2)}), flush=True)