# Matrice de responsabilité — service Rempart (GABARIT)

> ⚖️ **GABARIT — PAS UN ACTE DÉFINITIF.** Cette matrice de responsabilité
> (RACI) est un support de négociation contractuelle. Elle **doit être relue
> par un juriste** avant d'être annexée à un contrat : les lignes
> « indemnisation » et « notification de violation » en particulier.
>
> Les rôles correspondent au tableau du chapitre 6 du
> [cahier des charges](../cahier-des-charges-tests-intrusion-continu.md) et aux
> rôles codés dans `backend/rempart/common/tenant.py`
> (`platform_admin`, `analyst`, `account_manager` — MSP ;
> `client_security`, `client_dev`, `executive` — Client ; `demo`).
> L'agent IA de tri est un **outil** du Prestataire, jamais un responsable :
> ses propositions n'ont d'effet qu'après les garde-fous décrits plus bas.

**Légende RACI** : **R** = réalise · **A** = approuve / rend compte en dernier
ressort · **C** = consulté · **I** = informé.

---

## 1. Matrice RACI

| # | Activité | Client (`client_security` / direction) | MSP analyste | MSP `platform_admin` | Agent IA de tri | Prestataire (organisation) |
|---|---|---|---|---|---|---|
| 1 | **Décision de tester** (signature du [mandat](mandate-template.md), statuts `valid`) | **A + R** (signe, mandate) | I | R (enregistre le statut dans le portail) | — | A (refuse sans mandat) |
| 2 | **Étendue du périmètre** (domaines, environnements, exclusions, fenêtres) | **A + R** | C | R (saisit domaines, `test_windows`) | — | C (propose, vérifie les domaines) |
| 3 | **Classification d'une faille** (priorité P1–P4) | I | **A** (valide, décide) | I | **R** (propose seulement — voir § 2) | R (fournit la matrice déterministe) |
| 4 | **Acceptation d'un risque** | **A + R exclusif** (rôle `client_security` du client propriétaire — voir § 3) | **interdit par le code (403)** | **interdit par le code (403)** | — | I (enregistre la décision tracée) |
| 5 | **Correction de la faille** (code, déploiement) | **A + R** (`client_dev` reçoit le ticket, fusionne) | C (PR de correction générée sur demande) | I | — | C |
| 6 | **Preuve de fermeture** (retest concluant) | I | R (suit la fermeture) | R (le retest est automatisé) | — | **A** (fermeture uniquement sur retest, identifiant de run conservé comme preuve) |
| 7 | **Notification d'une violation de données** (autorité, personnes concernées) | **A + R** (responsable de traitement) | C (éléments techniques) | C (journaux, horodatages) | — | R (notifie le Client sans délai — [DPA](dpa-template.md) art. 7) |
| 8 | **Indemnisation** ⚖️ RELECTURE JURIDIQUE | selon contrat | — | — | — | selon contrat, plafond et assurance RC pro (pistes #35, #36) |

⚖️ **RELECTURE JURIDIQUE** sur les lignes 1, 4, 7, 8 : opposabilité du mandat,
pouvoir réel de la personne qui accepte un risque dans l'organisation du client
(piste #38), délais de notification, plafonds et garanties d'indemnisation.

## 2. Classification : ce que l'agent IA peut et ne peut pas (garde-fous codés)

L'agent de tri (Strands + Bedrock sur AgentCore Runtime) **propose** :
déduplication, résumé en trois phrases, statut suggéré. Ensuite **le code
reprend la main** — trois garde-fous vérifiés dans le dépôt :

1. **La matrice déterministe l'emporte.** La priorité est recalculée par
   `backend/rempart/common/priority.py` (sévérité × confiance × exposition ×
   sensibilité des données) ; en cas de divergence entre la proposition du
   modèle et la matrice, **la matrice gagne** et la divergence est journalisée
   (`_enforce_priority`, `backend/rempart/triage/guardrails.py` —
   « Matrix wins »).
2. **Validation humaine obligatoire sur Critical/High.** Une proposition
   « faux positif probable » sur une faille Critical ou High est **toujours**
   forcée en validation humaine (ENF-IA-02,
   `backend/rempart/triage/guardrails.py`, `HIGH_SEVERITIES = {"Critical",
   "High"}`) ; le modèle ne peut jamais écarter seul une faille grave.
   Tests : `backend/tests/triage/test_guardrails.py`.
3. **Journal d'audit horodaté, lecture seule.** Chaque décision (agent,
   analyste, client) est tracée (`Decision` avec auteur, action, justification,
   horodatage — `backend/rempart/common/models.py`) et le journal d'audit
   n'est pas modifiable (POST → 404/405, testé dans
   `backend/tests/api/test_audit.py`).

La résistance à l'injection de prompt est testée
(`backend/tests/triage/test_prompt_injection.py`) : un contenu hostile dans une
faille ne peut pas changer la priorité ni casser le pipeline.

## 3. Acceptation de risque : réservée au client, verrouillée par le code

Vérifié dans `backend/rempart/api/routes/findings.py` :

- `RISK_ACCEPTANCE_ROLES = ("client_security",)` — **seul le responsable
  sécurité du client** peut accepter un risque ; aucun rôle MSP (`analyst`,
  `platform_admin`) ne le peut ;
- le contrôle exige en plus que le tenant du demandeur soit **celui de la
  faille** (`principal.tenant_id != finding.tenant_id` → 403) ;
- une **justification non vide** est obligatoire (400 sinon) ;
- l'acceptation est horodatée et attribuée (`risk_review_at`,
  `risk_review_by` — `Finding`, `backend/rempart/common/models.py`).

**Le test qui le verrouille** : `backend/tests/api/test_risk_acceptance.py` —
8 tests, dont `test_analyste_msp_ne_peut_pas_accepter_un_risque` (403),
`test_platform_admin_ne_peut_pas_accepter_un_risque` (403),
`test_client_security_d_un_autre_tenant_est_refuse` (403) et
`test_acceptation_sans_justification_est_refusee` (400).

Conséquence contractuelle : **le Prestataire ne peut pas accepter un risque à
la place du Client** ; une faille non corrigée dans les délais sans acceptation
de risque tracée reste à la charge de décision du Client (relances et
escalade au responsable de compte — `backend/rempart/orchestrator/reminders.py`).

⚖️ **RELECTURE JURIDIQUE** (piste #38) : le rôle `client_security` est un
contrôle technique ; le contrat doit exiger que la personne qui l'occupe ait
**réellement le pouvoir d'engager son organisation** à accepter un risque.

## 4. Piste #21 — l'agent classe P4 une faille qui était P1, et elle est exploitée

**Scénario** : l'agent de tri propose P4 (ou « faux positif ») pour une faille
qui valait P1 ; personne ne la corrige ; elle est exploitée. Où s'arrête la
responsabilité du Prestataire ?

### Ce que le produit oppose déjà à ce scénario (bornes techniques)

1. **La proposition de l'agent ne fixe jamais seule la priorité.** La matrice
   déterministe recalcule la priorité et **l'emporte** sur la divergence
   (`backend/rempart/triage/guardrails.py`). Pour qu'une faille Critical/High
   à confiance haute finisse P4, il faudrait que la matrice elle-même se
   trompe — la faute de l'agent seul est déjà neutralisée par construction.
2. **Sur Critical/High, un humain passe toujours.** Le modèle ne peut pas
   écarter seul une faille grave : « faux positif probable » sur Critical/High
   → validation humaine forcée (garde-fou 2 du § 2). La chaîne de faute exige
   alors **deux** défaillances : la matrice **et** l'analyste humain.
3. **Tout est tracé.** Le journal d'audit horodaté, lecture seule, permet de
   reconstituer qui (agent, analyste, client) a décidé quoi et quand ; le
   paquet de preuves exportable porte la chaîne de décision par faille
   (`backend/rempart/reports/evidence.py`). La preuve de la faute — ou de son
   absence — est donc produite par le système lui-même.

### Lecture de responsabilité (à valider par un juriste ⚖️)

- **Cas 1 — l'agent propose P4, la matrice dit P1** : la priorité retenue est
  P1, échéance contractuelle 7 jours (`DEFAULT_DUE_DAYS`,
  `backend/rempart/common/priority.py`). La proposition erronée de l'agent est
  sans effet : **pas de responsabilité du Prestataire** au titre du tri ; la
  non-correction relève du Client (ligne 5 de la matrice).
- **Cas 2 — la matrice elle-même classe P4** (sévérité ou contexte
  sous-évalués) et la faille était en réalité P1 : la faute est dans l'outil du
  Prestataire. Sa responsabilité contractuelle s'apprécie alors au regard des
  obligations de **moyens** vs **résultat** du contrat ⚖️ RELECTURE JURIDIQUE
  INDISPENSABLE (piste #20 : ne jamais vendre un engagement de résultat sur la
  détection ; pistes #1/#2 : le taux de faux négatifs n'est pas encore mesuré —
  le dire au client).
- **Cas 3 — matrice correcte (P1) mais analyste MSP valide « faux positif »**
  sur une faille Critical/High : faute humaine du Prestataire, traçable dans le
  journal ; responsabilité du Prestataire, dans la limite du plafond
  d'indemnisation et de l'assurance RC pro ⚖️.
- **Cas 4 — le Client a accepté le risque** (`risk_accepted` tracé avec
  justification et auteur) : la décision est celle du Client ; le
  Prestataire a rempli son obligation d'information. ⚖️ Faire vérifier
  l'opposabilité de l'acceptation de risque en cas de dommages à des tiers
  (utilisateurs finaux).

**Limite honnête** : la matrice peut elle-même se tromper (piste #22) et le
service ne mesure pas encore son taux de faux négatifs sur un jeu de référence
réel (pistes #2, #24 : les 40 failles étiquetées du § 12.5 du cahier des
charges restent à construire). La promesse vendable est « couverture continue
de ce qui est automatisable » (piste #10), **pas** « aucune faille P1 ne passe
jamais ».

⚖️ **RELECTURE JURIDIQUE INDISPENSABLE** : obligations de moyens/résultat,
plafond d'indemnisation, assurance (piste #36), clause de limitation de
responsabilité pour les erreurs de classification malgré les garde-fous, et
régime en cas de dommages aux tiers.

## 5. Ce que cette matrice ne couvre pas (assumé)

- L'ingénierie sociale, l'intrusion physique, le réseau interne, les postes de
  travail et le déni de service sont **exclus du périmètre produit**
  ([mandat](mandate-template.md) art. 2.3) : aucune responsabilité du
  Prestataire sur ces vecteurs.
- La sécurité du compte AWS du Client (rôles, CloudTrail, secrets de test)
  reste sous son contrôle ; le Prestataire fournit les instructions de moindre
  privilège (annexe A du cahier des charges).
- Rien n'est déployé sur AWS à ce jour
  ([statuts réels](../submission-checklist.md)) : cette matrice décrit le
  service **tel que codé et testé**, pas un service en production.
