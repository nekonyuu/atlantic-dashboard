"""Phase 0 bis : découverte via l'API Magellan d'Atlantic (lecture seule).

Le compte n'existe pas côté Overkiz (UnknownUserError) : l'installation
(Navilink 228, sans box) n'est visible que sur apis.groupe-atlantic.com.
API non documentée ; routes reprises de mathieuletyrant/cozytouch-hacs
(docs/api-surface.md) et NicolasYDDER/homey-cozytouch.

Usage (depuis backend/, identifiants dans ../.env) :
    set -a && source ../.env && set +a && uv run python scripts/discover_magellan.py

Appels (tous GET sauf le jeton), ~10 au total, espacés :
- POST /users/token
- GET /magellan/cozytouch/setupviewv2           (x2, espacés de --gap s : fraîcheur)
- GET /magellan/capabilities/?deviceId=<id>     (1 par équipement)
- GET /magellan/setups/<setupId>/consumptions?periodicity=daily
- GET /magellan/productmodels/capabilities      (catalogue des noms de capacités)
Un 429 arrête la sonde immédiatement.

Sorties : discover_magellan_output.json (BRUT, hors git, 600) et
tests/fixtures/magellan_anonymized.json (à relire avant commit).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import aiohttp

API = "https://apis.groupe-atlantic.com"
# Identifiant client public de l'app Cozytouch, identique à celui de pyoverkiz.
CLIENT_ID = "Q3RfMUpWeVRtSUxYOEllZkE3YVVOQmpGblpVYToyRWNORHpfZHkzNDJVSnFvMlo3cFNKTnZVdjBh"
PAUSE = 2.0  # secondes entre deux appels

BACKEND_DIR = Path(__file__).resolve().parent.parent
RAW_OUTPUT = BACKEND_DIR / "discover_magellan_output.json"
FIXTURE_OUTPUT = BACKEND_DIR / "tests" / "fixtures" / "magellan_anonymized.json"

# Capacités dont la valeur identifie le foyer (numéros de série, noms, prix, dates d'absence).
_SENSITIVE_CAP_NAME = re.compile(r"Serial|Identification|Name|Price|DateAway|BLEPairing", re.I)
_SENSITIVE_KEYS = {
    "address", "name", "label", "longName", "serialNumber", "gatewaySerialNumber",
    "deviceUrl", "deviceURL", "email", "phone", "city", "zipCode", "postalCode",
    "latitude", "longitude", "zoneLabel", "firstName", "lastName", "id", "setupId",
}


def sensitive_capabilities(out: dict[str, Any]) -> frozenset[int]:
    cat = (out.get("capability_catalogue") or [None, []])[1] or []
    return frozenset(
        c["id"] for c in cat if c.get("type") == 3 or _SENSITIVE_CAP_NAME.search(c.get("name") or "")
    )


# Identifiants numériques remplacés par des pseudonymes stables (cohérence conservée).
_PSEUDO_KEYS = {"deviceId", "gatewayId", "zoneId", "masterDeviceId", "setupId"}


def pseudonymize(node: Any, table: dict[tuple[str, Any], int] | None = None) -> Any:
    table = {} if table is None else table
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k in _PSEUDO_KEYS and isinstance(v, int):
                out[k] = table.setdefault(("id", v), 1000 + len(table))
            else:
                out[k] = pseudonymize(v, table)
        return out
    if isinstance(node, list):
        return [pseudonymize(i, table) for i in node]
    return node


def write_fixture(out: dict[str, Any]) -> None:
    fixture = {k: v for k, v in out.items() if k not in ("capability_catalogue", "capabilities")}
    # Catalogue (métadonnées produit, non personnelles) réduit aux capacités présentes.
    body = (out.get("setupview_1") or {}).get("body") or []
    present = {c["capabilityId"] for s in body for d in s.get("devices", []) for c in d.get("capabilities", [])}
    catalogue = (out.get("capability_catalogue") or [None, []])[1] or []
    FIXTURE_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    data = pseudonymize(anonymize(fixture, sensitive_capabilities(out)))
    data["capability_catalogue"] = [c for c in catalogue if c.get("id") in present]
    FIXTURE_OUTPUT.write_text(json.dumps(data, indent=2, ensure_ascii=False))


class RateLimited(Exception):
    pass


def anonymize(node: Any, sensitive_caps: frozenset[int] = frozenset()) -> Any:
    """Masque les champs identifiants et les valeurs des capacités identifiantes."""
    if isinstance(node, dict):
        if node.get("capabilityId") in sensitive_caps and "value" in node:
            return {**node, "value": "MASKED"}
        out = {}
        for k, v in node.items():
            if k in _SENSITIVE_KEYS and v not in (None, ""):
                out[k] = "MASKED"
            else:
                out[k] = anonymize(v, sensitive_caps)
        return out
    if isinstance(node, list):
        return [anonymize(i, sensitive_caps) for i in node]
    if isinstance(node, str):
        return re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "user@example.invalid", node)
    return node


async def _get(session: aiohttp.ClientSession, token: str, path: str) -> tuple[int, Any]:
    await asyncio.sleep(PAUSE)
    async with session.get(API + path, headers={"Authorization": f"Bearer {token}"}) as r:
        if r.status == 429:
            raise RateLimited(f"429 sur {path.split('?')[0]} ; Retry-After={r.headers.get('Retry-After')}")
        try:
            body = await r.json(content_type=None)
        except ValueError:
            body = None
        return r.status, body


async def discover(args: argparse.Namespace) -> int:
    username = os.environ.get("COZYTOUCH_USERNAME")
    password = os.environ.get("COZYTOUCH_PASSWORD")
    if not username or not password:
        print("COZYTOUCH_USERNAME / COZYTOUCH_PASSWORD requis", file=sys.stderr)
        return 2

    out: dict[str, Any] = {"generated_at": int(time.time())}
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(
            API + "/users/token",
            data={
                "grant_type": "password",
                "scope": "openid",
                "username": f"GA-PRIVATEPERSON/{username}",
                "password": password,
            },
            headers={"Authorization": f"Basic {CLIENT_ID}"},
        ) as r:
            tok = await r.json(content_type=None)
        if tok.get("error") == "invalid_grant":
            print("Identifiants refusés (invalid_grant). Arrêt, pas de nouvelle tentative.", file=sys.stderr)
            return 3
        if "access_token" not in tok:
            print(f"Réponse de jeton inattendue (HTTP {r.status}).", file=sys.stderr)
            return 4
        token = tok["access_token"]
        out["token_expires_in"] = tok.get("expires_in")
        print("Connecté.")

        try:
            status, setup1 = await _get(session, token, "/magellan/cozytouch/setupviewv2")
            out["setupview_1"] = {"status": status, "at": int(time.time()), "body": setup1}
            setup = setup1[0] if isinstance(setup1, list) and setup1 else setup1
            if not isinstance(setup, dict):
                print(f"setupviewv2 inattendu (HTTP {status}).", file=sys.stderr)
                return 5
            devices = setup.get("devices", [])
            print(f"{len(devices)} équipement(s), rateLimit={setup.get('rateLimit')}.")

            out["capabilities"] = {}
            for d in devices:
                did = d.get("deviceId")
                out["capabilities"][str(did)] = await _get(session, token, f"/magellan/capabilities/?deviceId={did}")

            sid = setup.get("id")
            out["consumptions_daily"] = await _get(session, token, f"/magellan/setups/{sid}/consumptions?periodicity=daily")
            out["capability_catalogue"] = await _get(session, token, "/magellan/productmodels/capabilities")

            print(f"Attente {args.gap}s avant la 2e lecture du setup...")
            await asyncio.sleep(args.gap)
            status, setup2 = await _get(session, token, "/magellan/cozytouch/setupviewv2")
            out["setupview_2"] = {"status": status, "at": int(time.time()), "body": setup2}
        except RateLimited as exc:
            out["rate_limited"] = str(exc)
            print(f"Limité par Atlantic : {exc}. Arrêt.", file=sys.stderr)

    RAW_OUTPUT.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    os.chmod(RAW_OUTPUT, 0o600)
    write_fixture(out)
    _print_summary(out)
    print(f"\nBrut : {RAW_OUTPUT} (hors git)\nFixture anonymisée : {FIXTURE_OUTPUT} (à relire avant commit)")
    return 0


def _caps(device: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {c["capabilityId"]: c for c in device.get("capabilities", []) if "capabilityId" in c}


def _print_summary(out: dict[str, Any]) -> None:
    def setup_of(key: str) -> dict[str, Any]:
        body = (out.get(key) or {}).get("body")
        return (body[0] if isinstance(body, list) and body else body) or {}

    s1, s2 = setup_of("setupview_1"), setup_of("setupview_2")
    devs2 = {d.get("deviceId"): d for d in s2.get("devices", [])}
    print("\n=== Équipements ===")
    for d in s1.get("devices", []):
        c1, c2 = _caps(d), _caps(devs2.get(d.get("deviceId"), {}))
        changed = [k for k in c1 if k in c2 and c1[k].get("value") != c2[k].get("value")]
        st, per_dev = out.get("capabilities", {}).get(str(d.get("deviceId")), (None, None))
        print(
            f"modelId={d.get('modelId')} productId={d.get('productId')} "
            f"capacités(setup)={len(c1)} capacités(endpoint)={len(per_dev) if isinstance(per_dev, list) else st} "
            f"changées_entre_2_lectures={len(changed)}"
        )
    cons = out.get("consumptions_daily")
    if cons:
        st, body = cons
        n = sum(len(x.get("consumptionPeriods", [])) for x in body) if isinstance(body, list) else 0
        print(f"\nConsommations journalières : HTTP {st}, {n} période(s)")
    cat = out.get("capability_catalogue")
    if cat:
        print(f"Catalogue de capacités : HTTP {cat[0]}, {len(cat[1]) if isinstance(cat[1], list) else '?'} entrée(s)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--gap", type=int, default=180, help="secondes entre les 2 lectures du setup")
    parser.add_argument("--refixture", action="store_true", help="régénère la fixture depuis le dump, sans appel réseau")
    args = parser.parse_args()
    if args.refixture:
        write_fixture(json.loads(RAW_OUTPUT.read_text()))
        return 0
    return asyncio.run(discover(args))


if __name__ == "__main__":
    sys.exit(main())
