"""Erreurs de domaine : seules erreurs fournisseur que l'application connaît."""

from __future__ import annotations

from app.domain.values import ErrorKind


class ProviderError(Exception):
    kind: ErrorKind = ErrorKind.UNEXPECTED


class CredentialsRejected(ProviderError):
    """Identifiants refusés : ne plus réessayer (risque de bannissement)."""

    kind = ErrorKind.CREDENTIALS


class ProviderThrottled(ProviderError):
    """Le fournisseur limite les requêtes ; attendre ``retry_after`` secondes au moins."""

    kind = ErrorKind.THROTTLED

    def __init__(self, message: str, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ProviderUnavailable(ProviderError):
    """Panne, maintenance, timeout ou réponse inexploitable : backoff exponentiel."""

    kind = ErrorKind.UNAVAILABLE
