"""Gateway, historique et services techniques factices, pilotables par les tests."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime

from app.application.ports.history import HistoryCapabilities
from app.domain.model import Equipment
from app.domain.values import EnergyDay, EquipmentId, Instant, Measurement


class FakeEquipmentGateway:
    def __init__(self, equipment: Sequence[Equipment] = (), measurements: Sequence[Measurement] = ()) -> None:
        self.equipment: list[Equipment] = list(equipment)
        self.measurements: list[Measurement] = list(measurements)
        self.available: dict[EquipmentId, bool] = {e.id: e.available for e in self.equipment if e.available is not None}
        self.fail_with: Exception | None = None
        self.calls = 0

    def _check(self) -> None:
        if self.fail_with is not None:
            raise self.fail_with

    async def list_equipment(self) -> list[Equipment]:
        self._check()
        return list(self.equipment)

    async def read_measurements(self, equipment_ids: list[EquipmentId] | None = None) -> list[Measurement]:
        self.calls += 1
        self._check()
        if equipment_ids is None:
            return list(self.measurements)
        wanted = set(equipment_ids)
        return [m for m in self.measurements if m.equipment_id in wanted]

    async def availability(self) -> dict[EquipmentId, bool]:
        self._check()
        return dict(self.available)


class FakeHistorySource:
    def __init__(self, days: Sequence[EnergyDay] = (), max_days: int = 32, enabled: bool = True) -> None:
        self.days: list[EnergyDay] = list(days)
        self.max_days = max_days
        self.enabled = enabled
        self.requests: list[tuple[date, date]] = []
        self.fail_with: Exception | None = None

    def capabilities(self) -> HistoryCapabilities:
        return HistoryCapabilities(energy_daily=self.enabled, max_days=self.max_days)

    async def fetch_energy_days(self, since: date, until: date) -> list[EnergyDay]:
        self.requests.append((since, until))
        if self.fail_with is not None:
            raise self.fail_with
        return [d for d in self.days if since <= d.day <= until]


class NullHistorySource:
    """Fournisseur sans historique."""

    def capabilities(self) -> HistoryCapabilities:
        return HistoryCapabilities()

    async def fetch_energy_days(self, since: date, until: date) -> list[EnergyDay]:
        return []


class FakeBackupService:
    def __init__(self) -> None:
        self.snapshots: list[str] = []

    async def snapshot(self, now: Instant) -> str:
        name = f"pac-{datetime.fromtimestamp(now.epoch, UTC).date().isoformat()}.db"
        self.snapshots.append(name)
        return name


class FakeStorageStats:
    def __init__(self, size: int = 0) -> None:
        self.size = size

    async def size_bytes(self) -> int:
        return self.size
