"""Composition root (PLAN.md §3.6) : seul endroit qui assemble adaptateurs et cas d'usage."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import aiohttp
from fastapi import FastAPI

from app.adapters.inbound.http import HttpApi, mount_spa, router
from app.adapters.inbound.scheduler import Scheduler
from app.adapters.outbound.magellan.client import MagellanClient
from app.adapters.outbound.magellan.gateway import MagellanGateway, MagellanHistorySource
from app.adapters.outbound.magellan.mapping import Semantics
from app.adapters.outbound.sqlite import (
    Database,
    SqliteBackupService,
    SqliteCatalogueStore,
    SqliteEnergyRepository,
    SqliteEquipmentRepository,
    SqliteGapRepository,
    SqliteMeasurementRepository,
    SqlitePollLogRepository,
    SqliteStorageStats,
    StorageNotWritable,
)
from app.adapters.outbound.system import SystemClock
from app.application.usecases.backup import RunBackup
from app.application.usecases.catch_up import CatchUp
from app.application.usecases.collect import CollectSamples
from app.application.usecases.purge import PurgeRaw
from app.application.usecases.queries import (
    GetEnergy,
    GetEquipment,
    GetGaps,
    GetHealth,
    GetLatest,
    GetMetrics,
    GetSeries,
)
from app.config import ConfigError, Settings
from app.domain import events
from app.domain.services import GapDetector

log = logging.getLogger("app")


def log_event(event: events.DomainEvent) -> None:
    """Événements de domaine -> logs (uniquement des identifiants sûrs)."""
    match event:
        case events.GapDetected(gap):
            log.warning("Trou de collecte : %s s (%s)", gap.duration, gap.cause)
        case events.PollFailed(_, kind, _):
            log.warning("Échec de collecte (%s)", kind)
        case events.CredentialsRejected():
            log.error("Identifiants refusés par le fournisseur")
        case events.MeasurementRecorded(m):
            log.debug("Mesure %s/%s", m.equipment_id, m.metric_key)


@dataclass
class Container:
    settings: Settings
    db: Database
    session: aiohttp.ClientSession
    gateway: MagellanGateway
    collect: CollectSamples
    catch_up: CatchUp
    backup: RunBackup
    purge: PurgeRaw
    get_equipment: GetEquipment
    get_latest: GetLatest
    get_series: GetSeries
    get_gaps: GetGaps
    get_energy: GetEnergy
    get_health: GetHealth
    get_metrics: GetMetrics
    clock: SystemClock
    scheduler: Scheduler
    semantics: Semantics

    async def close(self) -> None:
        await self.scheduler.stop()
        await self.session.close()
        await self.db.close()


async def build(settings: Settings) -> Container:
    """Construit tout ; à appeler dans une boucle asyncio (jamais à l'import)."""
    db = await Database.open(settings.db_path)
    session = aiohttp.ClientSession()
    clock = SystemClock()
    lock = asyncio.Lock()
    semantics = Semantics.load()
    cumulative = semantics.cumulative_metrics()
    gap_detector = GapDetector(settings.poll_interval)

    equipment = SqliteEquipmentRepository(db)
    measurements = SqliteMeasurementRepository(db)
    gaps = SqliteGapRepository(db)
    poll_log = SqlitePollLogRepository(db)
    energy = SqliteEnergyRepository(db)

    client = MagellanClient(session, settings.username, settings.password)
    gateway = MagellanGateway(client, semantics, clock, SqliteCatalogueStore(db))
    history = MagellanHistorySource(client, gateway)

    collect = CollectSamples(
        gateway=gateway,
        equipment=equipment,
        measurements=measurements,
        poll_log=poll_log,
        gaps=gaps,
        clock=clock,
        gap_detector=gap_detector,
        writer_lock=lock,
        publish=log_event,
    )
    catch_up = CatchUp(history=history, energy=energy, gaps=gaps, clock=clock, writer_lock=lock)
    backup = RunBackup(SqliteBackupService(db, settings.backup_dir, settings.backup_keep), clock, lock)
    purge = PurgeRaw(
        measurements=measurements,
        gaps=gaps,
        clock=clock,
        writer_lock=lock,
        retention_days=settings.retention_days_raw,
        cumulative_metrics=cumulative,
    )
    scheduler = Scheduler(
        collect=collect, catch_up=catch_up, backup=backup, purge=purge, interval=settings.poll_interval
    )
    return Container(
        settings=settings,
        db=db,
        session=session,
        gateway=gateway,
        collect=collect,
        catch_up=catch_up,
        backup=backup,
        purge=purge,
        scheduler=scheduler,
        semantics=semantics,
        get_equipment=GetEquipment(equipment),
        get_latest=GetLatest(measurements, clock),
        get_series=GetSeries(
            measurements=measurements,
            gaps=gaps,
            poll_log=poll_log,
            clock=clock,
            gap_detector=gap_detector,
            cumulative_metrics=cumulative,
        ),
        get_gaps=GetGaps(gaps, poll_log, clock, gap_detector),
        get_energy=GetEnergy(energy),
        get_metrics=GetMetrics(gateway),
        clock=clock,
        get_health=GetHealth(
            poll_log=poll_log,
            gaps=gaps,
            equipment=equipment,
            storage=SqliteStorageStats(settings.db_path),
            clock=clock,
            gap_detector=gap_detector,
            poll_interval=settings.poll_interval,
        ),
    )


def configure_logging(level: str) -> None:
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # aiohttp journalise des URL qui peuvent contenir un identifiant de setup
    logging.getLogger("aiohttp").setLevel(max(logging.getLevelName(level), logging.WARNING))


def create_app(settings: Settings | None = None, *, start_scheduler: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            resolved = settings or Settings.from_env()
        except ConfigError as exc:
            configure_logging("INFO")
            log.error("Configuration invalide : %s", exc)
            raise
        configure_logging(resolved.log_level)
        try:
            container = await build(resolved)
        except StorageNotWritable as exc:
            log.error("Stockage inaccessible : %s", exc)
            raise
        app.state.container = container
        app.state.api = HttpApi(
            get_health=container.get_health,
            get_equipment=container.get_equipment,
            get_latest=container.get_latest,
            get_series=container.get_series,
            get_gaps=container.get_gaps,
            get_energy=container.get_energy,
            get_metrics=container.get_metrics,
            scheduler_state=lambda: container.scheduler.state,
            clock=container.clock,
        )
        if start_scheduler:
            container.scheduler.start()
        log.info("Démarrage : poll toutes les %d s", resolved.poll_interval)
        try:
            yield
        finally:
            await container.close()
            log.info("Arrêt propre")

    app = FastAPI(title="PAC dashboard", lifespan=lifespan)
    app.include_router(router)
    static_dir = settings.static_dir if settings else Path(os.environ.get("STATIC_DIR", "/app/static"))
    mount_spa(app, static_dir)
    return app


app = create_app()
