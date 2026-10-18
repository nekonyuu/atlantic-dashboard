"""Ports sortants techniques."""

from __future__ import annotations

from typing import Protocol

from app.domain.values import Instant


class Clock(Protocol):
    def now(self) -> Instant: ...


class BackupService(Protocol):
    async def snapshot(self, now: Instant) -> str:
        """Crée une sauvegarde datée, applique la rotation, renvoie son nom."""
        ...


class StorageStats(Protocol):
    async def size_bytes(self) -> int: ...
