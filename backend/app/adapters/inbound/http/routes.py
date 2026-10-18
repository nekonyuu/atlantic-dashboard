"""Routes REST en lecture seule (PLAN.md §9)."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.adapters.inbound.http.deps import HttpApi, api
from app.adapters.inbound.http.schemas import (
    EnergyOut,
    EquipmentOut,
    ErrorsOut,
    GapOut,
    HealthOut,
    LastErrorOut,
    LatestOut,
    MetricMetaOut,
    PointOut,
    PollerOut,
    SeriesOut,
)
from app.application.ports import MetricInfo
from app.domain.model import Gap
from app.domain.services import PARIS
from app.domain.values import BucketSize, EquipmentId, Instant, MeasurementValue, MetricKey, ValueType

router = APIRouter(prefix="/api")

DAY = 86400
# durée maximale demandable par taille de bucket (jours)
MAX_RANGE_DAYS = {BucketSize.FIVE_MINUTES: 7, BucketSize.HOUR: 400, BucketSize.DAY: 3660}
MAX_ENERGY_DAYS = 3660

Api = Annotated[HttpApi, Depends(api)]


def bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail=message)


def gap_out(gap: Gap) -> GapOut:
    return GapOut(
        start=gap.start.epoch,
        end=gap.end.epoch,
        duration_seconds=gap.duration,
        cause=str(gap.cause),
        recovered=gap.recovered,
        ongoing=gap.id is None,
    )


def parse_epoch(raw: str | None, name: str, default: int) -> int:
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        raise bad_request(f"paramètre « {name} » invalide : entier (secondes epoch) attendu") from None


def parse_day(raw: str | None, name: str, default: date) -> date:
    if raw is None or raw == "":
        return default
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise bad_request(f"paramètre « {name} » invalide : format YYYY-MM-DD attendu") from None


def parse_id(raw: str, name: str, factory: type[EquipmentId] | type[MetricKey]) -> Any:
    try:
        return factory(raw)
    except ValueError as exc:
        raise bad_request(str(exc)) from None


def json_value(value: MeasurementValue) -> Any:
    match value.type:
        case ValueType.INTEGER:
            return int(value.number or 0)
        case ValueType.FLOAT | ValueType.DATE:
            return value.number
        case ValueType.BOOLEAN:
            return bool(value.number)
        case ValueType.STRING:
            return value.text
        case ValueType.JSON:
            return json.loads(value.text or "null")
        case _:
            return None


def enum_label(info: MetricInfo | None, value: MeasurementValue) -> str | None:
    if info is None or not info.enum or value.number is None or value.type not in (ValueType.INTEGER, ValueType.FLOAT):
        return None
    if not float(value.number).is_integer():
        return None
    return info.enum.get(int(value.number))


@router.get("/health", response_model=HealthOut)
async def health(a: Api) -> HealthOut:
    h = await a.get_health.run()
    state = a.scheduler_state()
    return HealthOut(
        status="ok",
        poller=PollerOut(
            running=bool(state.running),
            stale=h.poller_stale,
            stopped_reason=state.stopped_reason,
            last_success=h.last_success.epoch if h.last_success else None,
            consecutive_failures=state.consecutive_failures,
            next_poll_in_seconds=state.next_delay_seconds,
        ),
        errors=ErrorsOut(
            counts={str(k): v for k, v in h.error_counts.items()},
            last={str(k): LastErrorOut(at=o.at.epoch, message=o.error) for k, o in h.last_errors.items()},
        ),
        equipment=[{"id": str(i), "available": av} for i, av in sorted(h.availability.items())],
        db_size_bytes=h.db_size_bytes,
        recent_gaps=[gap_out(g) for g in h.recent_gaps],
    )


@router.get("/equipment", response_model=list[EquipmentOut])
async def equipment(a: Api) -> list[EquipmentOut]:
    infos = await a.get_metrics.run()
    out = []
    for e in await a.get_equipment.run():
        metrics = [
            MetricMetaOut(
                key=str(i.metric_key),
                label=i.label,
                unit=i.unit,
                cumulative=i.cumulative,
                enum={str(k): v for k, v in i.enum.items()},
            )
            for i in infos
            if i.equipment_id == e.id
        ]
        out.append(
            EquipmentOut(
                id=str(e.id),
                label=e.label,
                kind=e.kind,
                available=e.available,
                last_seen=e.last_seen.epoch if e.last_seen else None,
                metrics=metrics,
            )
        )
    return out


@router.get("/latest", response_model=list[LatestOut])
async def latest(a: Api, equipment: str | None = None) -> list[LatestOut]:
    eq = parse_id(equipment, "equipment", EquipmentId) if equipment else None
    infos = {(i.equipment_id, i.metric_key): i for i in await a.get_metrics.run()}
    out = []
    for item in await a.get_latest.run(eq):
        m = item.measurement
        info = infos.get(m.series_key)
        out.append(
            LatestOut(
                equipment=str(m.equipment_id),
                metric=str(m.metric_key),
                label=info.label if info else str(m.metric_key),
                unit=info.unit if info and info.unit else m.value.unit,
                value=json_value(m.value),
                value_type=str(m.value.type),
                display=enum_label(info, m.value),
                at=m.instant.epoch,
                age_seconds=item.age_seconds,
                polled_at=m.polled_at.epoch,
            )
        )
    return out


def default_bucket(span: int) -> BucketSize:
    if span <= 2 * DAY:
        return BucketSize.FIVE_MINUTES
    if span <= 62 * DAY:
        return BucketSize.HOUR
    return BucketSize.DAY


@router.get("/series", response_model=SeriesOut, response_model_by_alias=True)
async def series(
    a: Api,
    equipment: str,
    metric: str,
    from_: Annotated[str | None, Query(alias="from")] = None,
    to: str | None = None,
    bucket: str | None = None,
) -> SeriesOut:
    eq = parse_id(equipment, "equipment", EquipmentId)
    key = parse_id(metric, "metric", MetricKey)
    end = parse_epoch(to, "to", a.clock.now().epoch)
    start = parse_epoch(from_, "from", end - DAY)
    if start >= end:
        raise bad_request("« from » doit être strictement antérieur à « to »")
    if bucket is None or bucket == "":
        size = default_bucket(end - start)
    else:
        try:
            size = BucketSize(bucket)
        except ValueError:
            raise bad_request(f"bucket inconnu : {bucket!r} (5m, 1h ou 1d)") from None
    max_days = MAX_RANGE_DAYS[size]
    if end - start > max_days * DAY:
        raise bad_request(f"période trop longue pour le bucket {size} (maximum {max_days} jours)")

    result = await a.get_series.run(eq, key, Instant(start), Instant(end), size)
    info = next((i for i in await a.get_metrics.run() if i.equipment_id == eq and i.metric_key == key), None)
    return SeriesOut(
        equipment=str(eq),
        metric=str(key),
        label=info.label if info else str(key),
        unit=info.unit if info else None,
        cumulative=info.cumulative if info else False,
        bucket=str(size),
        **{"from": start},
        to=end,
        points=[
            PointOut(
                start=b.start.epoch,
                end=b.end.epoch,
                avg=b.avg,
                min=b.min,
                max=b.max,
                last=b.last,
                samples=b.samples,
                covered_seconds=b.covered_seconds,
                delta=b.delta,
                delta_spans_gap=b.delta_spans_gap,
            )
            for b in result.series.buckets
        ],
        gaps=[gap_out(g) for g in result.gaps],
    )


@router.get("/gaps", response_model=list[GapOut])
async def gaps(a: Api, from_: Annotated[str | None, Query(alias="from")] = None, to: str | None = None) -> list[GapOut]:
    end = parse_epoch(to, "to", a.clock.now().epoch)
    start = parse_epoch(from_, "from", end - 7 * DAY)
    if start >= end:
        raise bad_request("« from » doit être strictement antérieur à « to »")
    return [gap_out(g) for g in await a.get_gaps.run(Instant(start), Instant(end))]


@router.get("/energy", response_model=list[EnergyOut])
async def energy(
    a: Api, from_: Annotated[str | None, Query(alias="from")] = None, to: str | None = None
) -> list[EnergyOut]:
    today = datetime.fromtimestamp(a.clock.now().epoch, PARIS).date()
    until = parse_day(to, "to", today)
    since = parse_day(from_, "from", until - timedelta(days=30))
    if since > until:
        raise bad_request("« from » doit être antérieur ou égal à « to »")
    if (until - since).days + 1 > MAX_ENERGY_DAYS:
        raise bad_request(f"période trop longue (maximum {MAX_ENERGY_DAYS} jours)")
    return [
        EnergyOut(day=d.day.isoformat(), category=d.category, tariff=str(d.tariff), kwh=d.kwh, cost=d.cost)
        for d in await a.get_energy.run(since, until)
    ]
