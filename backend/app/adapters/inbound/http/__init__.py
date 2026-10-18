"""Adaptateur entrant HTTP : API REST en lecture seule et service du front."""

from app.adapters.inbound.http.deps import HttpApi
from app.adapters.inbound.http.routes import router
from app.adapters.inbound.http.spa import mount_spa

__all__ = ["HttpApi", "mount_spa", "router"]
