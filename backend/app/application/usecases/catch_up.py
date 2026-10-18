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
    """``days_received`` : jours renvoyés par la source ; ``days_written`` : jours nouveaux ou modifiés
    en base (0 sur une relance : l'import est idempotent)."""

    days_received: int = 0
    days_written: int = 0
    first_day: date | None = None
    last_day: date | None = None
    gaps_recovered: int = 0
    source_available: bool = False

    def __str__(self) -> str:
        if not self.source_available:
            return "Aucune source d'historique déclarée : rien à rattraper."
        if self.days_received == 0:
            return "La source n'a renvoyé aucun jour de consommation pour la période demandée."
        return (
            f"{self.days_received} entrée(s) journalière(s) reçue(s) du {self.first_day} au {self.last_day}, "
            f"{self.days_written} nouvelle(s) ou modifiée(s) en base, "
            f"{self.gaps_recovered} trou(s) marqué(s) rattrapé(s)."
        )


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
        return CatchUpReport(
            days_received=len(days),
            days_written=written,
            first_day=lo,
            last_day=hi,
            gaps_recovered=len(ids),
            source_available=True,
        )


def _midnight(day: date) -> Instant:
    return Instant(int(datetime(day.year, day.month, day.day, tzinfo=PARIS).timestamp()))
