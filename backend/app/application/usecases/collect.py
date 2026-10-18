"""Cas d'usage : un cycle de collecte."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from app.application.events import Publisher, discard
from app.application.ports import (
    Clock,
    EquipmentGateway,
    EquipmentRepository,
    GapRepository,
    MeasurementRepository,
    PollLogRepository,
)
from app.domain import events
from app.domain.errors import CredentialsRejected, ProviderError
from app.domain.model import Gap, Installation
from app.domain.services import ChangeDetector, GapDetector
from app.domain.values import ErrorKind, Instant, PollOutcome


@dataclass(frozen=True, slots=True)
class CollectResult:
    outcome: PollOutcome
    gap: Gap | None
    recovered_after_failure: bool


class CollectSamples:
    """Lit le fournisseur, enregistre les mesures nouvelles, journalise le cycle.

    Catch-up niveau A : au premier succès après une interruption (redémarrage ou
    pannes), le trou depuis le dernier succès est enregistré avec sa cause.
    Les erreurs fournisseur sont journalisées puis relancées : la politique de
    retry appartient au scheduler.
    """

    def __init__(
        self,
        *,
        gateway: EquipmentGateway,
        equipment: EquipmentRepository,
        measurements: MeasurementRepository,
        poll_log: PollLogRepository,
        gaps: GapRepository,
        clock: Clock,
        gap_detector: GapDetector,
        writer_lock: asyncio.Lock,
        publish: Publisher = discard,
    ) -> None:
        self._gateway = gateway
        self._equipment = equipment
        self._measurements = measurements
        self._poll_log = poll_log
        self._gaps = gaps
        self._clock = clock
        self._gap_detector = gap_detector
        self._lock = writer_lock
        self._publish = publish
        self._detector = ChangeDetector()
        self._installation = Installation()
        self._primed = False

    async def _prime(self) -> None:
        self._detector = ChangeDetector()
        self._detector.load(await self._measurements.latest())
        self._installation = Installation()
        for e in await self._equipment.all():
            self._installation.equipment[e.id] = e
        self._primed = True

    async def run(self) -> CollectResult:
        if not self._primed:
            await self._prime()
        now = self._clock.now()
        started = time.monotonic()
        try:
            observed = await self._gateway.list_equipment()
            readings = await self._gateway.read_measurements()
            availability = await self._gateway.availability()
        except ProviderError as exc:
            await self._fail(now, started, exc.kind, exc)
            raise
        except Exception as exc:
            await self._fail(now, started, ErrorKind.UNEXPECTED, exc)
            raise

        async with self._lock:
            try:
                for e in observed:
                    e.available = availability.get(e.id, e.available)
                await self._equipment.upsert([self._installation.observe(e, now) for e in observed])
                kept = self._detector.filter(readings)
                recorded = await self._measurements.append(kept)
            except Exception:
                self._primed = False  # le cache peut diverger de la base : recharger
                raise

            previous = await self._poll_log.last_success()
            failures = [o for o in await self._poll_log.since(previous.at) if not o.ok] if previous else []
            gap = self._gap_detector.between(previous.at, now, failures) if previous else None
            if gap is not None:
                gap = await self._gaps.add(gap)
            outcome = PollOutcome.success(now, _elapsed_ms(started), recorded)
            await self._poll_log.add(outcome)

        for m in kept:
            self._publish(events.MeasurementRecorded(m))
        if gap is not None:
            self._publish(events.GapDetected(gap))
        return CollectResult(outcome, gap, recovered_after_failure=bool(failures) or gap is not None)

    async def _fail(self, now: Instant, started: float, kind: ErrorKind, exc: Exception) -> None:
        outcome = PollOutcome.failure(now, _elapsed_ms(started), kind, _describe(exc))
        async with self._lock:
            await self._poll_log.add(outcome)
        self._publish(events.PollFailed(now, kind, outcome.error or ""))
        if isinstance(exc, CredentialsRejected):
            self._publish(events.CredentialsRejected(now))


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _describe(exc: Exception) -> str:
    """Type et message, tronqués : les adaptateurs ne mettent aucun secret dans leurs messages."""
    return f"{type(exc).__name__}: {exc}"[:500]
