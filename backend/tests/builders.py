"""Constructeurs de données de test (aucun mock)."""

from __future__ import annotations

from datetime import datetime

from app.domain.services import PARIS
from app.domain.values import EquipmentId, Instant, Measurement, MeasurementValue, MetricKey, Origin

DHW = EquipmentId("dhw_0")
TEMP = MetricKey("dhw_temperature")
COUNTER = MetricKey("energy_dhw_cumulative")


def paris(y: int, mo: int, d: int, h: int = 0, mi: int = 0) -> Instant:
    return Instant(int(datetime(y, mo, d, h, mi, tzinfo=PARIS).timestamp()))


def m(
    t: int | Instant,
    value: float,
    *,
    eq: EquipmentId = DHW,
    key: MetricKey = TEMP,
    polled: int | Instant | None = None,
    stamped: bool = True,
    origin: Origin = Origin.LIVE,
) -> Measurement:
    instant = t if isinstance(t, Instant) else Instant(t)
    polled_at = polled if isinstance(polled, Instant) else Instant(polled) if polled is not None else instant
    return Measurement(
        equipment_id=eq,
        metric_key=key,
        instant=instant,
        value=MeasurementValue.of_number(value),
        source="111",
        polled_at=polled_at,
        provider_timestamped=stamped,
        origin=origin,
    )
