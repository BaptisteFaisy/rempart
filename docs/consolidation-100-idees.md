# 100 idées pour consolider Rempart — et les 10 à faire en premier

> État de référence : 12/11/2026, après correction des défauts D1–D12 (énumérations
> de l'API réelle, empreinte des failles, dossier de preuves scellé, preflight CORS,
> claims Cognito, portail authentifié, triage par un vrai LLM InferHub). `main`
> = `91c4b90`, 914 tests, CI verte, démo publique 0 € sur GitHub Pages.

Les idées sont numérotées de 1 à 100, classées en dix thèmes. Les **10 à faire
en premier** sont marquées ⭐ et détaillées en fin de document, avec le *pourquoi*.

---

## A. Soumission & juges (1–10)

1. ⭐ Script de soumission **one-shot** : imprime l'URL publique, les identifiants démo, télécharge les captures et vérifie que chaque page est en 200.
2. ⭐ Identifiants de **juge non expirables** (pas `FORCE_CHANGE_PASSWORD`), prêts à coller sur Devpost.
3. ⭐ **LICENCE (MIT)** à la racine — le dépôt n'en a pas encore.
4. ⭐ **SECURITY.md** (divulgation responsable) + **SUPPORT.md**.
5. Un « pitch 60 secondes » en tête de README : l'URL gratuite + 3 clics.
6. Un **badge** « 0 € / 0 donnée client / 0 compte AWS » sur la page de démo.
7. Une page `/demo` dédiée au parcours hors ligne, avec bandeau clair.
8. Rédiger le texte Devpost avec les **chiffres** (914 tests, 30/30 preuves, 12 défauts corrigés).
9. Vérifier le dépôt **public** et le scan de secrets avant soumission.
10. Archive d'un « touring test » : un tiers suit les instructions dans un environnement vierge.

## B. Preuves rejouables (11–20)

11. ⭐ `proof_real.py` exécuté en **CI périodique** (badge « preuves vertes »).
12. ⭐ **P6-llm** : prouver qu'un verdict vient du modèle (`source == "model"`).
13. Preuve d'**immutabilité** : le journal d'audit ne peut pas être modifié (route lecture seule).
14. Preuve de **confidentialité** : le dossier de preuves ne contient aucune `attackScript`/`verificationScript`.
15. Rapport de **performance** (ENF-PERF-01) publié avant le premier test réel.
16. Convention : chaque PR porte sa section « Preuves » (le script qui s'exécute).
17. Étendre le test « jeu figé == code de production » à toutes les collections.
18. Preuve CORS : l'origine non autorisée ne reçoit aucun `Access-Control-Allow-Origin` (déjà testé).
19. Preuve SSM : la clé n'apparaît jamais dans un template (déjà testé).
20. Publier le **rapport du 12/11** (les 12 défauts) dans `docs/` — pas seulement en `.scratch`.

## C. Premier test Continuum réel (21–30)

21. ⭐ La **recette de lancement** du premier test réel (jeton, fenêtre de test, budget) prête pour le 23/11.
22. Confirmer le **free tier** dans la console (le clic manuel qui débloque tout).
23. Un **domaine vérifié** + un `agent_space_id` pour la cible de démonstration.
24. Un **scope minimal** (1 app, 1 domaine) pour rester sous ~5 $.
25. Mesurer le **coût réel** du premier test (heures-tâches → dollars).
26. Vérifier l'**ingestion réelle** (`collect_findings` → vrai DynamoDB).
27. Vérifier la **fermeture réelle** (retest → `closed` avec preuve).
28. Écrire le **runbook post-mortem** du premier test.
29. Filmer le premier test (extrait pour la vidéo).
30. Alerter si le **coût dépasse** le budget pendant le test (auto-stop R8 déjà en place).

## D. Triage & LLM (31–40)

31. ⭐ **Cache des verdicts** : même faille + même verion → même proposition (moins d'appels LLM).
32. ⭐ **Évaluation modèle vs règleur** : mêmes failles, comparer les deux chemins.
33. Modèle **configurable par tenant** (modèle moins cher pour les gros volumes).
34. **Timeout/Cancel** propre du LLM (les fournisseurs sont lents).
35. Afficher la **confiance** du modèle sur chaque verdict.
36. **Mémoire par veto** : une correction humaine corrige le modèle durablement.
37. Mode **brouillon** : l'analyste relit avant d'enregistrer.
38. Stocker les **justifications** du modèle (déjà dans `Decision`).
39. Afficher la **divergence agent/humain** (industrialization) sur la file de triage.
40. Bouton **reproposer** (relancer le LLM sur une faille).

## E. Sécurité & garde-fous (41–50)

41. ⭐ **Fuzzing** des routes API (une faille = un test).
42. **Validation stricte** des champs d'entrée (types, bornes).
43. Garde-fou « jamais de vérité du modèle sur le coût » (ENF-IA-01) — vérifié.
44. **Audit des écritures de politique** (qui, quand, quoi).
45. **Chiffrement** du jeu de démo si on y met de la vraie donnée.
46. Scan de **secrets** régulier (le dépôt est public).
47. **Rate-limiting** sur le webhook CI/CD.
48. Signature/nonce du webhook (contre la rejeu).
49. ⭐ **Pentest de Rempart par lui-même** : rejouer le banc réel en CI hebdo.
50. `SUPPORT.md` sécurité.

## F. Coût & freemium (51–60)

51. ⭐ **Tableau de bord du coût** (par tenant, par mois, par test).
52. ⭐ **Optimiser le budget InferHub** : choisir le modèle par défaut selon le coût (mesuré : 402 `no_provider_under_bid`).
53. Coût **par finding** affiché.
54. ⭐ **Kill-switch** : un bouton/drapeau qui arrête tout.
55. Confirmer que le **contrôle plane** reste 0 € au repos (chiffrement AWS-managed).
56. **Suppression programmée** (`cdk destroy`) des ressources si la démo n'est plus servie.
57. Estimation **mensuelle** affichée (mesuré : −0,0000000344 $ en nov.).
58. Auto-stop **budget mensuel** affiché dans le portail.
59. Un guide « **ne jamais payer** » pour les juges.
60. Un budget **plafond** par test (déjà 5 h, à documenter côté juge).

## G. Plateforme & architecture (61–70)

61. **Timeout** des Lambdas de tâche vérifié (le plafond 5 min).
62. **Reprise sur échec** du pipeline (Step Functions).
63. **Observabilité** : alarmes sur chaque étape (déjà prévu, à tester en réel).
64. **Versioning** des assets Lambda.
65. **Cache du client LLM** (le modèle est créé une fois par processus).
66. **Parallélisme** borné (quota 5, déjà).
67. Test de **charge** réel de l'API (un juge clique).
68. **Sauvegarde** du jeu de démo (le seed est déterministe).
69. Journaliser les **latences** (TRIAGE, intake).
70. Rétention **ENF-DATA-01** vérifiée de bout en bout (13 mois).

## H. Données (71–80)

71. Étendre le **jeu de démo** (plus de failles, plus de types).
72. **Données réelles annotées** (le lockfile comme source).
73. **Traçabilité** de chaque chiffre du jeu (le code qui le calcule).
74. **Versioning** du dataset (un commit = un snapshot).
75. Script de **mise à jour** du jeu à partir d'un nouveau lot.
76. **Normalisation** des sévérités (fait).
77. **Corpus d'entraînement** du LLM (industrialization — à exploiter).
78. **Qualité** : aucune faille inventée (la promesse).
79. Mode **replay** d'un run.
80. Export **CSV/JSON** (audit, findings).

## I. Documentation & onboarding (81–90)

81. ⭐ **README juge** « 60 secondes » (pitch + URL + 3 clics) en tête.
82. Diagramme du **parcours** (le mermaid existe — à enrichir).
83. Guide « **déployer en 10 minutes** » pas à pas.
84. Guide « **rejouer toutes les preuves** ».
85. **Glossaire** (MSP, Control Plane, Continuum).
86. **FAQ** pour les juges.
87. **ADR** à jour (docs/decisions/).
88. **Captures** dans le README (fait, à maintenir).
89. Tester les instructions dans un **environnement vierge**.
90. Traduction **FR/EN** des docs clés.

## J. Vidéo & démo (91–100)

91. ⭐ La **vidéo de 3 min** (script prêt) tournée sur la démo gratuite.
92. Démo **pas-à-pas** (10 min) pour les juges.
93. Clip du **dossier de preuves scellé** (l'empreinte recomputée en direct).
94. Clip du **LLM** (le verdict du modèle, le lockfile cité).
95. Clip du **garde-fou** (un faux positif bloqué en direct).
96. Clip **« 0 € »** (mode offline + test réseau coupé).
97. **Avant/après** (page vide → vraies données).
98. Clip **coût** (le −0,0000000344 $).
99. Clip **sécurité** (un vrai scan → triage).
100. Clip **onboarding** (un client inscrit son domaine).

---

## Les 10 à faire en premier

Ordre = impact × faisabilité × urgence (avant le premier test réel du 23/11).

1. **Préparer et lancer le premier test Continuum réel (21+22+23+24+25).** C'est la
   seule brique du produit jamais exercée en production ; tout le reste l'entoure.
   Coût maîtrisé (< 5 $) et preuve de la boucle complète.

2. **Fiabiliser le coût/la dispo du LLM (52+31+32).** Le vrai coût du projet est le
   triage. Choisir le modèle par défaut selon le budget (combo/cheap → glm-5.2),
   cachet les verdicts identiques et évaluer modèle vs règleur.

3. **Ficher le LLM dans les preuves (12).** Ajouter `P6-llm` à `proof_real.py` :
   un appel de triage doit renvoyer au moins un verdict `source == "model"`.

4. **Identifiants juges + README « 60 secondes » (2+81+5).** La métrique finale est
   le juge qui clique. URL gratuite en tête, identifiants qui fonctionnent du premier coup.

5. **LICENCE + SECURITY.md + SUPPORT.md (3+4+50).** Zéro effort, gros gain de
   crédibilité (repos public, projet sécurité).

6. **La vidéo de démo (91+93+94+95).** Le juge qui ne clique pas regarde la vidéo ;
   elle doit montrer le dossier scellé, le LLM et le garde-fou.

7. **Script de soumission one-shot (1).** Vérifie tout (URL, identifiants, captures,
   200) et imprime ce qu'il faut coller sur Devpost — évite la dernière surprise.

8. **Coût & kill-switch (51+54+57).** Un tableau de bord du coût et un drapeau
   d'arrêt : « jamais de surprise payante » est un argument de vente du produit.

9. **Endurcir l'entrée (41+42+47+48).** Fuzzing des routes, validation stricte,
   rate-limit et signature du webhook — on pratique ce qu'on prêche.

10. **Le pentest de Rempart par lui-même (49).** Rejouer le banc réel (vraies
    failles, vrais scanners) en CI hebdo, pour prouver que Rempart attrape ses
    propres défauts.