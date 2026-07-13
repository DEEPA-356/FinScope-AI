# =============================================================================
# Backend Dockerfile — multi-stage build
# Stage 1: base (shared deps)
# Stage 2: development (with dev tools, hot-reload)
# Stage 3: production (slim, non-root user)
# =============================================================================

# ── Stage 1: Base ────────────────────────────────────────────────────────────
FROM python:3.11-slim AS base

# System deps for psycopg2-binary, Tesseract OCR, Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        tesseract-ocr \
        tesseract-ocr-eng \
        poppler-utils \
        libmagic1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (layer-cache friendly)
COPY requirements.txt requirements-dev.txt ./

# ── Stage 2: Development ─────────────────────────────────────────────────────
FROM base AS development

RUN pip install --no-cache-dir -r requirements.txt -r requirements-dev.txt

COPY . .

EXPOSE 8000

# Entrypoint provided by docker-compose command
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ── Stage 3: Production ───────────────────────────────────────────────────────
FROM base AS production

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Non-root user for security
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
RUN chown -R appuser:appgroup /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "4", "--log-level", "info"]
