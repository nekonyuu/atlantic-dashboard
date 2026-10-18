"""Accès à la fixture anonymisée de la phase 0 (``fixtures/magellan_anonymized.json``)."""

from __future__ import annotations

import copy
import json
from functools import cache
from pathlib import Path
from typing import Any

FIXTURE = Path(__file__).with_name("fixtures") / "magellan_anonymized.json"


@cache
def _load() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def fixture() -> dict[str, Any]:
    return copy.deepcopy(_load())


def setup_view() -> dict[str, Any]:
    return fixture()["setupview_1"]["body"][0]


def catalogue() -> list[dict[str, Any]]:
    return fixture()["capability_catalogue"]


def consumptions() -> list[dict[str, Any]]:
    return fixture()["consumptions_daily"][1]


class FixtureClient:
    """Remplace ``MagellanClient`` : sert la fixture, compte les appels."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.setup = setup_view()
        self.fail_with: Exception | None = None

    async def setup_view(self) -> dict[str, Any]:
        self.calls.append("setup")
        if self.fail_with:
            raise self.fail_with
        return copy.deepcopy(self.setup)

    async def capability_catalogue(self) -> list[dict[str, Any]]:
        self.calls.append("catalogue")
        return catalogue()

    async def daily_consumptions(self, setup_id) -> list[dict[str, Any]]:
        self.calls.append("consumptions")
        return consumptions()
