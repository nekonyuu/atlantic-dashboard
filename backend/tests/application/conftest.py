import asyncio
from dataclasses import dataclass, field

import pytest

from app.adapters.outbound.fake import (
    FakeEquipmentGateway,
    FakeHistorySource,
    FakeStorageStats,
    InMemoryEnergyRepository,
    InMemoryEquipmentRepository,
    InMemoryGapRepository,
    InMemoryMeasurementRepository,
    InMemoryPollLogRepository,
)
from app.adapters.outbound.system import FixedClock
from app.application.usecases.catch_up import CatchUp
from app.application.usecases.collect import CollectSamples
from app.domain.model import Equipment
from app.domain.services import GapDetector
from app.domain.values import Instant
from tests.builders import DHW, paris

INTERVAL = 300


@dataclass
class Ctx:
    clock: FixedClock
    gateway: FakeEquipmentGateway
    history: FakeHistorySource
    equipment: InMemoryEquipmentRepository = field(default_factory=InMemoryEquipmentRepository)
    measurements: InMemoryMeasurementRepository = field(default_factory=InMemoryMeasurementRepository)
    gaps: InMemoryGapRepository = field(default_factory=InMemoryGapRepository)
    poll_log: InMemoryPollLogRepository = field(default_factory=InMemoryPollLogRepository)
    energy: InMemoryEnergyRepository = field(default_factory=InMemoryEnergyRepository)
    storage: FakeStorageStats = field(default_factory=lambda: FakeStorageStats(4096))
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    events: list = field(default_factory=list)
    gap_detector: GapDetector = field(default_factory=lambda: GapDetector(INTERVAL))

    def collect(self) -> CollectSamples:
        return CollectSamples(
            gateway=self.gateway,
            equipment=self.equipment,
            measurements=self.measurements,
            poll_log=self.poll_log,
            gaps=self.gaps,
            clock=self.clock,
            gap_detector=self.gap_detector,
            writer_lock=self.lock,
            publish=self.events.append,
        )

    def catch_up(self) -> CatchUp:
        return CatchUp(
            history=self.history, energy=self.energy, gaps=self.gaps, clock=self.clock, writer_lock=self.lock
        )

    def at(self, t: Instant) -> None:
        self.clock.set(t)


@pytest.fixture
def ctx() -> Ctx:
    return Ctx(
        clock=FixedClock(paris(2026, 10, 18, 12)),
        gateway=FakeEquipmentGateway([Equipment(DHW, "Ballon ECS", "dhw", available=True)]),
        history=FakeHistorySource(),
    )
