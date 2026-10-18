"""Modèles de réponse JSON (instants en secondes epoch UTC, jours « YYYY-MM-DD »)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class GapOut(BaseModel):
    start: int
    end: int
    duration_seconds: int
    cause: str
    recovered: bool
    ongoing: bool


class PollerOut(BaseModel):
    running: bool
    stale: bool
    stopped_reason: str | None
    last_success: int | None
    consecutive_failures: int
    next_poll_in_seconds: float | None


class LastErrorOut(BaseModel):
    at: int
    message: str | None


class ErrorsOut(BaseModel):
    counts: dict[str, int]
    last: dict[str, LastErrorOut]


class EquipmentAvailabilityOut(BaseModel):
    id: str
    available: bool | None


class HealthOut(BaseModel):
    status: Literal["ok"]
    poller: PollerOut
    errors: ErrorsOut
    equipment: list[EquipmentAvailabilityOut]
    db_size_bytes: int
    recent_gaps: list[GapOut]


class MetricMetaOut(BaseModel):
    key: str
    label: str
    unit: str | None
    cumulative: bool
    enum: dict[str, str]


class EquipmentOut(BaseModel):
    id: str
    label: str
    kind: str
    available: bool | None
    last_seen: int | None
    metrics: list[MetricMetaOut]


class LatestOut(BaseModel):
    equipment: str
    metric: str
    label: str
    unit: str | None
    value: Any
    value_type: str
    display: str | None
    at: int
    age_seconds: int
    polled_at: int


class PointOut(BaseModel):
    start: int
    end: int
    avg: float | None
    min: float | None
    max: float | None
    last: float | None
    samples: int
    covered_seconds: int
    delta: float | None
    delta_spans_gap: bool


class SeriesOut(BaseModel):
    equipment: str
    metric: str
    label: str
    unit: str | None
    cumulative: bool
    bucket: str
    from_: int = Field(alias="from")
    to: int
    points: list[PointOut]
    gaps: list[GapOut]

    model_config = ConfigDict(populate_by_name=True)


class EnergyOut(BaseModel):
    day: str
    category: int
    tariff: str
    kwh: float
    cost: float | None
