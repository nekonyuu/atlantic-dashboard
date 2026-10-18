"""Entités et agrégat racine."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from app.domain.values import EquipmentId, Instant


@dataclass(slots=True)
class Equipment:
    """Un appareil de l'installation ; porte sa dernière disponibilité connue.

    ``provider_ref`` : identifiants fournisseur opaques (stockés, jamais loggés
    ni exposés par l'API) ; le domaine ne les interprète pas.
    """

    id: EquipmentId
    label: str
    kind: str
    available: bool | None = None
    first_seen: Instant | None = None
    last_seen: Instant | None = None
    provider_ref: Mapping[str, int | str | None] = field(default_factory=dict, repr=False)

    def seen(self, at: Instant, available: bool | None) -> None:
        if self.first_seen is None:
            self.first_seen = at
        self.last_seen = at
        self.available = available


@dataclass(slots=True)
class Installation:
    """Agrégat racine : l'ensemble PAC + ballon et ses équipements."""

    equipment: dict[EquipmentId, Equipment] = field(default_factory=dict)

    def observe(self, observed: Equipment, at: Instant) -> Equipment:
        """Intègre un équipement lu chez le fournisseur et renvoie l'entité à jour."""
        current = self.equipment.get(observed.id)
        if current is None:
            current = Equipment(id=observed.id, label=observed.label, kind=observed.kind)
            self.equipment[observed.id] = current
        current.label = observed.label
        current.kind = observed.kind
        current.provider_ref = dict(observed.provider_ref)
        current.seen(at, observed.available)
        return current

    def unavailable(self) -> list[EquipmentId]:
        return sorted(e.id for e in self.equipment.values() if e.available is False)


class GapCause(StrEnum):
    DOWNTIME = "downtime"
    PROVIDER_ERROR = "provider_error"
    CREDENTIALS = "credentials"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class Gap:
    """Intervalle ``[start, end)`` sans collecte réussie.

    ``recovered`` : l'énergie de la période a été rattrapée depuis l'historique
    fournisseur (les autres mesures ne le sont jamais).
    """

    start: Instant
    end: Instant
    cause: GapCause
    recovered: bool = False
    id: int | None = None

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError("un trou doit avoir une durée positive")

    @property
    def duration(self) -> int:
        return self.end - self.start

    def overlaps(self, start: Instant, end: Instant) -> bool:
        return self.start < end and start < self.end
