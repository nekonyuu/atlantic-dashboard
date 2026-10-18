"""CLI d'exploitation : ``python -m app.adapters.inbound.cli {catch-up,discover,backup}``."""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date

from app.config import ConfigError, Settings
from app.domain.errors import CredentialsRejected, ProviderError
from app.domain.values import MeasurementValue
from app.main import build, configure_logging

EXIT_CONFIG = 2
EXIT_CREDENTIALS = 3
EXIT_PROVIDER = 4


def _iso_date(raw: str) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise argparse.ArgumentTypeError(f"date invalide : {raw!r} (attendu YYYY-MM-DD)") from None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.adapters.inbound.cli", description="CLI PAC dashboard")
    sub = parser.add_subparsers(dest="command", required=True)
    catch = sub.add_parser("catch-up", help="rattrape l'historique fournisseur")
    catch.add_argument("--since", type=_iso_date, default=None, metavar="YYYY-MM-DD")
    sub.add_parser("discover", help="lance un cycle de collecte et affiche l'installation")
    sub.add_parser("backup", help="sauvegarde immédiate de la base (VACUUM INTO, sans appel fournisseur)")
    return parser


def _format_value(value: MeasurementValue) -> str:
    if value.text is not None:
        return value.text
    if value.number is None:
        return "-"
    return f"{value.number:g}"


async def _discover(container) -> None:
    await container.collect.run()
    for eq in await container.get_equipment.run():
        print(f"{eq.id} {eq.label} {eq.kind} available={eq.available}")
    for latest in await container.get_latest.run():
        m = latest.measurement
        print(f"{m.equipment_id} {m.metric_key} {_format_value(m.value)} {m.value.unit or '-'} {latest.age_seconds}s")


async def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        print(f"Configuration invalide : {exc}", file=sys.stderr)
        return EXIT_CONFIG
    configure_logging(settings.log_level)
    try:
        container = await build(settings)
    except ConfigError as exc:
        print(f"Configuration invalide : {exc}", file=sys.stderr)
        return EXIT_CONFIG
    try:
        if args.command == "catch-up":
            print(await container.catch_up.run(args.since))
        elif args.command == "backup":
            print(f"Sauvegarde : {settings.backup_dir / await container.backup.run()}")
        else:
            await _discover(container)
    except CredentialsRejected as exc:
        print(f"Identifiants refusés : {exc}", file=sys.stderr)
        return EXIT_CREDENTIALS
    except ProviderError as exc:
        print(f"Erreur fournisseur ({exc.kind}) : {exc}", file=sys.stderr)
        return EXIT_PROVIDER
    finally:
        await container.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
