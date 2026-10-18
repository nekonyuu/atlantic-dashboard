"""CLI : parsing, codes de sortie et sorties, sans réseau (le conteneur est remplacé)."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from app.adapters.inbound import cli
from app.application.usecases.catch_up import CatchUpReport
from app.application.usecases.queries import LatestValue
from app.domain.errors import CredentialsRejected, ProviderUnavailable
from app.domain.model import Equipment
from tests.builders import DHW, m

ENV = {"COZYTOUCH_USERNAME": "user@example.invalid", "COZYTOUCH_PASSWORD": "not-a-secret"}


def test_parser_accepts_valid_date():
    args = cli.build_parser().parse_args(["catch-up", "--since", "2026-01-31"])
    assert args.since == date(2026, 1, 31)


def test_parser_since_optional():
    assert cli.build_parser().parse_args(["catch-up"]).since is None


@pytest.mark.parametrize("argv", [["catch-up", "--since", "31/01/2026"], ["catch-up", "--since", "2026-13-01"], []])
def test_parser_rejects_invalid(argv, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.build_parser().parse_args(argv)
    assert exc.value.code == 2


async def test_missing_env_returns_2(monkeypatch, capsys):
    monkeypatch.delenv("COZYTOUCH_USERNAME", raising=False)
    monkeypatch.delenv("COZYTOUCH_PASSWORD", raising=False)
    assert await cli.main(["discover"]) == 2
    assert "requis" in capsys.readouterr().err


class FakeContainer:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.closed = False
        self.since: object = "unset"
        self.collected = 0
        self.catch_up = SimpleNamespace(run=self._catch_up)
        self.collect = SimpleNamespace(run=self._collect)
        self.get_equipment = SimpleNamespace(run=self._equipment)
        self.get_latest = SimpleNamespace(run=self._latest)
        self.backup = SimpleNamespace(run=self._backup)

    async def _backup(self):
        return "pac-2026-10-18.db"

    async def _catch_up(self, since=None):
        if self.error:
            raise self.error
        self.since = since
        return CatchUpReport(energy_days=3, source_available=True)

    async def _collect(self):
        if self.error:
            raise self.error
        self.collected += 1

    async def _equipment(self):
        return [Equipment(id=DHW, label="Ballon", kind="dhw", available=True)]

    async def _latest(self):
        return [LatestValue(measurement=m(1000, 52.5), age_seconds=42)]

    async def close(self):
        self.closed = True


def _patch(monkeypatch, container: FakeContainer) -> None:
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)

    async def fake_build(settings):
        return container

    monkeypatch.setattr(cli, "build", fake_build)


async def test_catch_up_prints_report(monkeypatch, capsys):
    c = FakeContainer()
    _patch(monkeypatch, c)
    assert await cli.main(["catch-up", "--since", "2026-02-01"]) == 0
    assert c.since == date(2026, 2, 1)
    assert "energy_days=3" in capsys.readouterr().out
    assert c.closed


async def test_discover_prints_equipment_and_values(monkeypatch, capsys):
    c = FakeContainer()
    _patch(monkeypatch, c)
    assert await cli.main(["discover"]) == 0
    out = capsys.readouterr().out
    assert c.collected == 1
    assert "Ballon dhw available=True" in out
    assert "dhw_temperature 52.5 - 42s" in out


@pytest.mark.parametrize(
    ("error", "code"),
    [(CredentialsRejected("non"), 3), (ProviderUnavailable("panne"), 4)],
)
async def test_provider_errors_exit_codes(monkeypatch, capsys, error, code):
    c = FakeContainer(error)
    _patch(monkeypatch, c)
    assert await cli.main(["catch-up"]) == code
    assert c.closed
    assert capsys.readouterr().err


async def test_backup_prints_file_and_never_collects(monkeypatch, capsys):
    container = FakeContainer()
    _patch(monkeypatch, container)
    assert await cli.main(["backup"]) == 0
    assert "pac-2026-10-18.db" in capsys.readouterr().out
    assert container.collected == 0 and container.closed
