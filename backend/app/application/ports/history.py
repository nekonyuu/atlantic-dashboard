"""Port sortant optionnel : historique fourni par le fournisseur (catch-up niveau C)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from app.domain.values import EnergyDay


@dataclass(frozen=True, slots=True)
class HistoryCapabilities:
    energy_daily: bool = False
    max_days: int = 0


class HistorySource(Protocol):
    def capabilities(self) -> HistoryCapabilities: ...

    async def fetch_energy_days(self, since: date, until: date) -> list[EnergyDay]:
        """Jours ``[since, until]`` disponibles (le fournisseur peut en renvoyer moins)."""
        ...
