# Déploiement du portail Rempart sur CloudFront

> Écrit le 11 novembre 2026 (déploiement `RempartPortalStack`), **mis à jour le
> 12 novembre 2026 : authentification Cognito réelle activée (EF-POR-01)**.
> Compte AWS 710332178565, région eu-north-1.

## État réel au 12/11/2026

Le portail CloudFront tourne en **mode API réelle** (`VITE_USE_MOCKS=0`) avec le
flux OIDC authorization-code + PKCE de `portal/src/auth/cognito.ts` :

| Élément | Valeur (publique, aucun secret) |
|---|---|
| URL du portail | **https://d1o2xnfrq8xomh.cloudfront.net** (distribution `EYN0KKBTR7INC`) |
| Domaine Cognito (gratuit) | **https://rempart.auth.eu-north-1.amazoncognito.com** — statut `ACTIVE` |
| User Pool | `eu-north-1_VkUAsvgSR` (`rempart-users`) |
| Client ID | `7qr971kfs2jlj5i2d065mb1fbl` (`rempart-portal-client`) — **sans secret** (`generate_secret=False`, vérifié : `ClientSecret` absent) |
| Flux OAuth | `code` uniquement (authorization-code + PKCE ; `implicit` retiré) |
| Scopes | `openid`, `email`, `profile` |
| Callback URLs | `https://d1o2xnfrq8xomh.cloudfront.net` **et** `…cloudfront.net/` |
| Logout URLs | idem (les deux variantes) |
| Provider | `COGNITO` |
| API | `https://qm6dmdkgdg.execute-api.eu-north-1.amazonaws.com` — `/v1/tenants` sans jeton → **401** (authorizer JWT sur ce User Pool) |

Vérifié en réel (`describe-user-pool-domain` → domaine `ACTIVE`,
`describe-user-pool-client` → callback/scopes/flows ci-dessus) et par curl :
`/oauth2/authorize` avec ces paramètres → **302 vers `/login`** puis **200**
(la page de connexion hébergée s'affiche).

Codes HTTP mesurés après redéploiement du 12/11 :

| Requête | Code |
|---|---|
| CloudFront `/` | **200** |
| CloudFront `/assets/index-CNrqUXk2.js` (bundle courant) | **200** |
| CloudFront `/fleet` (route profonde SPA) | **200** |
| GitHub Pages (https://tradoooo.github.io/rempart/) | **200** (intact, branche `gh-pages` non touchée) |

Le bundle servi contient bien la configuration Cognito (domaine, client ID,
URL d'API — vérifié par `grep` sur l'asset JS).

## Ce qui a été activé (12/11/2026)

`cdk deploy RempartIdentityStack --require-approval never` — succès en ~11 s +
~6 s (2e passe pour corriger l'output `CognitoDomainUrl`), **aucun rollback** :

1. **Domaine Cognito gratuit** ajouté dans `stacks/identity.py` :
   `user_pool.add_domain(…, cognito_domain=CognitoDomainOptions(domain_prefix="rempart"))`
   (API aws-cdk-lib 2.276 : l'ancien mot-clé `cognito_domain_prefix` n'existe
   plus ; `custom_domain` = domaine personnalisé payant, **jamais utilisé**).
2. **Client OAuth PKCE** : dans cette version de CDK l'API est unifiée sous
   `o_auth=OAuthSettings(flows=OAuthFlows(authorization_code_grant=True), scopes=…, callback_urls=…, logout_urls=…)`
   (les anciens `o_auth_flows`/`o_auth_scopes` ont disparu).
   **Point documenté** : modifier `AllowedOAuthFlows` d'un client existant exige
   `AllowedOAuthFlowsUserPoolClient=true` — le L2 CDK le positionne
   automatiquement dès qu'un flux OAuth est déclaré ; vérifié en réel
   (`AllowedOAuthFlowsUserPoolClient: true`), aucune propriété supplémentaire.
3. **Paramètre CDK `PortalUrl`** (défaut `https://d1o2xnfrq8xomh.cloudfront.net`,
   **sans slash final** — les deux variantes avec/sans sont dérivées). Surcharge :
   `cdk deploy RempartIdentityStack --parameters PortalUrl=https://autre-hote`.
   L'URL n'est plus codée en dur dans la stack.

## Connexion d'un humain : ce qui marche et ce qui reste à faire

- Le portail affiche le bouton **« Sign in with Amazon Cognito »** ; le clic mène
  à la page de connexion hébergée — comportement attendu.
- **Utilisateur de démonstration créé** : `demo@rempart.local`, groupe `demo`,
  `custom:tenant_id=demo`, e-mail marqué vérifié (côté serveur). Statut
  `FORCE_CHANGE_PASSWORD` : le mot de passe temporaire est à usage unique et
  Cognito impose d'en choisir un nouveau à la première connexion.
- **Le mot de passe temporaire n'est écrit NULLE PART** (ni dépôt, ni doc, ni
  rapport). Il a été généré en mémoire de shell puis perdu volontairement :
  **le régénérer soi-même** avec la commande ci-dessous, et le transmettre au
  juge **hors dépôt** (canal privé). Politique du pool : ≥ 12 caractères,
  majuscule, minuscule, chiffre, symbole.

  ```bash
  aws cognito-idp admin-set-user-password \
    --user-pool-id eu-north-1_VkUAsvgSR \
    --username demo@rempart.local \
    --password '<MOT_DE_PASSE_CONFORME_A_NE_PAS_COMMIT>' \
    --region eu-north-1
  # sans --permanent : l'utilisateur doit le changer à la première connexion
  ```

- Pour un autre rôle : créer l'utilisateur de la même façon puis
  `admin-add-user-to-group` avec l'un des 7 groupes (`platform_admin`, `analyst`,
  `account_manager`, `client_security`, `client_dev`, `executive`, `demo`). Le
  rôle affiché vient du claim `cognito:groups` ; le backend lit `cognito:groups`
  et `custom:tenant_id` (`resolve_principal`). Attention : le rôle `demo` est
  restreint côté API au tenant `demo` (`authorize_read`).

## Mode démo (toujours disponible)

Sans `VITE_COGNITO_CLIENT_ID`/`VITE_COGNITO_DOMAIN`, `cognitoConfig()` renvoie
`null` : persona picker hors ligne. Pour le rétablir sur CloudFront :
`VITE_USE_MOCKS=1 VITE_COGNITO_CLIENT_ID= VITE_COGNITO_DOMAIN= bash scripts/deploy_portal.sh`.
GitHub Pages reste en mode démo (build indépendant).

## Redéploiement

`scripts/deploy_portal.sh` : les valeurs réelles (domaine Cognito, client ID,
redirect URI, API, `VITE_USE_MOCKS=0`) sont désormais les **défauts** du script,
surchargeables par l'environnement. Build → copie `404.html` →
`aws s3 sync --delete` → invalidation CloudFront `/*` (1 000 chemins/mois
gratuits). Aucun secret dans le script (identifiants publics + session AWS locale).

## Coût réel : 0 €

- **Domaine Cognito** (préfixe `*.auth.eu-north-1.amazoncognito.com`) : gratuit.
  Aucun domaine personnalisé (pas de certificat ACM, pas de domaine acheté).
- **Cognito** : gratuit jusqu'à 50 000 utilisateurs actifs mensuels ; 1 utilisateur
  créé, 0 € .
- S3/CloudFront : inchangés (free tier, `PRICE_CLASS_100`, pas de logs).
- `RempartNotificationsStack` (SES) **non déployée** volontairement (exigerait un
  domaine vérifié donc acheté).
- Aucune ressource always-on créée : ni EC2, ni conteneur, ni KMS customer-managed,
  ni Step Functions démarrée. Seul l'existant (User Pool, client, groupes) a été
  modifié + 1 domaine gratuit.
- Seule vigilance inchangée : bucket versionné (anciennes versions des assets
  hashés, quelques Mo par déploiement).
