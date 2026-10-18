# Backend seul pour l'instant ; l'étape Node (frontend -> /app/static) viendra en phase 5.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /bin/uv

WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
ENV UV_PROJECT_ENVIRONMENT=/app/.venv UV_LINK_MODE=copy
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/app ./app

ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    DB_PATH=/data/pac.db \
    BACKUP_DIR=/data/backup

RUN useradd --uid 1000 --no-create-home app
USER app

VOLUME /data
EXPOSE 8000

# HEALTHCHECK à ajouter en phase 3 (nécessite /api/health).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
