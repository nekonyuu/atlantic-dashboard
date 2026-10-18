"""Repositories SQLite : mêmes sémantiques que les fakes en mémoire (reads sur reader, writes sur writer)."""

from __future__ import annotations

import json
import time
from collections.abc import Sequence
from datetime import date

from app.adapters.outbound.sqlite.connection import Database
from app.domain.model import Equipment, Gap, GapCause
from app.domain.values import (
    Bucket,
    EnergyDay,
    EquipmentId,
    ErrorKind,
    Instant,
    Measurement,
    MeasurementValue,
    MetricKey,
    Origin,
    PollOutcome,
    Tariff,
    ValueType,
)

_REF_COLUMNS = ("device_id", "model_id", "product_id", "slot", "zone_id")


class SqliteEquipmentRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def upsert(self, equipment: Sequence[Equipment]) -> None:
        # first_seen / last_seen sont NOT NULL en base : si l'un manque on reprend l'autre, sinon 0.
        rows = []
        for e in equipment:
            first = e.first_seen if e.first_seen is not None else e.last_seen
            last = e.last_seen if e.last_seen is not None else e.first_seen
            rows.append(
                (
                    str(e.id),
                    e.kind,
                    *(e.provider_ref.get(c) for c in _REF_COLUMNS),
                    e.label,
                    first.epoch if first else 0,
                    last.epoch if last else 0,
                    None if e.available is None else int(e.available),
                )
            )
        async with self._db.transaction() as conn:
            await conn.executemany(
                """
                INSERT INTO equipment (equipment_id, kind, device_id, model_id, product_id, slot, zone_id,
                                       label, first_seen, last_seen, available)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(equipment_id) DO UPDATE SET
                  kind=excluded.kind, device_id=excluded.device_id, model_id=excluded.model_id,
                  product_id=excluded.product_id, slot=excluded.slot, zone_id=excluded.zone_id,
                  label=excluded.label, last_seen=excluded.last_seen, available=excluded.available
                """,  # first_seen volontairement absent du UPDATE : on garde l'original
                rows,
            )

    async def all(self) -> list[Equipment]:
        sql = (
            "SELECT equipment_id, kind, label, available, first_seen, last_seen, "
            + ", ".join(_REF_COLUMNS)
            + " FROM equipment ORDER BY equipment_id"
        )
        async with self._db.reader.execute(sql) as cur:
            rows = await cur.fetchall()
        return [
            Equipment(
                id=EquipmentId(r[0]),
                kind=r[1],
                label=r[2] or "",
                available=None if r[3] is None else bool(r[3]),
                first_seen=Instant(r[4]),
                last_seen=Instant(r[5]),
                provider_ref={c: v for c, v in zip(_REF_COLUMNS, r[6:], strict=True) if v is not None},
            )
            for r in rows
        ]


_MEASUREMENT_COLUMNS = (
    "equipment_id, metric_key, ts, polled_at, source_state, value_type, value_num, value_text, origin"
)


def _to_measurement(r: tuple) -> Measurement:
    vtype = ValueType(r[5])
    # L'unité n'est pas stockée ; provider_timestamped non plus (toujours vrai en lecture).
    value = MeasurementValue(
        vtype,
        number=r[6] if vtype in (ValueType.INTEGER, ValueType.FLOAT, ValueType.BOOLEAN, ValueType.DATE) else None,
        text=r[7] if vtype in (ValueType.STRING, ValueType.JSON) else None,
    )
    return Measurement(
        equipment_id=EquipmentId(r[0]),
        metric_key=MetricKey(r[1]),
        instant=Instant(r[2]),
        value=value,
        source=r[4],
        polled_at=Instant(r[3]),
        origin=Origin(r[8]),
    )


class SqliteMeasurementRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def append(self, batch: Sequence[Measurement]) -> int:
        rows = [
            (
                str(m.equipment_id),
                str(m.metric_key),
                m.instant.epoch,
                m.polled_at.epoch,
                m.source,
                m.value.type.value,
                m.value.number,
                m.value.text,
                m.origin.value,
            )
            for m in batch
        ]
        async with self._db.transaction() as conn:
            before = conn.total_changes
            await conn.executemany(
                """
                INSERT OR IGNORE INTO measurement
                  (equipment_id, metric_key, ts, polled_at, source_state, value_type, value_num, value_text, origin)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            return conn.total_changes - before

    async def latest(self, equipment_id: EquipmentId | None = None) -> list[Measurement]:
        where = "" if equipment_id is None else "WHERE equipment_id = ?"
        params = () if equipment_id is None else (str(equipment_id),)
        sql = f"""
            SELECT {_MEASUREMENT_COLUMNS} FROM measurement
            JOIN (SELECT equipment_id AS e, metric_key AS k, MAX(ts) AS t FROM measurement {where}
                  GROUP BY equipment_id, metric_key)
              ON equipment_id = e AND metric_key = k AND ts = t
            ORDER BY equipment_id, metric_key
        """
        async with self._db.reader.execute(sql, params) as cur:
            return [_to_measurement(r) for r in await cur.fetchall()]

    async def range(
        self, equipment_id: EquipmentId, metric_key: MetricKey, start: Instant, end: Instant
    ) -> list[Measurement]:
        sql = f"""SELECT {_MEASUREMENT_COLUMNS} FROM measurement
                  WHERE equipment_id = ? AND metric_key = ? AND ts >= ? AND ts < ? ORDER BY ts"""
        async with self._db.reader.execute(sql, (str(equipment_id), str(metric_key), start.epoch, end.epoch)) as cur:
            return [_to_measurement(r) for r in await cur.fetchall()]

    async def last_recorded(
        self, equipment_id: EquipmentId, metric_key: MetricKey, before: Instant
    ) -> Measurement | None:
        sql = f"""SELECT {_MEASUREMENT_COLUMNS} FROM measurement
                  WHERE equipment_id = ? AND metric_key = ? AND ts < ? ORDER BY ts DESC LIMIT 1"""
        async with self._db.reader.execute(sql, (str(equipment_id), str(metric_key), before.epoch)) as cur:
            row = await cur.fetchone()
        return _to_measurement(row) if row else None

    async def save_hourly(self, equipment_id: EquipmentId, metric_key: MetricKey, buckets: Sequence[Bucket]) -> None:
        rows = [
            (str(equipment_id), str(metric_key), b.start.epoch, b.avg, b.min, b.max, b.last, b.delta, b.samples)
            for b in buckets
        ]
        async with self._db.transaction() as conn:
            await conn.executemany(
                """INSERT OR REPLACE INTO measurement_hourly
                   (equipment_id, metric_key, hour_ts, avg_w, min, max, last, delta, samples)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )

    async def purge_before(self, before: Instant) -> int:
        # (equipment_id, metric_key, ts) est unique : ts < MAX(ts) de la série <=> pas la dernière ligne.
        async with self._db.transaction() as conn:
            cur = await conn.execute(
                """DELETE FROM measurement WHERE ts < ? AND ts < (
                     SELECT MAX(m2.ts) FROM measurement m2
                     WHERE m2.equipment_id = measurement.equipment_id AND m2.metric_key = measurement.metric_key)""",
                (before.epoch,),
            )
            return cur.rowcount


class SqliteGapRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def add(self, gap: Gap) -> Gap:
        async with self._db.transaction() as conn:
            cur = await conn.execute(
                "INSERT INTO gap (from_ts, to_ts, cause, recovered) VALUES (?, ?, ?, ?)",
                (gap.start.epoch, gap.end.epoch, gap.cause.value, int(gap.recovered)),
            )
            new_id = cur.lastrowid
        return Gap(gap.start, gap.end, gap.cause, gap.recovered, id=new_id)

    async def list(self, start: Instant, end: Instant) -> list[Gap]:
        sql = """SELECT id, from_ts, to_ts, cause, recovered FROM gap
                 WHERE from_ts < ? AND ? < to_ts ORDER BY from_ts, id"""
        async with self._db.reader.execute(sql, (end.epoch, start.epoch)) as cur:
            rows = await cur.fetchall()
        return [Gap(Instant(r[1]), Instant(r[2]), GapCause(r[3]), bool(r[4]), id=r[0]) for r in rows]

    async def mark_recovered(self, gap_ids: Sequence[int]) -> None:
        async with self._db.transaction() as conn:
            await conn.executemany("UPDATE gap SET recovered = 1 WHERE id = ?", [(i,) for i in gap_ids])


class SqlitePollLogRepository:
    """``recorded`` n'est pas stocké (relu à 0)."""

    _COLUMNS = "ts, ok, duration_ms, error_kind, error"

    def __init__(self, db: Database) -> None:
        self._db = db

    async def add(self, outcome: PollOutcome) -> None:
        kind = outcome.error_kind.value if outcome.error_kind else None
        async with self._db.transaction() as conn:
            await conn.execute(
                "INSERT INTO poll_log (ts, ok, duration_ms, error_kind, error) VALUES (?, ?, ?, ?, ?)",
                (outcome.at.epoch, int(outcome.ok), outcome.duration_ms, kind, outcome.error),
            )

    @staticmethod
    def _to_outcome(r: tuple) -> PollOutcome:
        return PollOutcome(
            at=Instant(r[0]),
            ok=bool(r[1]),
            duration_ms=r[2] or 0,
            error_kind=ErrorKind(r[3]) if r[3] else None,
            error=r[4],
        )

    async def recent(self, limit: int = 50) -> list[PollOutcome]:
        sql = f"SELECT {self._COLUMNS} FROM poll_log ORDER BY ts DESC, rowid DESC LIMIT ?"
        async with self._db.reader.execute(sql, (limit,)) as cur:
            return [self._to_outcome(r) for r in await cur.fetchall()]

    async def last_success(self) -> PollOutcome | None:
        sql = f"SELECT {self._COLUMNS} FROM poll_log WHERE ok = 1 ORDER BY ts DESC, rowid DESC LIMIT 1"
        async with self._db.reader.execute(sql) as cur:
            row = await cur.fetchone()
        return self._to_outcome(row) if row else None

    async def since(self, after: Instant) -> list[PollOutcome]:
        sql = f"SELECT {self._COLUMNS} FROM poll_log WHERE ts > ? ORDER BY ts, rowid"
        async with self._db.reader.execute(sql, (after.epoch,)) as cur:
            return [self._to_outcome(r) for r in await cur.fetchall()]


class SqliteEnergyRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def upsert(self, days: Sequence[EnergyDay]) -> int:
        now = int(time.time())
        rows = [(d.day.isoformat(), d.category, d.tariff.value, d.kwh, d.cost, now) for d in days]
        async with self._db.transaction() as conn:
            before = conn.total_changes
            await conn.executemany(
                """INSERT INTO energy_daily (day, category, tariff, kwh, cost, origin, fetched_at)
                   VALUES (?, ?, ?, ?, ?, 'backfill', ?)
                   ON CONFLICT(day, category, tariff) DO UPDATE SET
                     kwh = excluded.kwh, cost = excluded.cost, fetched_at = excluded.fetched_at
                   WHERE kwh IS NOT excluded.kwh OR cost IS NOT excluded.cost""",
                rows,
            )
            return conn.total_changes - before

    async def range(self, since: date, until: date) -> list[EnergyDay]:
        sql = """SELECT day, category, tariff, kwh, cost FROM energy_daily
                 WHERE day >= ? AND day <= ? ORDER BY day, category, tariff"""
        async with self._db.reader.execute(sql, (since.isoformat(), until.isoformat())) as cur:
            rows = await cur.fetchall()
        return [EnergyDay(date.fromisoformat(r[0]), r[1], Tariff(r[2]), r[3], r[4]) for r in rows]

    async def latest_day(self) -> date | None:
        async with self._db.reader.execute("SELECT MAX(day) FROM energy_daily") as cur:
            row = await cur.fetchone()
        return date.fromisoformat(row[0]) if row and row[0] else None


class SqliteCatalogueStore:
    """Cache du catalogue de capacités fournisseur (remplacé en bloc)."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def load(self) -> list[dict] | None:
        sql = "SELECT capability_id, name, type, unit, resolution, enum_json FROM capability_catalogue ORDER BY 1"
        async with self._db.reader.execute(sql) as cur:
            rows = await cur.fetchall()
        if not rows:
            return None
        return [
            {
                "id": r[0],
                "name": r[1],
                "type": r[2],
                "unit": r[3],
                "resolution": r[4],
                "enum": json.loads(r[5]) if r[5] is not None else None,
            }
            for r in rows
        ]

    async def save(self, entries: list[dict], fetched_at: int) -> None:
        rows = [
            (
                e["id"],
                e.get("name"),
                e.get("type"),
                e.get("unit"),
                e.get("resolution"),
                json.dumps(e["enum"], ensure_ascii=False) if e.get("enum") is not None else None,
                fetched_at,
            )
            for e in entries
        ]
        async with self._db.transaction() as conn:
            await conn.execute("DELETE FROM capability_catalogue")
            await conn.executemany(
                """INSERT INTO capability_catalogue
                   (capability_id, name, type, unit, resolution, enum_json, fetched_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )
