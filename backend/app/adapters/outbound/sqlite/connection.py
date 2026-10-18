"""Connexions SQLite : un writer, un reader, migrations par ``PRAGMA user_version``."""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_SCRIPT_RE = re.compile(r"^(\d{4})_.+\.sql$")


def _connect(path: Path) -> aiosqlite.Connection:
    # Mode autocommit : les transactions sont explicites (voir Database.transaction).
    return aiosqlite.connect(path, isolation_level=None)


async def _configure(conn: aiosqlite.Connection) -> None:
    await conn.execute("PRAGMA foreign_keys=ON")
    await conn.execute("PRAGMA busy_timeout=5000")
    await conn.execute("PRAGMA synchronous=NORMAL")


def _scripts() -> list[tuple[int, Path]]:
    found = [(int(m.group(1)), p) for p in MIGRATIONS_DIR.iterdir() if (m := _SCRIPT_RE.match(p.name))]
    return sorted(found)


async def migrate(conn: aiosqlite.Connection) -> None:
    """Applique les scripts de numéro > ``user_version``, chacun dans une transaction. Idempotent."""
    async with conn.execute("PRAGMA user_version") as cur:
        row = await cur.fetchone()
    current = row[0] if row else 0
    for number, path in _scripts():
        if number <= current:
            continue
        script = path.read_text(encoding="utf-8")
        try:
            await conn.executescript(f"BEGIN;\n{script}\nPRAGMA user_version={number};\nCOMMIT;")
        except Exception:
            if conn.in_transaction:
                await conn.rollback()
            raise


class Database:
    """Une connexion d'écriture (sérialisée par un verrou) et une connexion de lecture distincte."""

    def __init__(self, writer: aiosqlite.Connection, reader: aiosqlite.Connection) -> None:
        self.writer = writer
        self.reader = reader
        self._lock = asyncio.Lock()

    @classmethod
    async def open(cls, path: str | Path) -> Database:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        is_new = not path.exists()
        writer = await _connect(path)
        try:
            await _configure(writer)
            if is_new:
                # Doit précéder toute création de table pour être pris en compte.
                await writer.execute("PRAGMA auto_vacuum=INCREMENTAL")
            await writer.execute("PRAGMA journal_mode=WAL")
            await migrate(writer)
            reader = await _connect(path)
        except Exception:
            await writer.close()
            raise
        await _configure(reader)
        return cls(writer, reader)

    @asynccontextmanager
    async def exclusive(self) -> AsyncIterator[aiosqlite.Connection]:
        """Accès exclusif au writer, sans transaction (pour VACUUM INTO)."""
        async with self._lock:
            yield self.writer

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[aiosqlite.Connection]:
        """Transaction d'écriture exclusive : commit en sortie, rollback sur exception."""
        async with self._lock:
            conn = self.writer
            await conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                await conn.rollback()
                raise
            await conn.commit()

    async def close(self) -> None:
        await self.reader.close()
        await self.writer.close()
