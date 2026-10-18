"""Événements de domaine : santé, logs et, plus tard, alertes."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.model import Gap
from app.domain.values import ErrorKind, Instant, Measurement


@dataclass(frozen=True, slots=True)
class MeasurementRecorded:
    measurement: Measurement


@dataclass(frozen=True, slots=True)
class GapDetected:
    gap: Gap


@dataclass(frozen=True, slots=True)
class PollFailed:
    at: Instant
    kind: ErrorKind
    error: str


@dataclass(frozen=True, slots=True)
class CredentialsRejected:
    at: Instant


DomainEvent = MeasurementRecorded | GapDetected | PollFailed | CredentialsRejected
