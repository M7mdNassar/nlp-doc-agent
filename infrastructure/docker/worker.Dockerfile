FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y \
    curl \
    tesseract-ocr \
    libtesseract-dev \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uv/bin/

ENV PATH="/uv/bin:/app/.venv/bin:$PATH"

WORKDIR /app

FROM base AS development
COPY backend/pyproject.toml backend/uv.lock* /app/
RUN uv sync --frozen --all-extras --no-cache
COPY backend/ /app/

FROM base AS production
COPY backend/pyproject.toml backend/uv.lock* /app/
RUN uv sync --frozen --no-dev --extra ml --no-cache
COPY backend/ /app/

CMD ["celery", "-A", "src.worker.main", "worker", "--loglevel=info"]
