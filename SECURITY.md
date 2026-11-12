# Security Policy — Rempart

## Signaler une vulnérabilité

Nous prenons les failles au sérieux, y compris sur un projet de démonstration.
Pour signaler une vulnérabilité sans l'exposer publiquement :

- **Voie recommandée** : ouvrez une **issue GitHub privée / un advisory de
  sécurité** sur le dépôt
  [`Tradoooo/rempart`](https://github.com/Tradoooo/rempart) (si l'onglet
  *Security → Report a vulnerability* est activé), en décrivant la faille, les
  étapes de reproduction et l'impact estimé.
- **Sinon** : contactez le propriétaire du dépôt par le canal de votre choix
  (mention d'utilisateur GitHub, message direct). Nous ne publions pas
  volontairement d'adresse e-mail dédiée ici : aucun e-mail réel n'est à
  inventer dans ce fichier.

Ne publiez **pas** de détails exploitables dans une issue publique avant qu'un
correctif soit disponible.

## Périmètre pris en charge

Sont dans le périmètre de cette politique :

- `backend/` — plan de contrôle (API, orchestrateur, triage IA, rapports) ;
- `iac/` — infrastructure AWS CDK et template CloudFormation client ;
- `portal/` — portail web (React + TypeScript) ;
- `demo/` — applications de démonstration et leurs vulnérabilités intentionnelles ;
- `scripts/` — scripts de démo et de preuves.

Sont **hors périmètre** :

- le site public **https://tradoooo.github.io/rempart/** (démo hors ligne sur
  données figées, sans backend ni données réelles) ;
- les services AWS déployés que nous ne contrôlons pas (quotas, enveloppes) ;
- les problèmes de disponibilité ou de contenu (→ voir [`SUPPORT.md`](SUPPORT.md)).

## Délais indicatifs

| Étape | Délai indicatif |
|---|---|
| Accusé de réception | sous 72 h |
| Premier tri (confirmé / non reproductible) | sous 7 jours |
| Correctif publié | selon la criticité, priorisé avant toute autre tâche |

Ces délais sont indicatifs : **Rempart est un projet de démonstration** porté
par une petite équipe dans le cadre d'un hackathon, sans instance déployée en
production ni données client réelles. Merci de votre patience.

## Mention honnête

Rempart est un **projet de démonstration** (AWS MSP AI Hackathon). À la date de
ce document, **aucune infrastructure n'est déployée sur AWS** et **aucun test
d'intrusion réel n'a été exécuté** : le code est validé contre des doubles de
test et un banc réel. Voir
[`docs/submission-checklist.md`](docs/submission-checklist.md) pour l'état réel.