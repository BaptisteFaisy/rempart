# Tests de performance — ENF-PERF-01

Ce dossier rend **mesurable** l'exigence non fonctionnelle ENF-PERF-01 du cahier
des charges (chapitre 10) :

> « Tri de 50 failles en moins de 5 minutes. Page du portail en moins de 2 secondes. »

Avant ces tests, cette exigence était une affirmation gratuite : rien dans le
dépôt ne la prouvait. Ici, la moitié « tri de 50 failles » est mesurée à chaque
exécution de la suite. La moitié « page du portail en moins de 2 secondes »
n'est **pas** mesurée ici (voir « Ce qui n'est pas mesuré »).

- `test_triage_throughput.py` — chaîne complète de tri sur 50 failles réalistes
  (`collect_findings` → `run_triage` → `enforce`), exactitude sur le volume,
  coût marginal de la recherche de doublons.
- `test_kpis_throughput.py` — `compute_kpis` et `freeze_month` sur un mois
  réaliste (5 applications, 50 tests, 200 failles), exactitude vérifiée par un
  calcul indépendant.
- `conftest.py` — générateurs de données déterministes et harnais de mesure
  (aucune duplication entre les deux fichiers de tests).

## Exécuter

```bash
cd backend
../.venv/bin/python -m pytest tests/performance -q --durations=10
```

Pas de marker `pytest` personnalisé : `backend/pyproject.toml` est hors de la
zone de ce travail, et un marker non enregistré produirait un avertissement.
Les tests sont assez rapides (≈ 0,2 s au total) pour rester dans la suite
normale : la suite complète passe de ~10-13 s à ~10-13 s (voir plus bas).

## Mesures

Machine de référence : **i5-11600K @ 3,90 GHz (12 cœurs), Linux 6.14.0-37,
Python 3.12.3, 2026-11-11**. Fakes en mémoire (`FakeStore`,
`FakeSecurityAgentClient`, `FakeGitHub`), aucun réseau, aucun AWS, chemin
déterministe de l'agent de tri (pas de modèle). Chaque chiffre est le **minimum
de 5 à 7 répétitions**, seed des données exclu de la fenêtre de mesure.

### Chaîne de tri complète (intake + agent de tri + garde-fous)

| Failles brutes | Total | dont intake | dont tri + garde-fous | Propositions |
|---|---|---|---|---|
| 50 | **2,53 ms** | 1,25 ms | 1,24 ms | 47 (+2 doublons, 1 régression) |
| 100 | 6,25 ms | 2,64 ms | 3,55 ms | 97 |
| 200 | 29,8 ms | 14,7 ms | 15,0 ms | 197 |
| 400 | 49,8 ms | 18,0 ms | 31,6 ms | 397 |

Dispersion sur 9 mesures indépendantes du lot de 50 (seed inclus) :
min 5,7 ms / médiane 7,5 ms / max 14,0 ms.

**L'exigence de 300 s est respectée avec une marge d'environ 100 000×** sur le
chemin déterministe : 50 failles sont triées en ~2,5 ms. Même à 400 failles
(50 ms) la marge reste de ~6 000×.

### Coût marginal de la recherche de doublons (`find_by_fingerprint`)

50 recherches d'empreintes, en faisant varier le nombre de failles déjà connues :

| Failles connues | 50 recherches | Coût unitaire |
|---|---|---|
| 0 | 0,030 ms | 0,6 µs |
| 50 | **0,140 ms** | 2,8 µs |
| 200 | **0,483 ms** | 9,7 µs |
| 800 | 2,01 ms | 40,2 µs |

De 50 à 200 failles connues (volume ×4), le coût est multiplié par **×3,4** :
la recherche est **linéaire en fonction du volume connu**, donc l'intake d'un
lot de *n* failles sur une base de *m* failles est en **O(n × m)**. Ce n'est pas
quadratique au sens strict (le lot ne grandit pas la base de façon cumulative
dans ce scénario), mais c'est bien le point de contention : en production,
chaque recherche est un aller-retour DynamoDB, pas un parcours mémoire.

### KPI mensuels (`compute_kpis`, `freeze_month`)

| Volume | `compute_kpis` | `freeze_month` |
|---|---|---|
| 200 failles / 50 runs / 5 apps | **1,02 ms** (méd. 1,48 ; max 6,14) | **2,30 ms** (méd. 4,98 ; max 6,29) |
| 800 failles / 200 runs / 20 apps | 6,78 ms (×6,6) | 16,3 ms (×7,1) |

Croissance ×6,6 pour un volume ×4 : quasi linéaire, avec le terme
`applications_detail` en O(applications × failles ouvertes).

### Coût annexe mesuré : l'import lazy de Strands

`run_triage` appelle `_strands_available()`, qui fait `import strands` au premier
appel : **2,4 s à 4,2 s** selon l'état du cache disque. Ce coût unique n'est pas
du tri et ne menace pas le budget de 5 minutes, mais il pèse sur le **cold start**
d'une Lambda de tri. Le harnais le paie volontairement hors mesure
(`warm_optional_imports`, fixture de session) pour ne pas fausser les chiffres.

### Impact sur la durée de la suite

Mesures alternées (3 paires, machine partagée avec d'autres chantiers — d'où la
dispersion) :

| Commande | Durées observées |
|---|---|
| `pytest tests -q --ignore=tests/performance` | 9,7 s / 10,4 s / 12,9 s |
| `pytest tests -q` (avec ce dossier) | 9,5 s / 10,7 s / 11,3 s |

`pytest tests/performance -q --durations=10` seul : **~1,3 s**, dont ~1,0-1,2 s
d'import de Strands (déjà payé par `tests/triage/test_agent.py` dans la suite
complète) ; les 8 tests eux-mêmes totalisent **≈ 0,15 s**. La suite complète
reste très loin des 5 minutes.

Robustesse vérifiée : 5 exécutions consécutives au repos, puis 3 exécutions
avec 8 processus saturant le CPU → **tout vert dans les deux cas** (les durées
montent jusqu'à ~0,7 s par test sous charge, toujours sous les seuils).

## Seuils retenus et justification

| Test | Mesuré (pire cas) | Seuil | Marge |
|---|---|---|---|
| Tri de 50 failles | 2,5 ms (14 ms seed inclus) | **1,0 s** | ~70× le pire observé, 300× sous les 300 s du contrat |
| Tri de 200 failles | 30 ms | **1,0 s** | ~33× |
| Croissance du tri (×4 volume) | ×5,5 à ×13 | **×100** | ~8× le pire ratio observé |
| 50 recherches d'empreinte | 0,14 / 0,48 ms | **0,5 s** | ~1 000× |
| Croissance des recherches (×4 base) | ×3,4 | **×20** | ~6× |
| `compute_kpis` (200/50) | 1,0 ms (max 6,1 ms) | **0,5 s** | ~80× |
| `freeze_month` (200/50) | 2,3 ms (max 19,5 ms) | **2,0 s** | ~100× |
| Croissance des KPI (×4 volume) | ×6,6 | **×60** | ~9× |

Pourquoi pas 300 s, la lettre de l'exigence ? Un seuil calé sur le contrat ne
détecterait aucune régression : il faudrait que le tri devienne 100 000 fois
plus lent pour rougir. Pourquoi pas 30 ms, soit 10× la mesure ? Parce que ces
tests tournent sur des runners partagés : sous charge CPU, les mêmes mesures
montent d'un facteur 20 à 50. Les seuils ci-dessus sont donc **assez serrés
pour signaler une dégradation d'ordre de grandeur, assez larges pour ne pas
rendre la CI aléatoire**. Les assertions de croissance (volume ×4) sont le
véritable filet algorithmique ; les budgets absolus sont l'alarme anti-explosion.

Tous les ratios utilisent un plancher de 0,1 ms (`TIME_FLOOR`) pour qu'une
mesure quasi nulle ne produise pas un ratio infini.

## Ce qui n'est PAS mesuré ici

- **La page du portail en moins de 2 s** (seconde moitié d'ENF-PERF-01) : c'est
  une latence de bout en bout — rendu front, réseau, API Gateway, Lambda,
  DynamoDB. Elle se mesure sur le portail déployé (ou en Lighthouse/Playwright
  sur `portal/`), pas dans la suite Python. Le seul chiffre backend pertinent
  mesuré ici est celui du calcul des KPI (1,0 ms), qui laisse ~2 s au reste.
- **Le temps réel d'un test Continuum/Security Agent** : il dépend d'AWS
  (durée d'un pentest, quotas de jobs simultanés). Ici, `FakeSecurityAgentClient`
  renvoie des failles déjà produites.
- **Le chemin Strands avec un modèle réel** : `run_triage` bascule sur l'agent
  Strands dès qu'un vrai `Model` est fourni. Sa durée dépend du nombre d'appels
  au LLM et du réseau ; elle n'est ni déterministe ni mesurable hors ligne. Le
  garde-fou contractuel (300 s pour 50 failles = 6 s par faille) doit être vérifié
  sur un déploiement réel, avec les traces ENF-OBS-01.
- **Les écritures DynamoDB réelles** : `FakeStore` est en mémoire. En production,
  chaque `save_finding` / `find_by_fingerprint` est un aller-retour réseau.

## Complexités suspectes observées (documentées, NON corrigées)

Ce dossier écrit des mesures : aucun fichier sous `backend/rempart/` n'a été
touché. Points relevés, avec l'effet mesuré ou attendu :

1. `rempart/common/store.py::find_by_fingerprint` (et `tests/fakes_store.py`)
   fait un `scan` complet de la table des failles puis un filtre en Python :
   coût linéaire en fonction du volume stocké, mesuré ci-dessus (0,6 µs à
   40 µs par recherche entre 0 et 800 failles). Appelée **une fois par faille**
   dans `findings_intake.collect_findings` → O(n × base). En production, c'est
   un aller-retour DynamoDB par faille, et un `scan` (le plus coûteux des accès)
   plutôt qu'un `query` sur une clé.
2. `rempart/triage/guardrails.py::_check_regression` relit `known_findings`
   **et** `store.list_findings(app_id=...)` pour **chaque** faille triée :
   O(n × base) en mémoire et, en production, un aller-retour supplémentaire par
   faille (soit ~100 appels pour 50 failles). La liste `known_findings` passée
   par `triage_dispatch.run_proposals` contient déjà ces failles : le second
   parcours est redondant.
3. `rempart/orchestrator/triage_dispatch.py::run_proposals` et
   `guardrails._check_regression` appellent `list_findings(app_id=...)` **sans
   `limit`**, donc avec la valeur par défaut **100**. Au-delà de 100 failles
   connues pour une application, les doublons et régressions peuvent être manqués
   silencieusement. Risque d'**exactitude** (pas de performance), observé en
   lisant le code — à traiter par le propriétaire du module.
4. `rempart/reports/metrics.py::freeze_month` appelle `_gather_scope` puis
   `compute_kpis`, qui rappelle `_gather_scope` : le corpus est parcouru deux
   fois (mesuré : `freeze_month` ≈ 2,3× `compute_kpis`).
5. `rempart/reports/metrics.py::applications_detail` filtre les failles ouvertes
   et les runs **par application** : O(applications × failles). C'est le terme
   qui explique la croissance ×6,6 pour un volume ×4 (applications ×4 aussi).
6. `rempart/triage/agent.py::run_triage` applique déjà `enforce` à chaque
   proposition ; la chaîne mesurée ici le rappelle explicitement (comme demandé
   par le scénario de test), ce qui double le parcours des garde-fous. Les
   chiffres publiés sont donc une **borne haute** du coût réel.

### Pistes d'optimisation si un seuil venait à être dépassé

1. Indexer les empreintes : table DynamoDB avec clé de partition `app_id` et clé
   de tri `fingerprint` (ou GSI), et `query` au lieu de `scan` → recherche en
   O(1) réseau. Côté `FakeStore`, un dictionnaire `(app_id, fingerprint)`.
2. Ne lire la base qu'**une fois par lot** dans `collect_findings` et dans les
   garde-fous, puis travailler sur un index local `{fingerprint: finding}`
   (comme le fait déjà `agent._index_known_findings`).
3. Passer un `limit` explicite (ou une pagination) à chaque `list_findings` pour
   supprimer le plafond silencieux de 100.
4. Dans `freeze_month`, calculer le `Scope` une fois et le transmettre à une
   variante interne de `compute_kpis` prenant le scope en paramètre.
5. Grouper les écritures (`batch_writer`) dans `collect_findings` et
   `apply_proposals`.
6. Si le cold start Strands devenait gênant : import au démarrage de la Lambda
   (init) plutôt qu'au premier appel, ou provisioned concurrency.
