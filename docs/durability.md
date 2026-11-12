# Pérennité : ce qui reste si AWS internalise, et tenir jusqu'au 22 janvier

> Répond aux pistes #59 et #99 de [`scaling-100-ideas.md`](scaling-100-ideas.md).
> Écrit le 11 novembre 2026, à l'état réel du dépôt (673 tests verts, portail
> public sur GitHub Pages, **rien de déployé sur AWS**, aucun test réel exécuté).

## 1. Que reste-t-il de Rempart si AWS ajoute un portail multi-clients ? (#59)

Le risque est réel : Continuum connaît déjà l'espace d'agent, les domaines, les
tests, les failles. Un portail « plusieurs applications, plusieurs équipes » est
une évolution naturelle du service, pas un saut.

### Ce qui disparaîtrait immédiatement

Tout ce qui n'est que du **câblage d'API** : le client `SecurityAgentClient`, la
découverte des runs CI/CD, le lancement et le suivi des tests, la collecte des
failles, la demande de pull request de correction. Environ
`rempart/orchestrator/` dans sa partie adaptation, soit une part minoritaire du
code mais une part réelle.

### Ce qui ne disparaîtrait pas

| Actif | Pourquoi il résiste |
|---|---|
| **La relation MSP ↔ client** | Un éditeur de cloud ne signe pas de mandat de test, ne négocie pas d'échéance contractuelle, ne porte pas la responsabilité d'un conseil. C'est un métier de service, pas de produit. |
| **La matrice de priorité paramétrable par contrat** | Continuum donne une sévérité et une confiance. Transformer ça en P1–P4 avec échéance contractuelle dépend du métier du client, de son exposition, de ses données. AWS peut fournir une matrice par défaut, pas 50 matrices négociées. |
| **Le corpus de décisions étiquetées** (piste #34) | Chaque correction d'analyste, par application, par client. Un éditeur n'a pas le contexte métier ; il a les failles. C'est l'actif qui s'apprécie avec l'usage et qu'on ne peut pas répliquer sans parc de clients. |
| **La base de référence sectorielle** (piste #31) | Délai moyen de correction d'un P1 dans l'e-commerce vs le SaaS B2B. Nécessite des dizaines de clients sous contrat. |
| **Le dossier de preuves orienté audit** | `reports/evidence.py` produit un dossier scellé SHA-256 mappé sur ISO 27001 / SOC 2. Un éditeur produit un rapport de test, pas un dossier d'audit opposable à un auditeur du client. |
| **La gouvernance budgétaire multi-clients** | Budget par client et par application, seuils, arrêt automatique, prévision, refacturation au-delà du forfait. AWS facture ; il ne gère pas l'enveloppe contractuelle d'un MSP. |
| **L'intégration au SI du client** | Tickets dans le dépôt du client, relances au responsable de compte, rapport mensuel au dirigeant. Le canal de chaque client diffère. |

### La conclusion opérationnelle

**La valeur n'est pas dans l'appel à Continuum, elle est dans ce qui l'entoure** —
ce que dit déjà [`what-rempart-adds.md`](what-rempart-adds.md). Mais cette
défense n'est crédible que si les quatre actifs immatériels ci-dessus existent
réellement. Aujourd'hui : la matrice existe et est testée ; le corpus, la base
sectorielle et l'usage réel du dossier de preuves **n'existent pas encore** faute
de clients.

**Donc la priorité n°1 n'est pas technique** : c'est la piste #1, un client
pilote. Sans lui, les quatre actifs restent des schémas.

### Signaux faibles à surveiller

- Continuum annonce une vue multi-espace ou un tableau de bord d'organisation.
- Continuum annonce une tarification par abonnement plutôt qu'à l'heure-tâche.
- Continuum ajoute des échéances ou des SLA par faille.
- AWS lance un programme partenaire « security operations » qui couvre le même périmètre.

Chacun de ces signaux déplace la frontière : il faut alors remonter d'un cran
vers le conseil, la conformité ou l'agrégation multi-fournisseurs.

---

## 2. Tenir en ligne jusqu'au 22 janvier 2027 (#99)

Le jugement se termine le **22 janvier 2027** et la solution doit rester en ligne
jusque-là (cahier des charges, chapitre 1). La soumission est le **11 décembre
2026**. Il y a donc **10 semaines** à tenir après la soumission.

### Ce qui doit rester accessible

| Élément | Où | Coût | Risque |
|---|---|---|---|
| Portail | https://tradoooo.github.io/rempart/ (branche `gh-pages`) | **0 €** | Faible : GitHub Pages, aucune dépendance runtime |
| Code et docs | `github.com/Tradoooo/rempart` | **0 €** | Faible, mais le dépôt est **public** alors que le cahier des charges demandait privé — décision à prendre |
| Vidéo | YouTube, publique | **0 €** | Moyen : une vidéo supprimée ou passée en privée disqualifie |
| Plan de contrôle AWS | **non déployé** | < 1 $/mois si déployé (serverless) | Élevé tant que non déployé : rien à montrer en réel |
| Premier test Continuum | **non exécuté** | 0 € si essai gratuit actif | **Élevé** : l'essai ne démarre qu'au premier test, et il dure 2 mois |

### Le piège de calendrier, chiffré

L'essai gratuit de Continuum pour le penetration testing dure **2 mois à partir
du premier test**, avec 400 heures-tâches par mois.

- Premier test le **23 novembre 2026** → essai jusqu'au **~23 janvier 2027**.
  Le jugement se termine le 22 janvier : **ça passe, avec un jour de marge.**
- Premier test le **12 novembre 2026** → essai jusqu'au ~12 janvier.
  **Le jugement dépasse l'essai de 10 jours** : les tests de démonstration
  finale seraient facturés (50 $/heure-tâche).

C'est exactement ce que dit le cahier des charges § 16.2, et c'est pourquoi le
garde-fou `REMPART_FREE_TIER_ONLY=1` bloque tout test tant que
`Tenant.free_tier_confirmed` n'est pas passé à `true` manuellement.

### Le plan des 10 semaines

| Semaine | Action | Coût |
|---|---|---|
| 12–22 nov. | Développer sur données figées et fakes. **Aucun test réel.** Préparer l'access key et vérifier l'éligibilité au free tier dans la console. | 0 € |
| 23 nov. | Premier test réel dans le compte de démonstration, périmètre minimal, plafond `max_task_hours_per_test=5`. L'essai démarre. | 0 € (essai) |
| 24 nov.–7 déc. | Déploiement complet (`cdk bootstrap` + `cdk deploy`), mesure des 3 indicateurs sur données réelles, enregistrement de la vidéo. | < 1 $/mois d'infra |
| 8–10 déc. | Recette, soumission Devpost, partage du dépôt avec les comptes des juges. | 0 € |
| 11 déc.–22 janv. | **Maintien en ligne** : ne rien casser, surveiller le budget d'heures-tâches, garder le portail et la vidéo accessibles. | < 1 $/mois |

### Les trois choses qui peuvent tout faire tomber pendant ces 10 semaines

1. **Le crédit hackathon expire le 31 décembre 2026** (200 $, cahier des charges
   § 16.3). Après cette date, ce qui n'est pas couvert par l'essai gratuit est à
   ta charge. En janvier, un test hors essai coûte ~173 $ pour une API simple.
2. **Un push sur `main` redéploie la branche `gh-pages`** : le portail public est
   régénéré par `.github/workflows/deploy-pages.yml`. Une régression du build
   casserait l'URL publique pendant le jugement. Garde la CI verte, ne désactive
   pas `ci-portal`.
3. **Le dépôt est public** : si tu le repasses en privé, **GitHub Pages cesse de
   servir** pour un compte gratuit… vérifie avant de changer la visibilité. Ton
   compte est `pro`, donc Pages reste disponible en privé, mais le lien
   d'accès des juges change de nature (il leur faut une invitation).

### Vérification hebdomadaire recommandée (10 minutes)

```bash
curl -sS -o /dev/null -w "portail: %{http_code}\n" https://tradoooo.github.io/rempart/
gh run list --repo Tradoooo/rempart --limit 5   # CI verte ?
gh api repos/Tradoooo/rempart/pages --jq '.status, .html_url'
# si déployé sur AWS : heures-tâches consommées ce mois-ci
```

Et une seule question à se poser chaque semaine : **est-ce que le portail public
affiche encore les données figées, et la vidéo est-elle encore publique ?**
Tout le reste peut attendre le 23 janvier.
