# 100 idées pour pousser Rempart plus loin

> Troisième volet, distinct des deux précédents :
> [`roadmap-100-ideas.md`](roadmap-100-ideas.md) = quoi **construire** ·
> [`deepening-100-pistes.md`](deepening-100-pistes.md) = quoi **creuser** ·
> ce fichier = quoi **étendre** : passage à l'échelle, avantage durable,
> pérennité au-delà du hackathon (jugement clos le 22 janvier 2027).
>
> Légende : **[1]** premier client réel · **[2]** onboarding à volume ·
> **[3]** extension de la surface sécurité · **[4]** la donnée comme actif ·
> **[5]** échelle technique · **[6]** écosystème AWS · **[7]** automatisation ·
> **[8]** modèle commercial · **[9]** pérennité & risque · **[10]** positionnement.

## 1. Du prototype au premier client réel

1. **[1]** Trouver un client pilote gratuit (un seul) avant toute autre extension : rien ne remplace une vraie application, un vrai pipeline, un vrai développeur qui reçoit un ticket.
2. **[1]** Cadre du pilote : 3 mois, 1 application, périmètre restreint, engagement de réponse du MSP, et un accord écrit sur ce qui sera mesuré.
3. **[1]** Instrumenter le pilote pour produire les 3 chiffres d'impact (délai livraison → résultat, failles bloquées avant prod, délai de correction) sur des données réelles.
4. **[1]** Journal de bord du pilote : chaque friction, chaque faux positif, chaque minute d'analyste — c'est la matière première du produit.
5. **[1]** Un témoin de réussite signé par le client : une phrase citable, utilisable dans la soumission et dans le discours commercial.
6. **[1]** Cas d'échec anticipé : que fait-on si le pilote trouve 40 failles la première semaine ? Préparer la séquence avant qu'elle arrive.
7. **[1]** Facturer symboliquement dès le pilote : un service gratuit n'est pas évalué comme un service acheté.
8. **[1]** Mesurer le coût réel du pilote (heures-tâches + temps MSP) et le comparer au modèle `economics` — première confrontation du calcul au réel.
9. **[1]** Documenter ce qui a été fait à la main pendant le pilote : c'est la liste exacte de ce qu'il faut automatiser ensuite.
10. **[1]** Décider si le pilote devient une référence publique (avec accord) ou reste anonyme — les deux se défendent, pas de la même façon.

## 2. Industrialiser l'onboarding

11. **[2]** Assistant d'onboarding auto-découvert : lire le compte AWS du client et proposer les applications candidates (EF-ONB-10, déjà en cible « C »).
12. **[2]** Onboarding en libre-service : le client installe le template, colle un jeton, et Rempart fait le reste sans intervention du MSP.
13. **[2]** Détection automatique du dépôt et du pipeline (GitHub, GitLab, Bitbucket) au lieu de les faire déclarer.
14. **[2]** Génération automatique du périmètre de test à partir des routes découvertes, avec validation humaine.
15. **[2]** Modèle de compte client par région : un déploiement par région pour respecter la résidence des données.
16. **[2]** Kit de bienvenue client automatisé : mandat pré-rempli, contacts, canal de tickets, premier rapport planifié.
17. **[2]** Mesurer le temps réel de mise en service et viser < 10 minutes d'action humaine (R1) sur 10 clients, pas sur 1.
18. **[2]** Gestion des échecs d'onboarding : domaine non vérifiable, rôle refusé, dépôt inaccessible — chaque cas doit avoir un message actionnable.
19. **[2]** Multi-comptes AWS par client (organisation avec plusieurs comptes) : un seul contrat, plusieurs déploiements.
20. **[2]** Tableau de bord d'onboarding côté MSP : qui en est où, ce qui bloque, depuis combien de temps.

## 3. Étendre la surface de sécurité

21. **[3]** Revue de code en option payante **explicitement chiffrée** : 200 $/M lignes/mois + 10 $/inférence — la vendre comme un add-on premium, jamais comme inclus.
22. **[3]** Modèle de menaces (STRIDE) au moment de l'onboarding : produit un document que le client n'a pas et qui alimente le périmètre des tests.
23. **[3]** Revue de conception : comparer l'architecture déclarée aux exigences de sécurité du client.
24. **[3]** Suivi de la surface d'attaque dans le temps : `ListDiscoveredEndpoints` donne les points d'entrée découverts — en faire une carte qui évolue.
25. **[3]** Détection de nouvelle surface : une route apparue sans test associé doit déclencher une alerte.
26. **[3]** Tests d'API spécifiques (GraphQL, gRPC, webhooks) comme modules distincts facturables.
27. **[3]** Chaîne d'approvisionnement : dépendances vulnérables du dépôt client, en complément du test dynamique.
28. **[3]** Conformité continue : mapper chaque faille à une exigence ISO 27001 / SOC 2 / NIS2 et produire l'état d'avancement.
29. **[3]** Surveillance de l'exposition externe (sous-domaines oubliés, environnements de dev exposés) — souvent la vraie porte d'entrée.
30. **[3]** Positionner explicitement ce que Rempart n'est PAS : ni SOC, ni réponse à incident, ni EDR. Le périmètre clair est un argument de vente.

## 4. La donnée comme avantage durable

31. **[4]** Base de référence sectorielle : délai moyen de correction d'un P1 dans l'e-commerce vs le SaaS B2B. Personne d'autre ne peut la constituer sans parc de clients.
32. **[4]** Détection transverse anonymisée (EF-TRI-10) : la même empreinte chez 3 clients → alerte MSP. À faire sur empreintes hashées, jamais sur contenu.
33. **[4]** Score de maturité sécurité par client, comparable dans le temps et entre pairs anonymisés.
34. **[4]** Corpus de décisions de tri étiquetées : chaque correction d'analyste enrichit le jeu de référence — l'actif s'apprécie avec l'usage.
35. **[4]** Bibliothèque de faux positifs par framework : « cette alerte sur Django est un faux positif connu » — valeur immédiate pour l'analyste.
36. **[4]** Historique des coûts réels par type d'application : permet d'estimer un test AVANT de le lancer, ce qu'AWS ne sait pas faire.
37. **[4]** Prédictif : quelles applications vont produire le plus de failles ce mois-ci, pour prioriser l'effort d'analyste.
38. **[4]** Anonymisation à la source : ce qui peut être agrégé doit être anonymisé **avant** stockage, pas au moment de l'export.
39. **[4]** Valoriser la donnée dans le récit investisseurs : un parc de clients produit un actif que ni AWS ni un concurrent ne peut répliquer.
40. **[4]** Limite à poser explicitement : aucune donnée d'un client ne doit permettre d'identifier un autre client. À prouver par test, pas à promettre.

## 5. Échelle technique

41. **[5]** Passer de 2 à 50 clients : où casse le plan de contrôle en premier ? (probablement les scans DynamoDB du journal d'audit et des KPI)
42. **[5]** Remplacer les scans par des index : les KPI de parc sur 50 clients ne doivent pas scanner toutes les failles.
43. **[5]** File d'attente réelle pour le quota de 5 tests simultanés par compte (EF-ORC-05) : persistance, reprise, priorité par formule.
44. **[5]** Coût du plan de contrôle mesuré par client : prouver ENF-COUT-01 (< 50 $/mois pour 10 applications) avec des chiffres réels, pas une estimation.
45. **[5]** Cache des lectures fréquentes (contexte d'application, politique par tenant) pour réduire les appels DynamoDB.
46. **[5]** Découper les Lambda longues : la découverte sur 50 clients toutes les 5 min ne tiendra pas dans un seul invocateur.
47. **[5]** Observabilité du coût : métriques CloudWatch sur les heures-tâches consommées, avec alarme de dérive.
48. **[5]** Stratégie de reprise après incident : que se passe-t-il si le plan de contrôle est hors service 4 h pendant qu'un test tourne ?
49. **[5]** Migration de version : un schéma DynamoDB qui évolue sur 50 clients sans interruption.
50. **[5]** Charge admissible du portail : 50 clients × 5 utilisateurs simultanés, avec les KPI de parc recalculés.

## 6. Écosystème AWS

51. **[6]** Place de marché AWS : abonnement transactable, ce qui supprime la friction d'achat et donne de la visibilité.
52. **[6]** Devenir partenaire APN : le cahier des charges pose la question (§ 22.9) — c'est un prérequis de crédibilité pour un MSP.
53. **[6]** Intégrer d'autres services AWS déjà présents chez le client : Security Hub (agrégation des findings), EventBridge (événements), Cost Explorer (réconciliation facture).
54. **[6]** Publier le template client comme produit autonome : « sécurisez votre compte en 1 template » — porte d'entrée gratuite vers le service.
55. **[6]** Contribuer en amont : remonter à AWS les frictions réelles de l'API Continuum (noms d'actions incohérents, champs de réponse) — c'est ainsi qu'on devient visible d'un éditeur.
56. **[6]** Suivre la préversion : Continuum évolue, une API peut changer sans préavis. Une veille automatisée sur la doc est un garde-fou.
57. **[6]** Position multi-région pour servir des clients hors UE, en gardant le plan de contrôle en Europe pour le RGPD.
58. **[6]** Exploiter AgentCore au-delà du tri : gateway d'outils, mémoire, évaluation — c'est le prix « Frontier Agents » qui est visé.
59. **[6]** Risque de plateforme : AWS peut internaliser la couche MSP. Définir ce qui reste défendable si Continuum ajoute un portail multi-clients.
60. **[6]** Bénéficier des crédits hackathon (200 $, expiration 31 décembre 2026) avant qu'ils expirent — calendrier à tenir.

## 7. Automatisation sans perdre le contrôle

61. **[7]** Fusion automatique des PR de correction à faible risque (ex. en-tête de sécurité manquant) avec revue humaine différée — à encadrer strictement.
62. **[7]** Tri automatique des faux positifs **connus** : une empreinte déjà jugée faux positif par un humain sur la même application ne remonte plus en validation.
63. **[7]** Pré-rédaction du ticket : titre, résumé, échéance, lien de preuve — l'analyste ne fait que valider, pas rédiger.
64. **[7]** Relances intelligentes : ne relancer que si rien n'a bougé sur le ticket, pas à date fixe.
65. **[7]** Détection de correction cosmétique : un commit qui ferme le ticket sans toucher au code concerné doit être signalé.
66. **[7]** Auto-évaluation continue de l'agent : rejouer le jeu de référence à chaque changement de prompt ou de modèle, en CI.
67. **[7]** Plafond d'automatisation assumé : écrire noir sur blanc ce qui restera toujours humain, et pourquoi.
68. **[7]** Mesurer le taux d'intervention humaine par mois : c'est LA métrique de l'industrialisation.
69. **[7]** Réduire le coût par faille triée (jetons + minutes analyste) — objectif chiffré à fixer.
70. **[7]** Boucle de rétroaction client : un bouton « cette faille ne nous concerne pas, voici pourquoi » qui alimente le corpus.

## 8. Modèle commercial et croissance

71. **[8]** Trois formules ne suffisent pas : ajouter une formule « audit ponctuel » (sans abonnement) comme porte d'entrée.
72. **[8]** Prix par surface d'attaque plutôt que par application : une app de 3 routes et une de 300 ne coûtent pas le même prix.
73. **[8]** Engagement de résultat : rembourser une partie si aucune faille P1/P2 n'est arrêtée en 6 mois. Risqué, mais différenciant.
74. **[8]** Canal indirect : vendre via des MSP existants en marque blanche plutôt qu'en direct — croissance plus rapide, marge plus faible.
75. **[8]** Offre « conformité » packagée : ISO 27001 / SOC 2 / NIS2 avec le dossier de preuves inclus, vendue plus cher que la technique.
76. **[8]** Saisonnalité : les audits et renouvellements de certification créent des pics — dimensionner l'équipe en conséquence.
77. **[8]** Coût d'acquisition : un pilote réussi produit un témoignage, qui produit deux clients. Budgéter cette boucle.
78. **[8]** Rétention : le taux de réouverture et le respect des échéances sont les meilleurs prédicteurs de renouvellement — les suivre comme des indicateurs commerciaux.
79. **[8]** Augmentation de prix : comment la justifier après 12 mois de données (le dossier de preuves devient l'argument).
80. **[8]** Décider du modèle : produit vendu à des MSP, ou service opéré par un MSP. Les deux ne demandent pas la même ingénierie.

## 9. Pérennité et risques

81. **[9]** Dépendance à une seule personne : documenter assez pour qu'un autre puisse opérer le service (ENF-REP-01 existe, le vérifier réellement).
82. **[9]** Dépendance à un seul fournisseur : si Continuum disparaît ou change de prix, que reste-t-il du produit ?
83. **[9]** Plan de continuité : sauvegarde des tables, restauration testée, procédure de bascule de région.
84. **[9]** Assurances et responsabilité civile professionnelle avant le premier client payant.
85. **[9]** Sécurité du MSP lui-même : le plan de contrôle concentre les failles de tous les clients, donc il est la cible la plus attractive.
86. **[9]** Revue de sécurité externe du plan de contrôle — par un tiers, pas par soi-même.
87. **[9]** Contrats et CGV : ce qui se passe en cas d'impayé, de résiliation, de litige sur une faille non détectée.
88. **[9]** Propriété intellectuelle : qui possède les prompts, la matrice, le corpus de décisions ?
89. **[9]** Veille réglementaire : NIS2, DORA, Cyber Resilience Act créent l'obligation de tester — à suivre comme une opportunité commerciale.
90. **[9]** Scénario du pire documenté : fuite de données de failles chez le MSP. Procédure, notification, responsabilité.

## 10. Positionnement à 12 mois

91. **[10]** Choisir le positionnement : outil de sécurité, service managé, ou plateforme MSP. Les trois ne se vendent pas au même acheteur.
92. **[10]** Nommer le produit pour un marché international (« Rempart » est un nom de travail francophone).
93. **[10]** Une phrase, répétée mot pour mot partout : « le test d'intrusion devient un abonnement avec engagement de délai et preuve de fermeture ».
94. **[10]** Preuve sociale : un logo client, un chiffre mesuré, une citation. Sans ça, le discours reste théorique.
95. **[10]** Contenu technique public : écrire sur les garde-fous d'un agent IA de sécurité attire les bons clients et les bons recrutements.
96. **[10]** Relation éditeur : être identifié par AWS comme un partenaire de référence sur Continuum vaut plus que n'importe quelle campagne.
97. **[10]** Comparaison publique et honnête avec l'existant (pentest annuel, SAST/DAST, bug bounty) — ce que chacun fait mieux.
98. **[10]** Feuille de route publiée : dire ce qui arrive dans 6 mois crédibilise ce qui est livré aujourd'hui.
99. **[10]** Après le hackathon : le jugement se termine le 22 janvier 2027 et la solution doit rester en ligne jusque-là — prévoir le coût et la maintenance de cette période.
100. **[10]** Définir le critère d'arrêt : à partir de quand ce projet cesse d'être un hackathon et devient (ou ne devient pas) une entreprise.
