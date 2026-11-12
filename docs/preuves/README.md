# Preuves rejouables des correctifs

Ce dossier contient la **fiche de preuves** du 12/11/2026
([`2026-11-12-corrections.md`](2026-11-12-corrections.md)) : pour chaque défaut
corrigé, le symptôme mesuré *avant*, le commit du correctif, et la preuve
*après* — avec la valeur observée et la commande qui la produit.

## Rejouer les preuves

```bash
# 1. un jeton Cognito (les preuves P2/P2b/P4 en ont besoin)
aws cognito-idp initiate-auth --auth-flow USER_PASSWORD_AUTH \
  --client-id 7qr971kfs2jlj5i2d065mb1fbl \
  --auth-parameters USERNAME="<utilisateur>",PASSWORD="<mot de passe>"

# 2. les preuves
REMPART_TOKEN="$(aws cognito-idp initiate-auth ... | jq -r .AuthenticationResult.IdToken)" \
REMPART_DEPLOY_SINCE="2026-11-12T14:30:00+00:00" \
  python3 scripts/proof_real.py
```

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
