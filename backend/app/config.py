"""Configuration par variables d'environnement (PLAN.md §6)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

MIN_POLL_INTERVAL = 60


class ConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Settings:
    username: str = field(repr=False)
    password: str = field(repr=False)
    poll_interval: int = 300
    db_path: Path = Path("/data/pac.db")
    backup_dir: Path = Path("/data/backup")
    backup_keep: int = 14
    retention_days_raw: int = 0
    static_dir: Path = Path("/app/static")
    log_level: str = "INFO"

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> Settings:
        username = env.get("COZYTOUCH_USERNAME", "").strip()
        password = env.get("COZYTOUCH_PASSWORD", "")
        if not username or not password:
            raise ConfigError("COZYTOUCH_USERNAME et COZYTOUCH_PASSWORD sont requis")
        poll = _int(env, "POLL_INTERVAL_SECONDS", 300)
        if poll < MIN_POLL_INTERVAL:
            raise ConfigError(f"POLL_INTERVAL_SECONDS doit valoir au moins {MIN_POLL_INTERVAL}")
        keep = _int(env, "BACKUP_KEEP", 14)
        retention = _int(env, "RETENTION_DAYS_RAW", 0)
        if keep < 1 or retention < 0:
            raise ConfigError("BACKUP_KEEP >= 1 et RETENTION_DAYS_RAW >= 0 attendus")
        level = env.get("LOG_LEVEL", "INFO").upper()
        if level not in ("DEBUG", "INFO", "WARNING", "ERROR"):
            raise ConfigError("LOG_LEVEL invalide")
        return cls(
            username=username,
            password=password,
            poll_interval=poll,
            db_path=Path(env.get("DB_PATH", "/data/pac.db")),
            backup_dir=Path(env.get("BACKUP_DIR", "/data/backup")),
            backup_keep=keep,
            retention_days_raw=retention,
            static_dir=Path(env.get("STATIC_DIR", "/app/static")),
            log_level=level,
        )


def _int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        raise ConfigError(f"{name} doit être un entier") from None
