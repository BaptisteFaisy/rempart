# Support — Rempart

## Poser une question

- **Questions / discussions** : ouvrez une issue sur
  [`Tradoooo/rempart`](https://github.com/Tradoooo/rempart) en décrivant le
  contexte. C'est le canal le plus direct.
- **Bogue ou faille de sécurité** : voir [`SECURITY.md`](SECURITY.md)
  (divulgation responsable) — ne postez pas de détails exploitables en public.

## Où trouver la documentation

| Besoin | Document |
|---|---|
| Présentation générale et démo | [`README.md`](README.md) |
| Page des évaluateurs (URL publique, tour guidé) | [`docs/JUDGES.md`](docs/JUDGES.md) |
| Tour guidé de 10 minutes pour les juges | [`docs/judging-test-instructions.md`](docs/judging-test-instructions.md) |
| FAQ évaluateurs (chiffres et preuves) | [`docs/judge-faq.md`](docs/judge-faq.md) |
| Runbook du premier test Continuum réel | [`docs/runbook-premier-test.md`](docs/runbook-premier-test.md) |
| Ne jamais payer une heure-tâche (free tier) | [`docs/free-tier-runbook.md`](docs/free-tier-runbook.md) |
| Conception (High-Level Design) | [`docs/HLD.md`](docs/HLD.md) |
| Cahier des charges (FR) | [`docs/cahier-des-charges-tests-intrusion-continu.md`](docs/cahier-des-charges-tests-intrusion-continu.md) |
| Matrice de recette (scénarios R1–R12) | [`docs/acceptance.md`](docs/acceptance.md) |

## Rempart en local

La démo tourne sans compte AWS, sur votre machine :

```bash
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements-ci.txt
.venv/bin/python scripts/serve_local.py        # API + jeu de données figé sur :8000
cd portal && npm ci && npm run dev:local       # portail relié à l'API locale
```

Détails et options (dont `npm run dev:offline` sans serveur) :
[`scripts/README-local-demo.md`](scripts/README-local-demo.md).