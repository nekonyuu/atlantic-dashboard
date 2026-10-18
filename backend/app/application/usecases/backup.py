"""Cas d'usage : sauvegarde quotidienne de la base."""

from __future__ import annotations

import asyncio

from app.application.ports import BackupService, Clock


class RunBackup:
    def __init__(self, backup: BackupService, clock: Clock, writer_lock: asyncio.Lock) -> None:
        self._backup = backup
        self._clock = clock
        self._lock = writer_lock

    async def run(self) -> str:
        async with self._lock:
            return await self._backup.snapshot(self._clock.now())
