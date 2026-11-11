# Mandat de test d'intrusion — GABARIT

> ⚖️ **GABARIT — PAS UN ACTE DÉFINITIF.** Ce document est un modèle à compléter
> par le client et le MSP. Il **doit être relu et validé par un juriste
> (avocat spécialisé en droit du numérique) avant toute signature**. Les
> emplacements marqués ⚖️ **RELECTURE JURIDIQUE** sont ceux où la relecture est
> indispensable : formulation de l'autorisation pénale, responsabilité,
> indemnisation, droit applicable.
>
> Sources produit : cahier des charges § 15.1 (autorisation de tester),
> exigence ENF-LEG-01 (« aucun test sans mandat valide et sans domaine
> vérifié »), piste #31 du [fichier d'approfondissement](../deepening-100-pistes.md).

---

## ENTRE LES PARTIES

### Le Client (donneur d'ordre)

| Champ | Valeur |
|---|---|
| Raison sociale | `[À COMPLÉTER]` |
| Forme juridique, capital | `[À COMPLÉTER]` |
| Siège social | `[À COMPLÉTER]` |
| RCS / SIREN | `[À COMPLÉTER]` |
| Représenté par (nom, qualité) | `[À COMPLÉTER — doit avoir pouvoir d'engager la société]` |
| Responsable sécurité du compte (rôle `client_security` dans le portail) | `[À COMPLÉTER]` |

### Le Prestataire (MSP)

| Champ | Valeur |
|---|---|
| Raison sociale | `[À COMPLÉTER]` |
| Siège social | `[À COMPLÉTER]` |
| Représenté par | `[À COMPLÉTER]` |
| Assurance RC professionnelle (compagnie, police, montant) | `[À COMPLÉTER — voir piste #36]` |

### Chaîne de sous-traitance technique ⚖️ RELECTURE JURIDIQUE

Le Prestataire n'exécute pas lui-même les tests : il pilote le service managé
**AWS Continuum** (Amazon Web Services) via son API, depuis un plan de contrôle
hébergé sur AWS. Le Client reconnaît et accepte cette chaîne :

1. **Client** — propriétaire des systèmes testés ; les tests s'exécutent contre
   son compte AWS et ses domaines vérifiés.
2. **Prestataire (MSP)** — opère le plan de contrôle Rempart, déclenche,
   suit et fait trier les tests ; agit en qualité de **sous-traitant RGPD**
   (voir l'[accord de sous-traitance](dpa-template.md) joint).
3. **AWS (Amazon Web Services EMEA SARL et affiliées)** — fournit le service
   Continuum qui exécute les agents de test ; sous-traitant ultérieur. Les
   appels du Prestataire au compte du Client passent par un rôle IAM
   cross-account à moindre privilège avec identifiant externe unique
   (`sts:ExternalId`), visible du Client dans son propre CloudTrail
   (cahier des charges § 15.2).

> ⚖️ **RELECTURE JURIDIQUE** : vérifier la qualification exacte (sous-traitance
> au sens de l'art. 28 RGPD vs prestation d'intermédiation), et l'opposabilité
> des conditions AWS au Client.

---

## ARTICLE 1 — OBJET

Le Client autorise le Prestataire à faire exécuter, par le service AWS
Continuum piloté par la plateforme Rempart, des tests d'intrusion automatisés
sur les systèmes strictement listés à l'article 2, dans le cadre d'un service
managé de tests d'intrusion continus.

Le test continu **ne remplace pas** un test d'intrusion manuel annuel ; il
couvre de façon continue ce qui est automatisable (piste #9).

## ARTICLE 2 — PÉRIMÈTRE EXACT

### 2.1 Domaines et applications autorisés

Chaque domaine doit être **vérifié** côté AWS Continuum avant tout test
(méthode `DNS_TXT`, `HTTP_ROUTE` ou `PRIVATE_VPC` — implémenté dans
`backend/rempart/api/routes/onboarding.py`). Tout test sur un domaine non
vérifié est refusé par le produit.

| Application | Domaines / URL | Environnement | Dépôt de code | Criticité |
|---|---|---|---|---|
| `[nom]` | `[ex. app.example.com]` | `[staging / production]` | `[repo]` | `[critique/standard]` |
| `[...]` | | | | |

### 2.2 Environnements

- Par défaut, les tests visent la **préproduction** (cahier des charges § 15.1).
- Un test complet en **production** n'est autorisé que dans une **fenêtre
  convenue**, enregistrée par application (`Application.test_windows`). Le
  produit refuse et audite tout test complet en production hors fenêtre
  (raison `outside_test_window`, `backend/rempart/orchestrator/gates.py` et
  `backend/rempart/orchestrator/windows.py`).

| Environnement | Fenêtres autorisées (jours, heures UTC) |
|---|---|
| `[production]` | `[ex. lundi 22:00 → mardi 06:00]` |

Les tests déclenchés par le pipeline CI/CD (porte de livraison) sur les
commits livrés ne sont **jamais** bloqués par une fenêtre : bloquer une
publication ne peut pas attendre (comportement codé et testé dans
`backend/tests/orchestrator/test_test_windows.py`).

### 2.3 EXCLUSIONS explicites — ne sont JAMAIS autorisés ⚖️ RELECTURE JURIDIQUE

Sauf avenant écrit, sont exclus du périmètre et interdits :

- **déni de service** (DoS/DDoS, tests de charge destructifs) ;
- **ingénierie sociale** (hameçonnage, prétexte, appels) ;
- **intrusion physique** (locaux, badges, matériel) ;
- **réseau interne** du Client (postes, serveurs internes, AD) ;
- **postes de travail** des employés du Client ;
- tout système tiers non listé à l'article 2.1.

Le service AWS Continuum utilisé ici est un test d'applications web/API sur
domaines vérifiés ; ces exclusions correspondent au périmètre réel du produit.

> ⚖️ **RELECTURE JURIDIQUE** : la liste des exclusions doit être conforme au
> droit applicable et aux assurances du Prestataire (piste #36).

## ARTICLE 3 — AUTORISATION EXPLICITE (article 323-1 du Code pénal) ⚖️ RELECTURE JURIDIQUE INDISPENSABLE

Le Client, propriétaire ou exploitant légitime des systèmes listés à
l'article 2, **autorise expressément** le Prestataire et son sous-traitant
technique AWS Continuum à :

- accéder, de manière automatisée, aux systèmes du périmètre ;
- y rechercher des vulnérabilités, y compris en tentant de contourner des
  contrôles d'accès dans la limite du périmètre ;
- exécuter les scripts de vérification produits par les tests.

Cette autorisation est donnée **au sens de l'article 323-1 et suivants du Code
pénal français** (accès ou maintien frauduleux dans un système de traitement
automatisé de données) et vaut pour la durée et le périmètre du présent mandat.
Sans elle, les mêmes actes constitueraient un délit : le mandat est donc une
**condition bloquante du produit**, pas une formalité (cahier des charges § 15.1).

Le Client déclare :

- avoir **qualité pour donner cette autorisation** sur chaque système du
  périmètre ;
- que les systèmes du périmètre ne contiennent **aucune donnée dont la
  divulgation serait interdite** par la loi ou un engagement envers des tiers,
  ou, à défaut, en accepte le risque lié à la découverte d'une faille.

> ⚖️ **RELECTURE JURIDIQUE INDISPENSABLE** : la portée exacte de
> l'autorisation pénale (personnes couvertes : employés du Prestataire, agents
> automatisés d'AWS ; actes couverts ; preuve de l'autorisation en cas de
> contestation — piste #32) doit être validée par un avocat. Le présent
> gabarit ne constitue pas un avis juridique.

## ARTICLE 4 — FENÊTRE DE VALIDITÉ, RENOUVELLEMENT, RÉVOCATION

| Champ | Valeur |
|---|---|
| Date de début | `[JJ/MM/AAAA]` |
| Date de fin | `[JJ/MM/AAAA]` |
| Renouvellement | `[tacite / exprès, préavis]` ⚖️ RELECTURE JURIDIQUE |
| Révocation | Le Client peut révoquer à tout moment par notification écrite au contact d'urgence ; la révocation prend effet dès réception et le statut du mandat est passé à non valide dans le portail, ce qui **bloque tout nouveau test** (voir article 9). |

**Changement de périmètre en cours de contrat (piste #34)** : si une
application change de domaine ou d'hébergeur, le nouveau domaine doit être
ajouté par avenant et **re-vérifié** avant tout test ; l'ancien domaine est
retiré du périmètre. Le produit ne teste que des domaines vérifiés du
périmètre enregistré.

> ⚠️ **Limite honnête du produit à ce jour** : le portail contrôle un
> **statut** de mandat (`mandate_status` : `pending` par défaut, `valid` pour
> autoriser — `backend/rempart/api/routes/tenants.py`). Il n'existe encore
> **ni dépôt du fichier signé, ni contrôle automatique de la date de fin** dans
> le code : l'expiration et la révocation doivent être opérées par un
> administrateur de plateforme qui repasse le statut à non valide. C'est une
> procédure opérationnelle, pas une garantie technique.

## ARTICLE 5 — CONTACTS D'URGENCE

| Rôle | Organisation | Nom | Téléphone | E-mail | Disponibilité |
|---|---|---|---|---|---|
| Contact d'urgence test | Client | `[...]` | `[...]` | `[...]` | `[24/7 ?]` |
| Responsable sécurité (`client_security`) | Client | `[...]` | | | |
| Astreinte du Prestataire | MSP | `[...]` | | | |

Ces contacts sont enregistrés dans le portail (`Tenant.contacts`) ; ce sont des
**données personnelles** traitées selon l'[accord de sous-traitance RGPD](dpa-template.md).

## ARTICLE 6 — INCIDENT PROVOQUÉ PAR LE TEST (piste #35) ⚖️ RELECTURE JURIDIQUE

1. **Arrêt immédiat** : à la demande du contact d'urgence du Client, le
   Prestataire arrête le test en cours (l'arrêt programmé `StopPentestJob`
   existe déjà pour le budget — `backend/rempart/orchestrator/tasks.py` ;
   l'arrêt sur demande suit la même mécanique).
2. **Diagnostic** : le Prestataire fournit sous `[X]` heures les journaux du
   test (identifiant de run, horodatages, actions) pour distinguer la panne
   provoquée par le test d'un incident indépendant. Les appels AWS sont
   visibles du Client dans son propre CloudTrail (§ 15.2 du cahier des charges).
3. **Responsabilité et indemnisation** : `[À COMPLÉTER par le juriste : plafond
   d'indemnisation, exclusions, articulation avec l'assurance RC pro du
   Prestataire — pistes #35 et #36]`.
4. Les tests n'incluent **aucun déni de service** (article 2.3) ; un
   ralentissement involontaire reste possible — `[régime à définir par le
   juriste]`.

## ARTICLE 7 — CONFIDENTIALITÉ

Les résultats de test (failles, preuves, scripts de vérification) sont des
informations confidentielles du Client. Le Prestataire s'engage à :

- ne les divulguer à aucun tiers hors chaîne de sous-traitance de l'article « Parties » ;
- les cloisonner par client dans le plan de contrôle (isolation vérifiée par
  test : `backend/tests/integration/test_isolation_journey.py`) ;
- les conserver chiffrés et pour une durée de **13 mois** par défaut
  (`backend/rempart/common/store.py`, `DEFAULT_RETENTION_MONTHS = 13`) ;
- les scripts de vérification et étapes d'exploitation **restent dans le
  compte AWS du Client** ; le plan de contrôle n'en garde que le lien
  (cahier des charges § 15.3).

⚖️ **RELECTURE JURIDIQUE** : durée, pénalités, survivance après contrat.

## ARTICLE 8 — HÉBERGEUR ET SERVICES TIERS (pistes #34, #37) ⚖️ RELECTURE JURIDIQUE

Lorsque l'application du périmètre dépend d'un **hébergeur** ou appelle des
**services tiers** (SaaS, API partenaires) :

- le Client **atteste que ses conditions contractuelles avec cet hébergeur ou
  ce tiers autorisent les tests de sécurité** sur ce qui le concerne, ou a
  obtenu les autorisations nécessaires ;
- le Prestataire ne teste que la surface du Client (domaines vérifiés du
  périmètre) ; les systèmes du tiers en tant que tels sont **exclus** ;
- si un test risque d'atteindre un système tiers, il est suspendu et le cas
  est traité par avenant.

> ⚖️ **RELECTURE JURIDIQUE** : rédiger l'attestation du Client de façon
> opposable et prévoir la garantie du Client en cas d'action du tiers.

## ARTICLE 9 — CE QUE LE PORTAIL REMPART CONTRÔLE DÉJÀ (état réel du code)

Le mandat est une **condition bloquante dans le produit** : sans mandat valide,
aucun test ne part. Vérifié dans le code au 11 novembre 2026 :

| Contrôle du portail | Champ / comportement codé | Fichier |
|---|---|---|
| Statut du mandat | `Tenant.mandate_status` ; défaut `pending` ; seul `valid` autorise | `backend/rempart/common/models.py`, `backend/rempart/api/routes/tenants.py` |
| Blocage à la demande de test (API) | `mandate_status != "valid"` → **HTTP 403** « Mandat de test non valide ou expiré » | `backend/rempart/api/routes/runs.py` (`_validate_tenant_gates`) |
| Blocage à l'orchestration | garde `_refuse_mandate` dans `budget_gate`, raison `mandate_invalid`, **refus audité** (`run.refused_mandate`) | `backend/rempart/orchestrator/gates.py` |
| Test automatisé du blocage | le lancement sans mandat valide est refusé | `backend/tests/orchestrator/test_tasks.py` (scénario d'acceptation **R12**, `docs/acceptance.md`) |
| Domaines vérifiés | `DNS_TXT` / `HTTP_ROUTE` / `PRIVATE_VPC` exigés à l'enrôlement | `backend/rempart/api/routes/onboarding.py` |
| Fenêtres de production | `Application.test_windows` ; refus audité `outside_test_window` | `backend/rempart/orchestrator/windows.py`, `gates.py` |
| Contacts d'urgence | `Tenant.contacts` | `backend/rempart/common/models.py` |
| Budget mensuel en heures-tâches | `Tenant.monthly_budget_hours`, seuils 50/80/100 %, arrêt automatique | `backend/rempart/common/budget.py` |
| Statut du mandat dans le paquet de preuves | exporté pour l'audit du client | `backend/rempart/reports/evidence.py` |

**Ce que le portail ne contrôle PAS encore** (à ne jamais laisser croire au
client) : le dépôt du fichier signé du mandat, la vérification automatique des
dates de début/fin, la signature électronique. L'exigence EF-ONB-06
(« enregistrer le mandat : fichier, périmètre, dates ») n'est implémentée que
par le champ de statut ; le document signé est conservé hors portail à ce jour.

## ARTICLE 10 — DONNÉES PERSONNELLES

Les parties signent conjointement l'[accord de sous-traitance RGPD
(article 28)](dpa-template.md), annexé au présent mandat.

## SIGNATURES

Fait à `[...]`, le `[...]`, en deux exemplaires.

| Pour le Client | Pour le Prestataire |
|---|---|
| `[Nom, qualité — personne ayant pouvoir d'engager la société]` | `[Nom, qualité]` |
| Signature : | Signature : |

> ⚖️ **RELECTURE JURIDIQUE FINALE** : ce gabarit dans son ensemble
> (qualification, loi applicable, juridiction, opposabilité de la chaîne de
> sous-traitance, régime d'indemnisation) doit être validé par un juriste avant
> le premier usage commercial. Ce n'est pas un acte définitif.
