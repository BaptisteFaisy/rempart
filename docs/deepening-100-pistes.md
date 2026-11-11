# 100 pistes pour approfondir le sujet

> Complément de [`roadmap-100-ideas.md`](roadmap-100-ideas.md) : celui-ci listait
> quoi **construire**. Ce fichier liste quoi **creuser** — comprendre, prouver,
> questionner. 10 axes × 10 pistes, écrites le 11 novembre 2026.
>
> Légende : **[P]** = produit / thèse · **[S]** = sécurité technique ·
> **[A]** = IA agentique · **[E]** = économie · **[L]** = droit & conformité ·
> **[M]** = mesure & preuve · **[R]** = recherche / état de l'art ·
> **[O]** = opérations MSP · **[C]** = client (PME sans équipe sécu) ·
> **[H]** = récit & positionnement.

## Axe 1 — Ce que le test automatisé ne sait pas faire

1. **[S]** Cartographier les classes de failles que Continuum trouve vraiment vs celles qu'il rate : logique métier, autorisation transverse, race conditions, chaîne d'approvisionnement.
2. **[S]** Mesurer le taux de faux négatifs sur un jeu connu : semer N failles, compter combien remontent. C'est le chiffre qui décide si le service est honnête.
3. **[S]** Déterminer la profondeur réelle du crawl : un agent qui ne dépasse pas 3 clics ne teste pas un back-office.
4. **[S]** Cas des authentifications complexes : MFA, OAuth, sessions à jeton tournant — le test peut-il vraiment se connecter ?
5. **[S]** APIs non documentées et endpoints internes : comment l'agent découvre-t-il la surface réelle ?
6. **[S]** Failles côté client (XSS DOM, prototype pollution) : couvertes ou hors périmètre ?
7. **[S]** Ce que « confiance Low » veut dire concrètement : un agent qui doute a-t-il raison plus souvent qu'à son tour ?
8. **[S]** Reproductibilité : deux exécutions sur le même code donnent-elles les mêmes failles ? Le cahier des charges note des résultats variables — à mesurer, pas à subir.
9. **[S]** Le test d'intrusion continu remplace-t-il le test annuel ? Non. Définir précisément ce qui reste indispensable en manuel.
10. **[P]** Formuler la promesse honnête : « couverture continue de ce qui est automatisable », pas « plus besoin de pentest ».

## Axe 2 — L'économie réelle du service

11. **[E]** Décomposer le coût d'un test : heures-tâches × 50 $, et identifier ce qui fait varier le multiplicateur (taille du périmètre, nombre de types de risques).
12. **[E]** Modèle de coût unitaire par formule : à quel prix l'abonnement couvre-t-il le test + le tri + le suivi + la marge ?
13. **[E]** Sensibilité au volume : le coût marginal d'un client supplémentaire (l'argument « > 40 applications par analyste » est-il tenable ?).
14. **[E]** Ce que coûte vraiment l'essai gratuit : 400 h-tâches/mois = 20 000 $ de valeur. Pourquoi AWS l'offre, et ce que ça devient après.
15. **[E]** Comparaison chiffrée avec un pentest annuel classique (15-40 k€) : le point de bascule en nombre de livraisons par an.
16. **[E]** Le risque de dépendance tarifaire : AWS peut changer le prix des tests CI/CD après la préversion. Quel contrat protège le MSP ?
17. **[E]** Coût caché du tri humain : si 20 % des failles exigent un analyste, combien de minutes par faille, et à quel taux horaire ?
18. **[E]** Marge par client selon la formule — relier à `marge-msp` pour la calculer réellement plutôt que l'estimer.
19. **[E]** Que se passe-t-il économiquement si un client abuse des tests à la demande ?
20. **[P]** Décider si le service se vend au prix coûtant majoré, au forfait, ou à l'engagement de résultat.

## Axe 3 — La confiance dans un agent IA de sécurité

21. **[A]** Qui est responsable quand l'agent classe P4 une faille qui était P1 ? La chaîne de responsabilité MSP/éditeur/client.
22. **[A]** Le garde-fou « la matrice l'emporte » est-il suffisant ? Cas où la matrice elle-même se trompe.
23. **[A]** Dérive du modèle : Bedrock change de version, les propositions changent. Comment le détecter avant le client ?
24. **[A]** Jeu de référence étiqueté (40 failles selon § 12.5) : le construire réellement, pas le décrire.
25. **[A]** Mesurer l'accord agent/analyste dans le temps : c'est la seule métrique qui dit si l'IA aide ou fatigue.
26. **[A]** Fatigue d'alerte : si l'agent propose trop de validations humaines, l'analyste clique « confirmer » sans lire. Comment le mesurer ?
27. **[A]** L'agent peut-il être trompé par une application qui se comporte différemment devant lui (anti-bot, WAF) ?
28. **[A]** Coût en jetons par tri, et l'arbitrage précision/coût du modèle choisi.
29. **[A]** Faut-il un second modèle qui contredit le premier sur les cas critiques ?
30. **[H]** Raconter la gouvernance IA comme un avantage concurrentiel, pas comme une contrainte : c'est ce qui distingue un produit vendable à un RSSI.

## Axe 4 — Droit, mandat et responsabilité

31. **[L]** Contenu réel d'un mandat de test opposable : domaines, environnements, dates, exclusions, contacts d'urgence, chaîne de sous-traitance.
32. **[L]** Article 323-1 du Code pénal : ce qui constitue exactement l'autorisation, et jusqu'où va la preuve.
33. **[L]** Le MSP sous-traitant RGPD : DPA, registre, durée de conservation, localisation européenne, sous-traitance en cascade (AWS Continuum lui-même).
34. **[L]** Que devient le mandat quand l'application change de domaine ou d'hébergeur en cours de contrat ?
35. **[L]** Responsabilité si le test provoque une panne chez le client (déni de service involontaire).
36. **[L]** Assurance : quelle couverture professionnelle pour un MSP qui teste des systèmes tiers ?
37. **[L]** Le cas des dépendances tierces : tester une app qui appelle un SaaS tiers — les conditions de ce SaaS l'autorisent-elles ?
38. **[L]** Preuve d'acceptation de risque : qui, dans l'organisation du client, a réellement le pouvoir d'accepter ?
39. **[L]** Conservation 13 mois vs droit à l'effacement : les failles contiennent-elles des données personnelles ?
40. **[P]** Vendre la conformité comme bénéfice, pas comme coût : ISO 27001 et SOC 2 exigent des tests réguliers, Rempart en produit la preuve.

## Axe 5 — Mesurer et prouver

41. **[M]** Définir le « délai livraison → résultat » sans ambiguïté : quel horodatage marque la livraison ?
42. **[M]** Le dénominateur de « failles graves arrêtées avant production » : toutes les failles P1/P2, ou seulement celles détectées ? Biais de sélection.
43. **[M]** Taux de réouverture : à partir de quand une réouverture est-elle une régression vs une correction incomplète ?
44. **[M]** Couverture : « applications testées / applications du contrat » — qui déclare la liste des applications ?
45. **[M]** Comparaison honnête : les indicateurs de Rempart vs ceux d'un programme de bug bounty.
46. **[M]** Ce qu'un chiffre ne dit pas : une faille P4 ouverte 18 mois est-elle un échec ?
47. **[M]** Méthode de mesure du temps analyste économisé — la promesse « > 40 applications par analyste » repose dessus.
48. **[M]** Reproductibilité du rapport : le même mois régénéré doit donner les mêmes chiffres (déjà testé, à étendre aux données réelles).
49. **[M]** Auditabilité : un tiers peut-il recalculer chaque KPI depuis les horodatages bruts ?
50. **[H]** Trois chiffres, pas dix : choisir ceux qu'un dirigeant retient.

## Axe 6 — Le client réel (PME sans équipe sécurité)

51. **[C]** Qui lit vraiment le rapport mensuel ? Un dirigeant ne lit pas un tableau de failles.
52. **[C]** La peur de savoir : une PME qui découvre 12 failles P1 le premier mois peut résilier. Séquence d'onboarding à penser.
53. **[C]** Que fait un développeur seul face à un ticket P1 avec échéance 7 jours et pas de temps ?
54. **[C]** Vocabulaire : « IDOR », « CVSS 8.1 » ne veulent rien dire pour un dirigeant. Le résumé en 3 phrases est le vrai produit.
55. **[C]** Le moment de la décision d'achat : qui signe, sur quel déclencheur (audit client, incident, appel d'offres) ?
56. **[C]** Ce que le client craint vraiment : la panne, la fuite, la facture surprise — dans cet ordre ?
57. **[C]** Intégrer le flux au travail existant (le ticket arrive dans GitHub/Jira, pas dans un portail de plus).
58. **[C]** Le client veut-il voir les failles de ses concurrents anonymisées ? (benchmark = levier de renouvellement, mais sujet sensible).
59. **[C]** Accompagnement : un rapport ne suffit pas, il faut une recommandation actionnable et priorisée.
60. **[P]** Segmenter : une PME e-commerce, un éditeur SaaS B2B et une collectivité n'ont ni les mêmes risques ni le même langage.

## Axe 7 — Opérations du MSP

61. **[O]** Procédure d'incident : une faille critique exploitée activement chez un client, à 23 h un samedi.
62. **[O]** Astreinte et engagement de délai : le « 4 heures ouvrées pour une P1 » de la formule Critique est-il tenable ?
63. **[O]** Charge de l'analyste : combien de failles par jour peut-il réellement qualifier sans perdre en qualité ?
64. **[O]** Transmission de savoir : les décisions de tri d'un analyste doivent profiter aux autres.
65. **[O]** Que fait le MSP quand AWS Continuum est indisponible ? Contrats, repli, communication client.
66. **[O]** Supervision du plan de contrôle lui-même : qui surveille le surveillant ?
67. **[O]** Gestion des versions : une évolution de Rempart doit-elle être déployée chez tous les clients simultanément ?
68. **[O]** Off-boarding : récupérer les données, purger, attester — et garder la preuve pour l'audit du client.
69. **[O]** Formation : un MSP traditionnel vend du support, pas de la sécurité offensive. Compétences à acquérir.
70. **[P]** Industrialiser la mise en service : l'objectif « < 30 min dont < 10 min d'actions humaines » (R1) est-il atteint en vrai ?

## Axe 8 — Recherche et état de l'art

71. **[R]** Comparer aux travaux académiques sur le pentest automatisé : ce que la littérature dit des limites réelles.
72. **[R]** Les agents IA de sécurité publiés (hors AWS) : quelles approches, quels taux de réussite déclarés, sur quels benchmarks.
73. **[R]** Benchmarks publics d'applications vulnérables (type OWASP Benchmark, Juice Shop) : s'en servir pour mesurer objectivement la détection.
74. **[R]** La littérature sur la fatigue d'alerte en SOC : applicable directement au tri automatisé.
75. **[R]** Empreinte de faille : les méthodes de similarité existantes font-elles mieux qu'un hash (type de risque + point d'entrée + paramètre) ?
76. **[R]** Détection de doublons sémantiques : au-delà de l'empreinte, deux failles décrites différemment mais identiques.
77. **[R]** Ce que disent les assureurs cyber : exigent-ils des tests continus ? C'est un argument commercial à vérifier.
78. **[R]** Évolution réglementaire (NIS2, DORA, Cyber Resilience Act) : obligations de test qui créent le marché.
79. **[R]** Position d'AWS : Continuum est-il un produit stratégique ou une expérimentation ? Le risque de le voir disparaître.
80. **[H]** Citer ses sources dans la soumission : un juge AWS reconnaît un travail documenté.

## Axe 9 — Limites et angles morts du projet lui-même

81. **[S]** Le plan de contrôle est une cible : il concentre les failles de tous les clients. Son durcissement est-il à la hauteur ?
82. **[S]** Les jetons de test (identifiants de connexion) restent dans le compte client — mais qui vérifie qu'ils ne fuient pas ailleurs ?
83. **[S]** Un employé du MSP malveillant a accès aux failles de tous les clients. Contrôles internes ?
84. **[A]** Le jeu de démonstration est figé : il ne prouve rien sur la détection réelle. Le dire clairement aux juges.
85. **[A]** Aucun test n'a encore été exécuté contre AWS Continuum : tout le code est validé contre des fakes. C'est le plus grand angle mort du projet.
86. **[M]** Les 668 tests mesurent la conformité au contrat, pas l'efficacité sécurité. Ne pas confondre les deux dans le récit.
87. **[E]** Le modèle économique suppose que le MSP sait vendre. Rien dans le projet ne le prouve.
88. **[L]** Le dépôt est devenu public : la stratégie commerciale, les prix et le planning sont lisibles par la concurrence.
89. **[O]** Dépendance à une seule personne (le MSP = l'utilisateur) : que vaut le service s'il est malade ?
90. **[P]** Se demander honnêtement : est-ce un produit, ou une démonstration d'architecture ? Les deux se défendent, mais pas avec le même récit.

## Axe 10 — Récit, positionnement et ce que les juges évaluent

91. **[H]** Les 4 critères à 25 % : mise en œuvre technique, conception, impact, innovation. Où le projet est-il le plus faible ? (Réponse probable : impact, faute d'exécution réelle.)
92. **[H]** Le prix visé est « Best AWS Frontier Agents Application » : il récompense l'usage d'un agent Frontier. Prouver l'usage réel, pas l'intention.
93. **[H]** La phrase unique : « le test d'intrusion devient un abonnement avec engagement de délai et preuve de fermeture ». La répéter partout, mot pour mot.
94. **[H]** Ce que Security Agent ne fait pas — déjà écrit dans [`what-rempart-adds.md`](what-rempart-adds.md) : s'assurer que la vidéo le dit en 20 secondes.
95. **[H]** Montrer l'échec autant que le succès : une faille bloquée, une régression rouverte. C'est plus crédible qu'un parcours parfait.
96. **[H]** Nommer le produit : « Rempart » est un nom de travail. Un nom anglais est probablement préférable pour un jury AWS international.
97. **[H]** Anticiper les 5 questions des juges et préparer les réponses (coût, isolation, RGPD, panne du service, pourquoi pas un outil existant).
98. **[H]** Le lien avec `marge-msp` : deux projets du même hackathon qui se nourrissent = un récit MSP complet que personne d'autre ne peut tenir.
99. **[H]** Honnêteté comme stratégie : dire ce qui n'est pas déployé renforce la crédibilité de ce qui l'est. Le dépôt le fait déjà (checklist avec statuts réels).
100. **[H]** Ce qu'il reste à prouver le 11 décembre : une exécution réelle, trois chiffres mesurés, une vidéo. Tout le reste est écrit.
