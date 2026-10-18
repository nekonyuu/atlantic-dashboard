"""Implémentations Magellan des ports ``EquipmentGateway`` et ``HistorySource``."""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any, Protocol

from app.adapters.outbound.magellan.client import MagellanClient
from app.adapters.outbound.magellan.mapping import (
    Catalogue,
    ResolvedEquipment,
    Semantics,
    energy_days_of,
    measurements_of,
    resolve_equipment,
)
from app.application.ports import Clock, HistoryCapabilities
from app.domain.errors import ProviderError
from app.domain.model import Equipment
from app.domain.values import EnergyDay, EquipmentId, Instant, Measurement

log = logging.getLogger(__name__)

CATALOGUE_MAX_AGE = 86400
SNAPSHOT_REUSE_SECONDS = 30
HISTORY_DAYS = 32


class CatalogueStore(Protocol):
    """Cache persistant du catalogue (implémenté par l'adaptateur SQLite)."""

    async def load(self) -> list[dict[str, Any]] | None: ...

    async def save(self, entries: list[dict[str, Any]], fetched_at: int) -> None: ...


class MagellanGateway:
    """Une seule lecture ``setupviewv2`` par cycle de collecte.

    ``list_equipment``, ``read_measurements`` et ``availability`` réutilisent la
    même lecture tant qu'elle a moins de ``SNAPSHOT_REUSE_SECONDS``.
    """

    def __init__(
        self,
        client: MagellanClient,
        semantics: Semantics,
        clock: Clock,
        catalogue_store: CatalogueStore | None = None,
        *,
        monotonic=time.monotonic,
    ) -> None:
        self._client = client
        self._semantics = semantics
        self._clock = clock
        self._store = catalogue_store
        self._monotonic = monotonic
        self._catalogue: Catalogue | None = None
        self._catalogue_at = 0
        self._snapshot: tuple[float, Instant, list[ResolvedEquipment]] | None = None
        self.setup_id: int | str | None = None

    async def list_equipment(self) -> list[Equipment]:
        _, _, resolved = await self._read()
        return [r.equipment for r in resolved]

    async def read_measurements(self, equipment_ids: list[EquipmentId] | None = None) -> list[Measurement]:
        _, polled_at, resolved = await self._read()
        catalogue = await self._ensure_catalogue()
        wanted = set(equipment_ids) if equipment_ids is not None else None
        return [
            m
            for r in resolved
            if wanted is None or r.equipment.id in wanted
            for m in measurements_of(r, catalogue, polled_at)
        ]

    async def availability(self) -> dict[EquipmentId, bool]:
        _, _, resolved = await self._read()
        return {r.equipment.id: r.equipment.available for r in resolved if r.equipment.available is not None}

    async def _read(self) -> tuple[float, Instant, list[ResolvedEquipment]]:
        now = self._monotonic()
        if self._snapshot is not None and now - self._snapshot[0] < SNAPSHOT_REUSE_SECONDS:
            return self._snapshot
        setup = await self._client.setup_view()
        self.setup_id = setup.get("id")
        self._snapshot = (now, self._clock.now(), resolve_equipment(setup["devices"], self._semantics))
        return self._snapshot

    async def _ensure_catalogue(self) -> Catalogue:
        now = self._clock.now().epoch
        if self._catalogue is None and self._store is not None:
            cached = await self._store.load()
            if cached:
                self._catalogue, self._catalogue_at = Catalogue(cached), now
        if self._catalogue is None or now - self._catalogue_at >= CATALOGUE_MAX_AGE:
            try:
                entries = await self._client.capability_catalogue()
                self._catalogue, self._catalogue_at = Catalogue(entries), now
                if self._store is not None:
                    await self._store.save(entries, now)
            except ProviderError:
                if self._catalogue is None:
                    raise
                log.warning("Catalogue non rafraîchi ; version en cache conservée")
                self._catalogue_at = now
        return self._catalogue


class MagellanHistorySource:
    """Catch-up niveau C : consommations électriques journalières (~32 jours glissants)."""

    def __init__(self, client: MagellanClient, gateway: MagellanGateway) -> None:
        self._client = client
        self._gateway = gateway

    def capabilities(self) -> HistoryCapabilities:
        return HistoryCapabilities(energy_daily=True, max_days=HISTORY_DAYS)

    async def fetch_energy_days(self, since: date, until: date) -> list[EnergyDay]:
        if self._gateway.setup_id is None:
            await self._gateway.list_equipment()
        series = await self._client.daily_consumptions(self._gateway.setup_id)
        return [d for d in energy_days_of(series) if since <= d.day <= until]
