# CLAUDE.md

Dashboard perso pour PAC Atlantic Alfea Excellia S + ballon ECS (thermostat Navilink 228, sans box), via le cloud **Magellan** d'Atlantic (`apis.groupe-atlantic.com`). Le compte n'existe **pas** chez Overkiz : `pyoverkiz` a été retiré (voir `docs/phase0-findings.md` §0). **`PLAN.md` (révision 3) est la référence : ne le modifier qu'avec l'accord explicite du propriétaire.**

## Environnement
- Outils gérés par **mise** (`mise.toml` : Python 3.12, Node 22, uv). `mise install` à la racine.
- Backend : `cd backend && uv sync` ; lancer avec `uv run ...`. Lockfile `uv.lock` commité.
- Frontend (phase 4) : `cd frontend && npm ci`.

## Commandes
- Découverte phase 0 : `cd backend && set -a && source ../.env && set +a && uv run python scripts/discover_magellan.py` (jamais d'identifiants en ligne de commande)
- Lint : `cd backend && uv run ruff check . && uv run ruff format --check .`
- Tests : `cd backend && uv run pytest` (inclut les contrats import-linter, aussi via `uv run lint-imports`)
- **Avant tout commit : lint et tests doivent passer.**

## Phases
Suivre §12 du plan. S'arrêter aux phases marquées ⏸ (0, 1, 4) et montrer le résultat. Phase en cours : **1 terminée, en attente de validation** (⏸). Suivante : 2 (adaptateurs SQLite + Magellan, scheduler, Dockerfile minimal).

## Architecture (hexagonale + DDD, §3)
- `app/domain/` : pur, stdlib uniquement, pas d'I/O, horloge injectée.
- `app/application/` : ports + cas d'usage, n'importe que `domain`.
- Adaptateur fournisseur (`app/adapters/outbound/overkiz/` dans le plan, cible désormais Magellan, nom à valider) : **seul** endroit qui connaît l'API Atlantic et les `capabilityId` (via `semantics.yaml`).
- `app/adapters/outbound/sqlite/` : **seul** accès `aiosqlite`/`sqlite3`.
- `app/adapters/inbound/http/` : **seul** import de `fastapi`.
- `app/main.py` : unique composition root (DI à la main).
Contrats `import-linter` dans `backend/pyproject.toml`, toujours verts.

## Règles impératives
- API Magellan non documentée : références `mathieuletyrant/cozytouch-hacs` et `NicolasYDDER/homey-cozytouch` (sans licence claire : s'inspirer, ne pas copier). Ne rien supposer qui n'ait été vu dans un dump réel.
- Quotas : respecter `rateLimit` du setup ; un seul `setupviewv2` par cycle ; jeton réutilisé jusqu'à expiration ; 429 → backoff (`Retry-After`, sinon ≥ 300 s).
- `invalid_grant` → `CredentialsRejected` → arrêt des tentatives (risque de bannissement).
- Jamais de vrais identifiants, device URL, numéros de série ou adresses dans code, tests, fixtures, logs. `discover_output.json` et `.env` hors git.
- Un trou reste un trou : ne jamais inventer de données (§8).
- Base en UTC (epoch s) ; buckets journaliers via `zoneinfo("Europe/Paris")`.
- Pas d'Alembic, pas de framework DI, pas de dépendance non justifiée par le plan.
