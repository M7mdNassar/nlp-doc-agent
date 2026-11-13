FROM python:3.12-slim AS base

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    tesseract-ocr \
    libtesseract-dev \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uv/bin/

ENV PATH="/uv/bin:/app/.venv/bin:$PATH"

WORKDIR /app

# -----------------
# Development Stage
# -----------------
FROM base AS development
COPY backend/pyproject.toml backend/uv.lock* /app/
RUN uv sync --frozen --all-extras --no-cache
COPY backend/ /app/

# -----------------
# Production Stage
# -----------------
FROM base AS production
COPY backend/pyproject.toml backend/uv.lock* /app/
RUN uv sync --frozen --no-dev --extra ml --no-cache
COPY backend/ /app/

# Create data dirs
RUN mkdir -p /app/data/uploads

EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
