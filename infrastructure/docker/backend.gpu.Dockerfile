FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    curl \
    tesseract-ocr \
    libtesseract-dev \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uv/bin/

ENV PATH="/uv/bin:/app/.venv/bin:$PATH"
WORKDIR /app

COPY backend/pyproject.toml backend/uv.lock /app/

RUN uv sync --frozen --no-dev --extra ml --no-cache \
    && uv pip install --python /app/.venv/bin/python --no-cache \
       "torch==2.14.1" \
       --index-url https://download.pytorch.org/whl/cu126 \
    && uv pip check --python /app/.venv/bin/python

COPY backend/ /app/

RUN mkdir -p /app/data/uploads

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]