# Accord de sous-traitance RGPD (article 28) — GABARIT

> ⚖️ **GABARIT — PAS UN ACTE DÉFINITIF.** Modèle d'accord de sous-traitance au
> sens de l'**article 28 du RGPD**, à compléter par les parties et **à faire
> relire par un juriste avant signature**. Les emplacements marqués ⚖️
> **RELECTURE JURIDIQUE** exigent une validation par un avocat.
>
> Sources : cahier des charges § 15.3 (données), pistes #33 et #39 du
> [fichier d'approfondissement](../deepening-100-pistes.md). Les affirmations
> techniques citées ici ont été vérifiées dans le code du dépôt le
> 11 novembre 2026 ; les fichiers sont cités à chaque fois.

---

## ENTRE

- **Le Client** (responsable de traitement) : `[raison sociale, siège, représentant]`
- **Le Prestataire MSP** (sous-traitant) : `[raison sociale, siège, représentant]`

## PRÉAMBULE

Dans le cadre du service managé de tests d'intrusion continus Rempart, le
Prestataire traite des données personnelles pour le compte du Client. Le
Prestataire agit **en qualité de sous-traitant au sens du RGPD** (cahier des
charges § 15.3 : « les contacts des clients sont des données personnelles ; le
MSP agit comme sous-traitant au sens du RGPD »). Le présent accord encadre ce
traitement, y compris la sous-traitance ultérieure confiée à AWS.

## ARTICLE 1 — OBJET ET DURÉE

- **Objet** : définir les conditions du traitement de données personnelles
  réalisé par le Prestataire pour l'exécution du service (pilotage des tests,
  tri des failles, suivi des corrections, rapports, journal d'audit).
- **Durée** : la durée du contrat de service, augmentée des durées de
  conservation de l'article 6. Le traitement cesse à la fin du contrat, sous
  réserve de la purge décrite à l'article 9.

## ARTICLE 2 — NATURE ET FINALITÉ DU TRAITEMENT

| Finalité | Données concernées |
|---|---|
| Pilotage des tests et suivi du parc | identifiant client, nom, compte AWS, région, ARN du rôle, identifiant externe, formule, budget, état du mandat (`Tenant` — `backend/rempart/common/models.py`) |
| Gestion des failles de sécurité | failles, preuves, décisions, priorités, échéances (`Finding`, `Decision`) |
| Contacts et notifications | **les contacts du Client sont des données personnelles** (noms, e-mails, téléphones — `Tenant.contacts`) |
| Traçabilité | journal d'audit horodaté (`AuditEvent`), paquet de preuves exportable |
| Rapports | indicateurs et rapports mensuels par client |

**Les failles peuvent révéler des données personnelles** (piste #39) : une
preuve d'exploitation (ex. accès aux commandes d'un autre utilisateur) peut
contenir des données de personnes concernées finales. Le Prestataire les traite
comme confidentielles ; les scripts de vérification et étapes d'exploitation
**restent dans le compte AWS du Client**, le plan de contrôle n'en garde que le
lien (cahier des charges § 15.3).

⚖️ **RELECTURE JURIDIQUE** : qualifier précisément chaque finalité et vérifier
la base légale côté Client ; prévoir le cas où une faille expose des données
personnelles de tiers (obligation de notification, article 7).

## ARTICLE 3 — CATÉGORIES DE PERSONNES CONCERNÉES

- contacts du Client (responsable sécurité, développeurs, dirigeants, contacts
  d'urgence du [mandat de test](mandate-template.md)) ;
- utilisateurs du portail (identités Cognito : rôle et client portés par les
  jetons — `backend/rempart/common/tenant.py`, `portal/src/auth/`) ;
- le cas échéant, **utilisateurs finaux du Client** dont les données
  apparaîtraient dans la preuve d'une faille.

## ARTICLE 4 — OBLIGATIONS DU SOUS-TRAITANT

Le Prestataire s'engage à :

1. traiter les données **uniquement** pour les finalités de l'article 2, sur
   instruction documentée du Client ;
2. garantir la **confidentialité** (article 7 du mandat de test) ;
3. mettre en œuvre les **mesures de sécurité** de l'article 8 ;
4. respecter les conditions de **sous-traitance ultérieure** de l'article 5 ;
5. **coopérer** aux audits du Client (article 10) ;
6. **notifier les violations** de données dans les délais de l'article 7 ;
7. assurer le **sort des données** en fin de contrat (article 9) ;
8. tenir le **registre** de l'article 11 ;
9. cloisonner strictement les données entre clients : l'isolation
   multi-tenant est vérifiée par des tests automatisés
   (`backend/tests/api/test_isolation.py`,
   `backend/tests/integration/test_isolation_journey.py` — un principal du
   client A reçoit 403 sur les routes du client B).

## ARTICLE 5 — SOUS-TRAITANCE ULTÉRIEURE

Le Client autorise la sous-traitance ultérieure suivante :

| Sous-traitant ultérieur | Rôle | Localisation / garanties |
|---|---|---|
| **AWS (Amazon Web Services EMEA SARL et affiliées)** | service Continuum qui exécute les tests ; hébergement du plan de contrôle (Lambda, DynamoDB, Step Functions, CloudFront, Cognito, Bedrock/AgentCore pour l'agent de tri) | **le plan de contrôle est hébergé en région européenne** : région par défaut `eu-west-3` (Paris) — `iac/control-plane/app.py` (`DEFAULT_REGION = "eu-west-3"`) ; garanties AWS : DPA AWS, clauses contractuelles types ⚖️ RELECTURE JURIDIQUE |

Points d'architecture qui limitent la sous-traitance ultérieure :

- les tests s'exécutent **dans le compte AWS du Client** ; le Prestataire y
  accède par un rôle cross-account à moindre privilège (exactement 16 actions
  `securityagent:`, sans joker, `sts:ExternalId` obligatoire — verrouillé par
  tests : `backend/tests/iac/test_least_privilege.py`,
  `backend/tests/iac/test_client_template.py`) ;
- les données du Client restent dans son compte ; le plan de contrôle ne
  conserve que métadonnées, failles et liens.

⚖️ **RELECTURE JURIDIQUE** : vérifier la chaîne contractuelle AWS (DPA AWS,
transfer/Addendum européen), le droit d'opposition du Client à un nouveau
sous-traitant ultérieur et le préavis d'information.

## ARTICLE 6 — DURÉE DE CONSERVATION ⚖️ vérifier avec l'article 9

- **13 mois par défaut** pour les données du service (failles, décisions,
  runs, audits) : `DEFAULT_RETENTION_MONTHS = 13` —
  `backend/rempart/common/store.py` ; cahier des charges § 15.3
  (« conservées 13 mois »).
- **Implémentation vérifiée dans le code** : chaque écriture en base horodate
  un attribut `expire_at` (TTL DynamoDB) calculé à 13 mois depuis la date de
  création (`ttl_epoch`, `_with_ttl` — `backend/rempart/common/store.py`),
  vérifié par 8 tests dont « toute entité enregistrée porte un `expire_at` »
  (`backend/tests/common/test_retention.py`).
- **Fin de contrat : suppression sous 30 jours** : `contract_end_epoch(months=1)`
  et `Store.set_expire_at` posent une échéance de purge à 30 jours
  (`backend/rempart/common/store.py`, testé dans
  `backend/tests/common/test_retention.py`).
- ⚠️ **Limite honnête du produit à ce jour** : la purge à 30 jours est
  implémentée **au niveau du stockage et testée**, mais **aucune route API ni
  procédure d'off-boarding automatisée ne l'invoque encore** — son déclenchement
  en fin de contrat est aujourd'hui une opération manuelle du Prestataire
  (piste #68 : off-boarding à industrialiser). Ne pas promettre au Client une
  purge automatique avant que le code ne la déclenche.

⚖️ **RELECTURE JURIDIQUE** : articuler la conservation de 13 mois avec le
**droit à l'effacement** (piste #39) : prévoir les exceptions légales
(preuve, contentieux) et la procédure de demande d'effacement anticipée.

## ARTICLE 7 — NOTIFICATION DE VIOLATION DE DONNÉES

- Le Prestataire notifie au Client toute violation de données personnelles
  **sans délai injustifié** après en avoir pris connaissance, et en tout état
  de cause sous `[X — ex. 24]` heures ⚖️ RELECTURE JURIDIQUE, afin de permettre
  au Client (responsable de traitement) de notifier l'autorité de contrôle
  **dans les 72 heures** (art. 33 RGPD) et les personnes concernées si
  nécessaire (art. 34).
- Contenu minimal : nature de la violation, catégories et volumes approximatifs,
  conséquences probables, mesures prises, point de contact.
- La notification au Client n'est **pas** une reconnaissance de faute.
- Une violation découverte **par** un test (faille exposant des données) suit
  la même procédure : le Client décide de la notification à l'autorité ; le
  Prestataire fournit les éléments techniques (run, horodatages, preuve).

⚖️ **RELECTURE JURIDIQUE** : délai contractuel, répartition des rôles dans la
notification, cas des failles exploitées activement (piste #61).

## ARTICLE 8 — MESURES DE SÉCURITÉ (état réel du produit)

| Mesure | Preuve dans le dépôt |
|---|---|
| Cloisonnement strict par client (RBAC 7 rôles, autorisation vérifiée avant toute lecture) | `backend/rempart/common/tenant.py`, `backend/tests/api/test_isolation.py` |
| Moindre privilège du rôle cross-account (16 actions, pas de joker, `sts:ExternalId`) | `backend/tests/iac/test_least_privilege.py` |
| Visibilité totale du Client sur les accès à son compte (CloudTrail) | cahier des charges § 15.2 |
| Journal d'audit **lecture seule par construction** (aucune route d'écriture : POST/PUT/DELETE/PATCH → 404/405, testé) | `backend/rempart/api/routes/audit.py`, `backend/tests/api/test_audit.py` |
| Preuves d'exploitation conservées dans le compte du Client, lien seul dans le plan de contrôle ; aucune donnée d'exploitation dans le paquet de preuves exporté (ENF-SEC-05) | cahier des charges § 15.3, `backend/rempart/reports/evidence.py` |
| Chiffrement et hébergement européen du plan de contrôle (`eu-west-3`) | `iac/control-plane/app.py` ⚖️ vérifier le chiffrement au repos effectif après déploiement (rien n'est déployé à ce jour) |
| Surveillance : alarmes sur erreurs API, tâches d'orchestration, exécutions d'état | `iac/control-plane/stacks/observability.py` |

## ARTICLE 9 — SORT DES DONNÉES EN FIN DE CONTRAT

Au choix du Client et dans un délai de **30 jours** après la fin du contrat :

1. **restitution** : export du paquet de preuves scellé (JSON + HTML, empreinte
   SHA-256 recalculable — `backend/rempart/reports/evidence.py`) ;
2. **suppression** : purge à 30 jours via l'attribut `expire_at`
   (`Store.set_expire_at`, article 6) et attestation écrite de suppression
   (piste #68) ;
3. les données déjà situées **dans le compte AWS du Client** (preuves,
   scripts) restent sous son contrôle exclusif.

## ARTICLE 10 — COOPÉRATION AUX AUDITS

Le Prestataire met à disposition du Client (ou de son auditeur) : le paquet de
preuves exportable, le journal d'audit de son périmètre, la documentation des
mesures de sécurité (article 8) et les résultats des tests d'isolation. Les
audits sur site ou accès directs au plan de contrôle sont `[à encadrer :
fréquence, préavis, confidentialité, coûts]` ⚖️ RELECTURE JURIDIQUE.

## ARTICLE 11 — REGISTRE

Le Prestataire tient un registre des activités de traitement effectuées pour le
compte du Client (art. 30 § 2 RGPD) : finalités, catégories, transferts,
durées de conservation, mesures de sécurité. `[Support et lieu de tenue à
préciser.]`

## SIGNATURES

Fait à `[...]`, le `[...]`, en deux exemplaires. Annexe indissociable du
[mandat de test](mandate-template.md).

| Pour le Client (responsable de traitement) | Pour le Prestataire (sous-traitant) |
|---|---|
| Signature : | Signature : |

> ⚖️ **RELECTURE JURIDIQUE FINALE** : ce gabarit n'est pas un acte définitif.
> Points à valider en priorité : chaîne de sous-traitance AWS (article 5),
> délais de notification (article 7), articulation conservation/effacement
> (article 6), régime d'audit (article 10).
