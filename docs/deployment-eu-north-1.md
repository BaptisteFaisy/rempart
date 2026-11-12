# Déploiement réel — eu-north-1 (compte 710332178565)

> Vérifié le **11 novembre 2026** par invocation et scan réels, pas par lecture
> du code. Chaque affirmation ci-dessous donne la commande exacte et la sortie
> (tronquée). Aucun secret ni jeton n'est reproduit dans ce document.
>
> Garde-fous respectés pendant toute la vérification : aucun test Continuum
> lancé, aucun appel `securityagent:*` en écriture, `free_tier_confirmed=false`
> intact sur les deux tenants, aucune exécution Step Functions démarrée.

## 1. Inventaire réel déployé

`aws cloudformation list-stacks --region eu-north-1` :

| Stack | État | Contenu vérifié |
|---|---|---|
| RempartStorageStack | CREATE_COMPLETE | 9 tables DynamoDB préfixe `rempart-` |
| RempartIdentityStack | CREATE_COMPLETE | Cognito `eu-north-1_VkUAsvgSR`, 7 groupes |
| RempartApiStack | CREATE_COMPLETE | API Gateway HTTP v2 `qm6dmdkgdg` + Lambda API |
| RempartOrchestratorStack | CREATE_COMPLETE | 10 Lambdas de tâches + 3 machines à états + 3 règles EventBridge |
| RempartPortalStack | CREATE_COMPLETE | **géré par un autre agent** — non touché, non vérifié ici |
| CDKToolkit | CREATE_COMPLETE | bootstrap CDK |

**Non déployé : NotificationsStack** — exige un domaine vérifié SES (envoi des
notifications). C'est le seul stack manquant du plan de contrôle.

### 1.1 Tables DynamoDB

`aws dynamodb list-tables --region eu-north-1` →
`rempart-applications, rempart-audit, rempart-budget, rempart-decisions,
rempart-findings, rempart-reports, rempart-runs, rempart-tenants,
rempart-test-configs` (9 tables).

Le préfixe réel `rempart-` **correspond au défaut de `Store()`**
(`backend/rempart/common/store.py`, `table_prefix="rempart-"`) : la variable
`REMPART_TABLE_PREFIX` n'a pas eu besoin d'être adaptée.

### 1.2 API Gateway

- Endpoint : `https://qm6dmdkgdg.execute-api.eu-north-1.amazonaws.com` (stage `$default`).
- Routes (`aws apigatewayv2 get-routes --api-id qm6dmdkgdg`) :
  - `ANY /v1/{proxy+}` — AuthorizationType **JWT** ;
  - `POST /v1/events/deployment` — NONE (webhook CI/CD, seul point sans jeton).
- Authorizer (`get-authorizers`) : `CognitoAuthorizer`, type JWT, issuer
  `https://cognito-idp.eu-north-1.amazonaws.com/eu-north-1_VkUAsvgSR`.

### 1.3 Lambdas (11 fonctions, python3.12)

`aws lambda list-functions --region eu-north-1` — handlers réels, **aucun
placeholder** :

| Fonction | Handler |
|---|---|
| RempartApiStack-RempartApiFunction… | `rempart.api.app.lambda_handler` |
| …LambdaDiscoverRuns… | `rempart.orchestrator.lambda_handlers.discover_runs` |
| …LambdaBudgetGate… | `rempart.orchestrator.lambda_handlers.budget_gate` |
| …LambdaStartRun… | `rempart.orchestrator.lambda_handlers.start_run` |
| …LambdaPollRun… | `rempart.orchestrator.lambda_handlers.poll_run` |
| …LambdaCollectFindings… | `rempart.orchestrator.lambda_handlers.collect_findings` |
| …LambdaDispatchTriage… | `rempart.orchestrator.lambda_handlers.dispatch_triage` |
| …LambdaCreateTickets… | `rempart.orchestrator.lambda_handlers.create_tickets` |
| …LambdaRequestRemediation… | `rempart.orchestrator.lambda_handlers.request_remediation` |
| …LambdaCloseOrReopen… | `rempart.orchestrator.lambda_handlers.close_or_reopen` |
| …LambdaReminders… | `rempart.orchestrator.reminders.lambda_handler` |

Environnement vérifié (ex. DiscoverRuns) : `REMPART_TABLE_PREFIX=rempart-`,
`REMPART_REGION=eu-north-1`, `REMPART_FREE_TIER_ONLY=1`,
`REMPART_MAX_TASK_HOURS_PER_TEST=5`, `REMPART_HOURLY_RATE=50.0`.

### 1.4 Machines à états

`aws stepfunctions list-state-machines --region eu-north-1` → les 3 attendues,
toutes `STANDARD` / `ACTIVE`, et leurs définitions (`describe-state-machine`)
référencent les vraies Lambdas de l'orchestrateur :

- `RempartPentestLifecycle` → budget_gate, start_run, poll_run, collect_findings,
  dispatch_triage, create_tickets, request_remediation ;
- `RempartCicdIntake` → collect_findings, create_tickets, dispatch_triage,
  request_remediation ;
- `RempartRetestClose` → close_or_reopen.

`list-executions` sur les trois : **0 exécution** (rien n'a jamais tourné, rien
n'a été démarré pendant cette vérification).

### 1.5 Planifications EventBridge

`aws events list-rules --region eu-north-1` — 3 règles ENABLED :
discovery `rate(5 minutes)`, reminders échéances `rate(1 hour)`,
planification mensuelle `cron(0 2 1 * ? *)`.

Note garde-fou : la règle mensuelle est active, mais un test réel resterait
refusé par `budget_gate` tant que `free_tier_confirmed=false` (vérifié §2) et
`REMPART_FREE_TIER_ONLY=1`. Premier test réel : **pas avant le 23/11/2026**.

### 1.6 Cognito

7 groupes (`aws cognito-idp list-groups --user-pool-id eu-north-1_VkUAsvgSR`) :
`platform_admin, analyst, account_manager, client_security, client_dev,
executive, demo`.

## 2. Jeu de démonstration chargé dans les tables réelles

Commande : `AWS_REGION=eu-north-1 …/.venv/bin/python scripts/seed_demo.py --load`
→ `chargé : 34 item(s) dans DynamoDB` (via le vrai `Store()`, pas un mock).

Comptages réels (`aws dynamodb scan --table-name … --query Count`), conformes au
jeu attendu :

| Table | Items | Attendu |
|---|---|---|
| rempart-tenants | 2 | 2 ✓ |
| rempart-applications | 2 | 2 ✓ |
| rempart-test-configs | 4 | 4 ✓ |
| rempart-runs | 6 | 6 ✓ |
| rempart-findings | 6 | 6 ✓ |
| rempart-decisions | 10 | 10 ✓ |
| rempart-budget | 2 | 2 ✓ |
| rempart-reports | 2 | 2 ✓ |
| rempart-audit | 0 | (journal, non seedé) |

Garde-fou vérifié après chargement (`scan rempart-tenants --projection-expression
tenant_id,free_tier_confirmed`) : `demo-a` et `demo-b` ont bien
`free_tier_confirmed=false`. Rien n'a été modifié.

## 3. API Gateway : l'autorisation fonctionne

Appels réels sans jeton (`curl -s -o … -w 'HTTP %{http_code}'`) :

```
GET /v1/tenants           → HTTP 401 {"message":"Unauthorized"}
GET /v1/applications      → HTTP 401 {"message":"Unauthorized"}
GET /v1/settings/defaults → HTTP 401 {"message":"Unauthorized"}
GET /                     → HTTP 404 {"message":"Not Found"}
```

Le **401 est un résultat valide et souhaité** : c'est l'authorizer JWT Cognito
qui rejette l'appel non authentifié avant même la Lambda. Il prouve que
l'autorisation est câblée sur `ANY /v1/{proxy+}`.

### Obtenir un jeton pour un appel authentifié (non fait ici)

Créer un utilisateur de démo exige de fixer un mot de passe — non fait par
l'agent de vérification. Procédure pour un humain :

```bash
aws cognito-idp admin-create-user --region eu-north-1 \
  --user-pool-id eu-north-1_VkUAsvgSR --username <user> \
  --temporary-password <mot de passe> \
  --user-attributes Name=email,Value=<email> Name=email_verified,Value=true
aws cognito-idp admin-add-user-to-group --region eu-north-1 \
  --user-pool-id eu-north-1_VkUAsvgSR --username <user> --group-name analyst
```

Puis récupérer un jeton via le flux PKCE du portail (`portal/src/auth/`) ou
`admin-initiate-auth`, et rappeler `GET /v1/tenants` avec
`Authorization: Bearer <id_token>`.

## 4. Les Lambdas exécutent le VRAI code

### 4.1 Échec initial et cause exacte

Première invocation de `discover_runs` (payload `{}`) :

```
Runtime.ImportModuleError: Unable to import module
'rempart.orchestrator.lambda_handlers': No module named 'requests'
```

Même échec côté API : `Unable to import module 'rempart.api.app': No module
named 'fpdf'`. Cause racine : le dossier `iac/control-plane/lambda-layer/`
n'existait pas au moment du `cdk deploy` — `runtime_layer()`
(`stacks/_helpers.py`) rend alors `None` **silencieusement** et les fonctions
ont été déployées avec `layers=[]`. Vérifié : `aws lambda list-layers` → `[]`,
`Layers: null` sur les 11 fonctions. Le code applicatif était bien présent
(CodeSize ≈ 99 Ko) mais ne pouvait pas importer ses dépendances tierces.

### 4.2 Correctif appliqué (hotfix AWS, réversible)

Sans toucher au dépôt ni au CDK : layer construit hors dépôt
(`pip install --target … --platform manylinux2014_x86_64 --python-version 3.12`
avec `fpdf2==2.9.0 requests==2.34.2 strands-agents==1.64.0`, paquets déjà
fournis par le runtime retirés : boto3/botocore/urllib3/s3transfer/jmespath/
dateutil/six), publié puis attaché aux 11 fonctions :

- `aws lambda publish-layer-version --layer-name rempart-runtime-deps` →
  `arn:aws:lambda:eu-north-1:710332178565:layer:rempart-runtime-deps:1` ;
- `aws lambda update-function-configuration --function-name <chacune> --layers <ARN>` × 11.

**Dérive CDK à connaître** : au prochain `cdk deploy`, le layer manuel sera
détaché (le CDK déclare `layers=[]` faute de dossier construit). Correctif
durable, à la charge du déploieur : exécuter `scripts/build_lambda_layer.sh`
AVANT `cdk deploy` — et idéalement faire échouer le synth quand le layer est
absent au lieu de rendre `None` silencieusement.

### 4.3 Preuves après correctif

Invocation réelle de la tâche de découverte (lecture seule ; elle liste les jobs
CI/CD et n'appelle jamais `StartPentestJob`) :

```
aws lambda invoke --function-name RempartOrchestratorStack-LambdaDiscoverRuns… \
  --payload '{}'
→ StatusCode 200, FunctionError null
→ {"discovered": 0, "run_ids": []}
```

C'est le contrat exact de `lambda_handlers.discover_runs` : le vrai code
s'exécute dans Lambda (import du module, construction du `Store` réel, parcours
des applications, dict du contrat rendu).

Invocation directe de la Lambda API avec un événement API Gateway v2
(`GET /v1/tenants`, sans claims JWT) :

```
aws lambda invoke --function-name RempartApiStack-RempartApiFunction… \
  --payload file:///tmp/api_event.json
→ StatusCode 200, FunctionError null
→ {"statusCode": 401, "headers": {…CORS…},
   "body": "{\"error\": \"Authentication required\"}"}
```

Le 401 vient cette fois du **handler applicatif réel** (`rempart.api.app`), pas
du gateway : la chaîne complète (import → router → couche d'autorisation →
réponse v2) fonctionne dans Lambda.

## 5. Ce qui reste à faire

1. **Correctif durable du layer** : `scripts/build_lambda_layer.sh` puis
   `cdk deploy` des stacks API + Orchestrator (sinon le hotfix §4.2 sera
   défait au prochain déploiement). Voir §4.2.
2. **Utilisateur Cognito de démo** pour les juges (procédure §3) — exige un
   mot de passe, donc une action humaine ; brancher ensuite un appel JWT
   authentiqué de bout en bout (`GET /v1/tenants` avec jeton → 200).
3. **NotificationsStack** : non déployé, bloqué sur un domaine vérifié SES
   (choisir la méthode de vérification — `HTTP_ROUTE` ne nécessite pas de zone
   DNS, cf. checklist idée #33).
4. **RempartPortalStack** : déployé (CREATE_COMPLETE) mais propriété d'un autre
   agent ; hors périmètre de cette vérification.
5. **Premier test réel Continuum** : toujours interdit avant le **23/11/2026**
   (essai gratuit 2 mois, jugement 22/01/2027). Les deux verrous sont en place
   et vérifiés : `free_tier_confirmed=false` (données §2) et
   `REMPART_FREE_TIER_ONLY=1` (environnement Lambda §1.3).

## 6. Bilan honnête

- Déployé et **prouvé fonctionnel** : stockage (34 items de démo lisibles),
  autorisation JWT (401 gateway ET 401 applicatif), code réel dans les Lambdas
  (invocation `discover_runs` conforme au contrat), 3 machines à états actives
  câblées sur les vraies Lambdas, 3 planifications actives, identité Cognito
  (7 groupes).
- **Cassé à la livraison, corrigé en hotfix** : absence du layer de dépendances
  sur les 11 Lambdas (§4) — sans le hotfix, aucune Lambda du plan de contrôle
  ne pouvait s'exécuter. La dérive CDK reste à corriger durablement (§5.1).
- **Non déployé** : NotificationsStack (SES, domaine requis).
