# Fiche de preuves — correctifs du 12/11/2026 (environnement réel)

> Chaque ligne est une **preuve rejouable**, pas une affirmation : la commande
> qui la produit et la valeur qu'elle a retournée sont dans le tableau.
> Rejouable par n'importe qui : `python3 scripts/proof_real.py` (jeton Cognito
> requis pour les preuves authentifiées, voir `docs/preuves/README.md`).

## Le contexte qui rend ces preuves nécessaires

Le 12/11/2026, un test sur un banc réel (DynamoDB Local au schéma CDK, S3Mock,
**vrai client boto3 `securityagent`** parlant au modèle officiel 2025-09-06,
vrais handlers de l'orchestrateur, vrai navigateur) a montré que les tests du
dépôt passaient tous alors que **la vraie API n'envoyait pas les mêmes
données** que les doubles de test. Dix défauts ont été trouvés ; huit ont été
corrigés et redéployés ce jour-là.

## Symptôme mesuré avant / correctif / preuve après

| Défaut | Symptôme mesuré AVANT | Correctif (commit) | Preuve APRÈS |
|---|---|---|---|
| D1 — heures-tâches | `poll_run` stockait `task_hours=0.0` alors que 0,005731 h étaient disponibles | `387c286` (`ListPentestJobTasks`) | **P6** — heures du mois recalculées depuis `rempart-runs` = heures de la prévision ; **P6b** — jours écoulés = jour du mois |
| D2 — casse des énumérations | 0 P1/P2, 0 échéance, 0 garde-fou EF-TRI-05 sur 21 failles réelles | `387c286` (normalisation à la frontière) | **P5.forecast.champs** — la prévision est servie avec les champs du modèle ; la matrice est couverte par 42 tests unitaires |
| D3 — empreinte dégénérée | 21 failles réelles → 3 créées, 18 avalées « doublons » | *ouvert* (enrichissement `BatchGetFindings` à faire) | — (un `xfail` documente le défaut restant) |
| D4 — dossier de preuves jamais stocké | `POST /evidence` → 201 + `s3_key` morte (aucun bucket dans le compte) | `9e41634` + `303610e` (bucket SSE-S3, `REMPART_REPORTS_BUCKET`) | **P4** / **P4b** / **P4c** (objet présent) / **P4d** (empreinte recalculée depuis l'objet retéléchargé = identique) |
| D5 — fenêtres de test inatteignables | `budget_gate` → `outside_test_window` pour toute app créée par l'API | `9e41634` (`test_windows` + `PUT /v1/applications/{id}`) | **P7** — la route de mise à jour existe (404 « Application », pas « route inconnue ») |
| D6 — le code ne compilait pas | `npm run build` en échec (`Audit.tsx` TS2322), `ci-portal` et `deploy-pages` rouges sur 3 pushes | `b9831d4` | **P11** / **P11b** — le bundle servi contient bien les 5 pages de gouvernance ; **P10** — la Lambda déployée est postérieure au correctif |
| D7 — preflight refusé | `OPTIONS /v1/tenants` → **401** (l'authorizer JWT s'appliquait à OPTIONS) | `303610e` (route `OPTIONS` sans authorisateur) | **P1** (204) / **P1b** (ACAO = origine du portail) |
| D8 — jeton Cognito refusé | `GET /v1/tenants` avec un vrai jeton → 401 « Authentication required » | `9e41634` + `caa48da` (forme réelle de `cognito:groups`) | **P2** (200 + tenants réels) / **P2b** (2 tenants) / **P3** (401 sans jeton) |
| D9 — webhook bavard | 403 « Clé pipeline non configurée côté serveur » (configuration divulguée) | `303610e` (clé SSM + message neutre) | **P8** (403) / **P8b** (le refus ne dit rien de la configuration) |
| D10 — portail non authentifié | « API unreachable (Failed to fetch). Is scripts/serve_local.py running? » | `caa48da` (porte d'authentification) | **P11** (200) + **P11c** (le site public reste fonctionnel) |
| CORS en libre | `Access-Control-Allow-Origin: *` sur toutes les réponses | `9e41634` + `303610e` | **P9** — une origine non autorisée ne reçoit aucun ACAO |

## Les 28 preuves, et leur valeur observée

| Preuve | Valeur observée |
|---|---|
| `P1 — le preflight CORS est traité par API Gateway (204), pas par la Lambda` | 'HTTP 204' |
| `P1b — l'origine du portail est autorisée au preflight` | 'https://d1o2xnfrq8xomh.cloudfront.net' |
| `P3 — sans jeton, l'API refuse la requête` | 401 |
| `P2 — avec un vrai jeton Cognito, l'API renvoie les tenants réels` | 200 |
| `P2b — des tenants réels sont renvoyés` | "2 tenant(s) : ['demo-b', 'demo-a']" |
| `P4 — POST /evidence est accepté` | 201 |
| `P4b — une clé de stockage est annoncée` | 'evidence/demo-b/2026-11/ev-faa374882886.json' |
| `P4c — l'objet annoncé EXISTE dans un bucket du compte` | '13 octets' |
| `P4d — l'empreinte se recalcule depuis l'objet retéléchargé` | '9f24d8d77794b0eb9f0f6c77f9ae6f9ba1c3a904b095d5bf1659c66dba28f4ce' |
| `P5.forecast — GET /v1/tenants/{id}/forecast répond 200` | 200 |
| `P5.forecast.champs — les champs forecast sont présents` | [] |
| `P5.industrialization — GET /v1/tenants/{id}/industrialization répond 200` | 200 |
| `P5.industrialization.champs — les champs industrialization sont présents` | [] |
| `P5.evidence — GET /v1/tenants/{id}/evidence répond 200` | 200 |
| `P5.evidence.champs — les champs evidence sont présents` | [] |
| `P5.policy — GET /v1/tenants/{id}/policy répond 200` | 200 |
| `P5.policy.champs — les champs policy sont présents` | [] |
| `P6 — les heures consommées du mois (DynamoDB) sont celles de la prévision (API)` | 0.0 |
| `P6b — les jours écoulés retenus sont bien ceux du jour (jamais 0, jamais 30)` | 12 |
| `P7 — PUT /v1/applications/{id} existe (404 « application », pas « route inconnue »)` | {'error': "Application 'app-book-inexistant' not found"} |
| `P8 — le webhook de déploiement refuse une requête sans clé` | 403 |
| `P8b — le refus ne révèle pas si une clé est configurée côté serveur` | {'error': 'Clé pipeline invalide ou absente'} |
| `P9 — une origine non autorisée ne reçoit pas d'Access-Control-Allow-Origin` | None |
| `P10 — la Lambda API déployée est bien plus récente que le correctif` | 'déployée le 2026-11-12T14:44:52.000+0000 (attendu >= 2026-11-12T14:30:00+00:00)' |
| `P10b — les variables attendues par les correctifs sont posées` | ['REMPART_CORS_ALLOW_ORIGINS', 'REMPART_FREE_TIER_ONLY', 'REMPART_HOURLY_RATE', 'REMPART_MAX_TASK_HOURS_PER_TEST', 'REMPART_REGION', 'REMPART_REPORTS_BUCKET', 'REMPART_TABLE_PREFIX'] |
| `P11 — le portail CloudFront répond 200` | 200 |
| `P11b — le bundle servi contient les pages de gouvernance` | {'Evidence Dossier': True, 'Audit Journal': True, 'Industrialization': True, 'Forecast': True, 'Contract Correction Policy': True} |
| `P11c — le site public (mode démo hors ligne) répond toujours 200` | 200 |

## Ce que ces preuves ne disent pas

- **P6** compare la prévision aux heures **réellement enregistrées** dans
  DynamoDB. Ces heures sont à 0 parce qu'aucun test Continuum réel n'a encore
  tourné (le garde-fou free tier refuse de lancer un test payant avant le
  23/11). La preuve atteste donc que l'arithmétique est exacte sur des données
  réelles, pas qu'un test a été facturé.
- **P10** ne peut pas afficher d'empreinte du code : AWS n'expose pas de SHA
  pour une Lambda zippée. La preuve est la date de déploiement comparée à
  `REMPART_DEPLOY_SINCE`, plus les preuves **comportementales** P1/P4/P9
  (qui ne peuvent passer qu'avec le code corrigé).
- Les preuves authentifiées (P2, P4) exigent un jeton Cognito : sans jeton,
  le script le dit et saute ces contrôles au lieu de les inventer.

## Rejouer

```bash
# jeton (utilisateur de test éphémère, à supprimer ensuite)
aws cognito-idp initiate-auth --auth-flow USER_PASSWORD_AUTH \
  --client-id 7qr971kfs2jlj5i2d065mb1fbl --auth-parameters USERNAME=…,PASSWORD=…
REMPART_TOKEN="$(…)" REMPART_DEPLOY_SINCE="2026-11-12T14:30:00+00:00" \
  python3 scripts/proof_real.py            # exit 0 si toutes les preuves tiennent
```

Le script n'écrit **rien** sur l'environnement observé : à part la génération
d'un dossier de preuves (c'est le comportement attendu de la route), il ne fait
que lire.
