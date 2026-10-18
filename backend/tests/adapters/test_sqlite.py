"""Adaptateur SQLite : pragmas, migrations, persistance, sauvegardes."""

from __future__ import annotations

import sqlite3
from datetime import datetime

import aiosqlite
import pytest

from app.adapters.outbound.sqlite import (
    Database,
    SqliteBackupService,
    SqliteCatalogueStore,
    SqliteEquipmentRepository,
    SqliteMeasurementRepository,
    SqliteStorageStats,
    migrate,
)
from app.domain.model import Equipment
from app.domain.services import PARIS
from app.domain.values import Instant, Measurement, MeasurementValue, Origin, ValueType
from tests.builders import DHW, TEMP, m


@pytest.fixture
async def db(tmp_path):
    database = await Database.open(tmp_path / "data" / "pac.db")
    yield database
    await database.close()


async def scalar(conn: aiosqlite.Connection, sql: str):
    async with conn.execute(sql) as cur:
        row = await cur.fetchone()
    return row[0]


async def seed(db: Database) -> SqliteMeasurementRepository:
    await SqliteEquipmentRepository(db).upsert([Equipment(DHW, "Ballon", "dhw", None, Instant(1), Instant(1))])
    return SqliteMeasurementRepository(db)


async def test_pragmas_on_both_connections(db):
    for conn in (db.writer, db.reader):
        assert await scalar(conn, "PRAGMA foreign_keys") == 1
        assert await scalar(conn, "PRAGMA journal_mode") == "wal"
        assert await scalar(conn, "PRAGMA busy_timeout") == 5000
        assert await scalar(conn, "PRAGMA synchronous") == 1  # NORMAL


async def test_new_database_is_incremental_auto_vacuum(db):
    assert await scalar(db.writer, "PRAGMA auto_vacuum") == 2


async def test_migrations_are_idempotent(tmp_path):
    path = tmp_path / "pac.db"
    first = await Database.open(path)
    version = await scalar(first.writer, "PRAGMA user_version")
    await migrate(first.writer)
    await first.close()
    second = await Database.open(path)
    assert version >= 1
    assert await scalar(second.writer, "PRAGMA user_version") == version
    assert await scalar(second.writer, "PRAGMA auto_vacuum") == 2
    await second.close()


async def test_data_persists_after_reopen(tmp_path):
    path = tmp_path / "pac.db"
    db = await Database.open(path)
    repo = await seed(db)
    await repo.append([m(10, 20.5)])
    await db.close()
    db = await Database.open(path)
    got = await SqliteMeasurementRepository(db).latest()
    await db.close()
    assert [x.value.number for x in got] == [20.5]


async def test_foreign_key_is_enforced(db):
    with pytest.raises(sqlite3.IntegrityError):
        await SqliteMeasurementRepository(db).append([m(10, 1.0)])  # équipement inconnu
    # la transaction a été annulée : le writer reste utilisable
    repo = await seed(db)
    assert await repo.append([m(10, 1.0)]) == 1


@pytest.mark.parametrize(
    "value",
    [
        MeasurementValue.of_number(3),
        MeasurementValue.of_number(3.5),
        MeasurementValue.of_bool(True),
        MeasurementValue.of_bool(False),
        MeasurementValue.of_text("auto"),
        MeasurementValue.of_json({"a": [1, 2], "é": "x"}),
        MeasurementValue.absent(),
        MeasurementValue(ValueType.DATE, number=1700000000.0),
    ],
)
async def test_value_types_roundtrip(db, value):
    repo = await seed(db)
    sample = Measurement(DHW, TEMP, Instant(10), value, "111", Instant(11))
    assert await repo.append([sample]) == 1
    [got] = await repo.latest()
    assert got.value == value
    assert got.origin is Origin.LIVE


async def test_unit_is_not_stored(db):
    repo = await seed(db)
    await repo.append([Measurement(DHW, TEMP, Instant(10), MeasurementValue.of_number(1, "°C"), "111", Instant(10))])
    [got] = await repo.latest()
    assert got.value.unit is None


def epoch(y: int, mo: int, d: int, h: int = 12) -> Instant:
    return Instant(int(datetime(y, mo, d, h, tzinfo=PARIS).timestamp()))


async def test_backup_creates_valid_file_and_replaces_same_day(db, tmp_path):
    repo = await seed(db)
    await repo.append([m(10, 1.0)])
    backups = tmp_path / "bk"
    service = SqliteBackupService(db, backups, keep=3)
    name = await service.snapshot(epoch(2026, 3, 1))
    assert name == "pac-2026-03-01.db"
    await repo.append([m(20, 2.0)])
    assert await service.snapshot(epoch(2026, 3, 1, 23)) == name  # même jour (Paris) : remplacé
    assert [p.name for p in backups.iterdir()] == [name]
    with sqlite3.connect(backups / name) as conn:
        assert conn.execute("SELECT COUNT(*) FROM measurement").fetchone()[0] == 2
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


async def test_backup_date_is_paris_local(db, tmp_path):
    service = SqliteBackupService(db, tmp_path / "bk", keep=3)
    # 2026-03-01T23:30:00Z = 00:30 le 2 mars à Paris
    assert await service.snapshot(Instant(1772407800)) == "pac-2026-03-02.db"


async def test_backup_rotation_keeps_newest(db, tmp_path):
    backups = tmp_path / "bk"
    service = SqliteBackupService(db, backups, keep=2)
    for d in (1, 2, 3, 4):
        await service.snapshot(epoch(2026, 3, d))
    assert sorted(p.name for p in backups.iterdir()) == ["pac-2026-03-03.db", "pac-2026-03-04.db"]


async def test_catalogue_roundtrip_and_replace(db):
    store = SqliteCatalogueStore(db)
    assert await store.load() is None
    entries = [
        {"id": 1, "name": "mode", "type": 3, "unit": None, "resolution": None, "enum": {"0": "off", "1": "on"}},
        {"id": 2, "name": "temp", "type": 2, "unit": "°C", "resolution": 0.5, "enum": None},
    ]
    await store.save(entries, 1000)
    assert await store.load() == entries
    await store.save(entries[1:], 2000)
    assert await store.load() == entries[1:]
    await store.save([], 3000)
    assert await store.load() is None


async def test_storage_stats(db, tmp_path):
    repo = await seed(db)
    await repo.append([m(10, 1.0)])
    assert await SqliteStorageStats(tmp_path / "data" / "pac.db").size_bytes() > 0
    assert await SqliteStorageStats(tmp_path / "absent.db").size_bytes() == 0
