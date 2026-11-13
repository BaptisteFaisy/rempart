# Fiche de preuves — session du 13/11/2026 : le vrai modèle en production

> Suite de `docs/preuves/2026-11-12-corrections.md`. Objectif de la session :
> rendre le **triage par un vrai LLM (InferHub)** effectif en production, et le
> prouver. Chaque ligne est une preuve rejouable, avec la valeur observée.

## Ce qui est livré (preuves mesurées)

| Défaut | Symptôme mesuré AVANT | Correctif | Preuve APRÈS |
|---|---|---|---|
| D13 — venv empaqueté + synthèse qui fuit | asset Lambda **655 Mo** (`.venv` copié) ; 111 dossiers `cdk.out*` = **59 Go**, disque 100 %, suite en ENOSPC | `ffd9db2` (exclusions + dossier de synthèse de session nettoyé) | asset **0,4 Mo** (70 fichiers) ; **0** `cdk.out*` après la suite ; 979 tests verts |
| D14 — dépendances CI ≠ layer | `requirements-ci.txt` sans `openai` → `build_model_client()` rend `None` → triage muet sur un poste installé de la CI | `a93d628` (+ test d'alignement layer/CI) | `proof_llm.py` → 3/3 verdicts `origine: model` |
| D15 — la clé SSM en référence dynamique | `cdk deploy` **échoue** : « SSM Secure reference is not supported in [Lambda/.../REMPART_LLM_API_KEY] » | `2f2bd0c` (la Lambda lit le SecureString au premier triage) | deployment OK ; env `REMPART_LLM_API_KEY_SSM_PARAM=/rempart/prod/llm-key` ; IAM restreint à `dispatch_triage` |
| D16 — repli déterministe silencieux | décision `triage-agent:deterministic` sans aucune trace de la cause | `8a93233` (journalisation du repli) | log `[WARNING] client du modèle indisponible … No package metadata was found for httpx2` |
| D17 — métadonnées du layer supprimées | `strands.models.openai` échoue dans la Lambda (`importlib.metadata`) → modèle jamais appelé | `7dd6b7c` (`.dist-info` conservés + `verify_layer.py` en isolement) | `verify_layer.py` → `OK` ; canari → décision `triage-agent:model` |
| D18 — booléens/lists du modèle mal lus | `bool("false")` → `true` : décision stockée `is_regression: true` alors que le modèle disait `false` ; `references` → `["item"]` | `[cette session]` (normalisation dans `from_dict`) | tests `test_les_booleans…` / `test_les_references_imbriquees` |

## Le vrai modèle tourne en production (preuve de bout en bout)

Canari isolé (aucune donnée de démonstration touchée, supprimé ensuite) :

```
app-canary / f-canary-1  (faille IDOR Critical, un doublon de app-shop)
  → invoke RempartOrchestratorStack-LambdaDispatchTriage… (HTTP direct au handler)
  réponse : {app_id: app-canary, findings_created: [f-canary-1], triaged: 1, queued: [f-canary-1]}
  décision : auteur = triage-agent:model, action = TO_VERIFY, justification = 1798 caractères
```

Journal CloudWatch de la Lambda, pendant l'invocation (le modèle **raisonne** dans
la vraie fonction, pas dans une simulation) :

```
Let me submit.
Tool #6: tool_submit_triage_proposal
References: CWE-639 (…IDOR), OWASP API1:2023 …, OWASP A01:2021.
```

Nettoyage vérifié après la preuve : `rempart-findings/applications/decisions`
contiennent **0** élément `canary`. Le pool Cognito est revenu à ses 2
utilisateurs d'origine (`303c599c…`, `703cb98c…`).

## 30/30 preuves contre l'environnement réel

Rejoué avec un vrai jeton Cognito (utilisateur de banc créé puis supprimé) :

```
$ python3 scripts/aws_bench_user.py --create --token-only   # jeton d'accès
$ REMPART_TOKEN="…" python3 scripts/proof_real.py
  30/30 preuves conformes
```

Les preuves P2 (tenants réels avec jeton), P4 (dossier de preuves stocké et
empreinte recalculable), P5.* (les 4 routes de gouvernance) sont jouées, pas
sautées.

## Deux nouveaux défauts vus par le modèle (à traiter)

Le modèle, pendant le canari, a constaté et contourné lui-même un défaut
d'échange : sa liste de `references` a été normalisée en `["item"]` et son
`isRegression: false` a été forcé à `true` — D18 ci-dessus, corrigé par la
normalisation de `TriageProposal.from_dict`. Un second reste ouvert : le
modèle émet du `reasoningContent` que l'API *Chat Completions* refuse en
conversation multi-tours (`[WARNING] reasoningContent is not supported in
multi-turn conversations with the Chat Completions API`) — sans effet
fonctionnel mesuré sur le verdict, mais à suivre (voir la PR dédiée le cas
échéant).