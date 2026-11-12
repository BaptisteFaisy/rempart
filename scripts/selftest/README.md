# Self-test — automation à expliciter

> `scripts/selftest.py` : Rempart s'analyse lui-même. Vrais scanners, vrai intake.

## Ce que ça prouve

Le défaut D3 (12/11/2026) a fait perdre **18 failles sur 21** : l'empreinte des
failles dégénérait, et des failles distinctes étaient avalées comme « doublons ».
Ce contrôle relance ce scénario régulièrement : il scanne le **vrai code** du
dépôt avec de **vrais scanners** (npm audit, pip-audit, bandit), fait ingérer les
résultats par le vrai `collect_findings`, et vérifie **aucune faille perdue**.

## Comment ça marche

1. **npm audit** sur `portal/package-lock.json` (les vrais avis GHSA du portail) ;
2. **pip-audit** sur `backend/requirements-ci.txt` (si l'outil est installé) ;
3. **bandit** sur `backend/rempart` (si l'outil est installé) ;
4. normalisation en failles (une = id + titre + sévérité + type + emplacement) ;
5. ingestion par le vrai `collect_findings` (double officiel `FakeSecurityAgentClient`) ;
6. assertion : nombre créé == nombre d'emplacements distincts, 0 doublon.

Sortie **0** si la conservation est exacte et qu'au moins un scanner a produit
des failles ; **1** sinon. Aucun appel AWS, aucun coût.

## Lancer en local

```bash
python3 scripts/selftest.py
```

Une exécution hebdomadaire en CI le fait tourner : `.github/workflows/selftest.yml`.

## Limites (honnêtes)

- Ce n'est **pas** un vrai test Continuum : aucun client, aucun compte distant.
- Les scanners peuvent être absents en local (pip-audit, bandit) : le script les
  saute proprement et ne s'appuie que sur ceux qui répondent.
- `npm audit --package-lock-only` suppose `npm` présent et au moins un avis de
  sécurité dans l'arbre du portail ; si l'arbre devient sain, la preuve devient
  vacante et le script le signale (sortie 1).