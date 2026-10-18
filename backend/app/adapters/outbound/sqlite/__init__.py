"""Adaptateur de persistance SQLite (aiosqlite)."""

from app.adapters.outbound.sqlite.connection import Database, migrate
from app.adapters.outbound.sqlite.repositories import (
    SqliteCatalogueStore,
    SqliteEnergyRepository,
    SqliteEquipmentRepository,
    SqliteGapRepository,
    SqliteMeasurementRepository,
    SqlitePollLogRepository,
)
from app.adapters.outbound.sqlite.system import SqliteBackupService, SqliteStorageStats

__all__ = [
    "Database",
    "SqliteBackupService",
    "SqliteCatalogueStore",
    "SqliteEnergyRepository",
    "SqliteEquipmentRepository",
    "SqliteGapRepository",
    "SqliteMeasurementRepository",
    "SqlitePollLogRepository",
    "SqliteStorageStats",
    "migrate",
]
