# Rempart — la page des évaluateurs

> URL publique : **https://tradoooo.github.io/rempart/**
> Démo **hors ligne** sur données figées : **0 €**, aucun compte AWS, aucune
> donnée client sur une URL publique. Prêt à regarder, rien à installer.

## Ce que c'est, en une phrase

Rempart transforme le test d'intrusion annuel en **abonnement mensuel piloté
par un MSP** : à chaque release, AWS Continuum (pentest) teste le changement
déployé dans le compte du client, Rempart trie les failles avec un vrai LLM,
impose une échéance contractuelle, et ne clôt une faille que lorsqu'un
**re-test prouve** qu'elle a disparu.

## Cinq pages de gouvernance, et ce que chacune prouve

Le portail va au-delà du simple « il y a des failles » : cinq pages montrent la
boucle de gestion *autour* du test. Toutes affichent de **vraies données**
calculées par le même code que le déploiement branché (le modèle n'écrit que de
la prose, jamais un chiffre).

| Page | Route | Ce qu'elle prouve |
|---|---|---|
| **Audit Journal** | `/audit` | Un journal d'audit **immuable**, lecture seule par construction : chaque action (refus de test, garde-fou, décision) y est horodatée, et l'API refuse toute écriture. |
| **Evidence Dossier** | `/evidence` | Le **dossier de preuves scellé** : son empreinte **SHA-256 se recalcule** à l'identique depuis l'objet retéléchargé — un tiers peut vérifier qu'il n'a pas été altéré. |
| **Industrialization** | `/industrialization` | Les **métriques d'industrialisation** (couverture, taux d'automatisation) produites par du code déterministe, pas par le modèle. |
| **Policy** | `/policy` | La **« Contract Correction Policy »** : matrice de priorité déterministe P1–P4, échéance contractuelle (P1 = 7 jours), dérogations contrôlées. |
| **Budget / Forecast** | `/budget` | La **gouvernance du budget** : heures-tâches consommées, prévision au rythme courant, alertes 50/80/100 %, et l'**auto-stop** (StopPentestJob en plein test à 100 %). |

## Mode « persona » hors ligne — pas de mot de passe à retenir

Sur l'URL publique, le portail tourne en **mode démo hors ligne** (bannière
« OFFLINE DEMO MODE » affichée en permanence). La page de connexion ne demande
**pas de mot de passe** : un sélecteur **Persona / Role** propose de rentrer
directement avec un rôle (par défaut *Judge Demo — Read-Only*). Aucun
identifiant à mémoriser, un clic suffit.

Le rôle `demo` est appliqué côté client comme côté API : lecture seule, une
demande de test à la demande par jour sur le périmètre minimal, aucune écriture
possible.

## Le tour guidé en 60 secondes

1. **`/fleet`** — le cockpit MSP : deux locataires de démo, les quatre KPI
   principaux, les failles par priorité.
2. **`/evidence`** — le dossier de preuves scellé, empreinte recalculable.
3. **`/triage`** — la file : proposition du LLM, priorité P1, échéance 7 jours,
   et le garde-fou qui interdit au modèle de clore seul une faille Critical/High.

## Ce que cette démo ne montre pas (honnêtement)

- **Aucun test Continuum réel** n'a encore tourné : le client Security Agent
  est simulé, rien n'est facturé. Le premier test réel est planifié au
  **23/11/2026** (voir [`runbook-premier-test.md`](runbook-premier-test.md)).
- **Aucun backend** : pas de Cognito, DynamoDB, S3 ni Step Functions sur cette
  URL. Les données sont le jeu figé `demo/seed/demo-dataset.json`.

Pour la faq détaillée, chiffres et preuves : [`docs/judge-faq.md`](judge-faq.md).
Pour le tour guidé de 10 minutes : [`docs/judging-test-instructions.md`](judging-test-instructions.md).