"""Cas d'usage : rattrapage de l'historique (section 8 du plan).

- Niveau A (trous) : enregistré par ``CollectSamples`` au premier succès après
  une interruption ; ici on ne fait que relier les trous à l'énergie rattrapée.
- Niveau B (compteurs cumulés) : calculé à la lecture par ``SeriesAggregator``.
- Niveau C (historique fournisseur) : consommations journalières, si la source
  en déclare. Rien n'est fabriqué pour les autres mesures.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.application.ports import Clock, EnergyRepository, GapRepository, HistorySource
from app.domain.services import PARIS
from app.domain.values import Instant


@dataclass(frozen=True, slots=True)
class CatchUpReport:
    energy_days: int = 0
    gaps_recovered: int = 0
    source_available: bool = False


class CatchUp:
    def __init__(
        self,
        *,
        history: HistorySource,
        energy: EnergyRepository,
        gaps: GapRepository,
        clock: Clock,
        writer_lock: asyncio.Lock,
    ) -> None:
        self._history = history
        self._energy = energy
        self._gaps = gaps
        self._clock = clock
        self._lock = writer_lock

    async def run(self, since: date | None = None) -> CatchUpReport:
        caps = self._history.capabilities()
        if not caps.energy_daily:
            return CatchUpReport()
        today = datetime.fromtimestamp(self._clock.now().epoch, PARIS).date()
        oldest = today - timedelta(days=caps.max_days)
        start = max(since, oldest) if since else oldest
        days = await self._history.fetch_energy_days(start, today)
        if not days:
            return CatchUpReport(source_available=True)

        lo, hi = min(d.day for d in days), max(d.day for d in days)
        covered_from, covered_to = _midnight(lo), _midnight(hi + timedelta(days=1))
        async with self._lock:
            written = await self._energy.upsert(days)
            candidates = await self._gaps.list(covered_from, covered_to)
            ids = [
                g.id
                for g in candidates
                if g.id is not None and not g.recovered and g.start >= covered_from and g.end <= covered_to
            ]
            if ids:
                await self._gaps.mark_recovered(ids)
        return CatchUpReport(energy_days=written, gaps_recovered=len(ids), source_available=True)


def _midnight(day: date) -> Instant:
    return Instant(int(datetime(day.year, day.month, day.day, tzinfo=PARIS).timestamp()))
