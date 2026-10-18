"""Boucle de collecte : poll immédiat, jitter, backoff selon le type d'erreur.

- Une exception ne tue jamais la boucle en silence : try/except global, et la
  tâche garde un ``add_done_callback`` qui journalise une sortie anormale.
- ``CredentialsRejected`` arrête net la collecte (risque de bannissement).
- Tâches quotidiennes (catch-up, sauvegarde, purge) : au démarrage puis une fois
  par jour civil (Europe/Paris), et catch-up après chaque récupération de panne.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime

from app.application.usecases.backup import RunBackup
from app.application.usecases.catch_up import CatchUp
from app.application.usecases.collect import CollectSamples
from app.application.usecases.purge import PurgeRaw
from app.domain.errors import CredentialsRejected, ProviderThrottled, ProviderUnavailable
from app.domain.services import PARIS

log = logging.getLogger(__name__)

MAX_BACKOFF = 3600
JITTER = 0.1


def next_delay(interval: int, failures: int, error: BaseException | None) -> float:
    """Délai avant le prochain poll (sans jitter).

    Succès : l'intervalle. 429 : ``Retry-After`` (au moins l'intervalle).
    Panne fournisseur ou erreur inattendue : backoff exponentiel plafonné à 1 h.
    """
    if error is None:
        return interval
    if isinstance(error, ProviderThrottled):
        return max(error.retry_after or 0, interval)
    return min(interval * 2 ** max(failures - 1, 0), MAX_BACKOFF)


@dataclass(slots=True)
class SchedulerState:
    running: bool = False
    stopped_reason: str | None = None
    consecutive_failures: int = 0
    next_delay_seconds: float | None = None


class Scheduler:
    def __init__(
        self,
        *,
        collect: CollectSamples,
        catch_up: CatchUp,
        backup: RunBackup,
        purge: PurgeRaw,
        interval: int,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rand: Callable[[], float] = random.random,
        today: Callable[[], date] = lambda: datetime.now(PARIS).date(),
    ) -> None:
        self._collect = collect
        self._catch_up = catch_up
        self._backup = backup
        self._purge = purge
        self._interval = interval
        self._sleep = sleep
        self._rand = rand
        self._today = today
        self._last_daily: date | None = None
        self._task: asyncio.Task[None] | None = None
        self.state = SchedulerState()

    def start(self) -> asyncio.Task[None]:
        if self._task is not None and not self._task.done():
            return self._task
        self._task = asyncio.create_task(self._run(), name="collect-loop")
        self._task.add_done_callback(self._on_done)
        return self._task

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    def _on_done(self, task: asyncio.Task[None]) -> None:
        self.state.running = False
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            self.state.stopped_reason = f"crash: {type(exc).__name__}"
            log.error("La boucle de collecte s'est arrêtée", exc_info=exc)

    async def _run(self) -> None:
        self.state.running = True
        while True:
            error: BaseException | None = None
            try:
                result = await self._collect.run()
                daily = self._last_daily != self._today()
                if result.recovered_after_failure or daily:
                    await self._guarded("catch-up", self._catch_up.run())
                if daily:
                    self._last_daily = self._today()
                    await self._guarded("sauvegarde", self._backup.run())
                    await self._guarded("purge", self._purge.run())
            except CredentialsRejected:
                log.error("Identifiants Cozytouch refusés : collecte arrêtée, aucune nouvelle tentative")
                self.state.stopped_reason = "credentials"
                self.state.running = False
                return
            except ProviderThrottled as exc:
                error = exc
                log.warning("Limité par le fournisseur (retry_after=%s)", exc.retry_after)
            except ProviderUnavailable as exc:
                error = exc
                log.warning("Fournisseur indisponible : %s", exc)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                error = exc
                log.exception("Erreur inattendue pendant la collecte")

            self.state.consecutive_failures = 0 if error is None else self.state.consecutive_failures + 1
            delay = next_delay(self._interval, self.state.consecutive_failures, error)
            delay *= 1 + JITTER * (2 * self._rand() - 1)
            self.state.next_delay_seconds = delay
            await self._sleep(delay)

    async def _guarded(self, name: str, job: Awaitable[object]) -> None:
        """Une tâche annexe en échec est journalisée sans interrompre la collecte."""
        try:
            result = await job
            log.info("%s : %s", name, result)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("%s en échec", name)
