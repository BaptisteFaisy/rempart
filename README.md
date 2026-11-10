# Rempart 🛡️

**Tests d'intrusion en continu par abonnement pilotés par AWS Security Agent**
*Hackathon AWS MSP AI — Track 2 : Deliver AI-Driven Outcomes for Customers*

---

## 📌 Présentation

Rempart transforme le test d'intrusion annuel ponctuel en un service managé continu :
- **À chaque livraison (porte CI/CD)** : AWS Security Agent teste l'incrément et bloque la mise en production si une faille critique apparaît.
- **Tri automatisé et contextualisé** : Strands Agents sur AgentCore Runtime & Bedrock qualifient les failles selon le contexte métier du client.
- **Cycle complet de remédiation** : Pull request automatique de correction, retest automatique après merge et fermeture avec preuve d'audit.
- **Gestion MSP multi-clients** : Plan de contrôle centralisé, respect strict des quotas et plafonnement budgétaire en heures-tâches par client.

Pour le détail complet, consultez le [Cahier des charges](docs/cahier-des-charges-tests-intrusion-continu.md).

## ⚙️ Socle CI & Automatisation

Le dépôt embarque les composants standard de gouvernance de livraison :
- **CI Budget (≤ 5 min)** : `.github/workflows/ci-budget.yml` garantit le respect de la règle stricte de temps d'exécution.
- **Hermes Lite Gate** : `.github/workflows/hermes-lite.yml` et `.github/hermes/gate.py` pour la fraîcheur des branches au moment du merge.
- **Stale Base Guard** : `.github/workflows/stale-base-guard.yml` pour le suivi des dérives de base.
- **Mergify** : `.mergify.yml` pour l'ordonnancement automatique en file de merge (squash & merge).
