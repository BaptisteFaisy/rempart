# CONTRAT PHASE 0 — câblage Lambda, notifications, machines à états

> Ce contrat fige les **noms** et les **frontières** entre modules pour que
> plusieurs agents travaillent en parallèle sans diverger. Tout écart doit être
> signalé, jamais décidé en silence.
>
> Rappel des règles projet : fichier < 500 lignes, fonction < 50 lignes, zéro
> duplication, tests sans réseau ni AWS, `ruff` clean.

## 1. Pourquoi cette phase

Quatre trous invisibles aux tests casseraient le déploiement :

| # | Trou | Preuve |
|---|---|---|
| A1 | Les 6 Lambdas de tâches pointent vers `rempart.orchestrator.tasks.<nom>`, mais ces fonctions ont la signature `(payload, deps)` et non `(event, context)` | `iac/control-plane/stacks/orchestrator.py:71` |
| A2 | `rempart.orchestrator.discovery.lambda_handler` n'existe pas | `orchestrator.py:57` |
| A3 | `rempart.notifications.handler.lambda_handler` : module absent | `stacks/notifications.py:45` |
| A4 | La machine à états s'arrête à `create_tickets` → `Succeed` : `request_remediation` et `close_or_reopen` ne sont jamais exécutés | `stacks/orchestrator.py:103` |

## 2. Handlers Lambda — module unique, noms figés

Nouveau fichier : **`backend/rempart/orchestrator/lambda_handlers.py`**

Il expose **neuf** handlers, chacun de signature `(event: dict, context: Any) -> dict` :

```
budget_gate            start_run              poll_run
collect_findings       dispatch_triage        create_tickets
request_remediation    close_or_reopen        discover_runs
```

Le CDK doit pointer vers `rempart.orchestrator.lambda_handlers.<nom>`
(**plus jamais** vers `rempart.orchestrator.tasks.<nom>` ni
`rempart.orchestrator.discovery.lambda_handler`).

Contrat de comportement de chaque handler :

1. Construit `Settings.from_env()`, un `Store(table_prefix=settings.table_prefix)`,
   un `SecurityAgentClient(region=settings.region, endpoint_url=settings.sa_endpoint_url)`,
   et un `GitHubClient` **seulement si** un jeton est disponible
   (`GITHUB_TOKEN` dans l'environnement ou Secrets Manager — sinon `None`).
2. Appelle la fonction de tâche correspondante avec `event` comme `payload`.
3. Retourne le `dict` produit (Step Functions le sérialise).
4. **Ne lève jamais** sur une erreur métier : une exception inattendue est
   capturée, journalisée, et renvoyée comme `{"error": "...", "task": "<nom>"}`
   avec un code de sortie normal — sinon Step Functions rejoue à l'infini.
   Exception : les tâches dont l'échec **doit** être visible (voir § 3).
5. Construction de `Deps` factorisée dans **une seule** fonction
   `build_deps(settings=None) -> Deps` : zéro duplication entre les neuf handlers.
   C'est le point d'injection des doubles de test.

`discover_runs` enveloppe `rempart.orchestrator.discovery.discover_cicd_runs` et
retourne `{"discovered": <n>, "run_ids": [...]}`.

## 3. Les trois machines à états (correction de A4)

Un seul run ne peut pas attendre le retest : le retest est **un autre run**,
déclenché par la fusion de la pull request de correction. Donc trois machines,
chacune courte et bornée.

### Machine A — `RempartPentestLifecycle` (tests lancés par Rempart)

Entrée : `{"tenant_id", "app_id", "pentest_id", "trigger"}` (`manual` ou `schedule`).

```
budget_gate
  └─ Choice: $.allowed == false ─────────────────────────► Succeed "Refused"
  └─ Choice: $.allowed == true
       └─ start_run → Wait 60 s → poll_run
            └─ Choice: $.done == false ──► Wait 60 s (boucle, plafond 4 h)
            └─ Choice: $.done == true
                 ├─ $.run_status != "completed" ──► Fail "PentestNotCompleted"
                 └─ $.run_status == "completed"
                      └─ collect_findings
                           ├─ $.findings_created == [] ──► Succeed "CleanRun"
                           └─ sinon ──► dispatch_triage → create_tickets
                                        → request_remediation → Succeed "RemediationRequested"
```

Plafond de boucle : un compteur `iterations` dans le payload, incrémenté par
`poll_run`, `Choice: $.iterations >= 240` → `Fail "PentestTimeout"` (240 × 60 s
= 4 h, cohérent avec le chapitre 11.4 et `ENF-PERF-01`).

### Machine B — `RempartCicdIntake` (runs découverts, déjà terminés)

Entrée : `{"app_id", "tenant_id", "run_id"}`.

```
collect_findings
  ├─ $.findings_created == [] ──► Succeed "CleanRun"
  └─ sinon ──► dispatch_triage → create_tickets → request_remediation
               → Succeed "RemediationRequested"
```

Pas de `budget_gate` ni de `start_run` : la porte CI/CD du client a **déjà**
lancé et terminé le test. Pas de `poll_run` non plus.

### Machine C — `RempartRetestClose` (preuve de fermeture)

Entrée : `{"app_id", "tenant_id", "run_id"}` où `run_id` est le run de retest.

```
close_or_reopen
  ├─ $.closed != [] ──► Succeed "ClosedWithProof"
  └─ $.reopened != [] ──► Succeed "RegressionReopened"
  └─ sinon ──► Succeed "NoChange"
```

C'est la machine qui rend réel le chapitre 8.4 : **fermeture avec preuve** ou
**réouverture en cas de régression**.

### Déclenchement

| Machine | Déclencheur |
|---|---|
| A | `POST /v1/applications/{id}/runs` (demande) et l'EventBridge Scheduler mensuel (planification) |
| B | La Lambda `discover_runs` (toutes les 5 min), une exécution par run découvert |
| C | Un run dont le `trigger` vaut `retest` et qui passe à l'état terminal |

## 4. Notifications — module absent à créer (A3)

Nouveau dossier : **`backend/rempart/notifications/`**

| Fichier | Rôle |
|---|---|
| `handler.py` | `lambda_handler(event, context)` — le nom exact que le CDK référence déjà. Distribue selon `event["kind"]`. |
| `kinds.py` | Les quatre événements d'EF-NOT-01 : `critical_finding_confirmed`, `delivery_blocked`, `deadline_overdue`, `budget_threshold`. Une constante par kind, jamais de chaîne magique dispersée. |
| `templates.py` | Sujet + corps **en anglais** (le portail et les livrables de soumission sont en anglais), une fonction par kind, paramètres explicites. Zéro duplication d'en-tête/pied : un gabarit commun. |
| `ses_client.py` | `SesClient.send(to, subject, body_html, body_text)` — boto3 injectable, donc testable. |

Contrat :
- `handler.lambda_handler(event, context)` rend `{"sent": <n>, "skipped": <n>, "errors": [...]}`.
- **Aucune exception ne sort** du handler : un échaut d'envoi est journalisé et
  compté dans `errors`. Une notification ne doit jamais casser l'orchestration.
- Les destinataires viennent du `Tenant.contacts` (champ déjà présent), filtrés
  par rôle si le contact le précise.
- Le corps cite toujours : le client, l'application, la faille ou le seuil, la
  priorité, l'échéance, et le lien vers le portail. **Aucun détail
  d'exploitation** (étapes, scripts) dans l'e-mail — ENF-SEC-05.
- Variables d'environnement lues : `REMPART_SES_FROM_DOMAIN`,
  `REMPART_SES_CONFIGURATION_SET`, `REMPART_REGION`, `REMPART_PORTAL_URL`.

## 5. Test de contrat CDK ↔ code (anti-récidive)

Nouveau test : **`backend/tests/iac/test_handler_contract.py`**

Il doit, pour chaque stack CDK synthétisée :
1. Extraire toutes les propriétés `Handler` des ressources
   `AWS::Lambda::Function` du template.
2. Pour chacune, vérifier que le module est importable **et** que la fonction
   existe, avec une signature compatible `(event, context)`.
3. Échouer en nommant précisément le handler introuvable.

Ce test est ce qui rend A1/A2/A3 **impossibles** à l'avenir : il casse la CI dès
qu'un handler déclaré n'existe pas. Il doit aussi couvrir
`rempart.api.app.lambda_handler`.

## 6. Périmètre d'écriture par agent (un seul écrivain par fichier)

| Agent | Écrit | Ne touche pas |
|---|---|---|
| A | `backend/rempart/orchestrator/lambda_handlers.py`, `backend/tests/orchestrator/test_lambda_handlers.py` | `tasks.py`, `iac/` |
| B | `backend/rempart/notifications/**`, `backend/tests/notifications/**` | tout le reste |
| C | `iac/control-plane/stacks/orchestrator.py`, `backend/tests/iac/test_handler_contract.py`, `backend/tests/iac/test_synth.py` | `backend/rempart/**` |

C dépend des noms de A : il code contre **ce contrat**, pas contre le code de A.
Si A doit renommer, A met à jour ce fichier **d'abord**.

## 7. Définition de fini

1. `cd backend && ../.venv/bin/python -m pytest tests -q` → tout vert
   (203 tests existants **plus** les nouveaux ; aucun test supprimé ni affaibli).
2. `ruff check rempart tests` et `ruff check iac` → clean.
3. `python3 -c "import rempart.orchestrator.lambda_handlers"` → les neuf
   handlers présents.
4. Le test de contrat § 5 passe **et** échoue si on renomme un handler (le
   vérifier une fois en cassant volontairement un nom, puis restaurer).
5. Aucun fichier ≥ 500 lignes, aucune fonction ≥ 50 lignes.
