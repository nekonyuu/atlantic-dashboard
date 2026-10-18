"""Dépendances des routes : tout est injecté via ``app.state.api`` (pas d'import du composition root)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import Request

from app.application.ports import Clock
from app.application.usecases.queries import (
    GetEnergy,
    GetEquipment,
    GetGaps,
    GetHealth,
    GetLatest,
    GetMetrics,
    GetSeries,
)


@dataclass
class HttpApi:
    get_health: GetHealth
    get_equipment: GetEquipment
    get_latest: GetLatest
    get_series: GetSeries
    get_gaps: GetGaps
    get_energy: GetEnergy
    get_metrics: GetMetrics
    # renvoie un objet avec running, stopped_reason, consecutive_failures, next_delay_seconds
    scheduler_state: Callable[[], Any]
    clock: Clock


def api(request: Request) -> HttpApi:
    return request.app.state.api
