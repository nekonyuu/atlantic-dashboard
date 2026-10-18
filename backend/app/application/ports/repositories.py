"""Ports sortants de persistance."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Protocol

from app.domain.model import Equipment, Gap
from app.domain.values import Bucket, EnergyDay, EquipmentId, Instant, Measurement, MetricKey, PollOutcome


class EquipmentRepository(Protocol):
    async def upsert(self, equipment: Sequence[Equipment]) -> None: ...

    async def all(self) -> list[Equipment]: ...


class MeasurementRepository(Protocol):
    async def append(self, batch: Sequence[Measurement]) -> int:
        """Insère sans doublon ``(équipement, métrique, instant)`` ; un ``backfill``
        n'écrase jamais un ``live``. Renvoie le nombre de lignes insérées."""
        ...

    async def latest(self, equipment_id: EquipmentId | None = None) -> list[Measurement]:
        """Dernière mesure de chaque série (de l'équipement, ou de toutes)."""
        ...

    async def range(
        self, equipment_id: EquipmentId, metric_key: MetricKey, start: Instant, end: Instant
    ) -> list[Measurement]:
        """Mesures d'instant dans ``[start, end)``, triées."""
        ...

    async def last_recorded(
        self, equipment_id: EquipmentId, metric_key: MetricKey, before: Instant
    ) -> Measurement | None:
        """Dernière mesure strictement avant ``before``."""
        ...

    async def save_hourly(
        self, equipment_id: EquipmentId, metric_key: MetricKey, buckets: Sequence[Bucket]
    ) -> None: ...

    async def purge_before(self, before: Instant) -> int:
        """Supprime les mesures d'instant < ``before``, **sauf la dernière de chaque
        série** (nécessaire au report de valeur et au rechargement du ChangeDetector)."""
        ...


class GapRepository(Protocol):
    async def add(self, gap: Gap) -> Gap: ...

    async def list(self, start: Instant, end: Instant) -> list[Gap]:
        """Trous qui recoupent ``[start, end)``."""
        ...

    async def mark_recovered(self, gap_ids: Sequence[int]) -> None: ...


class PollLogRepository(Protocol):
    async def add(self, outcome: PollOutcome) -> None: ...

    async def recent(self, limit: int = 50) -> list[PollOutcome]:
        """Derniers cycles, du plus récent au plus ancien."""
        ...

    async def last_success(self) -> PollOutcome | None: ...

    async def since(self, after: Instant) -> list[PollOutcome]:
        """Cycles strictement après ``after``, triés."""
        ...


class EnergyRepository(Protocol):
    async def upsert(self, days: Sequence[EnergyDay]) -> int: ...

    async def range(self, since: date, until: date) -> list[EnergyDay]: ...

    async def latest_day(self) -> date | None: ...
