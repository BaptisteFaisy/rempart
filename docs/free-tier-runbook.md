# Runbook « test gratuit » — ne jamais payer une heure-tâche

> Objectif : le test d'intrusion de démonstration coûte **0 $**.
> Vérifié contre la page de tarification officielle le 11 novembre 2026.

## 1. Ce qui est gratuit, ce qui ne l'est pas

| Poste | Coût | Couvert par le free tier ? |
|---|---|---|
| **Continuum for penetration testing** | 50 $/heure-tâche, à la seconde | **OUI** — 2 mois à partir du 1ᵉʳ test, **400 heures-tâches/mois**, pour les nouveaux clients |
| Les 3 premières revalidations d'une faille | 0 $ | oui, explicitement gratuit |
| **Continuum for code vulnerabilities** (revue de code) | 200 $/M lignes protégées/mois **+ 10 $/unité d'inférence** | **NON** — la page dit : « the free trial applies to Continuum for penetration testing only » |
| Porte CI/CD pendant la préversion | à confirmer | le cahier des charges la disait gratuite ; à revérifier avant le 1ᵉʳ test |
| Plan de contrôle Rempart (Lambda, DynamoDB, API GW, CloudFront, Cognito, S3, Step Functions, SES) | serverless, à l'usage | oui, dans les quotas gratuits à volume hackathon → **< 1 $/mois** |
| Apps de démonstration | 0 $ si **locales** | oui : elles tournent sur le PC, pas sur AWS |

**Le seul risque réel de facture = la revue de code et un test hors free tier.**

## 2. Les 4 verrous déjà codés dans Rempart

| Verrou | Où | Effet |
|---|---|---|
| `free_tier_only = True` | `rempart/common/config.py` (`REMPART_FREE_TIER_ONLY`, défaut **1**) | `budget_gate` et `POST /v1/applications/{id}/runs` **refusent** le test tant que `Tenant.free_tier_confirmed` est faux. Raison : `free_tier_not_confirmed`, HTTP 402. Audit `run.refused_free_tier`. |
| `max_task_hours_per_test = 5.0` | idem (`REMPART_MAX_TASK_HOURS_PER_TEST`) | `poll_run` appelle `StopPentestJob` dès qu'un test dépasse 5 heures-tâches, **même si le budget mensuel est large**. Audit `run.auto_stopped` avec la raison `task_hour_cap`. |
| Budget mensuel par client | `rempart/common/budget.py` | Alertes 50/80/100 %, `StopPentestJob` à 100 %. |
| `AWS::Budgets::Budget` dans le compte client | `iac/client-account/rempart-client.template.yaml` | Alarme côté AWS, indépendante de Rempart : deuxième filet si le code a un bug. |

Ces verrous sont testés : `tests/orchestrator/test_tasks.py` couvre le refus
sans free tier, la levée du garde-fou, l'audit, l'arrêt au plafond, et la
lecture des deux variables d'environnement.

**Conséquence pratique : par défaut, Rempart ne peut PAS lancer un test réel.**
Il faut une action explicite pour déverrouiller.

## 3. Procédure pour que le test soit gratuit

### Étape 1 — Vérifier l'éligibilité du compte (2 min, sans rien déployer)

1. Console AWS → **Billing** → **Free Tier** : le compte doit apparaître comme
   éligible (« Free Tier eligible »).
2. Console **AWS Continuum** (<https://console.aws.amazon.com/securityagent>) :
   si l'écran propose « Start your free trial », l'essai n'est pas encore
   consommé. S'il affiche des heures-tâches déjà facturées, le compte n'est
   **pas** neuf → aller à l'étape 4 (plan B).
3. Vérifier la **région** : Continuum n'est pas disponible partout. Le plan de
   contrôle peut être dans une autre région que les tests (cahier des charges
   § 20). Régions à tester en premier : `us-east-1`, `eu-west-1`, `eu-west-3`.

### Étape 2 — Créer un compte dédié si nécessaire

Si le compte existant n'est pas éligible : créer un **nouveau compte AWS**
dans une organisation, ou un compte indépendant. Le free tier Continuum est
accordé par compte. Trois comptes sont prévus (cahier des charges § 17.1) :
MSP, client A, client B — **le test réel se fait dans le compte client**, donc
c'est lui qui doit être neuf.

### Étape 3 — Déverrouiller, une seule fois, au bon moment

```bash
# 1. confirmer l'éligibilité pour le tenant de démonstration
aws dynamodb update-item --table-name rempart-tenants \
  --key '{"tenant_id":{"S":"demo-a"}}' \
  --update-expression 'SET free_tier_confirmed = :t' \
  --expression-attribute-values '{":t":{"BOOL":true}}'
```

**Ne pas lever `REMPART_FREE_TIER_ONLY` globalement.** Le verrou par tenant est
suffisant et il reste actif pour tous les autres.

### Étape 4 — Plan B si le compte n'est pas neuf : démonstration sans test réel

Le scénario du hackathon ne demande **pas** un test réel en direct. Trois
options, de la plus sûre à la plus coûteuse :

| Option | Coût | Ce que le juge voit |
|---|---|---|
| **A. Données figées** : un jeu de données de démonstration injecté dans DynamoDB (findings, runs, tickets, rapport mensuel) produit par une exécution réelle antérieure | **0 $** | Tout le portail fonctionne, les 3 indicateurs sont mesurés, la vidéo montre les horodatages réels |
| **B. Un seul test minimal** : périmètre réduit à 2-3 chemins d'URL, `blocking_threshold=Critical`, plafond `max_task_hours_per_test=1.0` | 0 $ si free tier, sinon **≤ 50 $** | Un test réel de bout en bout |
| **C. Test complet** | ~173 $ (3,5 h-tâches, exemple publié par AWS) | inutile pour la démo |

**Recommandation : option A pour la soumission, option B uniquement si le
compte est neuf.**

### Étape 5 — La date à ne pas manquer

> Cahier des charges § 16.2 : l'essai dure **2 mois à partir du premier test**,
> et le jugement se termine le **22 janvier 2027**.

**Donc : le premier test réel des comptes de démonstration ne doit pas partir
avant le 23 novembre 2026.** Avant cette date, développer sur un autre compte
ou sur données figées. Un test lancé le 12 novembre ferait expirer l'essai le
12 janvier, avant la fin du jugement.

## 4. Contrôle continu pendant le hackathon

```bash
# consommation du mois, par tenant
aws dynamodb scan --table-name rempart-budget \
  --projection-expression 'tenant_id, #m, hours_used, thresholds_hit' \
  --expression-attribute-names '{"#m":"month"}'
```

Et dans le portail : page **Budget** — heures consommées, seuils franchis,
interrupteur d'arrêt automatique. Le couper si la consommation monte plus vite
que prévu.

## 5. Résumé en une ligne

Par défaut Rempart **refuse** de lancer un test ; le déverrouillage est une
action manuelle par tenant, plafonnée à 5 heures-tâches, doublée d'une alarme
AWS Budgets côté client — et la démonstration peut se faire entièrement sur
données figées, à 0 $.
