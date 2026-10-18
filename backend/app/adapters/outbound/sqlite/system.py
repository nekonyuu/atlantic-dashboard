"""Sauvegarde et statistiques de stockage du fichier SQLite."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.adapters.outbound.sqlite.connection import Database
from app.domain.values import Instant

_PARIS = ZoneInfo("Europe/Paris")


class SqliteBackupService:
    """Sauvegarde quotidienne par ``VACUUM INTO`` (cohérente, sans arrêter la collecte)."""

    def __init__(self, db: Database, backup_dir: str | Path, keep: int) -> None:
        self._db = db
        self._dir = Path(backup_dir)
        self._keep = keep

    async def snapshot(self, now: Instant) -> str:
        self._dir.mkdir(parents=True, exist_ok=True)
        day = datetime.fromtimestamp(now.epoch, _PARIS).date().isoformat()
        name = f"pac-{day}.db"
        target = self._dir / name
        tmp = self._dir / f"{name}.tmp"  # VACUUM INTO refuse un fichier existant
        tmp.unlink(missing_ok=True)
        async with self._db.exclusive() as conn:  # exclusion avec les écritures
            await conn.execute("VACUUM INTO ?", (str(tmp),))
        os.replace(tmp, target)
        for old in sorted(self._dir.glob("pac-*.db"))[: -self._keep if self._keep > 0 else None]:
            old.unlink()
        return name


class SqliteStorageStats:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    async def size_bytes(self) -> int:
        total = 0
        for p in (self._path, self._path.with_name(self._path.name + "-wal")):
            if p.exists():
                total += p.stat().st_size
        return total
