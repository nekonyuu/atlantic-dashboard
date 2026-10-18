"""Horloges : réelle pour la production, figée et pilotable pour les tests."""

from __future__ import annotations

import time

from app.domain.values import Instant


class SystemClock:
    def now(self) -> Instant:
        return Instant(int(time.time()))


class FixedClock:
    """Horloge contrôlée : ne bouge que sur ``advance`` / ``set``."""

    def __init__(self, start: Instant) -> None:
        self._now = start

    def now(self) -> Instant:
        return self._now

    def advance(self, seconds: int) -> None:
        self._now = self._now + seconds

    def set(self, instant: Instant) -> None:
        self._now = instant
