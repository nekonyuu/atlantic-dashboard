# Phase 0 — Découverte

## 0. Constat bloquant : le compte n'existe pas chez Overkiz (18/10/2026)
`scripts/discover.py` : jeton Atlantic et JWT obtenus, puis `UnknownUserError: No such user account` au login Overkiz.
Cause : l'installation (Alfea Excellia S + thermostat Navilink 228, **sans box Cozytouch**) n'existe que sur le cloud **Magellan** d'Atlantic (`apis.groupe-atlantic.com`). Résultat identique documenté par `mathieuletyrant/cozytouch-hacs` (`docs/api-surface.md`, « The Overkiz plane is reachable, and empty for us ») et par `NicolasYDDER/homey-cozytouch` (« 401 No such user account » attendu pour les comptes Magellan seuls).
**Conséquence : `pyoverkiz` est inutilisable pour cette installation.** Révision du plan à décider par le propriétaire.

## 0 bis. Ce que la recherche établit sur Magellan (non vérifié sur notre compte)
Sources : `mathieuletyrant/cozytouch-hacs` (intégration HA Python, active, dernier commit 06/10/2026, aucune licence trouvée → ne pas copier de code, seulement s'inspirer du comportement), `NicolasYDDER/homey-cozytouch`.
- Auth : `POST /users/token` (password grant, `GA-PRIVATEPERSON/<email>`, même client ID que pyoverkiz), `expires_in` ≈ 3600 s. `invalid_grant` = identifiants refusés.
- Lecture : `GET /magellan/cozytouch/setupviewv2` renvoie **tout le setup en un appel** (équipements + capacités). C'est ce que cozytouch-hacs interroge à chaque cycle (60 s par défaut).
- Par équipement : `GET /magellan/capabilities/?deviceId=<id>`.
- Une capacité = `{capabilityId, value (texte), modificationDate (epoch)}`, **sans nom, type ni unité** : la correspondance vient d'un travail de rétro-ingénierie, et du catalogue `GET /magellan/productmodels/capabilities` (405 entrées).
- Quota : `rateLimit` déclaré dans le setup (30 sur un compte observé, unité inconnue, lue comme req/min). Aucun 429 observé publiquement ; backoff 300 s par défaut.
- **Alfea Excellia S** (issue gduteil/cozytouch#173) : 5 équipements : interface `CESA V2` (modelId 1691, consommation, température extérieure, code erreur), générateur `GENERATOR_0` (1391, heures/démarrages pompe chauffage et ECS, pression, débit, température départ), circuits `TESC_0/1` (1388/1389), pièce `ROOM_0` (557). ECS probablement en slot `DHW_0` (1376). Sens de la capacité 109 (eau du circuit ou ambiance) encore ouvert.
- **Catch-up niveau C : candidat sérieux** : `GET /magellan/setups/<setupId>/consumptions?periodicity=daily` renvoie des séries journalières (`date` minuit UTC, `consumedQuantity`, kWh, heures pleines/creuses, coût). Jamais vu répondre par cozytouch-hacs lui-même ; source : un fork sur une autre PAC. Profondeur d'historique inconnue.
- Pas d'historique de mesures instantanées (températures) identifié.

Sonde : `backend/scripts/discover_magellan.py` (~10 GET, arrêt sur 429). Résultats ci-dessous.

> Statut : **en attente des données réelles**. Rien n'est inventé ici ; chaque section sera remplie à partir de `discover_output.json`.

## Résultats de la sonde Magellan (18/10/2026, 22:05)
`scripts/discover_magellan.py` : 9 requêtes, aucun 429, `rateLimit=30` déclaré, jeton valable **28 800 s (8 h)**. Fixture : `backend/tests/fixtures/magellan_anonymized.json` (numéros de série, noms, prix, identifiants masqués ; vérifié par recherche des valeurs brutes).

## 1. Équipements
Une passerelle (`type 1000`, le Navilink), 3 zones, **5 équipements**, tous `isAvailable=true` :

| Rôle | slot | modelId | productId | zone | Capacités |
|---|---|---:|---:|---|---:|
| Interface PAC (CESA V2) | — | **1693** | 54 | technique (type 2) | 52 |
| Générateur | `GENERATOR_0` | 1391 | 58 | technique | 13 |
| Ballon ECS | `DHW_0` | 1376 | 47 | technique | 44 |
| Circuit chauffage 1 | `TESC_0` | 1388 | 55 | circuit (type 29) | 4 |
| Pièce / thermostat | `ROOM_0` | 557 | 26 | pièce (type 1) | 75 |

modelId 1693 diffère du 1691 documenté pour l'Excellia S (variante probable ; même structure que l'issue gduteil/cozytouch#173).
Pas de `controllable_name` / `ui_class` / `widget` (vocabulaire Overkiz) : l'identité est `(deviceId, modelId, productId)`.

## 2. États utiles
Valeurs en texte ; **noms, types et unités fournis par le catalogue** `GET /magellan/productmodels/capabilities` (407 entrées : `name`, `description`, `type`, `unit`, `resolution`, `min`, `max`, `enum` avec libellés). Plus besoin de deviner : le mapping se dérive du catalogue.

| capabilityId | Nom catalogue | Équipement | Unité | Valeur observée |
|---:|---|---|---|---|
| 111 | DHW_CurrentTemperature | ECS | °C | 53.17 |
| 22 / 312 | DHW_WaterSetpoint / WaterControlSetpoint | ECS | °C | 55 |
| 99 | DHW_HeatHotWaterStatus (enum) | ECS | — | 0 |
| 86 | DHW_ServiceOn | ECS | bool | 1 |
| 165 | DHW_BoostOn | ECS | bool | 0 |
| 105906 | DHW_V40StateOfChargeSetpoint | ECS | % | 81 |
| 119 | HOME_OutsideTempSensor | interface | °C | 10.02 |
| 91 | GENERATORStatus (enum) | interface | — | 1 = Heat |
| 109 | GENERATOR_WaterOut1 (départ) | générateur | °C | 26.13 |
| 116 | GENRATOR_WaterReturn (retour) | générateur | °C | 26.77 |
| 100 | GENERATOR_WaterCircuitHeating | générateur | bar | 1.36 |
| 112 | CirculatorFlowRate | interface | l/min | 0 |
| 50 | GENERATOR_ModulationLevel | générateur | % | 0 |
| 117 | ROOM1_AmbientRoom | pièce | °C | 20.69 |
| 17 / 40 | ROOM1_ControlSetpoint / SystemHeatSetpoint | pièce | °C | 19 |
| 181 | ROOM1_ThermostatOperatingMode (enum) | pièce | — | 4 = Heat |
| 184 | ROOM1_SystemSetpointMode (enum) | pièce | — | 1 = PROG |
| 153 | ROOM1_HeatCoolOnGoing (enum) | pièce | — | 0 = No |
| 19 | TESC1_NrjFlowSetpointRequest | circuit | °C | 20 |
| 180 / 150 / 182 | codes erreur, nb erreurs actives | interface | — | 100 = OK / 0 |
| 179 | WIFI_LevelRSSI | interface | dB | -57 |

Les compteurs du générateur (25, 26, 28, 29 : démarrages et heures de fonctionnement) valent 0 et n'ont jamais changé (âge ≈ 100 jours) : non alimentés sur cette installation.
Le drapeau `isSensitiveData` du catalogue couvre aussi des températures (111, 117) : il ne sert pas à décider de l'anonymisation.

## 3. Fraîcheur
- Chaque capacité porte une `modificationDate`. Âges observés : ambiance 0,2 h, départ 1 h, ECS 1,1 h, extérieure 1,5 h, consommations 3 à 7 h.
- **Aucune** `modificationDate` n'a changé entre deux lectures à 3 min d'intervalle. Les valeurs semblent poussées sur changement significatif, pas en continu.
- `setupviewv2` et `/magellan/capabilities/?deviceId=` renvoient le même nombre de capacités : **un seul `setupviewv2` par cycle suffit**.
- Pas d'écouteur d'événements sur Magellan.
- Conséquence : stocker l'**instant de mesure = `modificationDate`**, pas l'heure du poll. Un poll toutes les 5 min (défaut du plan) est largement suffisant, et 30 req/min ne seront jamais approchées.
- À confirmer : mesure sur 24 h (phase 2).

## 4. Compteurs d'énergie
- **Cumulés** sur l'interface : 57 `HOME_ElecHeatConsumptionCumulated` = 102040, 59 `HOME_ElecDHWConsumptionCumulated` = 190432 (catalogue : unité kWh, résolution 0,001, donc probablement **des Wh**, soit 102 et 190 kWh depuis la mise en service, il y a environ 100 jours d'après les âges). 60 (total) = null.
- **Journaliers** : `GET /magellan/setups/<id>/consumptions?periodicity=daily` → HTTP 200, **2 séries** (`category` 1 et 2, `type 1` électricité kWh), 64 périodes chacune, du **17/09 au 18/10/2026** (~32 jours glissants), découpées `mode` 1 / 2 (heures pleines / creuses, d'après cozytouch-hacs) avec coût en €. Totaux sur 32 j : cat. 1 = 71,66 kWh, cat. 2 = 86,94 kWh.
- **Confirmé par le propriétaire (19/10/2026)** : catégorie 1 = chauffage, catégorie 2 = eau chaude, d'après les profils de consommation observés.

## 5. Sonde catch-up (niveau C)
**Conclusion : source exploitable pour l'énergie, aucune source pour les mesures instantanées.**
- Énergie : l'endpoint journalier fournit ~32 jours d'historique par appel. Un appel quotidien, puis un upsert idempotent `origin='backfill'`, comble tout trou de moins d'un mois, à la granularité **journalière** (et non horaire).
- Compteurs cumulés 57 et 59 : le niveau B (delta à travers un trou) s'applique tel que prévu.
- Températures, modes, consignes : seule la dernière valeur est disponible, avec sa `modificationDate`. Aucun endpoint d'historique n'est connu. Les trous restent des trous (niveau A).

## 6. Propositions (à valider ; `PLAN.md` non modifié)
**Révision d'architecture**
- Remplacer l'adaptateur `overkiz/` par `adapters/outbound/magellan/` (aiohttp, déjà dépendance directe). Les ports, le domaine, SQLite, l'API et le front ne changent pas.
- Stratégie d'appel :
  - 1 `setupviewv2` par cycle (5 min) ;
  - jeton réutilisé jusqu'à expiration (8 h) ;
  - `consumptions?periodicity=daily` 1 fois par jour et au démarrage ;
  - catalogue : 1 fois au démarrage, mis en cache dans la base.
- Erreurs :
  - `invalid_grant` → `CredentialsRejected`, arrêt ;
  - 429 → `ProviderThrottled`, `Retry-After` sinon 300 s ;
  - 5xx ou timeout → `ProviderUnavailable`, backoff exponentiel ;
  - 401 → renouvellement du jeton une fois.
- Sous-section `HistorySource` : adaptateur Magellan *consommations journalières* (niveau C réel).

**`semantics.yaml` (proposition)**, clé `(slot, capabilityId)` :
```yaml
dhw:     {slot: DHW_0,  metrics: {dhw_temperature: 111, dhw_setpoint: 22, dhw_status: 99, dhw_on: 86, dhw_boost: 165, dhw_charge_setpoint: 105906}}
heatpump:{slot: CESA,   metrics: {outdoor_temperature: 119, generator_status: 91, circulator_flow: 112, energy_heating_cumulative: 57, energy_dhw_cumulative: 59, error_code: 180, active_errors: 182, wifi_rssi: 179}}
generator:{slot: GENERATOR_0, metrics: {flow_temperature: 109, return_temperature: 116, water_pressure: 100, modulation: 50}}
circuit1:{slot: TESC_0, metrics: {flow_setpoint: 19}}
room1:   {slot: ROOM_0, metrics: {room_temperature: 117, room_setpoint: 17, thermostat_mode: 181, setpoint_mode: 184, heating_ongoing: 153}}
```
Unités, types, plages et libellés d'enum sont lus dans le catalogue, et non recopiés.

**Schéma §7**
- `equipment` : remplacer `device_url` / `controllable` / `ui_class` / `widget` par `device_id`, `model_id`, `product_id`, `slot`, `zone_id`.
- `measurement.ts` = `modificationDate` du fournisseur. Ajouter `polled_at` pour distinguer une valeur stable d'un trou.
- Nouvelle table `energy_daily(day, category, mode, kwh, cost, origin)`, `PRIMARY KEY (day, category, mode)`.
- Nouvelle table `capability_catalogue(id, name, type, unit, resolution, enum_json)`.

**Ouvert**
- Rythme réel de mise à jour des capacités (24 h de collecte).
- Unité de `rateLimit`.

## Historique
- `pyoverkiz` 2.2.2 a été essayé puis retiré (compte absent d'Overkiz, §0).
