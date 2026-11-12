# Runbook — recette du premier test Continuum réel

> Objectif : lancer **un** test d'intrusion Continuum réel le **23/11/2026**,
> en restant **gratuit** (free tier) et **plafonné**. Ce document est une
> recette dans l'ordre, pas une procédure exhaustive : chaque étape pointe la
> route, la variable d'environnement ou la commande **réelle** du dépôt.
> Méthode et précautions tarifaires :
> [`free-tier-runbook.md`](free-tier-runbook.md).

## Rappel : pourquoi le 23/11

L'essai Continuum dure **2 mois à partir du premier test** et le jugement se
termine le **22/01/2027**. Un test lancé avant le 23/11 ferait expirer l'essai
avant la fin du jugement (cahier des charges § 16.2). Développer sur données
figées d'ici là.

## Prérequis — à vérifier AVANT de lancer

| # | Prérequis | Où / comment |
|---|---|---|
| 1 | **Éligibilité free tier confirmée** | Console AWS → **Billing → Free Tier** (« Free Tier eligible ») **et** console AWS Continuum qui propose « Start your free trial » (essai non consommé). |
| 2 | **Compte client neuf** | Le test réel se fait dans le **compte client** (pas le MSP) ; c'est lui qui doit être éligible. |
| 3 | **Domaine vérifié** | `POST /v1/applications/:id/onboarding` → `CreateTargetDomain` + `VerifyTargetDomain` (méthode `DNS_TXT` par défaut ; `HTTP_ROUTE` évite tout accès DNS). |
| 4 | **Agent space** | Onboarding → `CreateAgentSpace`, l'`agent_space_id` est posé sur l'application (`GET /v1/applications/:id/onboarding` le confirme). |
| 5 | **Fenêtre de test convenue** | `PUT /v1/applications/{id}` avec `test_windows` (format `{"days": […], "start": "HH:MM", "end": "HH:MM", "environment": "…"}`, heures **UTC**). Sans fenêtre, le test en production est refusé (`outside_test_window`). |

## Étapes, dans l'ordre

1. **Déployer le plan de contrôle** (MSP), si ce n'est pas déjà fait :
   `cd iac/control-plane && cdk deploy --all` (README § Deploy).
2. **Onboarder le compte client** avec le template
   `iac/client-account/rempart-client.template.yaml` : il crée le rôle
   cross-account `rempart-operator` (`sts:ExternalId`), le rôle pipeline GitHub
   OIDC, et l'alarme `AWS::Budgets::Budget`.
3. **Créer l'application** cible : `POST /v1/tenants/:id/applications`, puis
   **onboarder** : `POST /v1/applications/:id/onboarding`
   (`{"verification_method": "DNS_TXT"}`). Vérifier `GET /v1/applications/:id/onboarding`
   → `"onboarded": true`, `agent_space_id` présent, domaines listés.
4. **Confirmer l'éligibilité free tier pour le tenant** (déverrouillage d'un
   verrou par tenant, pas global) : poser `free_tier_confirmed = true` sur
   l'item du tenant (cf. `free-tier-runbook.md` § 3, étape 3). Ne **pas** lever
   `REMPART_FREE_TIER_ONLY` globalement.
5. **Poser la fenêtre de test** : `PUT /v1/applications/{id}` avec un périmètre
   minimal (1 app, 1 domaine, `blocking_threshold=Critical`), puis `test_windows`
   = une fenêtre courte qui couvre l'heure du test.
6. **Lancer le test** : `POST /v1/applications/{id}/runs` — uniquement pendant
   la fenêtre. C'est le point où une heure-tâche peut être facturée.
7. **Suivre** : `GET /v1/runs/{jobId}` et `GET /v1/applications/{id}/runs`
   (statut, `task_hours`, coût estimé). Le polling de l'orchestrateur est plafonné
   (4 h max) et `poll_run` remonte les heures réelles.
8. **Trier** : les failles arrivent dans la file (route `/v1/findings`) ; le LLM
   propose, la matrice déterministe impose, un Critical/High attend une décision
   humaine (`POST /v1/findings/:id/decision`).
9. **Clôturer** : uniquement quand un re-test ne retrouve plus l'empreinte
   (`POST /v1/findings/:id/remediation` puis re-test → `closed`).

## Garde-fou budget

| Verrou | Variable d'environnement (défaut) | Effet |
|---|---|---|
| Refus tant que free tier non confirmé | `REMPART_FREE_TIER_ONLY=1` | `POST /v1/applications/{id}/runs` répond **402** (`free_tier_not_confirmed`) tant que `Tenant.free_tier_confirmed` est faux. |
| Plafond par test | `REMPART_MAX_TASK_HOURS_PER_TEST=5` | `poll_run` appelle `StopPentestJob` dès 5 heures-tâches, même budget large. Audit `run.auto_stopped`. |
| Tarif horaire | `REMPART_HOURLY_RATE=50` | 50 $/heure-tâche, facturé à la seconde. |
| Budget mensuel par client | `PUT /v1/tenants/:id/budget` | Alertes 50/80/100 %, `StopPentestJob` à 100 % (scénario R8). |
| Alarme AWS indépendante | `AWS::Budgets::Budget` (template client) | Deuxième filet si le code a un bug. |

## Surveiller le coût pendant le test

- Portail → page **Budget** (heures consommées, seuils franchis, interrupteur
  d'auto-stop).
- API : `GET /v1/tenants/:id/budget` et `GET /v1/tenants/:id/forecast`
  (prévision au rythme courant).
- Console : `aws dynamodb scan` sur la table `rempart-budget`
  (`tenant_id`, `month`, `hours_used`, `thresholds_hit`) — voir
  [`free-tier-runbook.md`](free-tier-runbook.md) § 4.
- Si la consommation monte plus vite que prévu : **couper l'auto-stop** ou
  `POST /v1/runs/:jobId/stop`.

## Rollback / arrêt

- **Auto-stop budget** : `StopPentestJob` à 100 % du budget mensuel, ou à
  `REMPART_MAX_TASK_HOURS_PER_TEST` — c'est le filet automatique le plus rapide.
- **Arrêt manuel** : `POST /v1/runs/:jobId/stop`.
- **Démanteler le plan de contrôle** : `cd iac/control-plane && cdk destroy` —
  supprime les tables, API Gateway, Step Functions, CloudFront et Cognito.
- **Démanteler le compte client** : supprimer la stack CloudFormation
  `rempart-client-agent` (rôle cross-account, pipeline role, alarme budget).
- **Dans tous les cas** : révoquer tout token de test éphémère créé pour la
  recette, et repasser `free_tier_confirmed = false` sur le tenant si l'on veut
  refermer le verrou.

## Après le test

Noter le **coût réel** (heures-tâches → dollars), vérifier l'ingestion réelle
(`collect_findings` → DynamoDB), la clôture réelle (re-test → `closed`), puis
écrire le post-mortem (idée #28 du plan de consolidation).