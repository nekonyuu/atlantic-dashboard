"""Client HTTP Magellan : jeton, lectures, traduction des erreurs.

API non documentée (PLAN.md §3.4) ; seules les routes vues en phase 0 sont appelées.
Aucun identifiant ni secret n'apparaît dans les messages d'erreur.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import aiohttp

from app.domain.errors import CredentialsRejected, ProviderThrottled, ProviderUnavailable

log = logging.getLogger(__name__)

API = "https://apis.groupe-atlantic.com"
# Identifiant client public de l'application Cozytouch.
CLIENT_ID = "Q3RfMUpWeVRtSUxYOEllZkE3YVVOQmpGblpVYToyRWNORHpfZHkzNDJVSnFvMlo3cFNKTnZVdjBh"
TIMEOUT = aiohttp.ClientTimeout(total=30)
DEFAULT_THROTTLE = 300
TOKEN_MARGIN = 60


class MagellanClient:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
        *,
        base_url: str = API,
        monotonic=time.monotonic,
    ) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._base = base_url.rstrip("/")
        self._monotonic = monotonic
        self._token: str | None = None
        self._expires_at = 0.0
        self.logins = 0

    async def setup_view(self) -> dict[str, Any]:
        body = await self._get("/magellan/cozytouch/setupviewv2")
        setup = body[0] if isinstance(body, list) and body else body
        if not isinstance(setup, dict) or not isinstance(setup.get("devices"), list):
            raise ProviderUnavailable("setupviewv2 : réponse inattendue")
        return setup

    async def capability_catalogue(self) -> list[dict[str, Any]]:
        body = await self._get("/magellan/productmodels/capabilities")
        if not isinstance(body, list):
            raise ProviderUnavailable("catalogue : réponse inattendue")
        return body

    async def daily_consumptions(self, setup_id: int | str) -> list[dict[str, Any]]:
        body = await self._get(f"/magellan/setups/{setup_id}/consumptions?periodicity=daily")
        if not isinstance(body, list):
            raise ProviderUnavailable("consommations : réponse inattendue")
        return body

    async def _login(self) -> None:
        self.logins += 1
        try:
            async with self._session.post(
                self._base + "/users/token",
                data={
                    "grant_type": "password",
                    "scope": "openid",
                    "username": f"GA-PRIVATEPERSON/{self._username}",
                    "password": self._password,
                },
                headers={"Authorization": f"Basic {CLIENT_ID}"},
                timeout=TIMEOUT,
            ) as r:
                _raise_for_throttle(r)
                if r.status >= 500:
                    raise ProviderUnavailable(f"jeton : HTTP {r.status}")
                body = await r.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
            raise ProviderUnavailable(f"jeton : {type(exc).__name__}") from None
        if isinstance(body, dict) and body.get("error") == "invalid_grant":
            raise CredentialsRejected("identifiants refusés (invalid_grant)")
        if not isinstance(body, dict) or not isinstance(body.get("access_token"), str):
            raise ProviderUnavailable(f"jeton : réponse inattendue (HTTP {r.status})")
        self._token = body["access_token"]
        expires_in = body.get("expires_in") if isinstance(body.get("expires_in"), int) else 3600
        self._expires_at = self._monotonic() + max(expires_in - TOKEN_MARGIN, 0)

    async def _get(self, path: str) -> Any:
        if self._token is None or self._monotonic() >= self._expires_at:
            await self._login()
        for attempt in (1, 2):
            route = path.split("?")[0]
            try:
                async with self._session.get(
                    self._base + path, headers={"Authorization": f"Bearer {self._token}"}, timeout=TIMEOUT
                ) as r:
                    _raise_for_throttle(r)
                    if r.status == 401 and attempt == 1:
                        log.info("Jeton refusé (401) : renouvellement")
                        self._token = None
                        await self._login()
                        continue
                    if r.status != 200:
                        raise ProviderUnavailable(f"{_safe(route)} : HTTP {r.status}")
                    return await r.json(content_type=None)
            except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
                raise ProviderUnavailable(f"{_safe(route)} : {type(exc).__name__}") from None
        raise ProviderUnavailable(f"{_safe(path)} : 401 persistant")


def _raise_for_throttle(r: aiohttp.ClientResponse) -> None:
    if r.status != 429:
        return
    header = r.headers.get("Retry-After", "")
    retry_after = int(header) if header.isdigit() else DEFAULT_THROTTLE
    raise ProviderThrottled("HTTP 429", retry_after=max(retry_after, 1))


def _safe(route: str) -> str:
    """Route sans identifiant de setup."""
    return "/magellan/setups/…/consumptions" if "/setups/" in route else route
