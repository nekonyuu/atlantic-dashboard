"""Port sortant vers le fournisseur de télémétrie."""

from __future__ import annotations

from typing import Protocol

from app.domain.model import Equipment
from app.domain.values import EquipmentId, Measurement


class EquipmentGateway(Protocol):
    """Lecture de l'installation chez le fournisseur.

    Lève uniquement des ``app.domain.errors.ProviderError``.
    """

    async def list_equipment(self) -> list[Equipment]: ...

    async def read_measurements(self, equipment_ids: list[EquipmentId] | None = None) -> list[Measurement]:
        """Dernières valeurs connues ; ``None`` = tous les équipements."""
        ...

    async def availability(self) -> dict[EquipmentId, bool]:
        """Disponibilité vue lors de la dernière lecture."""
        ...
