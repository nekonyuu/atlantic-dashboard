"""Port sortant : description des métriques (libellés, unités, enums) pour l'affichage."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

from app.domain.values import EquipmentId, MetricKey


@dataclass(frozen=True, slots=True)
class MetricInfo:
    equipment_id: EquipmentId
    metric_key: MetricKey
    label: str
    unit: str | None = None
    cumulative: bool = False
    enum: Mapping[int, str] = field(default_factory=dict)


class MetricCatalog(Protocol):
    async def describe(self) -> list[MetricInfo]:
        """Métriques connues ; ne doit jamais solliciter le fournisseur (lecture API)."""
        ...
