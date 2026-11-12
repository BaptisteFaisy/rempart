# Déploiement du portail Rempart sur CloudFront

> Écrit le 11 novembre 2026, après le déploiement réel de `RempartPortalStack`
> (compte AWS 710332178565, région eu-north-1).

## URL publique

**https://d1o2xnfrq8xomh.cloudfront.net** (CloudFront, distribution
`EYN0KKBTR7INC`, statut `Deployed`).

Codes HTTP mesurés après déploiement (propagation < 2 min) :

| Requête | Code |
|---|---|
| `/` | **200** |
| `/assets/index-dlGhNbpx.js` (asset JS, `content-type: text/javascript`) | **200** |
| `/assets/index-H_plS3AC.css` | **200** |
| `/fleet` (route profonde SPA) | **200** |

Le site de démonstration GitHub Pages (https://baptistefaisy.github.io/rempart/)
reste en ligne et intact : **200** vérifié le même jour.

## Ce qui a été déployé

`cdk deploy RempartPortalStack --require-approval never` — succès en 212 s,
aucun échec ni rollback. Ressources créées (synth vérifié avant déploiement) :

- **Bucket S3** `rempartportalstack-portalbucketf34416c0-eekv0qxwomo8` :
  accès public bloqué, chiffrement **AWS-managed** (S3_MANAGED, aucune clé KMS
  customer-managed à 1 $/mois), SSL imposé, versionné, `RETAIN` à la suppression.
- **Distribution CloudFront** : OAC (Origin Access Control) vers le bucket,
  redirection HTTP→HTTPS, `CACHING_OPTIMIZED`, `default_root_object=index.html`,
  error responses 403/404 → `/index.html` en 200 (routage SPA),
  `PRICE_CLASS_100` (Amérique du Nord + Europe uniquement, le moins cher).
  **Aucun log CloudFront** : pas de bucket de logs, donc rien à purger ni de
  rétention à配置 — c'est un choix 0 €.
- Bucket policy (accès CloudFront via OAC uniquement).

`stacks/portal.py` n'a nécessité **aucune modification** : pas de KMS
customer-managed, pas de logs, PriceClass 100 — conforme à la contrainte 0 € de
`docs/durability.md`.

Contenu uploadé : `portal/dist/` via `aws s3 sync` (Content-Type automatiques
d'après l'extension, vérifiés : JS servi en `text/javascript`), plus une copie
`404.html` identique à `index.html` pour le routage SPA.

## Mode de fonctionnement actuel : démo hors ligne (`VITE_USE_MOCKS=1`)

Le portail CloudFront tourne en **mode démo hors ligne** sur le jeu de données
figé, comme GitHub Pages — il n'appelle pas l'API réelle.

**Pourquoi** : l'authentification Cognito du portail est un flux OIDC
authorization-code + PKCE (`portal/src/auth/cognito.ts`) qui exige un **domaine
Cognito** (hôtes `/oauth2/authorize` et `/oauth2/token`). Or le User Pool
`rempart-users` (`eu-north-1_VkUAsvgSR`) **n'a aucun domaine** :
`aws cognito-idp describe-user-pool-domain --domain rempart-users` renvoie un
`DomainDescription` vide, et `stacks/identity.py` ne crée ni `UserPoolDomain`
ni callback URLs. Sans domaine, `cognitoConfig()` ne peut pas aboutir ; le
build a donc été fait avec `VITE_USE_MOCKS=1` et `VITE_BASE_PATH=/`.

L'API, elle, est bien déployée et joignable :
`https://qm6dmdkgdg.execute-api.eu-north-1.amazonaws.com` (stage `$default`).

## Ce qu'il manque pour activer l'authentification Cognito réelle

Dans `stacks/identity.py` (hors périmètre de ce déploiement) :

1. **Domaine Cognito** : `user_pool.add_domain(…)` avec un préfixe (ex.
   `rempart`) → `https://rempart.auth.eu-north-1.amazoncognito.com`. Gratuit.
2. **Sur le client `rempart-portal-client`** (`7qr971kfs2jlj5i2d065mb1fbl`) :
   déclarer le flux OAuth authorization-code + PKCE, les scopes
   `openid email profile`, et les URLs :
   - callback : `https://d1o2xnfrq8xomh.cloudfront.net/`
   - logout : `https://d1o2xnfrq8xomh.cloudfront.net/`
3. **Rebuilder le portail** avec les vraies variables puis redéployer :

   ```bash
   VITE_USE_MOCKS=0 \
   VITE_API_URL=https://qm6dmdkgdg.execute-api.eu-north-1.amazonaws.com \
   VITE_COGNITO_DOMAIN=https://<prefix>.auth.eu-north-1.amazoncognito.com \
   VITE_COGNITO_CLIENT_ID=7qr971kfs2jlj5i2d065mb1fbl \
   VITE_COGNITO_REDIRECT_URI=https://d1o2xnfrq8xomh.cloudfront.net/ \
   bash scripts/deploy_portal.sh
   ```

4. Au moins un utilisateur réel dans le pool, membre d'un des 7 groupes
   (le rôle affiché vient du claim `cognito:groups`).

L'authorizer JWT de l'API valide déjà les tokens de ce User Pool : aucun
changement côté API n'est nécessaire.

## Redéploiement

`scripts/deploy_portal.sh` : build → copie `404.html` → `aws s3 sync --delete`
→ invalidation CloudFront `/*` (1 000 chemins/mois gratuits ; `/*` compte pour
1). Garde-fous : échec explicite si la CLI AWS ou le bucket est introuvable.
Aucun secret dans le script (session AWS locale). Variables surchargeables en
tête de fichier (`BUCKET`, `DISTRIBUTION_ID`, `REGION`, `VITE_*`).

## Coût attendu : ~0 €

- S3 : ~215 Ko statiques → < 0,01 $/mois.
- CloudFront : 1 To/mois + 10 M requêtes/mois gratuits (free tier) ; le trafic
  d'un portail de démo reste très en dessous. `PRICE_CLASS_100`, pas de domaine
  personnalisé, **pas de logs** (les logs CloudFront imposeraient un bucket
  dédié), invalidations dans le quota gratuit.
- Aucune ressource always-on : pas de Lambda, pas de KMS customer-managed
  (1 $/mois évité), pas de NAT.
- Seule vigilance : le bucket est **versionné** — chaque redéploiement stocke
  les anciennes versions des assets hashés (quelques Mo ; à purger via une
  règle de cycle de vie si les déploiements devenaient quotidiens).
