# Preuves rejouables des correctifs

Ce dossier contient les **fiches de preuves** :

- [`2026-11-12-corrections.md`](2026-11-12-corrections.md) — les 10 défauts du
  12/11/2026 (contrat de l'API,Seconds clés, CORS, portail) ;
- [`2026-11-13-session-llm-production.md`](2026-11-13-session-llm-production.md) —
  le 13/11/2026 : le **vrai modèle** (InferHub) rendu effectif en production, et
  5 défauts trouvés en route (asset/synthèse, dépendances, clé SSM, repli
  muet, métadonnées du layer) ;
- [`2026-11-14-boucle-pr-mergee.md`](2026-11-14-boucle-pr-mergee.md) — la
  boucle de retest (idée #51) : rien ne démarrait jamais `RempartRetestClose` ;
  webhook GitHub signé, isolation par dépôt, idempotence face aux rejouements,
  et le routage placé après « run terminé ».

Pour chaque défaut : le symptôme mesuré *avant*, le commit du correctif, et la
preuve *après* — avec la valeur observée et la commande qui la produit.

## Rejouer les preuves

```bash
# 1. un jeton Cognito (les preuves P2/P2b/P4 en ont besoin).
#    Le script crée un utilisateur de banc, le retire du groupe et le supprime.
export REMPART_TOKEN="$(python3 scripts/aws_bench_user.py --create --token-only)"

# 2. les preuves
REMPART_DEPLOY_SINCE="2026-11-12T14:30:00+00:00" python3 scripts/proof_real.py

# 3. toujours nettoyer
python3 scripts/aws_bench_user.py --delete
```

Deux pièges mesurés le 13/11/2026, corrigés dans le script : le pool exige un
identifiant **au format e-mail**, et l'auteurisateur JWT d'API Gateway attend le
jeton d'**accès** (`AccessToken`), pas l'`IdToken` (dont l'audience est le
pool, pas l'application).

- code de sortie **0** = toutes les preuves tiennent ; **1** = au moins une
  preuve ne tient plus (le détail est affiché, puis listé en fin de sortie) ;
- `--json` sort le même résultat en JSON, pour archivage ;
- sans `REMPART_TOKEN`, les preuves authentifiées sont **sautees et annoncées**
  (`P2`, `P2b`, `P4*`) — jamais inventées ;
- `REMPART_DEPLOY_SINCE` (optionnel) compare la date de déploiement de la
  Lambda à un instant : la preuve **P10** échoue si le code déployé est plus
  ancien que le correctif.

Le script ne modifie rien sur l'environnement observé, à la seule exception de
la génération d'un dossier de preuves — qui est précisément le comportement
attendu de `POST /v1/tenants/{id}/evidence`.

## Preuves d'un déploiement

Les deux scripts de déploiement affichent eux aussi leur preuve en fin de run :

- `scripts/deploy_api.sh` — commit déployé, date de déploiement de la Lambda,
  présence de la route `OPTIONS` sans authorisateur, statut du preflight réel,
  variables d'environnement posées ;
- `scripts/deploy_portal.sh` — **empreinte SHA-256 du bundle local comparée à
  celle du bundle réellement servi par CloudFront** : si les deux diffèrent, le
  site ne sert pas ce qui vient d'être construit, et ça se voit immédiatement.

## Pourquoi des preuves, et pas des tests

Un test local prouve que le code fait ce qu'on attend **avec les données du
test**. Les dix défauts trouvés le 12/11 venaient précisément de l'écart entre
les données des doubles de test et celles de l'API réelle : `taskHours` sur un
job que l'API ne renvoie pas, `entryPoint` sur un résumé de faille qui ne
l'a pas, des énumérations en MAJUSCULES là où le code attendait « Critical ».
Une preuve rejouée contre l'environnement déployé est la seule qui attrape ce
genre d'écart.
