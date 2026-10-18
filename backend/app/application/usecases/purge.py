"""Cas d'usage : purge des points bruts, après agrégation horaire."""

from __future__ import annotations

import asyncio
from collections.abc import Collection

from app.application.ports import Clock, GapRepository, MeasurementRepository
from app.domain.services import SeriesAggregator
from app.domain.values import BucketSize, Instant, MetricKey

HOUR = 3600


class PurgeRaw:
    """Ne fait rien si ``retention_days == 0`` (défaut v1).

    Sinon, agrège en heures toutes les séries jusqu'à la limite (alignée sur
    l'heure), enregistre les agrégats (conservés indéfiniment), puis purge.
    """

    def __init__(
        self,
        *,
        measurements: MeasurementRepository,
        gaps: GapRepository,
        clock: Clock,
        writer_lock: asyncio.Lock,
        retention_days: int,
        cumulative_metrics: Collection[MetricKey] = (),
        aggregator: SeriesAggregator | None = None,
    ) -> None:
        if retention_days < 0:
            raise ValueError("rétention négative")
        self._measurements = measurements
        self._gaps = gaps
        self._clock = clock
        self._lock = writer_lock
        self._retention_days = retention_days
        self._cumulative = set(cumulative_metrics)
        self._aggregator = aggregator or SeriesAggregator()

    async def run(self) -> int:
        if self._retention_days == 0:
            return 0
        cutoff_raw = self._clock.now().epoch - self._retention_days * 86400
        cutoff = Instant(cutoff_raw - cutoff_raw % HOUR)
        async with self._lock:
            gaps = await self._gaps.list(Instant(0), cutoff)
            for latest in await self._measurements.latest():
                eq, key = latest.series_key
                points = await self._measurements.range(eq, key, Instant(0), cutoff)
                if not points:
                    continue
                buckets = self._aggregator.aggregate(
                    points,
                    points[0].instant,
                    cutoff,
                    BucketSize.HOUR,
                    gaps=gaps,
                    cumulative=key in self._cumulative,
                )
                await self._measurements.save_hourly(eq, key, [b for b in buckets if b.covered_seconds or b.delta])
            return await self._measurements.purge_before(cutoff)
