# Preuve 2026-11-14 — revue de code InferHub + correctif STS

## Résumé vérifié

- **PR #33 mergée** (`ecd811a`, `feat(revue): la revue de code branchée sur un agent InferHub, avec garde-fous`).
- **Suite backend : 1 094 tests collectés et passés** après merge.
- `ruff check backend` : vert.
- Aucun fichier touché ≥ 500 lignes ; aucune fonction touchée ≥ 50 lignes.
- Plan de contrôle redéployé en eu-north-1 après merge. Preuve du script : code identique à `main`, preflight réel HTTP 204, route OPTIONS sans autorisation, vérification variable + droit SSM/KMS du vrai modèle.

## Demande et décision de coût

La revue de code est branchée sur **le même agent InferHub que le triage** — même endpoint, même clé SSM, mêmes modèles de repli. Rempart n'appelle **pas** la fonction « code review » d'AWS Security Agent/Continuum : le runbook la chiffre à 200 $/million de lignes protégées/mois + 10 $/inférence, hors essai gratuit.

Route : `POST /v1/applications/:id/reviews`. Elle prend un diff fourni, un diff GitHub PR ou un commit. Chaque commentaire est validé contre le diff réel ; fichier absent, ligne hors hunk, ou extrait inventé sont écartés avec raison. Sans modèle réel, réponse 503 `model_unavailable` — jamais un 200 vide qui ressemblerait à une revue propre.

## Preuve réelle du modèle

Exécution de `scripts/proof_review.py --ref HEAD~1..HEAD`, sur le diff réel du correctif IAM du 14/11, avec le modèle InferHub réellement configuré :

```text
statut         : reviewed (source model, modèle combo/cheap)
durée          : 303.4 s
jetons mesurés : input 43 392, output 22 807, total 66 199
commentaires   : 7 retenus, 0 rejeté par ancrage
```

Les jetons viennent des métriques d'usage Strands, pas d'une estimation sur la taille du diff. **Coût en dollars abstenu** : le prix n'était pas configuré ; aucune valeur n'a été inventée.

Les commentaires du modèle ne sont pas tous acceptés aveuglément. Le constat STS « `RoleSessionName` absent » a été reproduit indépendamment avec botocore local : `ParamValidationError: Missing required parameter in input: "RoleSessionName"`. Le constat d'expiration a été vérifié dans le code (credentials mis en cache, job suivi jusqu'à 4 h) puis verrouillé par test.

Les autres points du modèle (notamment sur la Lambda API) n'ont pas été présentés comme des défauts établis sans vérification du chemin d'exécution réel.

## Défauts corrigés à la suite de la revue

1. **`sts:AssumeRole` sans `RoleSessionName`** : botocore refusait la requête avant tout appel réseau. Ajout d'un nom déterministe compatible STS et d'un test.
2. **Credentials temporaires mis en cache sans renouvellement** : les credentials STS expirent, alors que la Lambda suit un pentest jusqu'à 4 h. Le client est désormais reconstruit à l'échéance retournée par STS (avec marge de repli si absente) ; tests expiration et réutilisation valides.
3. **External ID facultatif avec rôle opérateur configuré** : désormais exigé pour conserver la protection confused deputy.
4. **Câblage LLM omissible au déploiement** : la variable `REMPART_LLM_API_KEY_SSM_PARAM` était conditionnelle à l'environnement du shell ; oubliée, le déploiement réussissait et le triage retombait silencieusement sur le règleur. `deploy_api.sh` a maintenant une valeur de production par défaut, vérifie le paramètre avant le changeset et prouve après déploiement variable + `ssm:GetParameter` + `kms:Decrypt`.

Le commit de la PR #33 a aussi ajouté la suite de 37 tests de revue ; le total exact est celui du checkout au moment de cette note (1 094).

## Ce qui n'est PAS prouvé / exécuté

- **Le premier vrai test Continuum n'a PAS été lancé.** Le store AWS réel contient seulement `demo-a` et `demo-b` (compte `000000000000`), pas de compte client dédié/onboardé. `free_tier_confirmed` de `demo-a` est vrai mais ce tenant de démo n'est pas un compte client réel.
- Le runbook exige un compte client éligible, l'essai gratuit disponible, l'onboarding du compte/agent space/domaine, puis une fenêtre convenue. Ces prérequis ne sont pas réunis ; les contourner pourrait déclencher une facturation. Aucun verrou n'a été abaissé.
- La preuve InferHub réelle a pris **303 s** pour ce diff. Le plafond de taille (200 ko) borne la taille, mais il reste à ajuster les limites de tokens/temps ou choisir un diff plus petit pour les revues courantes.
- Un essai au faux modèle Strands a vérifié le chemin complet de bout en bout ; le test de production ci-dessus a vérifié le modèle InferHub lui-même. Aucun commentaire ne doit être considéré comme une décision humaine ou une preuve d'absence de vulnérabilité.

## Rejouer

```bash
# Tests sans réseau, sans AWS
.venv/bin/python -m pytest backend/tests/review backend/tests/api/test_reviews_route.py -q
.venv/bin/python -m ruff check backend

# Preuve réelle — coûte une inférence ; ne lancer que si l'opérateur l'accepte
set -a && . ~/.config/agent-secrets/inferhub.env && set +a
.venv/bin/python scripts/proof_review.py --ref HEAD~1..HEAD

# La preuve réutilise les variables InferHub existantes. Elle affiche le coût
# en jetons mesuré ; le coût USD reste abstenu tant que les deux prix ne sont
# pas configurés (REMPART_LLM_USD_PER_M_INPUT / OUTPUT).
```
