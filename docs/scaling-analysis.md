# Analyse d'échelle — où casse le plan de contrôle à 50 clients

Piste #41 de [`scaling-100-ideas.md`](scaling-100-ideas.md) : *« Passer de 2 à 50
clients : où casse le plan de contrôle en premier ? (probablement les scans
DynamoDB du journal d'audit et des KPI de parc) »*.

**Verdict : l'hypothèse est confirmée, mais la première cassure n'est pas le
coût — c'est l'exactitude.** `Store` lisait les neuf tables par `scan()` alors
que les GSI existaient déjà dans [`iac/control-plane/stacks/storage.py`](../iac/control-plane/stacks/storage.py).
Or un `scan()` DynamoDB ne renvoie **qu'une page de 1 Mo par appel** et `Store`
ne suivait pas `LastEvaluatedKey` : à 25 000 failles (14,4 Mo), une lecture ne
voyait que 6,9 % de la table, dans un ordre arbitraire. Les KPI d'un client
pouvaient donc être calculés sur un échantillon qui ne contenait **aucune** de
ses failles.

## Modèle de charge utilisé pour chiffrer

50 clients × 20 applications × 500 failles par client, rétention de 13 mois
(ENF-DATA-01). Tailles d'items **mesurées** sur les modèles réels
(`json.dumps(entity.to_item())`) :

| Table | Items | Taille item | Volume | Items par page de 1 Mo | % de la table lu par scan |
|---|---|---|---|---|---|
| `findings` | 25 000 | 577 o | 14,4 Mo | 1 733 | **6,9 %** |
| `runs` | 7 800 (12/mois/client) | 343 o | 2,7 Mo | 2 915 | 37,4 % |
| `applications` | 1 000 | 373 o | 0,37 Mo | 2 681 | 100 % |
| `audit` | ~250 000 (10 év./faille) | 182 o | 45,5 Mo | 5 494 | **2,2 %** |
| `decisions` | ~37 500 (1,5/faille) | 183 o | 6,9 Mo | 5 464 | 14,6 % |
| `test-configs` | 2 000 | 183 o | 0,37 Mo | 5 464 | 100 % |
| `reports` | 650 | 148 o | 0,1 Mo | — | 100 % |
| `tenants` | 50 | 382 o | 0,02 Mo | — | 100 % |

Convention de coût : lecture à cohérence éventuelle, item ≤ 4 Ko ⇒ **0,5 unité
de lecture (RCU)**. Tous les items ci-dessus font moins de 4 Ko, donc
1 item lu = 0,5 RCU quel que soit son poids exact.

## Inventaire exhaustif des lectures qui scannaient

Classé par gravité. « Avant » = coût d'**un appel** au modèle de charge
ci-dessus ; « après » = coût mesuré par `backend/tests/common/test_scale.py`.

| # | Gravité | Fonction (`common/store.py`) | Table | Pourquoi ça scannait | Avant (1 appel) | Après | État |
|---|---|---|---|---|---|---|---|
| 1 | **Critique** | `list_findings(tenant_id=…)` | `findings` | GSI `tenant_id-index` déjà provisionné mais jamais utilisé | 1 page = 1 733 items ≈ 866 RCU, **et 93 % de la table invisible** (KPI faux) | 500 items = **250 RCU**, exhaustif | ✅ **Corrigé** : `query` sur `tenant_id-index` + pagination `LastEvaluatedKey` |
| 2 | **Critique** | `find_by_fingerprint(app_id, fp)` | `findings` | GSI `app_id-fingerprint-index` (PK `app_id`, SK `fingerprint`) déjà provisionné mais jamais utilisé ; appelé **une fois par faille entrante** (`findings_intake.py`) | 1 page ≈ 866 RCU ; le dédoublonnage ratait la faille existante hors page ⇒ doublons | 1 item = **0,5 RCU** | ✅ **Corrigé** : `query` sur `app_id-fingerprint-index` avec PK+SK |
| 3 | **Critique** | `list_audit(object_id=…)` | `audit` | **Aucun GSI** ; appelé par `already_notified()` pour **chaque faille ouverte à chaque balayage horaire** (EF-COR-06) | 1 page = 5 494 items ≈ 2 747 RCU. Balayage horaire de 2 000 failles ouvertes : 11,0 M items/h ≈ **5,49 M RCU/h (≈ 1 526 RCU/s)** | mesuré : 2 items pour 2 événements de l'objet ≈ **1 RCU** (~10 événements/objet en prod ≈ 5 RCU) ; balayage horaire ≈ 10 000 RCU/h (≈ 2,8 RCU/s) | ✅ **Corrigé** : GSI `object_id-index` **ajouté** dans `storage.py` + `query` |
| 4 | Haute | `list_runs(tenant_id=…)` | `runs` | GSI `tenant_id-index` déjà provisionné mais jamais utilisé | 1 page = 2 915 items ≈ 1 457 RCU, 63 % des runs invisibles | ~12 items = **6 RCU** | ✅ **Corrigé** : `query` sur `tenant_id-index` (ou `app_id-index` si seul `app_id` est donné) |
| 5 | Haute | `list_decisions(finding_id)` | `decisions` | GSI `finding_id-index` déjà provisionné mais jamais utilisé ; appelé par le triage, la mémoire de triage et le pack d'évidence, **par faille** | 1 page = 5 464 items ≈ 2 732 RCU | ~2 items = **1 RCU** | ✅ **Corrigé** : `query` sur `finding_id-index` |
| 6 | Moyenne | `list_applications(tenant_id)` | `applications` | GSI `tenant_id-index` déjà provisionné mais jamais utilisé | 1 000 items = 500 RCU | 20 items = **10 RCU** | ✅ **Corrigé** : `query` sur `tenant_id-index` |
| 7 | Moyenne | `list_configs(app_id)` | `test-configs` | GSI `app_id-index` déjà provisionné mais jamais utilisé ; appelé à chaque run et à chaque onboarding | 2 000 items = 1 000 RCU | ~2 items = **1 RCU** | ✅ **Corrigé** : `query` sur `app_id-index` |
| 8 | Moyenne | `list_reports(tenant_id)` | `reports` | GSI `tenant_id-index` déjà provisionné mais jamais utilisé | 650 items = 325 RCU | ~13 items = **6,5 RCU** | ✅ **Corrigé** : `query` sur `tenant_id-index` |
| 9 | Haute | `list_findings()` / `list_runs()` / `list_applications()` **sans filtre** — KPI de parc (`GET /v1/fleet/kpis`) | `findings`, `runs`, `applications` | Aucun filtre ⇒ pas de clé de partition possible ; `gather_scope(store, None, period)` lit toute la flotte | 3 scans = 1 733 + 2 915 + 1 000 items ≈ 2 824 RCU, **et les chiffres sont faux** (chaque table tronquée à 1 Mo) | inchangé | ❌ **Non corrigé** : scan inévitable en l'état. Solution correcte au §« Scans inévitables » |
| 10 | Haute | `list_audit()` **sans `object_id`** — `GET /v1/audit`, `GET /v1/tenants/:id/audit`, `pack_audit()` | `audit` | `AuditEvent` **n'a pas de colonne `tenant_id`** ; l'appartenance à un client n'est déduite qu'après coup via les ids d'objets (`audit.py`) | 1 page = 5 494 items ≈ 2 747 RCU. Le « plus récent d'abord » de la route est faux : il ne trie que la page lue (2,2 % du journal) | inchangé | ❌ **Non corrigé** : exige un changement de schéma (voir §« Scans inévitables ») |
| 11 | Haute | `list_applications()` **sans filtre** — découverte toutes les 5 min (`discovery.py`), `events.py` | `applications` | Listage de parc : aucun filtre | 1 000 items = 500 RCU toutes les 5 min ≈ 144 000 RCU/jour | inchangé | ⚠️ **Laissé tel quel, seuil documenté** : tient tant que le parc fait ≤ 2 681 applications (1 Mo). Au-delà, paginer ou partitionner la découverte par client |
| 12 | Faible | `list_tenants()` | `tenants` | Listage complet d'administration, 50 items | 50 items = 25 RCU | inchangé | ⚠️ **Laissé tel quel** : aucun index n'aiderait (on veut tout), volume borné par le nombre de clients |

## GSI ajoutés

Un seul index manquait réellement ; les sept autres existaient déjà dans
`storage.py` et n'étaient simplement **pas utilisés** par `store.py`.

| Table | Index | Clé de partition | Clé de tri | Statut |
|---|---|---|---|---|
| `audit` | `object_id-index` | `object_id` | — | **Ajouté** (corrige la ligne 3) |
| `findings` | `app_id-fingerprint-index` | `app_id` | `fingerprint` | Existait, **désormais utilisé** (lignes 2, 4) |
| `findings` | `tenant_id-index` | `tenant_id` | — | Existait, **désormais utilisé** (ligne 1) |
| `runs` | `tenant_id-index` / `app_id-index` | `tenant_id` / `app_id` | — | Existaient, **désormais utilisés** (ligne 4) |
| `applications` | `tenant_id-index` | `tenant_id` | — | Existait, **désormais utilisé** (ligne 6) |
| `test-configs` | `app_id-index` | `app_id` | — | Existait, **désormais utilisé** (ligne 7) |
| `decisions` | `finding_id-index` | `finding_id` | — | Existait, **désormais utilisé** (ligne 5) |
| `reports` | `tenant_id-index` | `tenant_id` | — | Existait, **désormais utilisé** (ligne 8) |

Indexes volontairement **non** ajoutés :

- `findings` sur `(tenant_id, status)` ou `(tenant_id, priority)` : cardinalité
  faible et volume par client borné (500 failles). Le filtre secondaire reste
  appliqué en Python après le `query`, ce qui coûte ~250 RCU de toute façon. À
  reconsidérer si un client dépasse ~5 000 failles ouvertes.
- `runs` sur `(tenant_id, status)` : même raison.
- `audit` sur `created_at` : impossible sans clé de partition ; `AuditEvent` n'a
  ni `tenant_id` ni aucune colonne exploitable comme partition (ligne 10).

Coût d'écriture du nouvel index : 1 écriture de 182 o par événement d'audit,
soit ~19 000 écritures/mois au modèle de charge ⇒ négligeable (< 0,01 WCU/s).

### Vérification nom par nom : GSI déclarés vs GSI interrogés

Un GSI interrogé sous un nom différent de celui déclaré échouerait en
production avec une `ValidationException` — et passerait inaperçu dans les
tests, car le faux DynamoDB ignore l'index. Les **10 appels à `_query_gsi`**
(`store.py`) ont donc été confrontés aux **9 GSI de `TABLE_SPECS`**
(`storage.py`), index par index :

| Table | Index utilisé (`store.py`) | Index déclaré (`storage.py`) | Clé de partition | Clé de tri | Verdict |
|---|---|---|---|---|---|
| `applications` | `tenant_id-index` | `tenant_id-index` | `tenant_id` = `tenant_id` | — | conforme |
| `test-configs` | `app_id-index` | `app_id-index` | `app_id` = `app_id` | — | conforme |
| `runs` | `tenant_id-index` | `tenant_id-index` | `tenant_id` = `tenant_id` | — | conforme |
| `runs` | `app_id-index` | `app_id-index` | `app_id` = `app_id` | — | conforme |
| `findings` | `tenant_id-index` | `tenant_id-index` | `tenant_id` = `tenant_id` | — | conforme |
| `findings` | `app_id-fingerprint-index` (PK seule, `list_findings(app_id=…)`) | `app_id-fingerprint-index` | `app_id` = `app_id` | omise à l'appel, déclarée `fingerprint` : query PK-seule valide | conforme |
| `findings` | `app_id-fingerprint-index` (PK+SK, `find_by_fingerprint`) | `app_id-fingerprint-index` | `app_id` = `app_id` | `fingerprint` = `fingerprint` | conforme |
| `decisions` | `finding_id-index` | `finding_id-index` | `finding_id` = `finding_id` | — | conforme |
| `reports` | `tenant_id-index` | `tenant_id-index` | `tenant_id` = `tenant_id` | — | conforme |
| `audit` | `object_id-index` | `object_id-index` | `object_id` = `object_id` | — | conforme |

**Aucune divergence** : 10/10 appels couverts, 9/9 GSI déclarés utilisés (pas
d'index orphelin). Cette vérification est désormais un test automatisé
(`test_declared_gsis_match_the_queries`), qui relit les deux fichiers source à
chaque exécution : si quelqu'un renomme un index d'un côté sans l'autre, la
suite rougit avant la production.

## Lectures ponctuelles (`get_item`) — pour être exhaustif

Hors `list_*`, le plan de contrôle lit aussi par clé primaire directe :
`get_tenant`, `get_application`, `get_run`, `get_finding`, `get_report`,
`get_budget`. Coût : 0,5 RCU par lecture quelle que soit la taille de la table
(1 item), jamais de scan. À 50 clients comme à 500 : **inévitables et sans
risque** — aucune action requise. `budget_detail()` (metrics.py) passe par
`get_tenant` : O(1).

## Avant / après, mesuré

`backend/tests/common/test_scale.py` peuple 50 clients × 20 applications ×
500 failles (25 000 failles, 1 000 applications, 600 runs) et compte les
éléments réellement lus par un faux DynamoDB qui **respecte les conditions de
clé** et le plafond de 1 Mo. Chiffres mesurés, pas estimés.

Deux lectures « avant » sont possibles, et il faut les distinguer honnêtement :

- **scan réel** : ce que DynamoDB renvoie aujourd'hui, soit une page de 1 Mo —
  le moins cher en RCU, mais **le résultat est faux** (tronqué, ordre arbitraire) ;
- **scan complet** : ce que le code *prétend* faire (toute la table), qu'il
  n'atteint jamais sans boucle `LastEvaluatedKey`.

| Lecture | Avant — scan réel (1 page) | Avant — scan complet | Après (mesuré) | Gain |
|---|---|---|---|---|
| `compute_kpis` d'un client | 1 733 + 600 + 1 000 = **3 333 items** ≈ 1 667 RCU | 25 000 + 600 + 1 000 = **26 600 items** ≈ 13 300 RCU | **532 items** ≈ 266 RCU | × 6,3 vs page réelle, × 50 vs scan complet — et surtout **exact** au lieu de tronqué |
| `list_findings(tenant_id=…)` | 1 733 items (6,9 % de la table, client possiblement absent) | 25 000 items | **500 items** | × 3,5 vs page réelle, × 50 vs scan complet |
| `find_by_fingerprint` | 1 733 items | 25 000 items | **1 item** | × 1 733 |
| `list_audit(object_id=…)` | 5 494 items | 250 000 items | **2 items** | × 2 747 |
| `list_decisions(finding_id)` | 5 464 items | 37 500 items | **~2 items** | × 2 732 |
| Balayage horaire des relances (2 000 failles ouvertes) | 11,0 M items/h ≈ **5,49 M RCU/h (1 526 RCU/s)** | — | 20 000 items/h ≈ **10 000 RCU/h (2,8 RCU/s)** | × 549 |
| Client à 2 000 failles | 1 page (1 000 failles perdues) | — | **4 pages, 2 000 lues** | exhaustif |

Au modèle de charge complet (13 mois de rétention, 7 800 runs), le rapport
mensuel d'un client passe de 5 648 items ≈ 2 824 RCU (scan réel, chiffres faux)
à 676 items ≈ 338 RCU (query, chiffres exacts) ; pour les 50 clients, de
141 200 RCU à 16 900 RCU par mois.

Le test vérifie aussi l'**exactitude** : les KPI de chacun des 50 clients dans
la flotte sont égaux, clé par clé, à ceux du même client seul dans son magasin,
et les valeurs attendues sont épinglées (260 fermées, 240 ouvertes, couverture
0,6, médiane 6,5 h, MTTR 15 j sur P1/P3, risque `moderate`). Le `Store` réel
(chemin `query`) et le `FakeStore` (chemin dictionnaire) produisent les mêmes
KPI sur trois clients pris dans la flotte. Les listes scopées
(`list_findings`/`list_runs`/`list_applications`) ne renvoient que les lignes du
client demandé, et le **journal d'audit** scopé par client
(`tenant_object_ids` + `belongs_to` de `api/routes/audit.py`) n'attribue à un
client aucun événement d'un autre — y compris les événements pointant vers un
objet inexistant, invisibles pour tout le monde (ENF-SEC-01 à l'échelle). Les
lectures indexées restantes (`list_configs` 2 items, `list_reports` 13,
`list_decisions` 2) sont mesurées au compteur : zéro scan, coût = taille du
résultat.

## Scans inévitables : la solution correcte (non implémentée)

Ces trois points demandent un changement de schéma ou un nouveau composant
d'écriture ; ils sortent de la zone de cette analyse (`store.py`,
`storage.py`), donc ils sont documentés plutôt qu'implémentés.

### 1. KPI de parc (`GET /v1/fleet/kpis`) — ligne 9

**Problème** : `gather_scope(store, None, period)` appelle les trois `list_*`
sans filtre. Aucune clé de partition ne peut servir : on veut tout. Le scan est
donc structurel, **et il est faux** dès que la table dépasse 1 Mo : le parc à
50 clients produit des indicateurs calculés sur 6,9 % des failles.

**Solution correcte — table de synthèse précalculée.** Les KPI d'un client sont
déjà figés une fois par mois par `freeze_month()` (chapitre 8.5) : le résultat
est déterministe et ne change plus. Il faut donc :

1. une table `kpi-summaries` (PK `period`, SK `tenant_id`, projection : les 17
   champs de `compute_kpis`) écrite **au moment du gel mensuel**, qui a déjà
   lieu ;
2. `GET /v1/fleet/kpis` devient un `query` sur `period` : **50 items au lieu de
   33 800**, soit ~25 RCU au lieu de ~2 824 RCU, et des chiffres exacts puisque
   issus du gel ;
3. le gel d'un client ne dépend plus de la taille du parc (il est déjà scopé
   client après la correction des lignes 1, 4, 6).

Coût : 50 écritures/mois. C'est la correction qui rapporte le plus par ligne de
code, mais elle touche `reports/metrics.py`, `reports/monthly.py` et
`api/routes/kpis.py`.

### 2. Journal d'audit sans `object_id` — ligne 10

**Problème** : `AuditEvent` ne porte pas de `tenant_id`. L'appartenance à un
client est reconstruite après coup (`audit.py:tenant_object_ids`) en listant les
applications, runs, failles et rapports du client, puis en filtrant le journal.
Deux conséquences à 50 clients : le scan de 1 Mo ne contient pas forcément les
événements du client demandé, et `pack_audit()` ne retient que 2,2 % du journal
de la période.

**Solution correcte — dénormaliser le client + index temps.**

1. ajouter `tenant_id` à `AuditEvent` (`models.py`) et le renseigner dans
   `append_audit()` / `ctx.audit()` (tous les appelants connaissent déjà le
   client : c'est le contexte d'autorisation de la route ou le tenant du run) ;
2. GSI `tenant_id-created_at-index` (PK `tenant_id`, SK `created_at`) :
   `GET /v1/tenants/:id/audit` devient **un** `query` trié du plus récent au
   plus ancien, borné par `limit`, sans scan ni reconstruction d'index ;
3. `pack_audit(period)` devient un `query` par client avec `created_at` entre
   les bornes du mois (~2 500 RCU → ~50 RCU) ;
4. `GET /v1/audit` (vue plateforme, tous clients) reste un scan **assumé** :
   c'est un outil d'administration à faible fréquence. La bonne réponse à terme
   est l'export du journal vers S3 Athena (le journal est immuable, ENF-SEC-06)
   plutôt que sa lecture en ligne.

Contrainte à respecter : l'historique déjà écrit n'a pas de `tenant_id`. La
migration doit tolérer l'attribut absent (les GSI n'indexent pas les items sans
clé) — d'où un double chemin de lecture pendant la rétention de 13 mois.

### 3. Plafond de 1 Mo et pagination — résiduel

La pagination `LastEvaluatedKey` a été ajoutée **aux lectures indexées**
(`_query_gsi`), pas aux scans : paginer un scan de parc multiplierait le coût
par 14 (findings) pour un résultat toujours borné par le `limit` de l'appelant.
Le plafond reste donc actif sur les lignes 9, 10 et 11. Deux garde-fous à poser
hors de cette zone :

- `metrics.MAX_FETCH = 1000` tronque silencieusement les KPI d'un client au-delà
  de 1 000 failles ou 1 000 runs. À 500 failles/client on passe, mais c'est un
  plafond latent : il faut soit le remonter, soit paginer les KPI, soit passer
  par la table de synthèse du point 1.
- `audit.py:MAX_SCAN = 2000` et le tri « plus récent d'abord » ne sont exacts
  que dans la page lue. Le point 2 supprime le problème.

## Reproduction

```bash
cd /tmp/rempart/backend
JSII_RUNTIME_PACKAGE_CACHE_ROOT=/tmp/rempart/.jsii-cache \
  /tmp/rempart/.venv/bin/python -m pytest tests/common/test_scale.py -q
```

14 tests, ~2 s, déterministes, sans réseau ni AWS.
