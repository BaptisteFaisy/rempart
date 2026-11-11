# Vérification de l'API AWS Continuum / Security Agent

> Contrôle action par action contre la référence officielle :
> <https://docs.aws.amazon.com/securityagent/latest/APIReference/API_Operations.html>
> (service `securityagent`, version **2025-09-06**).
>
> Implémentation : [`backend/rempart/orchestrator/sa_client.py`](../backend/rempart/orchestrator/sa_client.py)
> Tests : [`backend/tests/orchestrator/test_sa_client.py`](../backend/tests/orchestrator/test_sa_client.py)
> Double de test : `FakeSecurityAgentClient` dans [`backend/tests/fakes_sa.py`](../backend/tests/fakes_sa.py)

Vérifié le **11 novembre 2026**. Toutes les actions sont en `POST` avec un corps
JSON ; **aucune n'utilise de paramètre d'URI**.

| Action | Paramètres requis (doc) | Réponse (doc) | Statut |
|---|---|---|---|
| `CreateAgentSpace` | `name` | `agentSpaceId` | conforme |
| `CreateTargetDomain` | `targetDomainName`, `verificationMethod` (`DNS_TXT` \| `HTTP_ROUTE` \| `PRIVATE_VPC`) | `targetDomainId`, `domainName`, `verificationStatus` | **corrigé le 2026-11-11** : on passait `agentSpaceId` + `domain` |
| `VerifyTargetDomain` | `targetDomainId` | `status` | **corrigé le 2026-11-11** : on passait `agentSpaceId` + `domainId` |
| `CreatePentest` | `agentSpaceId`, `title` | `pentestId` | **corrigé le 2026-11-11** : `title` était absent, on envoyait `configuration` |
| `StartPentestJob` | `agentSpaceId`, `pentestId` (optionnels : `jobType` `FULL`\|`REVALIDATION`\|`CICD`, `scopeChanges`, `selectedFindingIds`) | `pentestJobId`, `status` | **corrigé le 2026-11-11** : `agentSpaceId` absent ; réponse lue comme `jobId` |
| `StopPentestJob` | `agentSpaceId`, `pentestJobId` | corps vide | **corrigé le 2026-11-11** : on passait `jobId` seul |
| `BatchGetPentestJobs` | `agentSpaceId`, `pentestJobIds` (tableau) | `pentestJobs` | **corrigé le 2026-11-11** : `agentSpaceId` absent ; liste lue comme `jobs` |
| `ListPentests` | `agentSpaceId` | `pentestSummaries` | **corrigé le 2026-11-11** : liste lue comme `pentests` |
| `ListPentestJobsForPentest` | `agentSpaceId`, `pentestId` | `pentestJobSummaries` | **corrigé le 2026-11-11** : `agentSpaceId` absent ; liste lue comme `pentestJobs` |
| `ListFindings` | `agentSpaceId` (optionnels et **mutuellement exclusifs** : `pentestJobId`, `codeReviewJobId`) | `findingsSummaries` | **corrigé le 2026-11-11** : `agentSpaceId` absent ; `jobId` au lieu de `pentestJobId` ; liste lue comme `findings` |
| `UpdateFinding` | `agentSpaceId`, `findingId` | corps vide | **corrigé le 2026-11-11** : `agentSpaceId` absent |
| `StartCodeRemediation` | `agentSpaceId`, `findingIds` (**tableau**) ; `pentestJobId` **ou** `codeReviewJobId`, mutuellement exclusifs | corps vide | **corrigé le 2026-11-11** : on passait `findingId` au singulier, sans `agentSpaceId` |

## Bugs trouvés par cette vérification

1. **`StartCodeRemediation`** : la doc exige `agentSpaceId` (requis) et
   `findingIds` **au pluriel, tableau de chaînes**. Notre wrapper envoyait
   `findingId` au singulier et aucun espace d'agent → l'appel aurait échoué en
   production. C'est le bug qui a déclenché cette vérification.
2. **`agentSpaceId` requis presque partout** : 8 actions sur 12 l'exigent, notre
   wrapper ne le passait nulle part. Il faut donc que l'`Application` porte son
   `agent_space_id` et que chaque appel le transmette — c'est fait dans
   `orchestrator/tasks.py`, `orchestrator/discovery.py` et
   `api/routes/{onboarding,runs,findings}.py`.
3. **Noms des listes de réponse** : `pentestSummaries`, `pentestJobSummaries`,
   `findingsSummaries` — et non `pentests`, `pentestJobs`, `findings`. Un nom
   faux ne lève pas d'erreur : il renvoie une liste vide, donc « aucune faille
   trouvée ». Bug silencieux, le plus dangereux des trois.
4. **`stop_run` (API HTTP)** : la fonction référençait une variable `app`
   jamais définie dans sa portée → `NameError` à l'exécution, détecté par
   `ruff` (F821) et non par les tests (le chemin n'était pas couvert). Corrigé :
   l'application est rechargée depuis le `run`.

## Protection anti-régression

- `require_params(action, body, required)` lève une `ValueError` explicite
  **avant** l'appel réseau si un paramètre requis manque : on obtient un message
  nommant le paramètre, pas un 400 opaque d'AWS.
- `job_source(pentest_job_id, code_review_job_id)` refuse les deux à la fois
  (ils sont mutuellement exclusifs côté API).
- `FakeSecurityAgentClient` valide les **mêmes** requis et renvoie les
  **mêmes** noms de champs. Un test qui oublierait `agentSpaceId` échoue donc
  localement, au lieu d'échouer en production.
- 15 tests dédiés dans `test_sa_client.py` : un par action, plus les cas
  d'erreur sur les requis.

## Coût — point de conception critique

Le service s'appelle officiellement **AWS Continuum** (la documentation dit
« now part of AWS Continuum » ; le point 22.10 du cahier des charges demandait
lequel des deux noms employer — réponse : **AWS Continuum** dans la soumission).

Deux capacités, deux économies très différentes :

| Capacité | Prix | Essai gratuit |
|---|---|---|
| **Continuum for penetration testing** | 50 $/heure-tâche, à la seconde | **oui** : nouveaux clients, 2 mois à partir du 1ᵉʳ test, 400 heures-tâches/mois |
| **Continuum for code vulnerabilities** | 200 $/million de lignes protégées/mois + 10 $/unité d'inférence | **non** — la page de tarification précise : « The free trial applies to Continuum for penetration testing only » |

Le cahier des charges (§ 7.3) supposait la revue de code « sans frais pendant la
préversion ». **C'est faux** au 11 novembre 2026 : elle est facturée 200 $/M
lignes/mois minimum.

**Conséquence de conception** : Rempart n'appelle **aucune action** de la
capacité « code vulnerabilities ». Vérifiable :

```bash
# les ACTIONS de la capacité payante : aucun résultat attendu
grep -rniE "create_code_review|start_code_review|batch_get_code_review|\
create_threat_model|start_threat_model|list_threats|create_security_requirement" \
  backend/rempart iac demo portal/src
# → aucun résultat

# et personne ne renseigne le sélecteur codeReviewJobId (toujours None)
grep -rn "code_review_job_id=" backend/rempart | grep -v None
# → aucun résultat
```

Nuance honnête : `sa_client.py` **accepte** un paramètre optionnel
`code_review_job_id` sur `list_findings` et `start_code_remediation`, parce que
la documentation officielle le prévoit et que `require_params` doit refléter le
contrat réel de l'API. Aucun appelant ne le renseigne : le grepper le confirme.
Si un jour la revue de code est activée, ce sera un choix explicite et chiffré,
pas un effet de bord.

La pull request de correction est demandée avec `pentestJobId`, donc la
remédiation reste sur le compteur « penetration testing », couvert par l'essai
gratuit. Les 3 premières revalidations d'une faille sont gratuites ; au-delà
elles sont facturées en heures-tâches.

## Resté à confirmer en conditions réelles

| # | Question | Pourquoi elle ne peut pas être tranchée hors ligne |
|---|---|---|
| 1 | Régions où Continuum est disponible | La page « régions » de la doc n'a pas répondu ; à lire dans la console après connexion. Le plan de contrôle peut être dans une autre région que les tests. |
| 2 | Le mode CI/CD d'une configuration s'active-t-il par API ou seulement par la console ? | `UpdatePentest` n'a pas été vérifié faute de page accessible ; à tester en S1. |
| 3 | Les heures-tâches sont-elles lisibles **pendant** l'exécution ? | `poll_run` lit `taskHours` dans `BatchGetPentestJobs` ; si le champ n'est peuplé qu'à la fin, l'arrêt automatique sur budget ne fonctionne qu'après coup. À mesurer sur le premier test réel. |
| 4 | Existe-t-il un événement de fin de test (EventBridge) ? | Sinon l'interrogation périodique toutes les 60 s reste la seule voie — c'est ce que fait l'orchestrateur aujourd'hui. |
| 5 | `FindingSummary` renvoie-t-il `severity`/`confidence`/`entryPoint`, ou seulement `name`/`riskLevel` ? | `_finding_from_sa` accepte les deux vocabulaires (`severity` **ou** `riskLevel`) pour ne pas casser. À figer après le premier `ListFindings` réel. |
| 6 | Forme IAM exacte des actions | L'annexe A du cahier des charges liste 16 actions `securityagent:` ; les 6 premières viennent de la doc de la porte CI/CD, les autres de la référence d'API. Une page décrit une migration des noms d'actions IAM : à valider au déploiement du rôle. |
