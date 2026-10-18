"""Traduction du modèle Magellan vers le domaine (couche anti-corruption)."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from app.domain.model import Equipment
from app.domain.values import (
    EnergyDay,
    EquipmentId,
    Instant,
    Measurement,
    MeasurementValue,
    MetricKey,
    Tariff,
    ValueType,
)

log = logging.getLogger(__name__)

SEMANTICS_PATH = Path(__file__).with_name("semantics.yaml")

# Types du catalogue Magellan (constatés en phase 0).
CAT_INT, CAT_FLOAT, CAT_STRING, CAT_BOOL, CAT_ENUM, CAT_JSON = 1, 2, 3, 4, 5, 7

_TARIFFS = {1: Tariff.PEAK, 2: Tariff.OFF_PEAK}


@dataclass(frozen=True, slots=True)
class MetricSpec:
    key: MetricKey
    capability: int
    unit: str | None = None
    cumulative: bool = False


@dataclass(frozen=True, slots=True)
class EquipmentSpec:
    id: str
    kind: str
    label: str
    product_id: int
    single: bool
    metrics: tuple[MetricSpec, ...]


@dataclass(frozen=True, slots=True)
class Semantics:
    equipment: tuple[EquipmentSpec, ...]

    @classmethod
    def load(cls, path: Path = SEMANTICS_PATH) -> Semantics:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        specs = []
        for e in raw["equipment"]:
            metrics = tuple(
                MetricSpec(MetricKey(k), int(v["capability"]), v.get("unit"), bool(v.get("cumulative", False)))
                for k, v in e["metrics"].items()
            )
            specs.append(
                EquipmentSpec(e["id"], e["kind"], e["label"], int(e["product_id"]), bool(e.get("single")), metrics)
            )
        return cls(tuple(specs))

    def cumulative_metrics(self) -> set[MetricKey]:
        return {m.key for e in self.equipment for m in e.metrics if m.cumulative}


@dataclass(frozen=True, slots=True)
class CapabilityInfo:
    id: int
    name: str
    type: int | None
    unit: str | None
    enum: Mapping[int, str] = field(default_factory=dict)


class Catalogue:
    """Catalogue fournisseur des capacités : nom, type, unité, libellés d'enum."""

    def __init__(self, entries: Iterable[Mapping[str, Any]] = ()) -> None:
        self._by_id: dict[int, CapabilityInfo] = {}
        for e in entries:
            if not isinstance(e.get("id"), int):
                continue
            values = (e.get("enum") or {}).get("values") or []
            labels = {int(v["Key"]): str(v["Value"]) for v in values if "Key" in v and "Value" in v}
            unit = (e.get("unit") or "").strip() or None
            self._by_id[e["id"]] = CapabilityInfo(e["id"], str(e.get("name") or ""), e.get("type"), unit, labels)

    def __len__(self) -> int:
        return len(self._by_id)

    def get(self, capability_id: int) -> CapabilityInfo | None:
        return self._by_id.get(capability_id)


@dataclass(frozen=True, slots=True)
class ResolvedEquipment:
    """Équipement Magellan reconnu, avec ce qu'il faut pour lire ses mesures."""

    equipment: Equipment
    spec: EquipmentSpec
    capabilities: Mapping[int, Mapping[str, Any]]


def resolve_equipment(devices: Iterable[Mapping[str, Any]], semantics: Semantics) -> list[ResolvedEquipment]:
    """Associe les devices du setup aux équipements de ``semantics.yaml``.

    Un device dont le productId n'est pas décrit est ignoré (journalisé une fois
    par appel, sans identifiant).
    """
    by_product: dict[int, list[Mapping[str, Any]]] = {}
    for d in devices:
        if isinstance(d.get("productId"), int) and isinstance(d.get("deviceId"), int):
            by_product.setdefault(d["productId"], []).append(d)
    known = {s.product_id for s in semantics.equipment}
    for pid in sorted(set(by_product) - known):
        log.info("Équipement Magellan non décrit dans semantics.yaml ignoré (productId=%s)", pid)

    out = []
    for spec in semantics.equipment:
        matches = sorted(by_product.get(spec.product_id, []), key=lambda d: d["deviceId"])
        if spec.single and len(matches) > 1:
            log.warning("%d équipements pour %s (single) : seul le premier est lu", len(matches), spec.id)
            matches = matches[:1]
        for index, d in enumerate(matches, start=1):
            eq_id = spec.id if spec.single else f"{spec.id}_{index}"
            label = spec.label if spec.single else f"{spec.label} {index}"
            equipment = Equipment(
                id=EquipmentId(eq_id),
                label=label,
                kind=spec.kind,
                available=d.get("isAvailable") if isinstance(d.get("isAvailable"), bool) else None,
                provider_ref={
                    "device_id": d["deviceId"],
                    "model_id": d.get("modelId"),
                    "product_id": d.get("productId"),
                    "slot": d.get("customName"),
                    "zone_id": d.get("zoneId"),
                },
            )
            caps = {c["capabilityId"]: c for c in d.get("capabilities") or [] if isinstance(c.get("capabilityId"), int)}
            out.append(ResolvedEquipment(equipment, spec, caps))
    return out


def parse_value(raw: Any, info: CapabilityInfo | None, unit: str | None) -> MeasurementValue | None:
    """Valeur texte Magellan -> ``MeasurementValue`` ; ``None`` si inexploitable."""
    if raw is None:
        return MeasurementValue.absent()
    kind = info.type if info else None
    text = str(raw).strip()
    try:
        if kind == CAT_STRING:
            return MeasurementValue.of_text(text, unit)
        if kind == CAT_JSON:
            return MeasurementValue.of_json(json.loads(text) if isinstance(raw, str) else raw)
        if kind == CAT_BOOL:
            if text.lower() in ("1", "true"):
                return MeasurementValue.of_bool(True)
            if text.lower() in ("0", "false"):
                return MeasurementValue.of_bool(False)
            return None
        number = float(text)
        if kind in (CAT_INT, CAT_ENUM) and number.is_integer():
            return MeasurementValue(ValueType.INTEGER, number=number, unit=unit)
        return MeasurementValue(ValueType.FLOAT, number=number, unit=unit)
    except (ValueError, TypeError):
        return None


def measurements_of(resolved: ResolvedEquipment, catalogue: Catalogue, polled_at: Instant) -> list[Measurement]:
    out = []
    for metric in resolved.spec.metrics:
        cap = resolved.capabilities.get(metric.capability)
        if cap is None:
            continue
        info = catalogue.get(metric.capability)
        unit = metric.unit or (info.unit if info else None)
        value = parse_value(cap.get("value"), info, unit)
        if value is None:
            log.warning("Valeur inattendue ignorée pour %s/%s", resolved.equipment.id, metric.key)
            continue
        stamp = cap.get("modificationDate")
        stamped = isinstance(stamp, int) and 0 < stamp <= polled_at.epoch + 300
        out.append(
            Measurement(
                equipment_id=resolved.equipment.id,
                metric_key=metric.key,
                instant=Instant(stamp) if stamped else polled_at,
                value=value,
                source=str(metric.capability),
                polled_at=polled_at,
                provider_timestamped=stamped,
            )
        )
    return out


def energy_days_of(series: Iterable[Mapping[str, Any]]) -> list[EnergyDay]:
    """Séries ``consumptions?periodicity=daily`` -> ``EnergyDay`` (électricité, kWh).

    Les séries d'un autre type (eau, gaz) sont ignorées. ``date`` est un minuit UTC.
    Plusieurs périodes de même clé sont additionnées.
    """
    totals: dict[tuple, list[float | None]] = {}
    for s in series:
        if s.get("type") != 1 or s.get("unit") != 1 or not isinstance(s.get("category"), int):
            continue
        for p in s.get("consumptionPeriods") or []:
            try:
                day = datetime.fromtimestamp(int(p["date"]), UTC).date()
                kwh = float(p["consumedQuantity"])
            except (KeyError, TypeError, ValueError):
                continue
            if kwh < 0:
                continue
            key = (day, s["category"], _TARIFFS.get(p.get("mode"), Tariff.UNKNOWN))
            acc = totals.setdefault(key, [0.0, None])
            acc[0] += kwh
            if isinstance(p.get("cost"), int | float):
                acc[1] = (acc[1] or 0.0) + float(p["cost"])
    return [
        EnergyDay(day, cat, tariff, round(kwh, 6), None if cost is None else round(cost, 6))
        for (day, cat, tariff), (kwh, cost) in sorted(totals.items())
    ]
