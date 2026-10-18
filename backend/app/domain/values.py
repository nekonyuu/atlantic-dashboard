"""Value objects du contexte « Télémétrie de l'installation ».

Purs et immuables : aucune I/O, aucune dépendance hors bibliothèque standard.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any

_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True, order=True, slots=True)
class Instant:
    """Instant UTC, en secondes epoch."""

    epoch: int

    def __post_init__(self) -> None:
        if not isinstance(self.epoch, int) or isinstance(self.epoch, bool):
            raise TypeError("Instant attend un entier (secondes epoch)")

    def __add__(self, seconds: int) -> Instant:
        return Instant(self.epoch + seconds)

    def __sub__(self, other: Instant) -> int:
        return self.epoch - other.epoch


@dataclass(frozen=True, order=True, slots=True)
class EquipmentId:
    """Identifiant opaque d'un équipement (ex. ``dhw_0``), sûr pour les logs."""

    value: str

    def __post_init__(self) -> None:
        if not _KEY_RE.match(self.value):
            raise ValueError(f"EquipmentId invalide : {self.value!r}")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True, slots=True)
class MetricKey:
    """Nom logique d'une mesure (ex. ``dhw_temperature``), indépendant du fournisseur."""

    value: str

    def __post_init__(self) -> None:
        if not _KEY_RE.match(self.value):
            raise ValueError(f"MetricKey invalide : {self.value!r}")

    def __str__(self) -> str:
        return self.value


class ValueType(StrEnum):
    INTEGER = "INTEGER"
    FLOAT = "FLOAT"
    STRING = "STRING"
    BOOLEAN = "BOOLEAN"
    DATE = "DATE"
    JSON = "JSON"
    NULL = "NULL"


_NUMERIC = {ValueType.INTEGER, ValueType.FLOAT, ValueType.BOOLEAN, ValueType.DATE}


@dataclass(frozen=True, slots=True)
class MeasurementValue:
    """Valeur typée ; ``NULL`` représente une absence explicite."""

    type: ValueType
    number: float | None = None
    text: str | None = None
    unit: str | None = None

    def __post_init__(self) -> None:
        if self.type in _NUMERIC and self.number is None:
            raise ValueError(f"{self.type} exige un nombre")
        if self.type in (ValueType.STRING, ValueType.JSON) and self.text is None:
            raise ValueError(f"{self.type} exige un texte")
        if self.type is ValueType.NULL and (self.number is not None or self.text is not None):
            raise ValueError("NULL ne porte pas de valeur")

    @classmethod
    def of_number(cls, value: float, unit: str | None = None) -> MeasurementValue:
        is_int = isinstance(value, int) and not isinstance(value, bool)
        return cls(ValueType.INTEGER if is_int else ValueType.FLOAT, number=float(value), unit=unit)

    @classmethod
    def of_bool(cls, value: bool) -> MeasurementValue:
        return cls(ValueType.BOOLEAN, number=1.0 if value else 0.0)

    @classmethod
    def of_text(cls, value: str, unit: str | None = None) -> MeasurementValue:
        return cls(ValueType.STRING, text=value, unit=unit)

    @classmethod
    def of_json(cls, value: Any) -> MeasurementValue:
        return cls(ValueType.JSON, text=json.dumps(value, sort_keys=True, ensure_ascii=False))

    @classmethod
    def absent(cls) -> MeasurementValue:
        return cls(ValueType.NULL)

    @property
    def is_numeric(self) -> bool:
        return self.type in _NUMERIC

    def same_reading(self, other: MeasurementValue) -> bool:
        """Égalité de lecture (l'unité ne compte pas)."""
        return (self.type, self.number, self.text) == (other.type, other.number, other.text)


class Origin(StrEnum):
    LIVE = "live"
    BACKFILL = "backfill"


@dataclass(frozen=True, slots=True)
class Measurement:
    """Une mesure : ``instant`` est l'heure fournisseur de la valeur, ``polled_at`` celle de sa lecture."""

    equipment_id: EquipmentId
    metric_key: MetricKey
    instant: Instant
    value: MeasurementValue
    source: str
    polled_at: Instant
    provider_timestamped: bool = True
    origin: Origin = Origin.LIVE

    @property
    def series_key(self) -> tuple[EquipmentId, MetricKey]:
        return (self.equipment_id, self.metric_key)


class Tariff(StrEnum):
    PEAK = "peak"
    OFF_PEAK = "off_peak"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class EnergyDay:
    """Consommation électrique d'un jour civil, telle que déclarée par le fournisseur."""

    day: date
    category: int
    tariff: Tariff
    kwh: float
    cost: float | None = None

    def __post_init__(self) -> None:
        if self.kwh < 0:
            raise ValueError("une consommation ne peut pas être négative")

    @property
    def key(self) -> tuple[date, int, Tariff]:
        return (self.day, self.category, self.tariff)


class BucketSize(StrEnum):
    FIVE_MINUTES = "5m"
    HOUR = "1h"
    DAY = "1d"


@dataclass(frozen=True, slots=True)
class Bucket:
    """Agrégat d'une série sur ``[start, end)``.

    ``covered_seconds`` = durée où une valeur était connue (hors trous).
    ``delta`` n'est renseigné que pour les compteurs cumulés ; ``delta_spans_gap``
    signale qu'une partie du delta couvre un trou (niveau B du catch-up).
    """

    start: Instant
    end: Instant
    avg: float | None
    min: float | None
    max: float | None
    last: float | None
    samples: int
    covered_seconds: int
    delta: float | None = None
    delta_spans_gap: bool = False


@dataclass(frozen=True, slots=True)
class Series:
    equipment_id: EquipmentId
    metric_key: MetricKey
    bucket: BucketSize
    buckets: tuple[Bucket, ...]


class ErrorKind(StrEnum):
    CREDENTIALS = "credentials"
    THROTTLED = "throttled"
    UNAVAILABLE = "unavailable"
    UNEXPECTED = "unexpected"


@dataclass(frozen=True, slots=True)
class PollOutcome:
    """Résultat typé d'un cycle de collecte."""

    at: Instant
    ok: bool
    duration_ms: int
    error_kind: ErrorKind | None = None
    error: str | None = None
    recorded: int = 0

    def __post_init__(self) -> None:
        if self.ok and self.error_kind is not None:
            raise ValueError("un succès ne porte pas d'erreur")
        if not self.ok and self.error_kind is None:
            raise ValueError("un échec doit être typé")

    @classmethod
    def success(cls, at: Instant, duration_ms: int, recorded: int) -> PollOutcome:
        return cls(at=at, ok=True, duration_ms=duration_ms, recorded=recorded)

    @classmethod
    def failure(cls, at: Instant, duration_ms: int, kind: ErrorKind, error: str) -> PollOutcome:
        return cls(at=at, ok=False, duration_ms=duration_ms, error_kind=kind, error=error)
