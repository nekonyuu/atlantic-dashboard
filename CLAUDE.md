# CLAUDE.md

Dashboard perso pour PAC Atlantic **Alfea Excellia S** + ballon ECS (thermostat Navilink 228, sans box), données
lues sur le cloud **Magellan** d'Atlantic (`apis.groupe-atlantic.com`). Le compte n'existe **pas** chez Overkiz :
`pyoverkiz` a été retiré, ne pas le réintroduire (`docs/phase0-findings.md` §0).
**`PLAN.md` (révision 3) est la référence : ne le modifier qu'avec l'accord explicite du propriétaire.**

## État
Phases 0 à 5 terminées (`PLAN.md` §12) : collecte, API, front, image Docker publiée par la CI, en service sur le NAS.
Phase 6 (commandes) optionnelle. S'arrêter aux phases marquées ⏸ et montrer le résultat.

## Environnement et commandes
- Outils gérés par **mise** (`mise.toml` : Python 3.12, Node 22, uv) : `mise install` à la racine.
- Backend : `cd backend && uv sync` ; tout via `uv run ...` ; lockfile `uv.lock` commité.
- Frontend : `cd frontend && npm ci` ; `npm run dev` (proxy `/api` vers `API_URL`, défaut `127.0.0.1:8000`).
- Démo sans cloud ni identifiants (base temporaire, fixture + historique **synthétique**) :
  `cd backend && uv run python scripts/demo_server.py --port 8765` puis `cd frontend && API_URL=http://127.0.0.1:8765 npm run dev`.
- **Avant tout commit, lint et tests verts** :
  - `cd backend && uv run ruff check . && uv run ruff format --check . && uv run pytest -q` (inclut les contrats import-linter)
  - `cd frontend && npx tsc -b && npx vitest run && npm run build`
- CLI (dans le conteneur : `docker compose exec pac-dashboard python -m app.adapters.inbound.cli ...`) :
  `discover` (1 cycle réel), `catch-up [--since AAAA-MM-JJ]`, `backup`.
- Sonde phase 0 (appels réels, identifiants dans `../.env`, jamais en ligne de commande) :
  `cd backend && set -a && source ../.env && set +a && uv run python scripts/discover_magellan.py` ;
  `--refixture` régénère la fixture anonymisée depuis le dump sans appel réseau.

## Architecture (hexagonale + DDD, `PLAN.md` §3)
- `backend/app/domain/` : pur, stdlib uniquement, horloge injectée (`ChangeDetector`, `SeriesAggregator`, `GapDetector`).
- `backend/app/application/` : ports (`ports/`) + cas d'usage (`usecases/`), n'importe que `domain`.
- `backend/app/adapters/outbound/magellan/` : **seul** code qui connaît l'API Atlantic, les `capabilityId`, `productId`, slots.
  `client.py` (HTTP, jeton, erreurs), `mapping.py` (traduction), `gateway.py` (`EquipmentGateway`, `HistorySource`,
  `MetricCatalog`), `semantics.yaml` (correspondance).
- `backend/app/adapters/outbound/sqlite/` : **seul** accès `aiosqlite`/`sqlite3` ; migrations `migrations/NNNN_*.sql` + `PRAGMA user_version`.
- `backend/app/adapters/outbound/fake/` : implémentations en mémoire pour les tests.
- `backend/app/adapters/inbound/` : `http/` (**seul** import de FastAPI), `scheduler.py`, `cli.py`.
- `backend/app/main.py` : unique composition root (DI à la main, lifespan FastAPI). `config.py` : variables d'environnement.
- Contrats `import-linter` dans `backend/pyproject.toml`, vérifiés par `tests/architecture/`.
- Tests : `tests/domain` (sans mock), `tests/application` (fakes), `tests/contract` (même suite sur fake/SQLite et
  fake/Magellan sur `tests/fixtures/magellan_anonymized.json`), `tests/adapters`.

## Faits établis sur l'installation et l'API Magellan
- Lecture : `GET /magellan/cozytouch/setupviewv2` = tous les équipements et capacités en **un** appel, une fois par cycle (5 min).
  Jeton `POST /users/token` valable 8 h, réutilisé. Catalogue `GET /magellan/productmodels/capabilities` (noms, types,
  unités, enums) mis en cache en base, rafraîchi au plus une fois par jour.
- Équipements reconnus par `productId` (jamais par `customName`, modifiable par l'utilisateur) :
  54 = `heat_pump`, 58 = `generator`, 47 = `dhw`, 55 = `circuit_N`, 26 = `room_N`.
- Une capacité = `{capabilityId, value (texte), modificationDate}`. L'instant d'une mesure est `modificationDate` (date du
  dernier **changement**, pas de la lecture) : un point n'est enregistré que si elle change. Une valeur ancienne n'est
  pas « périmée » tant que la collecte fonctionne (c'est le bandeau d'état qui signale une panne).
- Aucun historique fournisseur pour températures, consignes, modes : les trous restent des trous.
- Énergie : `GET /magellan/setups/<id>/consumptions?periodicity=daily` = ~32 jours glissants, kWh et coût par jour.
  **Catégorie 1 = chauffage, 2 = eau chaude** (confirmé par le propriétaire). `mode` 1 = heures pleines, 2 = heures creuses.
  C'est la seule source de catch-up (niveau C) ; le rapport distingue jours reçus et jours écrits (relance idempotente = 0 écrit).
- Compteurs cumulés 57 (chauffage) et 59 (ECS) : unité supposée **Wh** (corrigée dans `semantics.yaml`), à confirmer.
- Erreurs : `invalid_grant` → `CredentialsRejected` (**arrêt définitif** des tentatives, risque de bannissement) ;
  429 → `ProviderThrottled` (`Retry-After`, sinon ≥ 300 s) ; 5xx/timeout → `ProviderUnavailable` (backoff ≤ 1 h) ;
  401 → un seul renouvellement du jeton.

## Ajouter une mesure
1. Trouver le `capabilityId` dans un dump réel (`discover_magellan.py`) et le catalogue ; ne rien supposer.
2. L'ajouter dans `semantics.yaml` (`label` FR, `capability`, éventuellement `unit`, `cumulative`).
3. Vérifier `tests/adapters/test_magellan_mapping.py` (toute capacité décrite doit exister dans la fixture et le catalogue).
4. Côté front : couleur fixe dans `frontend/src/lib/palette.ts`, traduction d'enum dans `frontend/src/lib/format.ts` si besoin.

## API HTTP (lecture seule, `backend/app/adapters/inbound/http/routes.py`)
`/api/health` (toujours 200, état dans le corps), `/api/equipment`, `/api/latest`, `/api/series` (bucket 5m/1h/1d auto),
`/api/gaps`, `/api/energy`. Instants en secondes epoch UTC ; libellés et unités viennent de `MetricCatalog`, le front ne voit
jamais de `capabilityId`. Repli SPA pour toute route non-API.

## Frontend (`frontend/src`)
- Vite + React + TypeScript, TanStack Query (rafraîchissement 60 s), uPlot (courbes), SVG maison (colonnes énergie).
- Pages : `pages/Overview`, `Dhw`, `Heating`, `History`, `Energy` (bascule par usage / par tarif, mémorisée).
- Règles de design (skill dataviz) :
  - un graphique = une unité = un axe Y, jamais de double axe ; plusieurs unités → petits multiples ;
  - couleur fixe par métrique (`lib/palette.ts`, palette validée par `validate_palette.js`), consignes en pointillé ;
  - statuts toujours icône + libellé ; chaque graphique a une vue tableau ; trous hachurés, jamais interpolés ;
  - thème clair/sombre/système par variables CSS (`data-theme` + `prefers-color-scheme`) ;
  - textes et nombres en français (`lib/format.ts`, enums du catalogue traduits).
- Vérifier visuellement tout changement d'UI sur la démo : desktop 1440 px et mobile 390 px, clair et sombre.

## Déploiement
- Image unique (front compilé servi par FastAPI) : `Dockerfile` multi-stage, non-root uid 1000, healthcheck Python.
- CI `.github/workflows/ci.yml` : lint + tests backend/frontend, puis image `linux/amd64` + `linux/arm64` publiée sur
  `ghcr.io/nekonyuu/atlantic-dashboard` depuis `main` (`latest`, `sha-…`) et les tags `vX.Y.Z`. Dépôt et image **privés**.
- NAS : `docker-compose.yml` (image via `PAC_IMAGE`), volume `/data` sur disque **local** (jamais SMB/NFS), dossier
  appartenant à l'UID:GID de `user:` (sinon « Stockage inaccessible » au démarrage). Détails dans `README.md`.

## Règles impératives
- API non documentée : références `mathieuletyrant/cozytouch-hacs` et `NicolasYDDER/homey-cozytouch`, sans licence
  claire : s'inspirer du comportement, ne pas copier de code.
- Jamais de vrais identifiants, e-mail, `deviceId`, `setupId`, numéros de série, adresses dans le code, les tests, les
  fixtures ou les logs. `.env` et `backend/discover_*output.json` hors git ; anonymiser via `discover_magellan.py`.
- Un trou reste un trou : ne jamais inventer de données (`PLAN.md` §8). Les données synthétiques n'existent que dans
  `scripts/demo_server.py`, sur une base temporaire.
- Base en UTC (epoch s) ; journées calculées avec `zoneinfo("Europe/Paris")`.
- Un seul writer SQLite (un seul worker uvicorn) ; pas d'Alembic, pas de framework DI, pas de dépendance non justifiée.

## Points ouverts
- Unité des compteurs 57/59 (Wh supposé) : comparer leurs deltas aux consommations journalières.
- Détection des cycles de chauffe ECS (`CycleDetector`, `/api/events`) : choisir la mesure après quelques jours de collecte.
- Libellés des mesures vides via l'API tant qu'aucun poll n'a réussi depuis le démarrage (`MetricCatalog` sans réseau).
