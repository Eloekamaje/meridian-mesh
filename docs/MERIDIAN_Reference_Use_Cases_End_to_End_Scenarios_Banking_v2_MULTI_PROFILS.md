# MÉRIDIAN — Reference Use Cases & End-to-End Scenarios
## Scénarios bancaires de référence, parcours de bout en bout, acteurs, sources, Claims, Mesh, Experts, décisions, outcomes et apprentissages

**Statut :** Référentiel produit / architecture / QA / démonstration  
**Version :** 2.0 — portefeuille multi-profils  
**Produit :** MÉRIDIAN  
**Tagline :** **DÉCOUVRIR · COMPRENDRE · DÉCIDER**

---

# 0. Objet du document

Ce document définit les **scénarios de référence de Méridian dans une banque**.

Il ne s’agit pas de simples exemples illustratifs.

Ces scénarios doivent servir simultanément de référence pour :

- le Produit ;
- l’Architecture fonctionnelle ;
- l’Architecture technique ;
- l’UX ;
- le backlog ;
- les évaluations IA ;
- la QA ;
- les démonstrations ;
- les pilotes ;
- le storytelling exécutif.

L’objectif est de vérifier que toutes les briques de Méridian racontent la même histoire.

Chaque scénario suit autant que possible la chaîne :

```text
Trigger
↓
Sources
↓
Artifacts / Observations
↓
Claims / Evidence
↓
Twin / Mesh
↓
Signal / Situation / Opportunity / Risk
↓
Flore
↓
Experts
↓
Investigation
↓
Hypotheses
↓
Scenarios
↓
Decision
↓
Initiative
↓
Outcome
↓
Learning
```

Le principe central est :

> **Un scénario Méridian n’est réussi que si l’on peut relier la donnée brute à une compréhension, puis à une action humaine ou à un apprentissage.**

---

# 0A. Correction structurante — les scénarios ne sont pas hiérarchisés par la TI

Le jumeau applicatif demeure une fondation importante parce qu’il donne accès à des faits riches :

```text
code
runtime
data
rules
changes
dependencies
```

Mais **l’entité de départ d’un scénario Méridian n’est pas forcément une application**.

Un scénario peut commencer par :

```text
un parcours client
un processus
une capacité métier
une règle
un risque
une donnée
une équipe
une initiative
une décision
```

Méridian résout ensuite les Twins, Sources et Experts nécessaires.

La règle du référentiel v2 est donc :

> **Même Mesh, plusieurs projections, plusieurs profils.**

---

# 0B. Les neuf perspectives bancaires

Le portefeuille de scénarios doit couvrir explicitement :

## 1. Direction / stratégie

Questions :

```text
Que devons-nous améliorer maintenant ?
Quelles décisions doivent être revisitées ?
Où existe-t-il duplication ou valeur non réalisée ?
```

## 2. Métier / Product

```text
Quel est l’impact réel d’un nouveau besoin ?
Avons-nous déjà cette capability ?
Quelle règle ou processus doit évoluer ?
```

## 3. Expérience client

```text
Pourquoi ce parcours se dégrade ?
Qu’est-ce qui explique les abandons ou contacts ?
```

## 4. Employé / opérations

```text
Où le travail manuel augmente ?
Quelle transformation déplace la charge ?
```

## 5. Risk / Compliance

```text
Où cette règle est-elle réellement appliquée ?
Quel risque transverse est en train d’émerger ?
```

## 6. Finance / portefeuille

```text
Où coût et valeur sont-ils désalignés ?
Quelles rationalisations sont plausibles ?
```

## 7. Data

```text
Qui produit et consomme cette donnée ?
Quel changement de schéma a un impact métier ?
```

## 8. Architecture / TI

```text
Quelles dépendances ?
Quels changements ?
Quelle modernisation ?
```

## 9. Transformation

```text
Nos initiatives produisent-elles réellement la valeur annoncée ?
Qu’avons-nous appris ?
```

Chaque profil doit pouvoir exploiter Méridian sans devoir entrer par un identifiant applicatif.

---

# 0C. Objets d’entrée de Flore / Atlas

La navigation doit permettre des entrées par :

```text
Application
Domain
Capability
Process
Journey
Customer phenomenon
Employee/Operations phenomenon
Risk
Rule
Data
Opportunity
Investigation
Decision
Initiative
Learning
```

---

# 1. Contexte bancaire de référence

Pour les scénarios de ce document, nous utilisons une banque universelle fictive appelée :

> **Banque Horizon**

Elle possède :

- plusieurs millions de clients ;
- des applications legacy et modernes ;
- des canaux Web, mobile et centre de contact ;
- des applications de paiements, hypothèques, cartes, fraude, crédit et conformité ;
- des plateformes API ;
- des bases Oracle et PostgreSQL ;
- des systèmes mainframe ;
- des microservices ;
- des outils SaaS ;
- une CMDB ;
- Jira ;
- Confluence ;
- GitHub ;
- ServiceNow ;
- Datadog ;
- Splunk ;
- différents systèmes de données et CRM.

Le paysage applicatif a grandi sur plusieurs décennies.

Il contient :

- des dépendances officielles ;
- des dépendances non documentées ;
- des règles métier dispersées ;
- des processus qui traversent plusieurs systèmes ;
- des décisions historiques difficiles à reconstruire ;
- des transformations partielles ;
- des applications difficiles à retirer.

C’est précisément dans ce type d’environnement que Méridian prend son sens.

---

# 2. Acteurs bancaires de référence

Les scénarios font intervenir les profils suivants.

## 2.1 Architecte d’entreprise

Veut comprendre :

- dépendances ;
- domaines ;
- transformations ;
- risques systémiques ;
- possibilités de rationalisation.

## 2.2 Architecte solution

Veut comprendre :

- impacts ;
- flux ;
- contrats ;
- données ;
- scénarios de changement.

## 2.3 Propriétaire applicatif

Veut comprendre :

- fonctionnement ;
- historique ;
- incidents ;
- consommateurs ;
- changements.

## 2.4 Product Owner métier

Veut comprendre :

- fonctionnalités ;
- parcours ;
- impacts clients ;
- opportunités.

## 2.5 Responsable opérations

Veut comprendre :

- charge ;
- reprises ;
- incidents ;
- frictions ;
- performance.

## 2.6 Risk / Compliance

Veut comprendre :

- exposition ;
- dépendances ;
- controls ;
- conséquences d’un changement.

## 2.7 Décideur

Veut comprendre :

- choix ;
- compromis ;
- valeur ;
- risques ;
- coûts ;
- outcomes attendus.

## 2.8 Analyste / Investigateur

Veut :

- tester des hypothèses ;
- confronter des preuves ;
- construire une synthèse.

---

# 3. Systèmes de référence

Les scénarios utilisent plusieurs systèmes fictifs.

```text
TBT
EligibilityService
MortgageJourney
PaymentsHub
Customer360
FraudEngine
DocumentVault
NotificationService
BatchSettlement
ContactCenter
AdvisorPortal
LegacyRules
RiskDataMart
```

---

# 3A. Portefeuille de scénarios — ordre de valeur recommandé

Pour éviter un cadrage trop TI, le référentiel doit être lu en **quatre familles parallèles**.

## Famille A — Compréhension du système

- Naissance du Twin TBT.
- Fonctionnalités sur trois ans.
- Suppression de TBT.
- Dépendance data.

## Famille B — Exploitation métier / client / employé

- Friction client hypothécaire.
- Friction employé et charge opérationnelle.
- Impact d’un nouveau besoin métier.
- Opportunity sans requête humaine.

## Famille C — Risque / gouvernance / stratégie

- Changement réglementaire.
- Résilience inter-applications.
- Domain Drift.
- Ownership réel vs déclaré.
- Décision historique à revisiter.

## Famille D — Amélioration et apprentissage

- Rationalisation.
- KPI local vs système global.
- Strategic modernization.
- Opportunity réactivée.
- Incident récurrent via mémoire.

Aucune famille ne constitue une simple extension de la famille A.

---

# 3B. Golden Stories multi-profils

Le set de démonstration bancaire recommandé comprend au minimum :

```text
GS-A  Comprendre TBT
GS-B  Friction client hypothécaire
GS-C  Charge opérationnelle déplacée
GS-D  Changement de règle / conformité
GS-E  Rationalisation portefeuille
GS-F  Decision → Outcome → Learning
```

Ainsi, le produit prouve simultanément :

```text
profondeur technique
+
compréhension métier
+
impact humain/client
+
gouvernance
+
valeur stratégique
```

---

# 4. Scénario 1 — Naissance du Twin TBT

## 4.1 Intention

Démontrer que Méridian peut faire naître un Twin applicatif vivant à partir de plusieurs sources.

## 4.2 Contexte

TBT est une application historique importante.

Les connaissances sont dispersées :

- code ;
- Jira ;
- Confluence ;
- CMDB ;
- Datadog.

Les nouveaux arrivants ont du mal à comprendre rapidement son rôle réel.

## 4.3 Trigger

Un architecte sélectionne :

> **Créer le Twin de TBT**

dans Atlas.

## 4.4 Sources initiales

```text
GitHub
Jira
Confluence
CMDB
Datadog
```

## 4.5 Étapes

```text
Source access
↓
Repository discovery
↓
Code graph
↓
Issue/history extraction
↓
Declared CMDB identity
↓
Runtime observations
↓
Initial Claims
↓
Neighbor resolution
↓
Twin Summary
```

## 4.6 Observations

Exemples :

```text
OBS-001
TBT repository contains module batch-validation.

OBS-002
TBT calls endpoint /eligibility/check.

OBS-003
Datadog traces show runtime calls from TBT to EligibilityService.

OBS-004
CMDB declares TBT part of "Transaction Processing".
```

## 4.7 Claims

```text
CLM-001
TBT IMPLEMENTS Batch Validation.

CLM-002
TBT CALLS EligibilityService.

CLM-003
TBT PARTICIPATES_IN Transaction Processing.

CLM-004
TBT IS_OWNED_BY Team Transaction Platforms.
```

## 4.8 Evidence

CLM-002 est supporté par :

- code ;
- configuration ;
- runtime trace.

Confidence :

```text
0.94
```

Maturity :

```text
M4 CROSS_VALIDATED
```

## 4.9 Unknowns

```text
UNK-001
Purpose of fallback path is unclear.

UNK-002
One batch consumer cannot yet be identified.

UNK-003
Business ownership of a legacy rule remains unclear.
```

## 4.10 Atlas

Atlas fait apparaître :

```text
TBT
├── EligibilityService
├── BatchSettlement
└── LegacyRules
```

Les domaines environnants restent visibles.

## 4.11 Flore

L’utilisateur demande :

> **Que sais-tu de TBT ?**

Flore répond en trois couches :

### Résumé

TBT orchestre une partie du traitement batch et des validations associées.

### Confiance

Élevée sur la structure technique.

Moyenne sur certaines règles métier.

### Inconnues

Trois zones restent à éclaircir.

## 4.12 UX attendue

La page Twin montre :

```text
Role
Capabilities
Dependencies
Knowledge Health
Unknowns
Recent Changes
Sources
```

## 4.13 Critères de succès

- Twin créé ;
- 3+ Sources ;
- Evidence traçable ;
- Claims structurés ;
- voisins détectés ;
- Unknowns explicites ;
- résumé utile en moins de quelques minutes après première indexation significative ;
- toutes les conclusions importantes sont vérifiables.

## 4.14 Valeur bancaire

Réduit :

- dépendance aux experts historiques ;
- temps d’onboarding ;
- risque de compréhension partielle ;
- effort de collecte manuelle.

---

# 5. Scénario 2 — Reconstruction des fonctionnalités ajoutées sur trois ans

## 5.1 Question

> **Je veux les dernières fonctionnalités ajoutées à TBT sur les trois dernières années, avec un rapport détaillé et les références de code.**

## 5.2 Pourquoi ce scénario est critique

Cette question paraît simple.

En réalité, il faut reconstruire l’évolution fonctionnelle depuis :

- commits ;
- branches ;
- Jira ;
- documentation ;
- code ;
- changements de structure.

## 5.3 Intent Flore

```text
HISTORICAL_ANALYSIS
+
REPORT
```

## 5.4 Scope

```text
Twin: TBT
Time: last 3 years
Output: functional features
Evidence requirement: code references
```

## 5.5 Workflow

```text
Resolve TBT
↓
Load historical index
↓
Cluster commits
↓
Link Jira
↓
Identify functional candidates
↓
Retrieve relevant code slices
↓
Functional Expert
↓
Evidence Auditor
↓
Synthesis
↓
Report
```

## 5.6 Anti-pattern à éviter

```text
3 years of repository
↓
send everything to LLM
```

## 5.7 Clustering

Exemple :

```text
42 commits
+
7 Jira issues
↓
Candidate Feature:
"Batch eligibility validation"
```

## 5.8 Feature object

```yaml
Feature:
  name: Batch Eligibility Validation
  introduced_at: 2025-03-14
  classification: BUSINESS_FEATURE
  confidence: 0.89
  jira_refs:
    - TBT-1842
    - TBT-1910
  code_refs:
    - BatchEligibilityHandler.java:88-147
    - EligibilityClient.java:32-71
```

## 5.9 Distinction technique/fonctionnelle

Méridian doit séparer :

```text
Business Feature
Functional Change
Technical Refactor
Platform Upgrade
Unknown
```

## 5.10 Report UX

Le rapport final contient :

1. Executive Summary
2. Feature Timeline
3. Feature Cards
4. Evidence
5. Code References
6. Confidence
7. Uncertain Items
8. Source Coverage

## 5.11 Progress UX

Pendant l’analyse :

```text
✓ 2,841 commits indexed
✓ 219 candidate changes
✓ 41 Jira clusters
● Functional interpretation
○ Evidence validation
○ Final report
```

## 5.12 Résultats partiels

Flore peut déjà afficher :

> 3 fonctionnalités sont confirmées.

avant completion.

## 5.13 Critères de succès

- traitement durable ;
- reprise après interruption ;
- pas de scan LLM global ;
- code refs précises ;
- classification feature/refactor ;
- Evidence ;
- report reproductible ;
- coût traçable.

## 5.14 Valeur bancaire

Réduit potentiellement :

- jours de reverse engineering ;
- dépendance aux anciens développeurs ;
- ambiguïtés dans les modernisations ;
- erreurs dans l’analyse d’impact.

---

# 6. Scénario 3 — Que se passerait-il si TBT était retiré ?

## 6.1 Question stratégique

> **Que se passerait-il si la banque retirait TBT dans 18 mois ?**

## 6.2 Type

```text
IMPACT_ANALYSIS
+
MODERNIZATION
+
STRATEGIC_OPTION
```

## 6.3 Trigger

Programme de modernisation du patrimoine applicatif.

## 6.4 Baseline

Méridian rassemble :

- consommateurs ;
- appels ;
- données ;
- processus ;
- capacités ;
- équipes ;
- incidents ;
- coûts ;
- changements.

## 6.5 Mesh traversal

```text
TBT
├── EligibilityService
├── BatchSettlement
├── AdvisorPortal
└── LegacyRules

TBT
SUPPORTS
Batch Transaction Validation

Batch Transaction Validation
PART_OF
Operations Process
```

## 6.6 Hypothèses

```text
H1
Most TBT capabilities can be replaced by existing services.

H2
Hidden batch consumers make retirement high-risk.

H3
The largest risk is not technical but operational.
```

## 6.7 Expert Team

```text
Architecture Expert
Code Expert
Data Expert
Process Expert
Operations Expert
Risk Expert
Finance Expert
Contradictor
```

## 6.8 Architecture Expert

Analyse :

- direct dependencies ;
- transitive dependencies ;
- API contracts ;
- replacement candidates.

## 6.9 Process Expert

Analyse :

- steps supported ;
- manual fallback ;
- business handoffs.

## 6.10 Risk Expert

Analyse :

- criticality ;
- failure modes ;
- unknown consumers ;
- regulatory exposure if applicable.

## 6.11 Contradictor

Recherche :

- consommateurs absents de CMDB ;
- flows uniquement batch ;
- dépendances saisonnières ;
- old integrations.

## 6.12 Finding important

Méridian découvre :

> un processus batch mensuel utilise encore TBT mais n’apparaît pas dans la CMDB.

## 6.13 Expression

> **Le retrait de TBT est techniquement possible, mais l’incertitude sur les consommateurs batch rend un retrait direct risqué.**

## 6.14 Scénarios

### Scenario A — Big Bang Replacement

Avantage :

- retrait rapide.

Risque :

- élevé.

### Scenario B — Progressive Decomposition

Avantage :

- apprentissage progressif ;
- réversibilité.

Risque :

- durée plus longue.

### Scenario C — Retain & Modernize

Avantage :

- plus faible changement initial.

Risque :

- prolongation du legacy.

## 6.15 Decision Board

Comparaison :

```text
Value
Risk
Cost
Time
Reversibility
Operational Impact
Customer Impact
Confidence
```

## 6.16 Décision

Le comité choisit :

> Progressive Decomposition.

## 6.17 Expected Outcomes

```text
Legacy dependency -40%
Batch risk reduced
No customer regression
```

## 6.18 Learning futur

Après première phase :

> consommateurs batch historiques doivent être cartographiés avant chaque retrait de capability.

## 6.19 Valeur bancaire

Aide à éviter :

- retrait prématuré ;
- dépendance cachée ;
- sous-estimation d’impacts ;
- migrations fondées sur documentation obsolète.

---

# 7. Scénario 4 — Incident après changement

## 7.1 Trigger

Après un déploiement du service EligibilityService :

```text
latency +35%
retries +60%
customer journey duration +18%
```

## 7.2 Sources

```text
Datadog
GitHub
Deployment events
ServiceNow
Splunk
```

## 7.3 Signal Detection

```text
SIG-101 latency anomaly
SIG-102 retry anomaly
SIG-103 journey duration anomaly
SIG-104 recent deployment
```

## 7.4 Correlation

Le Situation Correlator détecte :

- même fenêtre temporelle ;
- même dépendance ;
- même parcours.

## 7.5 Situation

> **Dégradation du parcours de renouvellement après changement d’EligibilityService.**

## 7.6 Maturity

Au début :

```text
evidence 0.54
causal 0.31
impact 0.82
```

Le sujet est important mais la cause n’est pas encore connue.

## 7.7 Flore

Utilisateur :

> **Pourquoi cette situation apparaît-elle ?**

Flore répond :

> La proximité temporelle avec le déploiement est forte, mais Méridian ne dispose pas encore d’assez de preuves pour conclure à une causalité.

## 7.8 Investigation

Hypothèses :

```text
H1 deployment regression
H2 traffic increase
H3 downstream database latency
H4 new business validation path
```

## 7.9 Experts

```text
Observability
Performance
Architecture
Change
Contradictor
```

## 7.10 Evidence

FOR H1 :

- deployment at 14:02 ;
- latency rise at 14:07 ;
- new call path.

AGAINST H1 :

- same deployment worked in test ;
- some traffic increase exists.

## 7.11 Contradiction

Le Contradictor montre que :

> le trafic a augmenté de 9 %, mais cela n’explique pas l’augmentation de 35 % de latence.

## 7.12 Synthesis

Conclusion :

> La cause la plus plausible est l’activation d’un nouveau chemin de validation synchrone introduit par le déploiement.

## 7.13 Scénarios opérationnels

```text
A rollback
B feature flag disable
C hotfix async validation
D capacity scale only
```

## 7.14 Decision

Feature flag disable temporaire.

## 7.15 Outcome

```text
latency -31%
retry -55%
journey duration back near baseline
```

## 7.16 Learning

> La validation synchrone doit être testée sous charge de parcours complet, pas seulement au niveau service.

## 7.17 Valeur bancaire

Réduit :

- MTTR ;
- réunions ad hoc ;
- diagnostic silo ;
- confusion entre corrélation et causalité.

---

# 8. Scénario 5 — Opportunité de rationalisation applicative

## 8.1 Trigger

Méridian observe progressivement :

```text
usage Application A ↓
maintenance cost high
capability overlap with Platform B
few unique consumers
```

Aucun incident.

## 8.2 Pourquoi ce scénario est important

Il démontre que Méridian n’est pas un produit d’incidents.

## 8.3 Signals

```text
low usage trend
capability overlap
high maintenance ratio
consumer count decline
```

## 8.4 Situation

> **Une application semble perdre progressivement ses capacités uniques.**

## 8.5 Maturation

Sur plusieurs semaines.

Sources :

- runtime ;
- CMDB ;
- cost ;
- Claims ;
- portfolio data.

## 8.6 Experts

```text
Architecture
Business Capability
Finance
Operations
Contradictor
```

## 8.7 Opportunity

> **Possibilité de rationaliser Application A au profit de Platform B.**

## 8.8 Value Dimensions

```text
Cost
Maintenance effort
Operational complexity
Architecture simplification
Risk
```

## 8.9 Unknown

> Deux consommateurs historiques ne sont pas suffisamment documentés.

## 8.10 Investigation

Questions :

- les consumers peuvent-ils migrer ?
- les règles métier sont-elles identiques ?
- quelle fonctionnalité reste réellement unique ?

## 8.11 Scénarios

```text
Retire
Merge capabilities
Freeze / maintain
Partial retirement
```

## 8.12 Decision

Pilot partial retirement.

## 8.13 Outcome

Mesurer :

- incidents ;
- coûts ;
- customer impact ;
- manual fallback.

## 8.14 Learning

> Rationalisation réussie lorsque les capacités sont comparées au niveau métier, pas uniquement via les APIs.

## 8.15 Valeur bancaire

Permet de transformer :

> patrimoine applicatif

en :

> portefeuille de capacités réellement comprises.

---

# 9. Scénario 6 — Friction client dans un parcours hypothécaire

## 9.1 Trigger

Le Product Owner observe :

```text
abandonment +7%
contact-center calls +11%
journey duration +14%
```

## 9.2 Sources

```text
Journey analytics
CRM
Contact Center
Datadog
Jira
Application Claims
```

## 9.3 Situation

> **Friction émergente dans le parcours de renouvellement hypothécaire.**

## 9.4 Mesh Context

```text
MortgageJourney
↓
AdvisorPortal
↓
EligibilityService
↓
DocumentVault
```

## 9.5 Hypothèses

```text
H1 document upload friction
H2 eligibility delay
H3 customer messaging unclear
H4 additional advisor validation
```

## 9.6 Expert Team

```text
Customer Journey Expert
Process Expert
Application Expert
Product Expert
Operations Expert
Contradictor
```

## 9.7 Customer Journey Expert

Relie :

- abandon ;
- wait time ;
- channel switching ;
- contacts.

## 9.8 Process Expert

Découvre :

> une validation manuelle a été ajoutée récemment pour certains dossiers.

## 9.9 Application Expert

Confirme :

> le changement a créé un nouvel appel synchrone vers EligibilityService.

## 9.10 Product Expert

Découvre :

> la communication client n’a pas été modifiée pour refléter l’étape supplémentaire.

## 9.11 Synthesis

La friction n’a pas une cause unique.

Elle combine :

- délai technique ;
- étape manuelle ;
- manque d’information client.

## 9.12 Scénarios

### A — Performance only

Optimiser service.

### B — Process only

Automatiser validation.

### C — End-to-end redesign

Performance + process + communication.

## 9.13 Decision

Pilot Scenario C sur segment contrôlé.

## 9.14 Expected Outcomes

```text
duration -15%
abandon -8%
calls -10%
manual work -12%
```

## 9.15 Outcome

Exemple :

```text
duration -12%
abandon -6%
calls -8%
manual work -9%
```

## 9.16 Learning

> Une friction client peut être systémique et ne doit pas être attribuée uniquement au canal visible.

## 9.17 Valeur bancaire

Méridian relie :

```text
client
↔ process
↔ employee
↔ application
```

C’est un cas emblématique du dépassement de la seule vision TI.

---

# 10. Scénario 7 — Friction employé et charge opérationnelle cachée

## 10.1 Trigger

Méridian observe :

```text
manual corrections rising
tickets rising
application switching rising
processing time stable
```

Le client ne voit pas encore de dégradation majeure.

## 10.2 Situation

> **La performance client reste stable, mais la charge opérationnelle semble augmenter.**

## 10.3 Pourquoi ce cas est stratégique

Une optimisation peut masquer un coût humain.

## 10.4 Sources

```text
Process events
ServiceNow
Operational KPIs
Application usage
Documentation
```

## 10.5 Expert Team

```text
Employee Experience Expert
Process Expert
Operations Expert
Architecture Expert
```

## 10.6 Finding

Le Process Expert identifie :

> un contrôle supprimé dans le parcours digital est maintenant réalisé manuellement en back-office.

## 10.7 Claim

```text
Digital Process Change
SHIFTS_WORK_TO
Operations Team
```

## 10.8 Opportunity

> **Automatiser le contrôle déplacé vers les opérations.**

## 10.9 Guardrail

Méridian ne note pas les employés.

Il analyse :

- travail ;
- flux ;
- étapes ;
- charge.

## 10.10 Decision

Automatiser le contrôle sous certaines conditions.

## 10.11 Outcome

```text
manual corrections -18%
processing time -7%
customer impact neutral/positive
```

## 10.12 Learning

> Une amélioration digitale doit toujours être observée également du point de vue opérationnel.

---

# 11. Scénario 8 — Domain Drift : structure réelle vs BCM déclaré

## 11.1 Trigger

Sur plusieurs mois, le Mesh observe :

```text
new cross-domain dependencies
shared APIs
shared data
shared teams
```

qui ne correspondent plus au modèle de domaine déclaré.

## 11.2 Atlas

Deux couches :

```text
Declared
Observed
```

## 11.3 Declared Model

```text
Mortgage
Payments
Customer
```

## 11.4 Observed Model

Un cluster émergent apparaît autour :

```text
Eligibility
Risk Decisioning
Customer Verification
```

## 11.5 Signal

```text
domain topology drift
```

## 11.6 Situation

> **Le fonctionnement observé diverge progressivement de l’architecture de domaine déclarée.**

## 11.7 Expert Team

```text
Enterprise Architecture Expert
Domain Architect Expert
Process Expert
Data Expert
Contradictor
```

## 11.8 Hypothèses

```text
H1 declared model is stale
H2 shared platform creates legitimate cross-domain topology
H3 responsibilities have shifted organizationally
```

## 11.9 Investigation

Méridian analyse :

- ownership ;
- dependencies ;
- change history ;
- capabilities ;
- processes.

## 11.10 Result

Le modèle officiel n’est pas totalement faux.

Mais un sous-domaine observé :

> **Decisioning**

semble émerger réellement.

## 11.11 Recommendation

Ne pas remplacer automatiquement le BCM.

Proposer :

> revue architecturale du domaine émergent.

## 11.12 Decision

Créer un domaine proposé en statut :

```text
PROPOSED
```

puis validation humaine.

## 11.13 Learning

> La topologie d’un système peut évoluer plus vite que sa taxonomie organisationnelle.

## 11.14 Valeur bancaire

Méridian devient un outil de :

- découverte organisationnelle ;
- architecture réelle ;
- alignement capability/system/team.

---

# 12. Scénario 9 — Changement réglementaire / politique métier transverse

## 12.1 Trigger

Une nouvelle exigence interne ou réglementaire impose de modifier une règle d’admissibilité ou de contrôle.

## 12.2 Question

> **Quels systèmes, processus et parcours seraient affectés par la modification de cette règle ?**

## 12.3 Sources

```text
Policy documents
Confluence
Code
Business Rules
Process models
CMDB
Jira
```

## 12.4 Rule Claim

```text
RULE-X
APPLIES_TO
Mortgage Renewal
```

## 12.5 Mesh traversal

Méridian retrouve :

```text
Rule
↓
EligibilityService
↓
TBT
↓
AdvisorPortal
↓
MortgageJourney
```

## 12.6 Investigation

Questions :

- où la règle est-elle implémentée ?
- existe-t-elle en double ?
- quelles exceptions ?
- quels tests ?
- quels segments ?
- quels impacts opérationnels ?

## 12.7 Experts

```text
Business Rule Expert
Compliance Expert
Code Expert
Process Expert
Risk Expert
```

## 12.8 Finding

La même règle est implémentée dans :

- EligibilityService ;
- LegacyRules ;
- une étape batch historique.

## 12.9 Risk

> Modification partielle pourrait créer des décisions incohérentes selon le canal.

## 12.10 Scenarios

```text
A modify all implementations independently
B centralize rule
C temporary compatibility layer
```

## 12.11 Decision

Choisir approche centralisée progressive.

## 12.12 Outcome

Mesurer :

- inconsistencies ;
- processing time ;
- manual exceptions ;
- incident rate.

## 12.13 Learning

> Les règles critiques doivent être modélisées comme des connaissances transverses, pas comme du code appartenant à une seule application.

---

# 13. Scénario 10 — Détection d’un risque de résilience inter-applications

## 13.1 Trigger

Le Mesh observe :

```text
12 applications
↓
same downstream service
```

sans mécanisme de fallback connu.

## 13.2 Situation

> **Concentration de dépendance sur un service unique.**

## 13.3 Sources

```text
runtime traces
code dependencies
CMDB
architecture docs
incident history
```

## 13.4 Claims

```text
APP-A DEPENDS_ON SERVICE-X
APP-B DEPENDS_ON SERVICE-X
...
SERVICE-X HAS_NO_CONFIRMED_FALLBACK
```

## 13.5 Unknown

> capacité de reprise réelle de SERVICE-X non confirmée.

## 13.6 Risk

```text
single point of failure
```

## 13.7 Risk Expert

Évalue :

- exposure ;
- criticality ;
- propagation radius ;
- historical incidents.

## 13.8 Atlas

Le service central apparaît comme un nœud de concentration.

## 13.9 Scenarios

```text
A add redundancy
B reduce dependency
C introduce circuit/fallback
D accept risk temporarily
```

## 13.10 Decision

Programme de résilience priorisé.

## 13.11 Outcome

```text
blast radius reduced
recovery improved
```

## 13.12 Learning

> Criticality should consider graph concentration, not only individual application tiering.

---

# 14. Scénario 11 — Données : dérive de schéma et impact caché

## 14.1 Trigger

Un changement de schéma est détecté dans une base partagée.

## 14.2 Observation

```text
column renamed
nullable constraint changed
```

## 14.3 Mesh Context

Plusieurs applications lisent cette table.

Certaines ne sont pas déclarées comme consommatrices.

## 14.4 Signal

```text
data contract change
```

## 14.5 Investigation

Experts :

```text
Database Expert
Data Expert
Code Expert
Architecture Expert
```

## 14.6 Finding

Deux consommateurs utilisent encore l’ancien champ via accès SQL direct.

## 14.7 Risk

> Déploiement pourrait provoquer une panne silencieuse de batch.

## 14.8 Decision

Créer phase de compatibilité.

## 14.9 Outcome

Aucun incident.

## 14.10 Learning

> Les dépendances data directes doivent être intégrées au Mesh au même niveau que les APIs.

---

# 15. Scénario 12 — Décision stratégique de modernisation d’un domaine

## 15.1 Trigger

La banque souhaite moderniser un domaine complet, par exemple :

> **Payments**

## 15.2 Question

> **Quelle trajectoire de modernisation minimise le risque tout en réduisant la complexité ?**

## 15.3 Scope

```text
20 applications
8 databases
several batch flows
3 critical customer journeys
multiple teams
```

## 15.4 Baseline

Méridian synthétise :

- architecture ;
- capabilities ;
- technical debt ;
- incidents ;
- cost ;
- change velocity ;
- dependencies ;
- business criticality.

## 15.5 Expert Team

```text
Enterprise Architecture
Payments Domain
Data
Operations
Risk
Finance
Transformation
Contradictor
```

## 15.6 Findings

Exemple :

- 4 applications partagent la même capability ;
- 2 bases dupliquent des données ;
- un batch central limite la migration ;
- une application legacy concentre 6 dépendances.

## 15.7 Scenarios

### A — Platform consolidation

### B — Capability-by-capability decomposition

### C — Journey-first modernization

### D — Selective modernization

## 15.8 Decision Board

Les scénarios sont comparés sur :

```text
Business value
Customer impact
Risk
Migration effort
Cost
Time
Reversibility
Organizational impact
Architecture simplification
```

## 15.9 Decision

Par exemple :

> Journey-first pour le parcours paiement client, puis capability decomposition.

## 15.10 Initiative Portfolio

Plusieurs initiatives peuvent être liées à la même Decision stratégique.

## 15.11 Outcome

Observations sur 6-18 mois.

## 15.12 Transformation Memory

Chaque phase devient un Transformation Episode.

## 15.13 Learning

Méridian apprend :

- quels patterns fonctionnent ;
- quels risques se répètent ;
- quelles dépendances sont systématiquement sous-estimées.

## 15.14 Valeur bancaire

C’est le cas où Méridian devient :

> **système d’exploitation cognitif de la transformation**, et non simplement moteur d’analyse applicative.

---

# 16. Scénario 13 — Écart entre ownership déclaré et ownership réel

## 16.1 Trigger

CMDB :

```text
Application X → Team A
```

Mais observations :

```text
80% commits Team B
70% incidents handled Team B
Jira ownership mostly Team B
```

## 16.2 Situation

> **Ownership déclaré et fonctionnement opérationnel divergent.**

## 16.3 Expert

```text
Organization / Process Expert
Architecture Expert
```

## 16.4 Hypothèses

```text
H1 CMDB stale
H2 Team B temporary support
H3 ownership has informally shifted
```

## 16.5 Decision

Ne pas changer automatiquement la CMDB.

Proposer :

> validation humaine.

## 16.6 Learning

> organisation réelle et organisation déclarée doivent être deux représentations comparables, pas une seule vérité.

---

# 17. Scénario 14 — Changement qui améliore un KPI mais détériore le système global

## 17.1 Trigger

Une équipe optimise un service.

Résultat :

```text
service latency -25%
```

Mais :

```text
downstream retries +20%
manual exceptions +9%
```

## 17.2 Outcome Evaluation

Méridian constate :

> optimisation locale positive, impact global négatif.

## 17.3 Side Effect Detector

Analyse :

- neighbors ;
- process ;
- operations.

## 17.4 Learning

> Les optimisations doivent être évaluées au niveau du processus ou parcours, pas uniquement du composant.

## 17.5 Opportunity

Créer une opportunité :

> optimiser le flux end-to-end.

---

# 18. Scénario 15 — Décision historique à revisiter

## 18.1 Trigger

Flore reçoit :

> **Pourquoi avions-nous conservé Application Z il y a deux ans ?**

## 18.2 Transformation Memory

Méridian retrouve :

```text
Investigation
Scenarios
Decision
Rationale
Expected Outcomes
Outcome
Learning
```

## 18.3 Réponse

Flore explique :

- contexte historique ;
- contraintes de l’époque ;
- scénario choisi ;
- risques acceptés ;
- résultats observés.

## 18.4 Question suivante

> **Ces raisons sont-elles encore valables aujourd’hui ?**

## 18.5 New Investigation

Méridian compare :

```text
Then
vs
Now
```

## 18.6 Opportunity

La décision historique peut devenir obsolète.

## 18.7 Valeur

Réduit le phénomène :

> **“on a toujours fait comme ça”**

en exposant le raisonnement historique réel.

---

# 19. Scénario 16 — Nouveau collaborateur : comprendre une application critique

## 19.1 Trigger

Un nouveau développeur ou architecte rejoint une équipe.

## 19.2 Questions

> À quoi sert TBT ?

> Quels sont ses voisins ?

> Quelles parties sont risquées à modifier ?

> Quelles règles métier importantes sont implémentées ici ?

> Quels changements récents dois-je connaître ?

## 19.3 Flore

Construit un parcours d’onboarding contextualisé.

## 19.4 Sources

Twin + Claims + history + Learnings.

## 19.5 Outcome

Réduction du temps d’onboarding.

## 19.6 Guardrail

Flore expose Unknowns et confidence.

---

# 20. Scénario 17 — Product Owner : comprendre l’impact d’un besoin métier

## 20.1 Trigger

Nouveau besoin :

> ajouter une option de traitement prioritaire pour certains dossiers.

## 20.2 Question

> **Qu’est-ce que cela implique réellement ?**

## 20.3 Mesh impact

Méridian relie :

```text
Capability
↓
Process
↓
Applications
↓
Data
↓
Customer Journey
↓
Operations
```

## 20.4 Experts

```text
Business
Process
Architecture
Data
Customer
```

## 20.5 Output

- systems impacted ;
- rules ;
- customer consequences ;
- operational changes ;
- unknowns.

## 20.6 Scenario

Possibilité de :

```text
modify existing flow
create dedicated path
reuse existing capability
```

## 20.7 Valeur

Méridian intervient **avant même que le besoin devienne une solution technique**.

C’est un point essentiel de l’évolution du produit.

---

# 21. Scénario 18 — Méridian découvre une opportunité sans requête humaine

## 21.1 Trigger

Aucune question utilisateur.

Méridian observe sur plusieurs semaines :

```text
three teams
perform similar validation
in different tools
with similar rules
```

## 21.2 Situation

> **Duplication de capacité de validation.**

## 21.3 Maturation

Cross-check :

- process ;
- code ;
- rules ;
- teams ;
- volume.

## 21.4 Opportunity

> **Possibilité de mutualiser une capacité de validation commune.**

## 21.5 Why now

Méridian explique :

> Le niveau de confiance a augmenté après confirmation par trois domaines et observation de règles équivalentes.

## 21.6 Human Action

Un architecte lance une Investigation.

## 21.7 Strategic value

C’est le scénario qui démontre que Méridian peut produire :

> **de l’intelligence nouvelle**, et pas seulement répondre.

---

# 22. Scénario 19 — Une opportunité est rejetée, puis revient plus tard

## 22.1 Initial Opportunity

Retirer Application A.

## 22.2 Decision

Rejected.

Raison :

> dépendance critique non remplaçable.

## 22.3 Six mois plus tard

Nouvelle plateforme déployée.

Claim :

```text
Capability X now available elsewhere
```

## 22.4 Discovery Engine

Réactive l’Opportunity.

## 22.5 Flore

> **Cette opportunité avait été rejetée il y a six mois. La contrainte principale n’existe plus.**

## 22.6 Value

Méridian se comporte comme un système de mémoire active.

---

# 23. Scénario 20 — Incident récurrent reconnu par mémoire de transformation

## 23.1 Trigger

Nouveau incident.

## 23.2 Similarity search

Méridian trouve deux incidents historiques proches.

## 23.3 Flore

> Deux épisodes similaires avaient pour cause une saturation du même pool de connexions.

## 23.4 Guardrail

Elle ajoute :

> Cette similarité ne confirme pas la cause actuelle.

## 23.5 Investigation

L’hypothèse historique est testée.

## 23.6 Outcome

Si confirmée :

Learning strengthened.

Si non :

Learning scope reduced.

---

# 24. Scénario transverse — Cycle complet d’une Opportunity

Ce scénario synthétise toute la mécanique.

```text
Observation
↓
Signal
↓
Situation
↓
Maturation
↓
Expression
↓
Opportunity
↓
Investigation
↓
Hypotheses
↓
Experts
↓
Scenarios
↓
Decision
↓
Initiative
↓
Outcome
↓
Learning
↓
New Opportunity
```

---

# 25. Modèle de scénario standardisé

Tous les scénarios produit futurs devraient être décrits selon le template suivant.

```yaml
Scenario:
  id:
  title:
  business_context:
  actors:
  trigger:
  user_question:
  scope:
  sources:
  observations:
  claims:
  unknowns:
  contradictions:
  mesh_context:
  signals:
  situation:
  experts:
  hypotheses:
  investigation:
  scenarios:
  decision:
  expected_outcomes:
  observed_outcomes:
  learnings:
  UX_surfaces:
  acceptance_criteria:
  product_metrics:
```

---

# 26. Scénarios par profil

## Direction / stratégie

Scénarios prioritaires :

```text
Rationalization Opportunity
Strategic Domain Modernization
Historical Decision Review
Outcome / Learning
Opportunity Reactivation
```

## Métier / Product Owner

```text
Customer Friction
Business Need Impact
Rule Change
Capability Duplication
Opportunity Discovery
```

## Expérience client

```text
Mortgage Journey Friction
Channel inconsistency
Customer-impact Outcome
```

## Employé / opérations

```text
Work Displacement
Manual Rework
Incident context
Operational side effects
```

## Risk / Compliance

```text
Rule Change
Resilience Concentration
Control inconsistency
Decision risk
```

## Finance / portefeuille

```text
Rationalization
Cost / usage mismatch
Realized value
Strategic investment review
```

## Data

```text
Schema drift
Data dependency
Rule/data lineage
```

## Architecture / TI

```text
Twin Birth
Historical Feature Reconstruction
TBT Retirement
Domain Drift
Resilience
```

## Transformation

```text
Decision
Initiative
Outcome
Learning
Transformation Memory
```

Aucun profil n’est considéré comme « principal » par nature ; la priorité dépend du problème à résoudre.

---

# 27. Scénarios par capacité produit

## Twin Intelligence

- Scénario 1
- Scénario 16

## Historical Intelligence

- Scénario 2
- Scénario 15

## Mesh

- Scénario 3
- Scénario 8
- Scénario 10
- Scénario 11

## Discovery

- Scénario 4
- Scénario 5
- Scénario 18
- Scénario 19

## Investigation

- Scénario 3
- Scénario 4
- Scénario 6
- Scénario 9

## Continuous Improvement

- Scénario 7
- Scénario 14
- Scénario 20

---

# 28. Scénarios pour la QA

Chaque scénario doit posséder :

- dataset de test ;
- expected Claims ;
- expected Evidence ;
- expected Unknowns ;
- expected UI state ;
- expected policy behavior.

---

# 29. Golden Scenario Dataset

Exemple :

```text
GS-01 TBT Birth
GS-02 TBT 3-Year Features
GS-03 TBT Retirement
GS-04 Eligibility Incident
GS-05 Rationalization Opportunity
GS-06 Mortgage Customer Friction
GS-07 Operations Work Shift
GS-08 Domain Drift
GS-09 Rule Change
GS-10 Resilience Concentration
```

---

# 30. AI Evaluation per Scenario

Pour chaque Golden Scenario, mesurer :

```text
Entity resolution accuracy
Claim correctness
Evidence correctness
Tool selection
Unknown recognition
Hypothesis diversity
Contradiction quality
Scenario quality
Confidence calibration
```

---

# 31. Product Evaluation per Scenario

Mesurer :

```text
time to insight
time to evidence
time to investigation
time to decision
user usefulness
```

---

# 32. Demo Tiering

## Demo courte — 5 à 10 min

Utiliser :

```text
Twin birth
Flore question
Atlas
Opportunity/Incident
Investigation
Decision
```

## Demo détaillée — 20 à 30 min

Ajouter :

```text
historical report
Evidence
contradiction
Outcome
Learning
```

## Workshop — 60 min

Faire jouer un scénario complet avec interaction utilisateur.

---

# 33. Scénario de démo recommandé pour un jury bancaire

Le meilleur scénario n’est pas un incident pur.

Il doit montrer :

1. compréhension ;
2. découverte ;
3. transversalité ;
4. décision.

Proposition :

```text
TBT twin exists
↓
Flore historical question
↓
Atlas reveals new dependency
↓
Situation emerges
↓
Opportunity / Risk
↓
Investigation
↓
Experts
↓
Decision
```

---

# 34. Pourquoi ce scénario fonctionne

Il permet de démontrer :

- connaissance ;
- preuve ;
- Mesh ;
- IA ;
- UX ;
- valeur métier ;
- gouvernance.

Sans réduire Méridian à un outil d’observabilité.

---

# 35. Scénario exécutif idéal

Pour un comité de direction :

> Une application legacy coûte cher et paraît difficile à retirer.

Méridian :

- comprend ses capacités ;
- retrouve ses consommateurs ;
- révèle une dépendance cachée ;
- compare plusieurs stratégies ;
- expose le risque ;
- permet une décision ;
- mesure le résultat.

C’est immédiatement compréhensible.

---

# 36. Scénario métier idéal

Pour un Product Owner :

> Pourquoi ce parcours client se dégrade-t-il ?

Méridian relie :

```text
journey
process
applications
changes
operations
```

---

# 37. Scénario architecte idéal

> Notre architecture réelle correspond-elle encore à l’architecture déclarée ?

Atlas :

```text
Declared
vs
Observed
```

---

# 38. Scénario opérations idéal

> Cette amélioration technique a-t-elle déplacé la charge ailleurs ?

Expected vs Observed.

---

# 39. Scénario risque idéal

> Quel serait le blast radius si ce service devenait indisponible ?

Mesh + Risk.

---

# 40. Scénario apprentissage idéal

> Avons-nous déjà vécu une transformation similaire ?

Transformation Memory.

---

# 41. Métriques business potentielles

Selon le scénario :

```text
Time to understand
Time to impact analysis
Incident resolution time
Avoided rework
Architecture review effort
Change failure avoided
Manual analysis effort
Decision lead time
```

---

# 42. Valeur qualitative

Méridian améliore aussi :

- confiance ;
- continuité de connaissance ;
- alignement TI/métier ;
- qualité de discussion ;
- explicabilité des décisions.

---

# 42A. Modèle d’impact transverse obligatoire

Chaque Situation / Opportunity / Investigation importante devrait, lorsque pertinent, pouvoir présenter les impacts selon une grille commune :

```text
Business
Customer
Employee / Operations
Risk / Compliance
Financial
Data
Technology
Strategic
```

Exemple :

> Nouvelle validation dans le renouvellement hypothécaire.

### Business

Cycle plus long.

### Customer

Abandon en hausse.

### Employee

Rework back-office.

### Risk

Meilleure couverture d’un contrôle.

### Financial

Coût opérationnel supplémentaire.

### Technology

Nouvel appel synchrone.

Le rôle de Méridian est précisément d’éviter que chacune de ces lectures reste isolée.

---

# 43. Ce que ces scénarios démontrent collectivement

Ensemble, ils montrent que Méridian peut opérer à plusieurs niveaux.

```text
APPLICATION
↓
DOMAIN
↓
PROCESS
↓
CUSTOMER
↓
EMPLOYEE
↓
ENTERPRISE
```

---

# 44. Ce qu’ils prouvent sur la vision

Méridian n’est pas :

> un réseau de jumeaux pour visualiser l’architecture.

Il devient :

> **une couche d’intelligence d’exploitation qui transforme la connaissance vivante de l’entreprise en décisions et améliorations.**

---

# 45. Critères de qualité d’un scénario Méridian

Un bon scénario doit :

1. partir d’un problème réel ;
2. mobiliser plusieurs types de connaissance ;
3. exposer Evidence et Unknowns ;
4. montrer une valeur du Mesh ;
5. éviter une réponse purement LLM ;
6. aboutir à une action ou un apprentissage ;
7. conserver la décision humaine ;
8. être démontrable ;
9. être testable ;
10. produire une valeur identifiable.

---

# 46. Anti-patterns de scénarios

## Scénario purement technique

> « Montre-moi un graphe de classes. »

Trop faible comme histoire produit.

## Scénario purement chat

> « Pose une question à l’IA. »

Ne démontre pas le Mesh.

## Incident-only

Réduit Méridian à l’observabilité.

## Scenario without decision

Pas de valeur d’exploitation.

## Scenario without Evidence

Pas de confiance.

## Scenario impossible à mesurer

Difficile à valider.

---

# 47. Priorisation des scénarios pour MVP

Le MVP doit démontrer **deux axes**, et non une succession où tous les usages non-TI arrivent après la compréhension applicative.

## P0 — Fondation de connaissance

```text
Twin Birth
TBT 3-Year Features
Mesh / Evidence / Claims
```

## P0 — Exploitation transverse

Au moins un de :

```text
Customer Friction
Business Change Impact
Rule / Compliance Impact
Operational Work Displacement
```

## P1

```text
TBT Retirement
Rationalization Opportunity
Domain Drift
Resilience Concentration
Strategic Decision
```

## P2

```text
Transformation Memory
Strategic Domain Modernization
Recurring Incident Learning
Portfolio pattern discovery
```

Le MVP n’est donc pas validé si seuls les scénarios d’architecture et de code fonctionnent.

---

# 48. P0 Golden Path détaillé

Le MVP doit posséder **deux Golden Paths de même importance**.

## Golden Path A — profondeur de connaissance

```text
TBT connected
↓
Twin born
↓
Claims + Evidence
↓
Flore historical question
↓
Mesh shows neighbors
↓
Impact / Investigation
↓
Decision
```

## Golden Path B — exploitation entreprise

Exemple recommandé :

```text
Mortgage Journey abandonment
↓
Customer signals
↓
Process + Rule + Operations
↓
Application / Runtime context
↓
Situation
↓
Multi-expert Investigation
↓
Scenarios
↓
Business decision
↓
Expected vs Observed
```

Le deuxième chemin est indispensable pour démontrer que Méridian est **une plateforme d’intelligence d’entreprise**, pas seulement de Software Intelligence.

---

# 49. P1 Golden Path métier

```text
Customer friction
↓
Journey + Process + Application
↓
Opportunity
↓
Investigation
↓
End-to-end scenario
```

C’est la démonstration que Méridian sort du pur TI.

---

# 50. P2 Golden Path apprentissage

```text
Decision
↓
Outcome
↓
Side effect
↓
Learning
↓
Similar future situation
```

C’est la démonstration de l’entreprise apprenante.

---

# 51. Scenario Traceability Matrix

| Scenario | Twin | Claims | Mesh | Flore | Discovery | Experts | Decision | Learning |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Twin Birth | ✓ | ✓ | ✓ | ✓ |  |  |  |  |
| 3-Year Features | ✓ | ✓ |  | ✓ |  | ✓ |  |  |
| TBT Retirement | ✓ | ✓ | ✓ | ✓ |  | ✓ | ✓ | ✓ |
| Incident | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Rationalization | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Customer Friction | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Employee Friction | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Domain Drift | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |
| Rule Change | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Resilience Risk | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

---

# 52. UX Surface Matrix

| Scenario | Aujourd’hui | Atlas | Flore | Twin | Investigation | Decision | Memory |
|---|---:|---:|---:|---:|---:|---:|---:|
| Twin Birth |  | ✓ | ✓ | ✓ |  |  |  |
| Historical Features |  |  | ✓ | ✓ | ✓ |  | ✓ |
| TBT Retirement | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Incident | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Customer Friction | ✓ | ✓ | ✓ |  | ✓ | ✓ | ✓ |
| Domain Drift | ✓ | ✓ | ✓ |  | ✓ | ✓ | ✓ |

---

# 53. Architecture Validation Matrix

Les scénarios doivent valider au minimum :

```text
Source Connector
Artifact/Evidence
Claim Engine
Graph/Mesh
Search/Retrieval
Flore
Workflow
Expert Runtime
SSE
Security
Observability
```

---

# 54. Security Scenarios

Chaque use case doit également être exécuté avec :

```text
full access user
restricted user
cross-domain user
admin without content entitlement
```

pour vérifier le security trimming.

---

# 55. Example Security Test

Utilisateur sans accès au code :

Question :

> Pourquoi TBT dépend-il de X ?

Réponse possible :

> Méridian dispose de plusieurs preuves supportant cette relation. Une partie des preuves techniques est restreinte pour votre rôle.

Sans exposer le code.

---

# 56. Failure Scenario — Source unavailable

Pendant une Investigation :

```text
Datadog unavailable
```

Méridian doit :

- continuer avec knowledge existante ;
- marquer freshness ;
- réduire confidence ;
- ne pas échouer entièrement.

---

# 57. Failure Scenario — Contradiction unresolved

Decision Board doit afficher :

> **1 contradiction critique non résolue.**

---

# 58. Failure Scenario — Expert failure

L’Investigation reste durable.

Un Expert peut être relancé ou remplacé.

---

# 59. Failure Scenario — Job interrupted

Le rapport historique reprend depuis checkpoint.

---

# 60. Failure Scenario — Claim invalidated after Decision

Méridian doit :

- marquer la Decision comme basée sur une connaissance maintenant modifiée ;
- proposer review si la policy le prévoit.

---

# 61. Storytelling structure commune

Chaque scénario de présentation doit suivre :

### 1. Une tension

Quelque chose est difficile à comprendre.

### 2. Une découverte

Méridian révèle une relation ou connaissance.

### 3. Une maturation

Le système évite de conclure trop tôt.

### 4. Une investigation

Les Experts travaillent.

### 5. Un choix

Des scénarios sont comparés.

### 6. Une conséquence

Le résultat est observé.

---

# 62. Exemple de narration exécutive

> Une application existe depuis quinze ans. Tout le monde sait qu’elle est importante, mais personne ne sait précisément jusqu’où va son impact.

> Méridian ne commence pas par donner une réponse.

> Il reconstitue ce qu’elle fait, retrouve les dépendances, expose ce qu’il sait et ce qu’il ignore.

> Puis une dépendance non déclarée apparaît.

> Une investigation est ouverte.

> Plusieurs experts confrontent leurs hypothèses.

> Trois options de transformation émergent.

> Le décideur choisit.

> Quelques semaines plus tard, Méridian mesure le résultat.

> Et cette expérience devient une connaissance utilisable pour la prochaine transformation.

---

# 63. Product principle démontré

Cette narration contient toute la philosophie :

```text
Discover
Understand
Decide
Learn
```

---

# 64. Réutilisation du document

Ce document doit être utilisé pour :

## Product

Valider la valeur.

## Architecture

Valider les flows.

## UX

Concevoir les écrans.

## Backlog

Créer les Stories.

## QA

Construire les E2E tests.

## AI Evaluation

Créer les golden datasets.

## Demo

Construire les scripts.

---

# 65. Scenario Governance

Chaque scénario possède :

- owner ;
- version ;
- test dataset ;
- acceptance criteria ;
- last validated release.

---

# 66. Scenario Versioning

Exemple :

```text
SCN-TBT-RETIREMENT v1.0
```

---

# 67. Scenario Registry

```yaml
ScenarioRegistryEntry:
  id:
  title:
  owner:
  priority:
  capabilities:
  golden_dataset_ref:
  demo_ready:
  automated_test:
  last_validated_at:
```

---

# 68. Scenario Release Gate

Une release n’est pas prête si ses Golden Scenarios ne passent pas.

---

# 69. Example Release Gate R2

Doivent passer :

```text
Twin Birth
Flore Explain
Historical Features
Mesh Navigation
```

---

# 70. Example Release Gate R4

Doivent passer :

```text
Incident Investigation
TBT Retirement Investigation
Customer Friction Investigation
```

---

# 71. Example Release Gate R6

Doivent passer :

```text
Outcome
Learning
Similar Episode Retrieval
```

---

# 72. MVP Reference Scenario Set

Le set minimal de référence est :

```text
SCN-01 Twin Birth
SCN-02 TBT 3-Year Features
SCN-03 TBT Retirement
SCN-04 Incident after Change
SCN-05 Rationalization Opportunity
SCN-06 Investigation + Decision
```

---

# 73. Enterprise Reference Scenario Set

Après MVP :

```text
SCN-07 Customer Friction
SCN-08 Employee Friction
SCN-09 Domain Drift
SCN-10 Rule Change
SCN-11 Resilience Concentration
SCN-12 Strategic Modernization
SCN-13 Historical Decision Review
SCN-14 Recurring Incident Learning
```

---

# 74. Ultimate banking scenario

Le scénario ultime de Méridian n’est pas :

> « une banque comprend parfaitement toutes ses applications ».

Il est :

> **La banque peut observer un phénomène depuis n’importe quelle perspective — client, métier, employé, risque, finance, donnée ou technologie — et Méridian reconstruit le contexte partagé nécessaire pour le comprendre, décider et apprendre.**

Exemple :

```text
Customer abandonment rises
↓
Process friction emerges
↓
Operational workload shifts
↓
Application change is implicated
↓
Risk control explains part of the change
↓
Finance quantifies operational cost
↓
Investigation compares alternatives
↓
Human decision
↓
Outcome
↓
Learning
```

C’est la vision qui réunit tous les scénarios.

---

# 75. Conclusion

Les scénarios de référence confirment que le **Twin applicatif est une fondation, pas la frontière fonctionnelle de Méridian**.

L’exploitation réelle se déroule dans les relations entre :

```text
Business Capabilities
Processes
Customer Journeys
Employees / Operations
Applications
Data
Rules
Risks
Costs
Initiatives
Decisions
Outcomes
```

Le même phénomène doit pouvoir être exploré selon plusieurs projections.

Une hausse d’abandon, par exemple, peut être :

- une friction pour le responsable client ;
- un problème de processus pour le métier ;
- une charge de reprise pour les opérations ;
- un changement de règle pour le risque ;
- une dépendance pour l’architecte ;
- un coût pour la finance ;
- une décision à arbitrer pour la direction.

Méridian n’a pas à choisir laquelle est « la vraie ».

Il doit construire une compréhension cohérente de leurs relations.

La chaîne fondamentale devient :

```text
un fait
↓
une connaissance
↓
un phénomène transverse
↓
plusieurs perspectives
↓
une investigation
↓
une décision
↓
une conséquence
↓
un apprentissage
```

C’est ce qui fait passer Méridian de la **Software Intelligence** à une véritable **Enterprise Intelligence**.

---

# 76. Prochain document

Le prochain document recommandé est :

> **MÉRIDIAN — Product Strategy & Business Case**

Il devra transformer la vision produit et les scénarios de valeur en logique économique et stratégique :

- problème marché ;
- proposition de valeur ;
- utilisateurs ;
- buyers ;
- differentiation ;
- alternatives / concurrence ;
- bénéfices mesurables ;
- ROI ;
- adoption ;
- modèle de déploiement ;
- stratégie SaaS ;
- pricing hypotheses ;
- moat ;
- go-to-market ;
- risques ;
- business case bancaire.

Ce sera le document qui répondra clairement :

> **Pourquoi une grande banque devrait-elle financer, adopter et généraliser Méridian ?**
