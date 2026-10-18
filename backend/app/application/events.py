"""Diffusion des événements de domaine (logs, santé, alertes futures)."""

from __future__ import annotations

from collections.abc import Callable

from app.domain.events import DomainEvent

Publisher = Callable[[DomainEvent], None]


def discard(_: DomainEvent) -> None:
    """Publisher par défaut."""
