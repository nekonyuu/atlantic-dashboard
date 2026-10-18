# Dashboard PAC Atlantic (Alfea Excellia S + ballon ECS)

Dashboard perso, plus lisible que Cozytouch, avec historique durable. Un seul conteneur Docker sur un NAS Ugreen. Architecture hexagonale + DDD pour isoler tout ce qui peut casser (API Magellan non officielle en tête).

Révision 2 : intègre la revue critique de la v1 (quotas, schéma, Docker, SQLite sur NAS), l'architecture hexagonale et un mécanisme de catch-up.

Révision 3 (18/10/2026, après la phase 0, voir `docs/phase0-findings.md`) : le compte n'existe pas chez Overkiz (installation Navilink 228 sans box). `pyoverkiz` est abandonné ; la source est l'API **Magellan** d'Atlantic (`apis.groupe-atlantic.com`), appelée directement en `aiohttp`. Schéma, catch-up et `semantics.yaml` ajustés sur les données réelles.

## 1. Objectifs et non-objectifs

**Objectifs**
- Collecter en continu l'état de la PAC et du ballon via le cloud Magellan d'Atlantic (backend de l'app Cozytouch).
- Stocker un historique durable dans SQLite.
- Dashboard React sur mesure : état courant, courbes, cycles, consommation si disponible.
- Rattraper l'historique manquant quand c'est possible (section 8), et rendre les trous visibles quand ça ne l'est pas.
- Tout dans un conteneur, données persistées dans un volume local du NAS.

**Non-objectifs (v1)**
- Pas de pilotage (lecture seule). Les commandes viendront en phase 6, optionnelles.
- Pas d'exposition Internet. LAN uniquement.
- Pas de multi-utilisateurs.

## 2. Contraintes et risques

- **API non officielle** : l'API Magellan n'est pas documentée et peut changer sans préavis. Références : `mathieuletyrant/cozytouch-hacs`, `NicolasYDDER/homey-cozytouch` (sans licence claire : s'en inspirer, ne pas copier). Réponse structurelle : l'architecture de la section 3 confine tout appel à Magellan dans un seul adaptateur.
- **Pas d'Overkiz** : le login Overkiz renvoie `UnknownUserError` pour ce compte (constaté en phase 0). Ne pas réintroduire `pyoverkiz`.
- **Quotas** : le setup déclare `rateLimit=30` (unité inconnue, lue comme requêtes/minute, plafond jamais approché à 1 requête / 5 min). Un 429 impose un backoff (`Retry-After`, sinon 300 s). Jeton valable 8 h (`expires_in=28800`) : le réutiliser.
- **Pas d'API locale** pour Cozytouch : tout passe par le cloud.
- **Compte partagé avec l'app mobile Cozytouch** : effet des sessions concurrentes inconnu, à surveiller.
- **Schéma des données** : connu depuis la phase 0 (5 équipements, capacités numérotées décrites par le catalogue `/magellan/productmodels/capabilities`). Les valeurs ne sont mises à jour que sur changement (`modificationDate` par capacité).
- **Architecture CPU du NAS** : les Ugreen DXP sont à ma connaissance en x86-64, à confirmer pour ton modèle. Multi-arch seulement si nécessaire.

## 3. Architecture : hexagonale + DDD

### 3.1 Principe

Le **domaine** (règles métier pures) ne connaît ni Magellan, ni SQLite, ni FastAPI, ni l'horloge système. Il parle à l'extérieur uniquement via des **ports** (interfaces). Les **adaptateurs** implémentent ces ports et sont les seuls à toucher aux technologies concrètes.

```
            adaptateurs entrants (pilotent l'application)
        ┌──────────────┐        ┌───────────────────┐
        │ HTTP FastAPI │        │ Scheduler/poller  │   + CLI (catch-up manuel)
        └──────┬───────┘        └─────────┬─────────┘
               │ appellent                │
        ┌──────▼──────────────────────────▼──────────┐
        │  APPLICATION  (cas d'usage)                │
        │  CollectSamples · CatchUp · GetLatest ·    │
        │  GetSeries · GetHealth · Backup · Purge    │
        │                                            │
        │   ┌────────────────────────────────────┐   │
        │   │  DOMAINE (pur, sans I/O)           │   │
        │   │  entités, value objects, services, │   │
        │   │  événements de domaine             │   │
        │   └────────────────────────────────────┘   │
        │   ports sortants (interfaces)              │
        └──────┬──────────────┬──────────────┬───────┘
               │ implémentés par               │
        ┌──────▼─────┐  ┌─────▼──────┐  ┌─────▼───────┐
        │ Magellan   │  │ SQLite     │  │ Horloge,    │
        │ (aiohttp)  │  │ (aiosqlite)│  │ backup, ... │
        └────────────┘  └────────────┘  └─────────────┘
            adaptateurs sortants (appelés par l'application)
```

**Règle de dépendance** : les flèches d'import vont toujours vers l'intérieur (adaptateurs → application → domaine). Le domaine n'importe rien du reste. Cette règle est **vérifiée automatiquement** (section 3.5).

### 3.2 Langage du domaine (ubiquitous language)

Un seul contexte borné, **Télémétrie de l'installation**, suffisant pour la v1. Termes à utiliser tels quels dans le code :

| Concept | Type DDD | Rôle |
|---|---|---|
| `Installation` | agrégat racine | L'ensemble PAC + ballon, contient ses `Equipment` |
| `Equipment` | entité | Un appareil identifié par `EquipmentId` ; porte sa disponibilité |
| `EquipmentId` | value object | Identifiant opaque (dérivé du `deviceId` Magellan et du slot, ex. `dhw_0`) |
| `MetricKey` | value object | Nom **logique** d'une mesure (ex. `dhw_temperature`, `outdoor_temperature`), indépendant de Magellan |
| `Measurement` | value object | `(equipment_id, metric_key, instant, value)` |
| `MeasurementValue` | value object | Valeur typée : nombre, booléen, texte, JSON, ou « absente » explicite ; porte son unité |
| `Instant` | value object | Instant UTC (epoch secondes) |
| `Gap` | entité | Intervalle `[from, to)` sans collecte, avec sa cause |
| `EnergyDay` | value object | Consommation d'un jour civil : `(day, category, tariff, kwh, cost)` |
| `Series` / `Bucket` | value objects | Résultat d'agrégation sur une période |
| `PollOutcome` | value object | Succès ou échec typé d'un cycle de collecte |

**Services de domaine (purs, testables sans I/O)**
- `ChangeDetector` : décide si une mesure doit être enregistrée (nouvel instant fournisseur `modificationDate`, ou valeur changée à instant égal ; jamais deux fois le même `(équipement, métrique, ts)`).
- `SeriesAggregator` : moyenne **pondérée par la durée** avec report de la dernière valeur connue (LOCF), min/max, deltas pour les compteurs cumulés (gestion des remises à zéro), buckets calculés en **Europe/Paris** (journées de 23 h et 25 h).
- `GapDetector` : produit des `Gap` à partir de l'historique des `PollOutcome`.
- `CycleDetector` (après phase 0) : détecte les cycles de chauffe à partir de transitions d'une mesure identifiée.

**Événements de domaine** : `MeasurementRecorded`, `GapDetected`, `PollFailed`, `CredentialsRejected`. Ils servent à la santé, aux logs et, plus tard, aux alertes, sans coupler les modules entre eux.

### 3.3 Ports

**Sortants (définis dans `application/ports/`, implémentés par les adaptateurs)**

| Port | Contrat | Adaptateurs |
|---|---|---|
| `EquipmentGateway` | `list_equipment()`, `read_measurements()`, `availability()` | `magellan` (réel), `fake` (tests) |
| `HistorySource` | `capabilities()`, `fetch_energy_days(since, until)` ; **optionnel** | `magellan` (consommations journalières), `null` (tests) |
| `EnergyRepository` | `upsert(days)` idempotent, `range(...)` | `sqlite` |
| `MeasurementRepository` | `append(batch)` idempotent, `latest()`, `range(...)`, `last_recorded(...)` | `sqlite` |
| `GapRepository` | `add`, `list(range)` | `sqlite` |
| `PollLogRepository` | `add(outcome)`, `recent()` | `sqlite` |
| `BackupService` | `snapshot()` avec rotation | `sqlite` (`VACUUM INTO`) |
| `Clock` | `now()` | `system`, `fixed` (tests) |

**Entrants** : les cas d'usage eux-mêmes (`CollectSamples`, `CatchUp`, `GetLatest`, `GetSeries`, `GetHealth`, `RunBackup`, `PurgeRaw`), appelés par FastAPI, par le scheduler et par la CLI.

### 3.4 Couche anti-corruption Magellan

C'est **le** point d'isolement. L'adaptateur `adapters/outbound/magellan/` est le seul endroit qui :
- connaît les URL, le jeton et le format JSON de `apis.groupe-atlantic.com` ;
- connaît les `capabilityId`, `modelId`, `productId` et slots (`DHW_0`, `ROOM_0`...) ;
- connaît les codes HTTP et erreurs Magellan.

Il fait trois traductions :
1. **Modèle** : capacités Magellan → `Measurement` du domaine, via **`semantics.yaml`** (slot + `capabilityId` → `MetricKey`). Type, unité, résolution et libellés d'enum viennent du **catalogue** du fournisseur, pas d'une recopie. L'instant d'une mesure est la `modificationDate` de la capacité. Une capacité inconnue ou de valeur inattendue est journalisée et ignorée, sans planter.
2. **Erreurs** :
   - `invalid_grant` au jeton → `CredentialsRejected` : **arrêt des tentatives**, santé en erreur, pas de retry (risque de bannissement) ;
   - HTTP 429 → `ProviderThrottled` : backoff `Retry-After`, sinon 300 s minimum ;
   - 5xx, timeout, réponse malformée → `ProviderUnavailable` : backoff exponentiel ;
   - 401 sur une lecture → renouvellement du jeton **une seule fois**, puis `ProviderUnavailable`.
3. **Session** : un jeton par processus, renouvelé à expiration (8 h, marge de 60 s) ou sur 401. Jamais de login à chaque cycle.

**Stratégie d'appel dans l'adaptateur**
- `POST /users/token` : au démarrage puis à expiration.
- `GET /magellan/cozytouch/setupviewv2` : **un seul appel par cycle** (tous les équipements et capacités).
- `GET /magellan/productmodels/capabilities` (catalogue) : au démarrage, mis en cache en base ; rafraîchi au plus une fois par jour.
- `GET /magellan/setups/<id>/consumptions?periodicity=daily` : au démarrage puis une fois par jour (source `HistorySource`).
- Le client (et sa `ClientSession` aiohttp) est créé **dans le lifespan** de l'application, jamais à l'import ; fermeture propre à l'arrêt.

### 3.5 Garde-fous automatiques

- **`import-linter`** (contrats déclarés dans `pyproject.toml`), exécuté dans les tests :
  1. `domain` n'importe rien d'autre que la bibliothèque standard ;
  2. `application` n'importe que `domain` ;
  3. seul `adapters.outbound.magellan` peut importer `aiohttp` ;
  4. seul `adapters.outbound.sqlite` peut importer `aiosqlite` / `sqlite3` ;
  5. seul `adapters.inbound.http` peut importer `fastapi`.
- **Tests de contrat** sur le port `EquipmentGateway` : la même suite de tests passe sur l'adaptateur `fake` et sur l'adaptateur Magellan alimenté par des **fixtures enregistrées** (`tests/fixtures/magellan_anonymized.json`). Quand Magellan change, c'est ce test qui casse, pas le reste.
- **Tests de domaine** sans aucun mock : services purs, horloge injectée.

### 3.6 Composition root

`app/main.py` est le seul endroit qui assemble les adaptateurs et les cas d'usage (injection de dépendances à la main, pas de framework). Le lifespan FastAPI y construit le client Magellan, démarre le scheduler, expose l'état du poller, et arrête tout proprement.

## 4. Stack et décisions fermes

| Couche | Choix |
|---|---|
| Backend | Python 3.12, FastAPI, uvicorn **avec un seul worker**, `aiohttp`, `aiosqlite`, pydantic, PyYAML, `tzdata` (paquet pip, ne pas supposer l'OS), `import-linter` |
| Environnement | `mise` (`mise.toml` : Python, Node, uv) |
| Stockage | SQLite, WAL, un fichier dans `/data` |
| Frontend | Vite + React + TypeScript, TanStack Query, **uPlot** pour les courbes, CSS maison |
| Packaging | Dockerfile multi-stage, `docker-compose.yml`, **lockfiles commités** (`package-lock.json`, `uv.lock` ou `requirements.lock`) |
| Tests | pytest, Vitest, import-linter |

Décisions tranchées : `aiosqlite` (pas de `sqlite3` synchrone dans une coroutine), uPlot, migrations par `PRAGMA user_version` + scripts SQL ordonnés (pas d'Alembic), pas de framework d'injection.

## 5. Structure du repo

```
pac-dashboard/
├─ PLAN.md  CLAUDE.md  README.md  mise.toml  Dockerfile  docker-compose.yml  .env.example
├─ docs/
│  └─ phase0-findings.md          # rédigé par l'agent, validé par moi
├─ backend/
│  ├─ pyproject.toml              # deps épinglées + contrats import-linter
│  ├─ app/
│  │  ├─ domain/                  # PUR : aucune I/O
│  │  │  ├─ model.py              # Installation, Equipment, Gap...
│  │  │  ├─ values.py             # EquipmentId, MetricKey, Measurement, Instant...
│  │  │  ├─ services.py           # ChangeDetector, SeriesAggregator, GapDetector
│  │  │  ├─ events.py
│  │  │  └─ errors.py             # CredentialsRejected, ProviderThrottled...
│  │  ├─ application/
│  │  │  ├─ ports/                # EquipmentGateway, HistorySource, repositories...
│  │  │  └─ usecases/             # collect.py, catch_up.py, queries.py, backup.py, purge.py
│  │  ├─ adapters/
│  │  │  ├─ inbound/
│  │  │  │  ├─ http/              # routes FastAPI, schémas pydantic, repli SPA
│  │  │  │  ├─ scheduler.py       # boucle de collecte, backoff, jitter
│  │  │  │  └─ cli.py             # catch-up manuel, discover
│  │  │  └─ outbound/
│  │  │     ├─ magellan/          # SEUL client HTTP fournisseur ; mapper + semantics.yaml
│  │  │     ├─ sqlite/            # repositories, migrations/, connexion
│  │  │     ├─ fake/              # gateway de test
│  │  │     └─ system.py          # Clock
│  │  ├─ config.py
│  │  └─ main.py                  # composition root + lifespan
│  ├─ scripts/discover_magellan.py # phase 0
│  └─ tests/                      # domain/, application/, contract/, adapters/, architecture/
└─ frontend/
   ├─ package.json  package-lock.json  vite.config.ts   # proxy /api en dev
   └─ src/
```

## 6. Configuration (variables d'environnement)

| Variable | Rôle | Défaut |
|---|---|---|
| `COZYTOUCH_USERNAME` / `COZYTOUCH_PASSWORD` | identifiants | requis |
| `POLL_INTERVAL_SECONDS` | période de collecte | `300` (min `60`) |
| `DB_PATH` | chemin SQLite | `/data/pac.db` |
| `BACKUP_DIR` / `BACKUP_KEEP` | sauvegardes internes | `/data/backup` / `14` |
| `RETENTION_DAYS_RAW` | rétention des points bruts (0 = jamais purger) | `0` en v1 |
| `STATIC_DIR` | build du front dans l'image | `/app/static` |
| `LOG_LEVEL` | niveau de logs | `INFO` |

Le fuseau est défini **une seule fois**, dans le compose (`TZ=Europe/Paris`), à des fins d'affichage des logs ; la base reste en UTC et le calcul des buckets journaliers utilise `zoneinfo("Europe/Paris")`, pas la variable `TZ`.

Identifiants : jamais dans git ni dans l'image. `.env` en permissions `600` sur le NAS. Les variables d'environnement sont lisibles via `docker inspect` et l'UI Docker ; des secrets de compose basés sur fichier sont préférables si UGOS les accepte (non vérifié).

## 7. Modèle de données SQLite

Schéma générique (EAV), ajusté après la phase 0 aux identifiants Magellan.

```sql
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=ON;      -- à répéter sur CHAQUE connexion
PRAGMA busy_timeout=5000;
PRAGMA auto_vacuum=INCREMENTAL;  -- à la création de la base

CREATE TABLE equipment (
  equipment_id   TEXT PRIMARY KEY,    -- EquipmentId du domaine (ex. 'dhw_0')
  kind           TEXT NOT NULL,       -- dhw | heat_pump | generator | circuit | room
  device_id      INTEGER,             -- deviceId Magellan, jamais loggé
  model_id       INTEGER,
  product_id     INTEGER,
  slot           TEXT,                -- DHW_0, ROOM_0, TESC_0, GENERATOR_0, CESA
  zone_id        INTEGER,
  label          TEXT,
  first_seen     INTEGER NOT NULL,    -- epoch secondes UTC
  last_seen      INTEGER NOT NULL,
  available      INTEGER              -- dernière disponibilité connue
);

CREATE TABLE measurement (
  id            INTEGER PRIMARY KEY,
  ts            INTEGER NOT NULL,      -- epoch s UTC = modificationDate fournisseur
  polled_at     INTEGER NOT NULL,      -- epoch s UTC du poll qui l'a enregistrée
  equipment_id  TEXT NOT NULL REFERENCES equipment(equipment_id),
  metric_key    TEXT NOT NULL,         -- clé logique (voir semantics.yaml)
  source_state  TEXT NOT NULL,         -- capabilityId Magellan d'origine
  value_type    TEXT NOT NULL,         -- INTEGER|FLOAT|STRING|BOOLEAN|DATE|JSON|NULL
  value_num     REAL,                  -- booléen stocké en 0/1
  value_text    TEXT,                  -- JSON sérialisé ici
  origin        TEXT NOT NULL DEFAULT 'live',   -- 'live' | 'backfill'
  UNIQUE (equipment_id, metric_key, ts)         -- rend le catch-up idempotent
);
CREATE INDEX idx_measurement_lookup ON measurement(equipment_id, metric_key, ts);

CREATE TABLE measurement_hourly (    -- agrégats CONSERVÉS INDÉFINIMENT
  equipment_id TEXT NOT NULL, metric_key TEXT NOT NULL,
  hour_ts INTEGER NOT NULL,          -- début d'heure UTC
  avg_w REAL, min REAL, max REAL, last REAL, delta REAL, samples INTEGER,
  PRIMARY KEY (equipment_id, metric_key, hour_ts)
);

CREATE TABLE energy_daily (         -- consommations journalières fournisseur
  day      TEXT NOT NULL,             -- 'YYYY-MM-DD' (date fournisseur à minuit UTC)
  category INTEGER NOT NULL,          -- 1 = chauffage, 2 = ECS (confirmé)
  tariff   TEXT NOT NULL,             -- 'peak' | 'off_peak' | 'unknown' (mode fournisseur 1 / 2)
  kwh      REAL NOT NULL,
  cost     REAL,
  origin   TEXT NOT NULL DEFAULT 'backfill',
  fetched_at INTEGER NOT NULL,
  PRIMARY KEY (day, category, tariff)
);

CREATE TABLE capability_catalogue (  -- cache du catalogue fournisseur
  capability_id INTEGER PRIMARY KEY,
  name TEXT, type INTEGER, unit TEXT, resolution REAL, enum_json TEXT,
  fetched_at INTEGER NOT NULL
);

CREATE TABLE poll_log (
  ts INTEGER NOT NULL, ok INTEGER NOT NULL, duration_ms INTEGER,
  error_kind TEXT, error TEXT
);

CREATE TABLE gap (
  id INTEGER PRIMARY KEY,
  from_ts INTEGER NOT NULL, to_ts INTEGER NOT NULL,
  cause TEXT NOT NULL,                -- 'downtime'|'provider_error'|'credentials'|'unknown'
  recovered INTEGER NOT NULL DEFAULT 0   -- 1 si comblé par catch-up/backfill
);
```

**Règles**
- Enregistrer un point uniquement si l'instant fournisseur ou la valeur a **changé**. Au démarrage, le cache des dernières valeurs est **rechargé depuis la base** (sinon chaque redémarrage double les points).
- Un « trou » de collecte est distinct d'une « valeur stable » : `poll_log` et `gap` permettent de les distinguer à l'affichage.
- États de type inconnu : stockés avec `value_type` explicite ou ignorés avec un log, jamais d'exception.
- Compteurs d'énergie : stockés bruts (cumulés, capacités 57 chauffage et 59 ECS, probablement en Wh) ; les **deltas** sont calculés à la lecture et dans `measurement_hourly`, avec gestion des remises à zéro.
- Les consommations journalières du fournisseur vont dans `energy_daily` (upsert : le jour en cours est réécrit jusqu'à être clos).
- Les valeurs ne changent que sur événement : un point n'est enregistré que si la `modificationDate` change. Pas de point « heartbeat » (il faudrait inventer un instant). « Valeur stable » se déduit de `poll_log` : polls réussis sans nouvelle `modificationDate`.
- **Rétention** : `measurement_hourly` n'est jamais purgée. Les points bruts ne sont purgés que si `RETENTION_DAYS_RAW > 0`, et seulement après agrégation horaire. Volumétrie estimée faible (quelques dizaines de Mo par an) : pas de purge en v1.
- Migrations : `PRAGMA user_version` + scripts ordonnés dans `adapters/outbound/sqlite/migrations/`.
- Un seul **writer** (le cas d'usage de collecte, plus purge et sauvegarde sous le même verrou applicatif). Lectures de l'API sur des connexions séparées.
- **Le fichier doit être sur un disque local du NAS, jamais sur un montage SMB/NFS** (le WAL repose sur de la mémoire partagée et y est peu fiable). Ne jamais ouvrir `pac.db` depuis un poste via SMB pendant que le conteneur tourne.

## 8. Catch-up (rattrapage de l'historique)

Constat de la phase 0 : Magellan ne renvoie que la **dernière** valeur de chaque capacité (avec sa `modificationDate`). Aucun historique de températures, modes ou consignes n'est connu. En revanche, `GET /magellan/setups/<id>/consumptions?periodicity=daily` renvoie environ **32 jours glissants** de consommation journalière (2 catégories, HP/HC, coût). Le catch-up est conçu en trois niveaux, du garanti au fournisseur.

**Niveau A : détection et traçabilité des trous (toujours actif, aucune dépendance au fournisseur)**
- Au démarrage et après chaque série d'échecs, `GapDetector` calcule l'intervalle entre le dernier poll réussi et maintenant, et l'enregistre dans `gap` avec sa cause.
- Un poll immédiat est fait au démarrage (pas d'attente du prochain intervalle).
- Le front affiche les trous (zones hachurées) au lieu d'interpoler à tort. Les agrégats ignorent les trous au lieu de reporter la dernière valeur dessus (LOCF interrompu par les `gap`).

**Niveau B : réconciliation des compteurs cumulés (si la phase 0 en trouve)**
- Un compteur d'énergie cumulé conserve l'information à travers un trou : le premier delta après le trou couvre toute la période manquante.
- Ce delta est enregistré comme une mesure d'**intervalle** rattachée au `gap` (marquée `recovered`), sans être étalée artificiellement sur le trou : on ne fabrique pas de courbe, on conserve le total correct.

**Niveau C : historique fournisseur de l'énergie (confirmé en phase 0, via le port `HistorySource`)**
- Adaptateur `magellan` : `fetch_energy_days(since, until)` lit l'endpoint journalier. `CatchUp` l'appelle au démarrage, une fois par jour et après une panne. Upsert dans `energy_daily` : rejouable, sans doublons.
- Tout trou de moins de ~32 jours est comblé pour l'énergie, à la granularité **journalière**. Les `gap` correspondants sont marqués `recovered` pour l'énergie uniquement.
- Pour les autres mesures, **on ne fabrique rien** : les niveaux A et B restent la réponse honnête.

**Déclenchement du catch-up** : automatique au démarrage et après récupération d'une panne fournisseur ; manuel via `python -m app.adapters.inbound.cli catch-up [--since DATE]` (pas de route HTTP d'administration en v1, pas d'authentification). Une première exécution sur base vide tente aussi un backfill initial si une source existe.

## 9. API REST (v1, lecture seule)

| Route | Description |
|---|---|
| `GET /api/health` | HTTP 200 tant que le process vit ; corps : `poller_stale` (bool), dernier poll réussi, dernière erreur par type, compteurs d'erreurs, état de disponibilité des équipements, taille de la base, trous récents |
| `GET /api/equipment` | équipements connus |
| `GET /api/latest?equipment=...` | dernières valeurs par `metric_key`, avec âge de la donnée |
| `GET /api/series?equipment=...&metric=...&from=...&to=...&bucket=5m\|1h\|1d` | série agrégée (moyenne pondérée, min, max ; delta pour les compteurs), buckets journaliers en Europe/Paris ; renvoie aussi les `gap` de la période |
| `GET /api/gaps?from=...&to=...` | trous de collecte et leur statut de récupération |

`/api/events` (cycles de chauffe, démarrages) est **reportée après la phase 0** : on ne sait pas encore quelle mesure porte l'information. Elle sera définie comme un dérivé calculé par `CycleDetector` à partir des transitions d'une `metric_key` identifiée.

Pas d'authentification en v1 (LAN). Le statut HTTP de `/api/health` reste 200 même si le poller est en retard : avec `restart: unless-stopped`, un statut « unhealthy » ne relance rien, donc l'information utile est dans le corps.

## 10. Frontend

Pages :
1. **Vue d'ensemble** : température ECS, mode PAC, consigne, état, dernière mise à jour, disponibilité des équipements.
2. **Ballon / ECS** : courbe de température, cycles de chauffe, durée et fréquence.
3. **Chauffage** : températures (départ, retour, extérieure si dispo), consignes, mode.
4. **Historique** : sélecteur de période, superposition de plusieurs séries, zones de trou hachurées.
5. **Énergie** : si des compteurs existent (sinon masquer la page).

Le front manipule des `metric_key` logiques fournies par l'API, jamais des `capabilityId` Magellan. Libellés et unités viennent de l'API (`semantics.yaml` + catalogue). Design sobre, responsive, thème clair/sombre, rafraîchissement toutes les 60 s via TanStack Query, états d'erreur explicites (« données vieilles de X min », « passerelle indisponible »).

Routage : si le front utilise un routeur côté client, le backend doit servir `index.html` en repli pour toute route non-API (voir section 11).

## 11. Docker et déploiement sur le NAS Ugreen

**Dockerfile (multi-stage)**
1. Étape Node (`FROM --platform=$BUILDPLATFORM node:22-alpine`, le résultat est statique) : `npm ci && npm run build` (nécessite `package-lock.json`).
2. Étape `python:3.12-slim` : installer le backend depuis le lockfile, copier `frontend/dist` vers **`/app/static`** (variable `STATIC_DIR`), utilisateur non-root, `EXPOSE 8000`.
3. `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]` en forme exec (uvicorn est PID 1, SIGTERM bien géré), **un seul worker**.
4. `HEALTHCHECK` en Python (l'image slim n'a ni `curl` ni `wget`) : `python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"`.
5. `StaticFiles` monté **après** les routes `/api`, avec un handler de repli vers `index.html` pour le routage SPA.

**docker-compose.yml**
```yaml
services:
  pac-dashboard:
    build: .                        # ou image: registre/pac-dashboard:tag
    container_name: pac-dashboard
    restart: unless-stopped
    user: "1000:10"                 # UID:GID du propriétaire du dossier sur le NAS
    env_file: .env
    environment:
      TZ: Europe/Paris
    ports:
      - "8080:8000"
    volumes:
      - /volume1/docker/pac-dashboard:/data   # disque LOCAL du NAS, pas un montage réseau
    stop_grace_period: 30s          # une requête Magellan peut prendre jusqu'à 30 s (timeout)
    logging:
      driver: json-file
      options: { max-size: "10m", max-file: "3" }
```

**Points d'attention NAS**
- `user: "UID:GID"` est le **seul** mécanisme de permissions retenu (pas de `PUID`/`PGID`, qui supposent un entrypoint de changement d'utilisateur). SQLite doit pouvoir écrire dans le **dossier** `/data` (création de `-wal` et `-shm`), pas seulement dans le fichier.
- **Sauvegarde intégrée** : tâche quotidienne dans l'application (`VACUUM INTO '/data/backup/pac-YYYY-MM-DD.db'`), rotation sur `BACKUP_KEEP` jours. La CLI `sqlite3` n'est pas dans l'image. Une copie sur le même volume ne protège pas d'une panne disque : prévoir en plus une sauvegarde NAS du dossier `backup/` vers un autre support.
- Deux voies de déploiement : build sur le NAS (`docker compose up -d --build`) ou build sur le poste puis registre. La seconde est préférable si le NAS est ARM ou lent.
- L'interface Docker/Compose d'UGOS varie selon la version : valider l'import du compose ou la création manuelle du conteneur avec les mêmes paramètres. Je ne sais pas si les secrets de compose sont acceptés.
- Accès : `http://IP-DU-NAS:8080`. Pas d'exposition hors LAN sans reverse proxy avec authentification.

## 12. Plan d'implémentation par phases

Un agent doit **s'arrêter** à chaque fin de phase marquée « ⏸ » et me montrer le résultat.

**Phase 0 : découverte et sonde ⏸ (bloquante)**
- `backend/scripts/discover_magellan.py` : connexion Magellan, liste des équipements, dump complet (setup, capacités, catalogue, consommations) dans `discover_magellan_output.json`, **hors git** (`.gitignore`).
- Version anonymisée commitée comme **fixture de test**.
- **Statut (18/10/2026) : terminée.** Compte absent d'Overkiz ; sonde `scripts/discover_magellan.py` exécutée, conclusions dans `docs/phase0-findings.md`, révision 3 du plan validée.
- Livrable : `docs/phase0-findings.md` couvrant :
  1. liste des équipements (`deviceId`, `modelId`, `productId`, slot, zone) ;
  2. liste des états utiles avec **type et unité** (ECS, PAC, températures, consigne, mode, consommation) ;
  3. **fraîcheur** : rythme de mise à jour des capacités (`modificationDate`) ;
  4. compteurs d'énergie cumulés ou non, unité ;
  5. **sonde catch-up** : existe-t-il une source d'historique exploitable (section 8, niveau C) ? Conclusion nette.
  6. proposition de `semantics.yaml` et d'ajustements du schéma de la section 7.
- Sortie : **je valide** les ajustements ; l'agent ne modifie pas ce `PLAN.md` de lui-même.

**Phase 1 : domaine et application (sans réseau ni base) ⏸**
- `domain/` complet, `application/ports/`, cas d'usage `CollectSamples`, `CatchUp` (niveaux A/B), requêtes, avec adaptateurs `fake` et `fixed clock`.
- Contrats `import-linter` en place dès cette phase.
- Critères : tests de domaine verts (ChangeDetector, SeriesAggregator avec LOCF et deltas, passage heure d'été/hiver, GapDetector), contrats d'architecture verts.

**Phase 2 : adaptateurs sortants et collecte réelle**
- `adapters/outbound/sqlite/` (migrations par `user_version`, repositories, pragmas par connexion, backup `VACUUM INTO`, purge).
- `adapters/outbound/magellan/` (client, mapper, `semantics.yaml`, catalogue, consommations journalières, traduction d'erreurs, stratégie d'appel de la section 3.4) et tests de contrat sur fixtures.
- `scheduler.py` : boucle avec try/except global, **référence conservée à la tâche** et `add_done_callback` qui journalise (une exception ne doit pas tuer la tâche en silence), jitter, backoff selon le type d'erreur, arrêt net sur `CredentialsRejected`, annulation propre à l'arrêt.
- **Dockerfile minimal dès cette phase** pour lancer le test de 24 h **sur le NAS**.
- Critères : 24 h sans erreur non gérée ; aucun point en double `(équipement, métrique, ts)` ; chaque point correspond à une `modificationDate` fournisseur distincte ; un redémarrage du conteneur ne crée pas de doublons ; un trou provoqué (coupure réseau) apparaît dans `gap`.

**Phase 3 : API REST**
- Routes de la section 9, lifespan (client créé dans le lifespan, un seul worker, état du poller dans `/api/health`).
- Tests pytest avec gateway `fake` et base temporaire.

**Phase 4 : frontend ⏸**
- Pages 1 à 4, puis 5 si des compteurs existent ; zones de trou ; repli SPA.
- Critère : utilisable sur desktop et mobile, états d'erreur gérés.

**Phase 5 : conteneurisation finale**
- Dockerfile complet (multi-stage, healthcheck Python, lockfiles, `STATIC_DIR`), compose, README de déploiement (variables, build, NAS, sauvegarde).
- Critère : persistance après redémarrage du conteneur sur le NAS ; restauration d'une sauvegarde testée.

**Phase 6 (optionnelle) : commandes**
- Nouveau port sortant `CommandGateway` (jamais d'appel direct à Magellan depuis l'application ; écriture via `/magellan/executions/writecapability`), authentification, journal des commandes. Seulement après une période de lecture seule stable.

## 13. Sécurité

- Identifiants en variables d'environnement uniquement, `.env` en `600`, jamais dans l'image ni dans git.
- Conteneur non-root, port exposé sur le LAN uniquement.
- Aucune exposition Internet sans reverse proxy authentifié (obligatoire dès la phase 6).
- Ne jamais logger mot de passe, jetons, nom d'utilisateur, `deviceId`, `setupId`, numéros de série : utiliser `EquipmentId` dans les logs et les réponses d'API. Anonymiser les dumps avec `discover_magellan.py` (masque aussi les capacités identifiantes : numéros de série, noms, prix).

## 14. Consignes pour l'agent Claude Code

- Phase 0 terminée. Enchaîner les phases dans l'ordre et **s'arrêter** à chaque « ⏸ ». Ne modifier `PLAN.md` qu'avec l'accord explicite du propriétaire.
- Avant d'écrire du code Magellan, s'appuyer sur le dump réel et la fixture, pas sur sa mémoire : l'API n'est pas documentée.
- Respecter la règle de dépendance : le domaine n'importe rien d'extérieur. Les contrats `import-linter` doivent rester verts.
- Tout accès HTTP fournisseur reste dans `adapters/outbound/magellan/`. Tout accès SQLite dans `adapters/outbound/sqlite/`.
- Ne jamais inventer de données pour combler un trou : un trou reste un trou, sauf source d'historique réelle (section 8).
- Ne jamais inclure de vrais identifiants dans le code, les tests, les fixtures ou les logs.
- Écrire les tests de chaque phase avant de passer à la suivante. Lint et tests verts avant tout commit.
- Rester simple : pas d'abstraction, de framework ou de dépendance non justifiés par ce plan (pas d'Alembic, pas de conteneur d'injection).
- Documenter dans le README : variables d'environnement, build, déploiement NAS, sauvegarde et restauration, catch-up manuel.
