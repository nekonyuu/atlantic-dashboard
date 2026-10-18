"""Repositories en mémoire : respectent les contrats des ports, pour les tests."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import date

from app.domain.model import Equipment, Gap
from app.domain.values import Bucket, EnergyDay, EquipmentId, Instant, Measurement, MetricKey, PollOutcome

_SeriesKey = tuple[EquipmentId, MetricKey]


class InMemoryEquipmentRepository:
    def __init__(self) -> None:
        self._items: dict[EquipmentId, Equipment] = {}

    async def upsert(self, equipment: Sequence[Equipment]) -> None:
        for item in equipment:
            stored = replace(item)
            known = self._items.get(item.id)
            if known is not None and known.first_seen is not None:
                stored.first_seen = known.first_seen  # le premier instant vu est conservé
            self._items[item.id] = stored

    async def all(self) -> list[Equipment]:
        return [replace(e) for e in self._items.values()]


class InMemoryMeasurementRepository:
    def __init__(self) -> None:
        self._rows: dict[tuple[EquipmentId, MetricKey, Instant], Measurement] = {}
        self.hourly: dict[tuple[EquipmentId, MetricKey, Instant], Bucket] = {}

    async def append(self, batch: Sequence[Measurement]) -> int:
        inserted = 0
        for m in batch:
            key = (m.equipment_id, m.metric_key, m.instant)
            if key not in self._rows:
                self._rows[key] = m
                inserted += 1
        return inserted

    def _latest_by_series(self) -> dict[_SeriesKey, Measurement]:
        latest: dict[_SeriesKey, Measurement] = {}
        for m in self._rows.values():
            current = latest.get(m.series_key)
            if current is None or m.instant > current.instant:
                latest[m.series_key] = m
        return latest

    async def latest(self, equipment_id: EquipmentId | None = None) -> list[Measurement]:
        return [
            m for key, m in sorted(self._latest_by_series().items()) if equipment_id is None or key[0] == equipment_id
        ]

    async def range(
        self, equipment_id: EquipmentId, metric_key: MetricKey, start: Instant, end: Instant
    ) -> list[Measurement]:
        rows = [
            m
            for m in self._rows.values()
            if m.equipment_id == equipment_id and m.metric_key == metric_key and start <= m.instant < end
        ]
        return sorted(rows, key=lambda m: m.instant)

    async def last_recorded(
        self, equipment_id: EquipmentId, metric_key: MetricKey, before: Instant
    ) -> Measurement | None:
        rows = [
            m
            for m in self._rows.values()
            if m.equipment_id == equipment_id and m.metric_key == metric_key and m.instant < before
        ]
        return max(rows, key=lambda m: m.instant, default=None)

    async def save_hourly(self, equipment_id: EquipmentId, metric_key: MetricKey, buckets: Sequence[Bucket]) -> None:
        for b in buckets:
            self.hourly[(equipment_id, metric_key, b.start)] = b

    async def purge_before(self, before: Instant) -> int:
        keep = {(m.equipment_id, m.metric_key, m.instant) for m in self._latest_by_series().values()}
        doomed = [k for k in self._rows if k[2] < before and k not in keep]
        for k in doomed:
            del self._rows[k]
        return len(doomed)


class InMemoryGapRepository:
    def __init__(self) -> None:
        self._gaps: dict[int, Gap] = {}
        self._next_id = 1

    async def add(self, gap: Gap) -> Gap:
        stored = replace(gap, id=self._next_id)
        self._gaps[self._next_id] = stored
        self._next_id += 1
        return replace(stored)

    async def list(self, start: Instant, end: Instant) -> list[Gap]:
        found = [g for g in self._gaps.values() if g.overlaps(start, end)]
        return [replace(g) for g in sorted(found, key=lambda g: g.start)]

    async def mark_recovered(self, gap_ids: Sequence[int]) -> None:
        for gap_id in gap_ids:
            if gap_id in self._gaps:
                self._gaps[gap_id].recovered = True


class InMemoryPollLogRepository:
    def __init__(self) -> None:
        self._log: list[PollOutcome] = []

    async def add(self, outcome: PollOutcome) -> None:
        self._log.append(outcome)

    async def recent(self, limit: int = 50) -> list[PollOutcome]:
        return sorted(self._log, key=lambda o: o.at, reverse=True)[:limit]

    async def last_success(self) -> PollOutcome | None:
        return max((o for o in self._log if o.ok), key=lambda o: o.at, default=None)

    async def since(self, after: Instant) -> list[PollOutcome]:
        return sorted((o for o in self._log if o.at > after), key=lambda o: o.at)


class InMemoryEnergyRepository:
    def __init__(self) -> None:
        self._days: dict[tuple, EnergyDay] = {}

    async def upsert(self, days: Sequence[EnergyDay]) -> int:
        written = 0
        for d in days:
            if self._days.get(d.key) != d:
                self._days[d.key] = d
                written += 1
        return written

    async def range(self, since: date, until: date) -> list[EnergyDay]:
        return [d for k, d in sorted(self._days.items()) if since <= d.day <= until]

    async def latest_day(self) -> date | None:
        return max((d.day for d in self._days.values()), default=None)
