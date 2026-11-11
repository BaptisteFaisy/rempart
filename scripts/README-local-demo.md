# Démonstration locale de Rempart — 100 % locale, 0 €

> **Aucun compte AWS, aucune credential, aucun appel réseau sortant, aucun
> centime.** Le produit complet tourne sur `127.0.0.1` : le portail React, l'API
> (le **vrai** `lambda_handler` du chapitre 14) et le jeu de données figé.
>
> Voir aussi la version anglaise pour les juges :
> [`docs/judging-test-instructions.md`](../docs/judging-test-instructions.md),
> section *Running the demo locally with zero AWS cost*.

## La procédure en 4 commandes

```bash
# 1. Vérifier que tout se monte (ne bloque pas, sort en 0, liste les routes)
cd /tmp/rempart && .venv/bin/python scripts/serve_local.py --check

# 2. Lancer l'API locale sur http://127.0.0.1:8000 (terminal 1)
cd /tmp/rempart && .venv/bin/python scripts/serve_local.py

# 3. Installer les dépendances du portail (terminal 2, une seule fois)
cd /tmp/rempart/portal && npm ci

# 4. Lancer le portail branché sur l'API locale (terminal 2)
cd /tmp/rempart/portal && npm run dev:local
```

Puis ouvrir **<http://localhost:5173/fleet>**.

Variante **sans aucun serveur** (portail seul, données figées embarquées) :

```bash
cd /tmp/rempart/portal && npm run dev:offline
```

Une bannière orange « OFFLINE DEMO MODE » apparaît en bas de l'écran : c'est le
signal que rien ne vient d'un backend vivant.

## Ce qui tourne vraiment

| Brique | Ce que c'est | Coût |
|---|---|---|
| `scripts/serve_local.py` | serveur HTTP **stdlib uniquement** (`http.server`) | 0 € |
| `rempart.api.app.lambda_handler` | le **vrai** handler Lambda, appelé avec un événement API Gateway HTTP API v2 reconstitué | 0 € |
| `rempart.common.store.Store` → `FakeStore` | persistance en mémoire (même interface) | 0 € |
| `SecurityAgentClient` → `FakeSecurityAgentClient` | client AWS Continuum factice | 0 € |
| `demo/seed/demo-dataset.json` | jeu figé : 2 clients, 2 applications, 4 configurations, 6 tests, 6 failles sur tout le cycle de vie, 10 décisions, budgets, 2 rapports | 0 € |
| portail Vite | `npm run dev:local` → `VITE_API_URL=http://127.0.0.1:8000` | 0 € |

Aucune dépendance Python ni npm n'est ajoutée par ce mode.

## Une seule source de vérité

Le jeu figé est produit par `scripts/seed_demo.py` (`build_dataset()`), écrit
dans `demo/seed/demo-dataset.json`, et **ce même fichier** est :

- chargé par `scripts/serve_local.py` dans le `FakeStore` (mode API) ;
- importé par `portal/src/api/mockData.ts` (mode hors ligne `VITE_USE_MOCKS=1`).

Il n'existe plus de second jeu de données écrit à la main dans le portail :
l'ancien `mockData.ts` (tenants « Acme », failles inventées) a été remplacé par
un chargement du JSON de seed, et les KPI affichés hors ligne sont **dérivés**
de ce jeu par `deriveKpis()` (compteurs et ratios déterministes, jamais de
chiffre inventé — ENF-IA-01). `backend/tests/scripts/test_serve_local.py`
vérifie que le JSON versionné et le générateur ne divergent pas.

## Les deux modes du portail (explicites, jamais de repli silencieux)

| Mode | Activation | Comportement en cas d'échec |
|---|---|---|
| **API** (défaut) | `VITE_API_URL` renseigné (`npm run dev:local`) | l'erreur est **affichée** (bannière rouge `API error — <status> <route>`) et propagée ; **aucune donnée de substitution** |
| **Démo hors ligne** | `VITE_USE_MOCKS=1` (`npm run dev:offline`) | aucun appel réseau ; bannière orange permanente ; données = jeu figé |

Avant cette correction, `service.ts` retombait silencieusement sur des données
bidon dès qu'un appel échouait : un 500 ou un appel lent faisait croire à des
données réelles. C'est supprimé.

## Identité de démonstration (ce n'est PAS une authentification)

Le serveur local fabrique des **claims Cognito synthétiques** à partir de deux
en-têtes, pour que `resolve_principal()` et l'isolation par tenant s'exercent
exactement comme en production :

| En-tête | Défaut | Effet |
|---|---|---|
| `X-Demo-Role` | `platform_admin` | claim `cognito:groups` |
| `X-Demo-Tenant` | `demo-a` pour les rôles `client_*`/`executive`/`demo` | claim `custom:tenant_id` |

Les en-têtes `X-Rempart-Role` / `X-Rempart-Tenant` envoyés par le portail sont
acceptés comme alias. **N'importe qui peut se déclarer `platform_admin`** : ce
mode ne doit jamais être exposé au-delà de `127.0.0.1` (défaut de `--host`).

Le rôle et le tenant restent **appliqués** : un `client_security` du tenant
`demo-b` reçoit un `403` sur les ressources de `demo-a`.

```bash
curl -s http://127.0.0.1:8000/v1/tenants | head -c 200
curl -s 'http://127.0.0.1:8000/v1/findings?tenant_id=demo-b&status=new'
curl -s http://127.0.0.1:8000/v1/tenants/demo-a/kpis
curl -s -H 'X-Demo-Role: client_security' -H 'X-Demo-Tenant: demo-b' \
     http://127.0.0.1:8000/v1/tenants/demo-a     # -> 403
```

## Options du serveur

```bash
python3 scripts/serve_local.py --port 9000        # autre port
python3 scripts/serve_local.py --dataset autre.json
python3 scripts/serve_local.py --check            # CI : vérifie et sort
```

Au démarrage, le serveur affiche le résumé du jeu (nombre d'items par
collection, failles par priorité), l'URL et le nombre de routes servies.

**Horloge de démonstration** : les routes KPI et budget lisent le mois courant
en production. Le jeu figé porte sur **octobre 2026** ; sans correction, les
cartes KPI afficheraient des zéros. Le serveur épingle donc la période sur le
mois du jeu (`period` / `month`) quand l'appelant ne la précise pas. Un
paramètre explicite reste prioritaire.

## Ce que ce mode montre

- le portail complet : Fleet, Tenant, Application, Run, Finding, TriageQueue,
  Reports, Budget ;
- le cycle de vie d'une faille : `new` → `pending_validation` → `confirmed` →
  `in_remediation` → `closed` **avec preuve de retest** (`closed_by_run_id`) ;
- les KPI déterministes (délai livraison → résultat, blocage avant production,
  MTTR par priorité, conformité SLA, couverture, heures-tâches, coût) ;
- l'isolation multi-tenant et la matrice de rôles (403 réels) ;
- les écritures : une décision de tri saisie dans le portail est enregistrée
  dans le `FakeStore` et change le statut de la faille.

## Ce que ce mode ne montre PAS

- **Aucun test AWS Continuum réel** : le client Security Agent est factice,
  aucun test d'intrusion n'est lancé, aucune heure-tâche n'est consommée.
- **Le garde-fou anti-facture reste actif** : `Settings(free_tier_only=True)` et
  les tenants du jeu ont `free_tier_confirmed=False`, donc
  `POST /v1/applications/{id}/runs` renvoie **402**. C'est voulu
  (`docs/free-tier-runbook.md`) : la démo locale ne peut pas déclencher un test
  facturable.
- Pas d'agent de tri Strands/Bedrock : les décisions d'agent présentes dans le
  jeu sont celles du chemin déterministe.
- Pas de Cognito, pas de DynamoDB, pas de S3, pas de Step Functions, pas de
  GitHub, pas de SES : tout est en mémoire et **perdu au redémarrage**.
- Persistance : rien n'est écrit sur disque ; relancer le serveur recharge le
  jeu figé.

## Deux routes de liste manquantes (écart connu, à corriger côté backend)

Le contrat (chapitre 14) ne définit ni `GET /v1/tenants/{id}/applications` ni
`GET /v1/tenants/{id}/reports`, que le portail appelle pour les pages **Tenant**
(liste des applications) et **Reports** (liste des rapports). En mode API local,
ces deux appels renvoient donc `404` et le portail affiche la bannière d'erreur
— comportement voulu : **on affiche l'échec, on n'invente pas de lignes**.

En mode hors ligne (`VITE_USE_MOCKS=1`), ces deux écrans fonctionnent, puisqu'ils
lisent le jeu figé. Correctif attendu côté `rempart/api/routes/` : exposer
`Store.list_applications(tenant_id)` et `Store.list_reports(tenant_id)`, qui
existent déjà.

## Tests

```bash
cd /tmp/rempart/backend && ../.venv/bin/python -m pytest tests/scripts -q
```

`backend/tests/scripts/test_serve_local.py` couvre la traduction requête →
événement (GET avec paramètres, POST avec corps JSON), le mapping des en-têtes
de démo en claims, le preflight CORS, la route inconnue (404), l'horloge de
démonstration, le cloisonnement par tenant et le mode `--check` — **sans ouvrir
de socket**.
