"""Service du front compilé (SPA) : fichiers statiques et repli sur ``index.html`` (PLAN.md §10)."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

log = logging.getLogger(__name__)


def mount_spa(app: FastAPI, static_dir: Path) -> None:
    """À appeler APRÈS ``include_router`` : la route fourre-tout ne doit pas masquer l'API."""
    root = static_dir.resolve()
    index = root / "index.html"
    if not index.is_file():
        log.info("Pas de front à servir (%s/index.html absent)", static_dir)
        return

    app.mount("/assets", StaticFiles(directory=root / "assets", check_dir=False), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> Response:
        if full_path == "api" or full_path.startswith("api/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        candidate = (root / full_path).resolve()
        if candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        return FileResponse(index)
