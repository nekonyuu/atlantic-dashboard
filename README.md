# Dashboard PAC Atlantic

Dashboard personnel pour une pompe à chaleur **Atlantic Alfea Excellia S** et son ballon d'eau chaude,
plus lisible que l'application Cozytouch, avec un **historique durable**.

- Collecte en continu (lecture seule) depuis le cloud **Magellan** d'Atlantic, celui de l'app Cozytouch.
- Historique dans SQLite, trous de collecte rendus visibles et jamais comblés par des valeurs inventées.
- Rattrapage des consommations électriques journalières (environ 32 jours) fournies par Atlantic.
- Un seul conteneur Docker (API FastAPI + front React), prévu pour un NAS, accessible sur le LAN.

> L'API Magellan n'est pas officielle : elle peut changer sans préavis. Tout ce qui en dépend est isolé dans
> `backend/app/adapters/outbound/magellan/` (voir `PLAN.md`, `docs/phase0-findings.md`).

## Sommaire

1. [Déploiement sur le NAS](#déploiement-sur-le-nas)
2. [Variables d'environnement](#variables-denvironnement)
3. [Mise à jour](#mise-à-jour)
4. [Sauvegarde et restauration](#sauvegarde-et-restauration)
5. [Commandes d'exploitation](#commandes-dexploitation)
6. [Développement](#développement)
7. [Image Docker et CI](#image-docker-et-ci)
8. [Sécurité](#sécurité)
9. [Dépannage](#dépannage)

## Déploiement sur le NAS

L'image est publiée par GitHub Actions sur `ghcr.io/nekonyuu/atlantic-dashboard` (amd64 et arm64).

1. **Dossier de données** sur un disque **local** du NAS (jamais un montage SMB/NFS : SQLite en WAL y est
   peu fiable), par exemple `/volume1/docker/pac-dashboard`. Le conteneur doit pouvoir écrire dans le
   **dossier** (création de `pac.db-wal` et `pac.db-shm`), pas seulement dans le fichier.
   **Créez-le avant le premier démarrage** : sinon Docker le crée en `root` et l'application ne peut pas
   y écrire. Puis alignez propriétaire et utilisateur du conteneur :
   ```sh
   sudo mkdir -p /volume1/docker/pac-dashboard
   sudo chown -R 1000:10 /volume1/docker/pac-dashboard   # ou votre UID:GID (`id`) reporté dans `user:`
   ```
2. **Fichiers** : copiez `docker-compose.yml` et `.env.example` dans un dossier du NAS, renommez
   `.env.example` en `.env`, renseignez vos identifiants Cozytouch, puis `chmod 600 .env`.
3. **Accès à l'image** : les paquets GHCR sont **privés** par défaut. Soit vous rendez le paquet public
   (GitHub → Packages → `atlantic-dashboard` → Package settings → Change visibility), soit vous vous
   connectez une fois depuis le NAS avec un jeton GitHub ayant le droit `read:packages` :
   ```sh
   echo "<jeton>" | docker login ghcr.io -u nekonyuu --password-stdin
   ```
4. **Démarrage** :
   ```sh
   docker compose pull && docker compose up -d
   docker compose logs -f
   ```
   Le premier cycle de collecte a lieu immédiatement. Ouvrez `http://IP-DU-NAS:8080`.

L'interface Docker d'UGOS varie selon les versions : si l'import du compose n'est pas possible, créez le
conteneur à la main avec les mêmes paramètres (image, utilisateur, port 8080→8000, volume `/data`,
fichier d'environnement, `TZ=Europe/Paris`, redémarrage « sauf arrêt »).

**Architecture du NAS** : les Ugreen DXP sont en x86-64 (`linux/amd64`) ; l'image arm64 existe aussi.

## Variables d'environnement

| Variable | Rôle | Défaut |
|---|---|---|
| `COZYTOUCH_USERNAME` / `COZYTOUCH_PASSWORD` | identifiants de l'app Cozytouch | requis |
| `POLL_INTERVAL_SECONDS` | période de collecte (minimum 60) | `300` |
| `DB_PATH` | base SQLite | `/data/pac.db` |
| `BACKUP_DIR` / `BACKUP_KEEP` | sauvegardes quotidiennes et nombre conservé | `/data/backup` / `14` |
| `RETENTION_DAYS_RAW` | purge des points bruts après agrégation horaire (0 = jamais) | `0` |
| `STATIC_DIR` | front compilé dans l'image | `/app/static` |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR` | `INFO` |
| `PAC_IMAGE` | image utilisée par le compose | `ghcr.io/nekonyuu/atlantic-dashboard:latest` |

Le fuseau `TZ=Europe/Paris` du compose ne sert qu'aux logs : la base est en UTC et les journées sont
calculées en `Europe/Paris` par l'application.

Si les identifiants sont refusés, la collecte **s'arrête** (pas de nouvelle tentative, pour éviter un
blocage du compte) : corrigez `.env` puis `docker compose up -d`.

## Mise à jour

```sh
docker compose exec pac-dashboard python -m app.adapters.inbound.cli backup   # précaution
docker compose pull && docker compose up -d
```

Les migrations de schéma s'appliquent automatiquement au démarrage. Pour figer une version, utilisez un
tag publié (`PAC_IMAGE=ghcr.io/nekonyuu/atlantic-dashboard:1.2.0` ou `:sha-abc1234`) plutôt que `latest`.

## Sauvegarde et restauration

**Sauvegarde automatique** : une fois par jour, l'application écrit `/data/backup/pac-AAAA-MM-JJ.db`
(`VACUUM INTO`, cohérent même pendant la collecte) et garde les `BACKUP_KEEP` plus récentes.
Sauvegarde immédiate :

```sh
docker compose exec pac-dashboard python -m app.adapters.inbound.cli backup
```

Une copie sur le même disque ne protège pas d'une panne disque : programmez en plus une sauvegarde du
dossier `backup/` vers un autre support (tâche de sauvegarde du NAS, disque USB, cloud).

**Restauration** (procédure testée) :

```sh
docker compose stop
cd /volume1/docker/pac-dashboard
mv pac.db pac.db.avant-restauration
rm -f pac.db-wal pac.db-shm                 # indispensable : WAL de l'ancienne base
cp backup/pac-AAAA-MM-JJ.db pac.db
docker compose start
```

Ne copiez ni n'ouvrez jamais `pac.db` depuis un poste via SMB pendant que le conteneur tourne.

## Commandes d'exploitation

Toutes s'exécutent dans le conteneur : `docker compose exec pac-dashboard python -m app.adapters.inbound.cli <commande>`.

| Commande | Effet |
|---|---|
| `catch-up [--since AAAA-MM-JJ]` | rattrape les consommations journalières fournies par Atlantic (≈ 32 jours au plus). Aucun autre historique n'existe côté fournisseur : les trous de températures restent des trous. |
| `discover` | lance un cycle de collecte et affiche équipements et dernières valeurs |
| `backup` | sauvegarde immédiate (aucun appel au fournisseur) |

Codes de sortie : `2` configuration invalide, `3` identifiants refusés, `4` erreur du fournisseur.

Le catch-up s'exécute aussi tout seul au démarrage, une fois par jour et après chaque panne.

`GET /api/health` répond toujours 200 tant que le process vit ; l'état de la collecte est dans le corps
(`poller.stale`, dernière collecte réussie, erreurs par type, trous récents).

## Développement

Outils gérés par [mise](https://mise.jdx.dev) (`mise.toml` : Python 3.12, Node 22, uv) :

```sh
mise install
cd backend && uv sync && uv run pytest          # 200+ tests, dont les contrats d'architecture
cd frontend && npm ci && npm test
```

Front sans cloud ni identifiants, sur une base temporaire (données de la phase 0 anonymisées et
historique **synthétique**) :

```sh
cd backend && uv run python scripts/demo_server.py --port 8765
cd frontend && API_URL=http://127.0.0.1:8765 npm run dev
```

Avec la vraie API (identifiants dans `.env`) :

```sh
cd backend && set -a && source ../.env && set +a && DB_PATH=./dev.db BACKUP_DIR=./backup uv run uvicorn app.main:app
cd frontend && npm run dev
```

Lint et tests doivent passer avant chaque commit :

```sh
cd backend && uv run ruff check . && uv run ruff format --check . && uv run pytest -q
cd frontend && npx tsc -b && npm test
```

Architecture : hexagonale + DDD (`PLAN.md` §3). Le domaine (`backend/app/domain`) n'importe que la
bibliothèque standard ; les règles de dépendance sont vérifiées par `import-linter` dans les tests.

## Image Docker et CI

`.github/workflows/ci.yml` :

- à chaque push et PR : lint + tests backend (ruff, pytest, import-linter) et frontend (tsc, vitest, build) ;
- puis construction de l'image `linux/amd64` + `linux/arm64` ;
- publication sur `ghcr.io/nekonyuu/atlantic-dashboard` depuis `main` (`latest`, `sha-xxxxxxx`) et
  depuis les tags `vX.Y.Z` (`X.Y.Z`, `X.Y`) ; les PR construisent sans publier.

Publier une version :

```sh
git tag v1.0.0 && git push origin v1.0.0
```

Aucun secret à configurer : le workflow publie avec le `GITHUB_TOKEN` du dépôt (droit `packages: write`).

Construction locale : `docker build -t pac-dashboard .`

## Sécurité

- Identifiants uniquement dans `.env` (permissions `600`), jamais dans l'image ni dans git.
  Ils restent visibles via `docker inspect` : limitez l'accès à l'interface Docker du NAS.
- Conteneur non-root, LAN uniquement, sans authentification : **ne l'exposez pas sur Internet** sans
  reverse proxy authentifié.
- Les logs et l'API n'exposent ni identifiants, ni jetons, ni identifiants d'appareil Atlantic.

## Dépannage

| Symptôme | Piste |
|---|---|
| Bandeau « Collecte arrêtée : identifiants refusés » | corriger `.env`, puis `docker compose up -d` |
| Bandeau « Cloud Atlantic indisponible » | panne ou limitation côté Atlantic ; reprise automatique (backoff jusqu'à 1 h) |
| « Stockage inaccessible : /data n'est pas accessible en écriture » | `sudo chown -R 1000:10 /volume1/docker/pac-dashboard` (ou l'UID:GID de `user:`), puis `docker compose up -d` |
| `denied` au `docker compose pull` | paquet GHCR privé : le rendre public ou `docker login ghcr.io` |
| Page Énergie absente | Atlantic ne déclare pas encore de consommation pour l'installation |
