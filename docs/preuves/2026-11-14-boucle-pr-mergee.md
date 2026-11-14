# Preuve 2026-11-14 — la boucle de retest se ferme toute seule (idée #51)

**Défaut** : `RempartRetestClose` était synthétisée par le CDK, `close_or_reopen`
avait ses tests, le cycle 8.4 (« fermeture avec preuve ») était décrit dans le
cahier des charges — et **rien ne démarrait jamais cette machine**. Un `grep` sur
`backend/rempart` (main `a57514b`) ne renvoyait **aucun** `start_execution`.

Concrètement : une faille confirmée recevait sa PR de correction
(`request_remediation`), le client mergait la PR, et Rempart ne s'en apercevait
jamais. La faille restait `in_remediation` jusqu'à ce qu'un humain y pense. Le
« tests d'intrusion **en continu** » du produit était une promesse documentée, pas
un comportement.

**Correctif** : `POST /v1/events/github`, second point d'entrée sans jeton du
produit, plus la branche `trigger == "retest"` dans la machine A.

---

## 1. Ce qui est prouvé, et comment

Les 55 tests ajoutés (34 route, 10 orchestrateur, 11 IaC) tournent **sans AWS** :
double de magasin, double de démarreur d'exécutions, vraie Lambda `lambda_handler`
appelée avec un vrai corps brut signé. Suite complète verte :

```bash
cd backend
python -m pytest tests -q          # 1045 tests, exit 0
ruff check rempart tests           # All checks passed
ruff check ../iac tests/iac        # All checks passed
```

### L'authentification refuse sans rien révéler

```python
def test_sans_signature_le_refus_est_neutre():
    absent == false == secret_non_configure == 403
    and len({messages}) == 1
    and "configur" not in message.lower()
```

La signature porte sur les **octets bruts** du corps (schéma GitHub), pas sur un
JSON ré-écrit — testée explicitement : un HMAC calculé sur le corps canonicalisé
est **refusé** (`test_la_signature_porte_sur_les_octets_bruts_pas_sur_le_json_reecrit`).
C'est la distinction qui a motivé l'extraction de `api/webhook_auth.py` : le
webhook CI/CD du client signe le corps canonicalisé (notre propre script), GitHub
signe les octets. Une seule implémentation de la comparaison constante-temps pour
les deux.

### L'isolation multi-tenant tient sur la jointure, pas sur l'URL

```python
def test_une_pr_d_un_autre_locataire_ne_mut_rien_chez_voisin():
    # PR sur `t-b/shop`, URL de la faille de `t-a`
    assert payload["ignored"] == "no_matching_finding"
    assert starter.calls == []
    assert store.get_finding("f-t-a").status == "in_remediation"
    assert store.get_finding("f-t-b").status == "in_remediation"
```

La recherche de la faille est **bornée à l'application du dépôt**
(`_finding_for_pull_request(store, app.app_id, url)`). Sans cette borne, un dépôt
d'un autre locataire portant une URL de PR semblable muterait une faille d'autrui.

### Un rejouement de GitHub ne coûte pas un second test

GitHub rejoue toute livraison sans 2xx. Le nom d'exécution est dérivé de
(faille, PR) — `retest-f-t-a-pr7` — et Step Functions refuse un doublon pendant
90 jours ; ce refus devient `DuplicateExecution`, rendu par 202 avec
`started: false, reason: "already_requested"` :

```python
def test_un_rejouement_ne_debute_pas_deux_tests():
    assert first_body["started"] is True
    assert second_body["started"] is False
    assert second_body["reason"] == "already_requested"
```

À 50 $/heure-tâche, un webhook qui démarre deux tests par PR mergée est un défaut
facturé.

### Le retest vise la seule faille corrigée

`StartPentestJob` accepte `jobType` (FULL | REVALIDATION | CICD) et
`selectedFindingIds` (modèle officiel `securityagent` 2025-09-06). Le payload les
porte, et `tasks.start_run` les transmet :

```python
def test_start_run_transmet_le_type_de_job_et_les_failles():
    assert calls[0]["jobType"] == "REVALIDATION"
    assert calls[0]["selectedFindingIds"] == ["f-t-a"]

def test_un_test_ordinaire_ne_porte_aucune_option():
    assert "jobType" not in body and "selectedFindingIds" not in body
```

Sans `selectedFindingIds`, Continuum retesterait **toute** l'application alors
qu'une seule correction a été mergée : plus cher, et la preuve de fermeture
(EF-COR-04) ne dirait plus quelle faille ce run a éteinte.

### Le routage du retest est atteint seulement après un run terminé

Vérifié dans le gabarit CloudFormation synthétisé, pas seulement dans le code :

```python
def test_le_routage_est_atteint_seulement_un_run_termine():
    completed = _choice(definition, "IsRunCompleted")
    assert branch[0]["Next"] == "RetestRouting"
    assert completed["Default"] == "PentestNotCompleted"   # un Fail
```

Placé **avant** le contrôle « terminé », un job arrêté par le garde-fou de budget
atteindrait `close_or_reopen` sur un run vide — et `close_or_reopen` **fermerait**
les failles, faute de les voir dans les résultats. Déclarer corrigé ce qui ne
l'est pas : le pire défaut possible pour un produit de sécurité.

```python
def test_le_bloc_de_fermeture_na_une_seule_implementation():
    assert named["RempartRetestClose"] == CLOSE_BLOCK_ORDERED
    assert named["RempartPentestLifecycle"] == CLOSE_BLOCK_ORDERED
    assert named["RempartCicdIntake"] == []   # découvre des failles, n'en ferme aucune
```

Machine A (branche retest) et machine C portent le **même** bloc, état par état :
`_close_block()` est partagé, donc la preuve de fermeture n'a pas deux
implémentations.

### Le droit IAM est exact, et le secret jamais en clair

```text
Route      : "POST /v1/events/github"  AuthorizationType=NONE  AuthorizerId absent
Droit      : {"Action": "states:StartExecution",
              "Resource": {"Fn::ImportValue":
                "RempartOrchestratorStack:ExportsOutputRefPentestLifecycleMachine…"}}
Environ.   : REMPART_RETEST_MACHINE_ARN = même export
Secret     : absent du gabarit non configuré ;
             {{resolve:ssm-secure:/rempart/github-webhook-secret}} quand configuré
```

Une seule instruction, une seule ressource, **pas de joker** : sinon une route
publique pourrait exécuter n'importe quelle machine du compte. L'ARN vient du
paramètre d'environnement de la Lambda, jamais du corps de requête.

### Aucune entrée invalide ne rend 500

Douze corps hostiles parametrés (`repository` chaîne au lieu d'objet, `a/b/c`,
300 caractères, `html_url` numérique, corps tronqué…) : statuts attendus
`400/403/429`. Un 5xx ferait rejouer la livraison par GitHub, puis **désactiver
le hook** — la boucle se rouvrirait silencieusement, sans alarme.

Et un événement d'un autre type (`push`, `issues`, `deployment`) rend **202** avec
`ignored: "unsupported_event:…"`, pas 400 : même raison.

---

## 2. Un défaut réel trouvé pendant ce travail

`_event_of` faisait `(body.get("repository") or {}).get("full_name")`. Si
`repository` arrive en chaîne (`{"repository": "t-a/shop"}`), `.get` levait
`AttributeError` → **500**. Attrapé par le test de fuzz, corrigé par un
`isinstance(envelope, dict)` explicite. Même classe de bug que celui du 12/11
(une chaîne non fermée dans `import_verdicts.py`) : la validation d'entrée est le
seul endroit où elle se voit.

---

## 3. Ce qui n'est PAS prouvé

- **Aucun déploiement AWS** : la session `aws login` a expiré. La route
  `/v1/events/github`, le paramètre SSM du secret et le droit
  `states:StartExecution` sont dans le gabarit synthétisé, pas dans le compte.
  Tant que la stack `RempartApiStack` n'est pas redéployée, le webhook réel
  répond 404 sur `d1o2xnfrq8xomh.cloudfront.net`.
- **Aucun test Continuum réel** : le retest n'a donc jamais été exécuté contre
  l'API de AWS. Il reste borné par le free tier non confirmé (`402`,
  `free_tier_not_confirmed`) et par la fenêtre de test en production —
  volontairement : une fusion de PR ne franchit aucun garde-fou.
- **Le hook côté GitHub n'est pas configuré** : il faut créer le webhook sur le
  dépôt du client (URL, secret, événement `pull_request`) — opération côté client,
  hors de ce dépôt.
- `scripts/proof_real.py` ne couvre pas encore cette route : les preuves
  rejouées contre l'environnement déployé viendront après le déploiement.

## 4. Rejouer

```bash
cd backend
python -m pytest tests/api/test_github_webhook.py \
                        tests/orchestrator/test_retest.py \
                        tests/iac/test_retest_loop.py -q
# 55 tests, dont la synthèse CDK (route, droit, routage, secret).
```

En local, sans AWS : `REMPART_GITHUB_WEBHOOK_SECRET=<secret> python3
scripts/serve_local.py`, puis une livraison signée sur le corps brut :

```bash
BODY='{"action":"closed","number":7,"pull_request":{"html_url":"https://github.com/t-a/shop/pull/7","merged":true},"repository":{"full_name":"t-a/shop"}}'
SIG=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$SECRET" -hex | awk '{print $NF}')
curl -s -X POST http://127.0.0.1:8080/v1/events/github \
  -H "X-GitHub-Event: pull_request" -H "X-Hub-Signature-256: sha256=$SIG" \
  -H 'Content-Type: application/json' -d "$BODY"
```
