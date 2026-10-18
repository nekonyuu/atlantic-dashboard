"""Suite de comportement unique, jouée sur les fakes en mémoire ET sur SQLite."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pytest

from app.adapters.outbound import fake, sqlite
from app.domain.model import Equipment, Gap, GapCause
from app.domain.values import (
    Bucket,
    EnergyDay,
    EquipmentId,
    ErrorKind,
    Instant,
    Origin,
    PollOutcome,
    Tariff,
)
from tests.builders import COUNTER, DHW, TEMP, m


@dataclass
class Repos:
    equipment: object
    measurements: object
    gaps: object
    polls: object
    energy: object


@pytest.fixture(params=["memory", "sqlite"])
async def repos(request, tmp_path):
    if request.param == "memory":
        yield Repos(
            fake.InMemoryEquipmentRepository(),
            fake.InMemoryMeasurementRepository(),
            fake.InMemoryGapRepository(),
            fake.InMemoryPollLogRepository(),
            fake.InMemoryEnergyRepository(),
        )
        return
    db = await sqlite.Database.open(tmp_path / "pac.db")
    yield Repos(
        sqlite.SqliteEquipmentRepository(db),
        sqlite.SqliteMeasurementRepository(db),
        sqlite.SqliteGapRepository(db),
        sqlite.SqlitePollLogRepository(db),
        sqlite.SqliteEnergyRepository(db),
    )
    await db.close()


def equipment(eq: EquipmentId = DHW, **kw) -> Equipment:
    base = {"label": "Ballon", "kind": "dhw", "first_seen": Instant(100), "last_seen": Instant(100)}
    return Equipment(id=eq, **{**base, **kw})


@pytest.fixture
async def seeded(repos):
    await repos.equipment.upsert([equipment(), equipment(EquipmentId("pac_0"), kind="heat_pump", label="PAC")])
    return repos


# --- équipements ---


async def test_equipment_upsert_keeps_first_seen_and_roundtrips_ref(repos):
    ref = {"device_id": 42, "model_id": 7, "slot": "DHW_0"}
    await repos.equipment.upsert([equipment(provider_ref=ref, available=True)])
    await repos.equipment.upsert(
        [equipment(first_seen=Instant(999), last_seen=Instant(500), available=False, label="Ballon 2")]
    )
    [got] = await repos.equipment.all()
    assert got.first_seen == Instant(100)
    assert got.last_seen == Instant(500)
    assert got.available is False
    assert got.label == "Ballon 2"
    assert got.provider_ref == {}  # remplacé par l'observation la plus récente

    await repos.equipment.upsert([equipment(provider_ref=ref)])
    [got] = await repos.equipment.all()
    assert dict(got.provider_ref) == ref
    assert got.available is None


async def test_equipment_all_empty(repos):
    assert await repos.equipment.all() == []


# --- mesures ---


async def test_append_is_idempotent(seeded):
    batch = [m(10, 1.0), m(20, 2.0)]
    assert await seeded.measurements.append(batch) == 2
    assert await seeded.measurements.append(batch) == 0
    assert len(await seeded.measurements.range(DHW, TEMP, Instant(0), Instant(100))) == 2


async def test_live_is_not_overwritten_by_backfill(seeded):
    await seeded.measurements.append([m(10, 1.0)])
    assert await seeded.measurements.append([m(10, 9.0, origin=Origin.BACKFILL)]) == 0
    [got] = await seeded.measurements.range(DHW, TEMP, Instant(0), Instant(100))
    assert got.value.number == 1.0
    assert got.origin is Origin.LIVE


async def test_latest_per_series(seeded):
    pac = EquipmentId("pac_0")
    await seeded.measurements.append([m(10, 1.0), m(30, 3.0), m(20, 2.0), m(15, 5.0, key=COUNTER), m(12, 7.0, eq=pac)])
    latest = await seeded.measurements.latest()
    assert [(x.equipment_id, x.metric_key, x.value.number) for x in latest] == [
        (DHW, TEMP, 3.0),
        (DHW, COUNTER, 5.0),
        (pac, TEMP, 7.0),
    ]
    only = await seeded.measurements.latest(DHW)
    assert [x.equipment_id for x in only] == [DHW, DHW]
    assert await seeded.measurements.latest(EquipmentId("absent")) == []


async def test_range_bounds_are_start_inclusive_end_exclusive(seeded):
    await seeded.measurements.append([m(10, 1.0), m(20, 2.0), m(30, 3.0)])
    got = await seeded.measurements.range(DHW, TEMP, Instant(10), Instant(30))
    assert [x.instant.epoch for x in got] == [10, 20]


async def test_last_recorded_is_strictly_before(seeded):
    await seeded.measurements.append([m(10, 1.0), m(20, 2.0)])
    got = await seeded.measurements.last_recorded(DHW, TEMP, Instant(20))
    assert got is not None
    assert got.instant == Instant(10)
    assert await seeded.measurements.last_recorded(DHW, TEMP, Instant(10)) is None
    assert (await seeded.measurements.last_recorded(DHW, TEMP, Instant(21))).instant == Instant(20)


async def test_measurement_roundtrip_fields(seeded):
    await seeded.measurements.append([m(10, 21.5, polled=15, origin=Origin.BACKFILL)])
    [got] = await seeded.measurements.range(DHW, TEMP, Instant(0), Instant(100))
    assert got.polled_at == Instant(15)
    assert got.source == "111"
    assert got.origin is Origin.BACKFILL
    assert got.value.number == 21.5


async def test_purge_keeps_last_point_of_each_series(seeded):
    await seeded.measurements.append([m(10, 1.0), m(20, 2.0), m(30, 3.0), m(5, 9.0, key=COUNTER)])
    assert await seeded.measurements.purge_before(Instant(25)) == 2
    assert [x.instant.epoch for x in await seeded.measurements.range(DHW, TEMP, Instant(0), Instant(100))] == [30]
    assert [x.instant.epoch for x in await seeded.measurements.range(DHW, COUNTER, Instant(0), Instant(100))] == [5]
    assert await seeded.measurements.purge_before(Instant(25)) == 0


async def test_save_hourly_is_replayable(seeded):
    bucket = Bucket(Instant(3600), Instant(7200), 1.0, 0.5, 1.5, 1.2, 4, 3600, delta=2.0)
    await seeded.measurements.save_hourly(DHW, COUNTER, [bucket])
    await seeded.measurements.save_hourly(DHW, COUNTER, [bucket])


# --- trous ---


async def test_gaps_overlap_and_mark_recovered(repos):
    a = await repos.gaps.add(Gap(Instant(100), Instant(200), GapCause.DOWNTIME))
    b = await repos.gaps.add(Gap(Instant(10), Instant(50), GapCause.PROVIDER_ERROR))
    assert a.id is not None
    assert b.id is not None
    assert a.id != b.id
    assert [g.id for g in await repos.gaps.list(Instant(0), Instant(1000))] == [b.id, a.id]
    assert [g.id for g in await repos.gaps.list(Instant(150), Instant(160))] == [a.id]
    assert await repos.gaps.list(Instant(200), Instant(300)) == []  # [start, end) : bord exclu
    assert await repos.gaps.list(Instant(50), Instant(100)) == []

    await repos.gaps.mark_recovered([a.id, 9999])
    got = {g.id: g for g in await repos.gaps.list(Instant(0), Instant(1000))}
    assert got[a.id].recovered is True
    assert got[b.id].recovered is False
    assert got[a.id].cause is GapCause.DOWNTIME


# --- journal de collecte ---


async def test_poll_log_ordering(repos):
    ok1 = PollOutcome.success(Instant(10), 100, 0)
    ko = PollOutcome.failure(Instant(20), 50, ErrorKind.THROTTLED, "429")
    ok2 = PollOutcome.success(Instant(30), 80, 0)
    for o in (ok2, ok1, ko):
        await repos.polls.add(o)
    assert [o.at.epoch for o in await repos.polls.recent()] == [30, 20, 10]
    assert [o.at.epoch for o in await repos.polls.recent(2)] == [30, 20]
    assert (await repos.polls.last_success()).at == Instant(30)
    assert [o.at.epoch for o in await repos.polls.since(Instant(10))] == [20, 30]
    failure = (await repos.polls.recent())[1]
    assert (failure.ok, failure.error_kind, failure.error, failure.duration_ms) == (
        False,
        ErrorKind.THROTTLED,
        "429",
        50,
    )


async def test_poll_log_empty(repos):
    assert await repos.polls.last_success() is None
    assert await repos.polls.recent() == []


# --- énergie ---


def day(d: int, kwh: float = 1.0, cost: float | None = 0.2, cat: int = 1, tariff: Tariff = Tariff.PEAK) -> EnergyDay:
    return EnergyDay(date(2026, 3, d), cat, tariff, kwh, cost)


async def test_energy_upsert_counts(repos):
    assert await repos.energy.upsert([day(1), day(2)]) == 2
    assert await repos.energy.upsert([day(1), day(2)]) == 0
    assert await repos.energy.upsert([day(1, kwh=2.0), day(2)]) == 1
    assert await repos.energy.upsert([day(2, cost=None)]) == 1
    assert await repos.energy.upsert([day(2, tariff=Tariff.OFF_PEAK), day(2, cat=2)]) == 2


async def test_energy_range_inclusive_and_latest_day(repos):
    assert await repos.energy.latest_day() is None
    await repos.energy.upsert([day(1), day(2), day(3), day(3, tariff=Tariff.OFF_PEAK, kwh=0.5, cost=None)])
    got = await repos.energy.range(date(2026, 3, 2), date(2026, 3, 3))
    assert sorted((d.day.day, d.tariff.value) for d in got) == [(2, "peak"), (3, "off_peak"), (3, "peak")]
    assert await repos.energy.latest_day() == date(2026, 3, 3)
    assert {d.cost for d in got} == {0.2, None}
