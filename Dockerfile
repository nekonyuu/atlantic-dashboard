# syntax=docker/dockerfile:1.7
# Image unique : front compilé (Vite) servi par l'API FastAPI (PLAN.md §11).

# 1. Front : résultat statique, construit sur l'architecture de la machine de build.
FROM --platform=$BUILDPLATFORM node:22-alpine AS frontend
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# 2. Backend
FROM python:3.12-slim AS runtime
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /bin/uv

WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/app/.venv UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project && rm /bin/uv

COPY backend/app ./app
COPY --from=frontend /src/dist /app/static

ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    DB_PATH=/data/pac.db \
    BACKUP_DIR=/data/backup \
    STATIC_DIR=/app/static

RUN useradd --uid 1000 --no-create-home app
USER app

VOLUME /data
EXPOSE 8000

# L'image slim n'a ni curl ni wget. /api/health répond 200 tant que le process vit ;
# l'état de la collecte est dans le corps (avec restart: unless-stopped, « unhealthy » ne relance rien).
HEALTHCHECK --interval=60s --timeout=5s --start-period=30s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"]

# Forme exec : uvicorn est PID 1 et reçoit SIGTERM ; un seul worker (un seul writer SQLite).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
