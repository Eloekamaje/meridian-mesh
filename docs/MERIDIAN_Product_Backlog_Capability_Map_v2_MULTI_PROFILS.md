# MÉRIDIAN — Product Backlog & Capability Map
## Capabilities, Epics, Features, User Stories, Enablers, Dependencies, Priorities & Release Mapping

**Statut :** Backlog produit de référence  
**Version :** 2.0 — exploitation multi-profils  
**Produit :** MÉRIDIAN  
**Tagline :** **DÉCOUVRIR · COMPRENDRE · DÉCIDER**

---

# 0. Objet

Ce document transforme le **MVP Definition & Delivery Roadmap** en backlog exploitable par une équipe produit et technique.

Il organise le travail selon :

```text
Capability
  ↓
Epic
  ↓
Feature
  ↓
User Story / Technical Story
  ↓
Acceptance Criteria
```

Principe directeur :

> **Construire Méridian par vertical slices de valeur, jamais par couches techniques isolées.**

> **Le Twin applicatif est une fondation. Le backlog doit néanmoins produire très tôt des usages métier, client, employé, risque, finance, data et stratégie afin que la TI ne devienne pas la frontière implicite du produit.**

La progression cible est :

```text
R0 Platform
↓
R1 Know
↓
R2 Understand
↓
R3 Discover
↓
R4 Investigate
↓
R5 Decide
↓
R6 Learn
↓
R7 Productize
↓
R8 Enterprise / SaaS
```

---

# 1. Priorités

```text
P0 — indispensable au MVP
P1 — différenciation produit essentielle
P2 — productisation
P3 — scale / enterprise / SaaS
```

Le MVP strict doit démontrer :

> **Source → Twin → Evidence → Claim → Mesh → Flore → Situation → Investigation → Scenario → Decision**

avec une première preuve de :

> **Decision → Outcome → Learning**

---

# 2. Capability Map

```text
C01 Platform Foundation
C02 Identity, Security & Governance
C03 Source Connectivity
C04 Artifact & Evidence Management
C05 Code Intelligence
C06 Twin Intelligence
C07 Claims & Knowledge
C08 Mesh Intelligence
C09 Search & Retrieval
C10 Atlas
C11 Flore
C12 Jobs & Durable Workflows
C13 Discovery & Maturation
C14 Opportunities & Risks
C15 Investigation
C16 Expert Framework
C17 Scenarios & Decision
C18 Continuous Improvement
C19 Transformation Memory
C20 Observability, Evaluation & Cost
C21 Administration & Product Operations
C22 SaaS & Tenant Management
C23 Business Capability & Process Intelligence
C24 Customer & Employee Intelligence
C25 Risk, Compliance & Control Intelligence
C26 Finance, Portfolio & Strategic Intelligence
C27 Enterprise Perspectives & Role Projections
```

---

# 3. C01 — Platform Foundation

**Priorité : P0**  
**Release : R0**

## Epic C01-E01 — Application Skeleton

### Feature — Frontend Shell

**User Story**

En tant qu’utilisateur, je veux disposer d’une coquille Méridian cohérente afin de naviguer entre Atlas, Flore, Investigations et Decisions.

**Acceptance Criteria**

- top bar ;
- navigation gauche ;
- routing ;
- dark theme ;
- placeholder Atlas ;
- placeholder Flore ;
- erreurs globales ;
- responsive desktop.

### Feature — Backend Skeleton

**Technical Stories**

- BFF ;
- versioning API ;
- common error contract ;
- correlation IDs ;
- health endpoints ;
- configuration externalisée.

## Epic C01-E02 — CI/CD

Features :

- build ;
- tests ;
- containerisation ;
- déploiement DEV/TEST ;
- secret injection ;
- rollback.

## Epic C01-E03 — Shared Contracts

Tous les objets distribués portent :

```text
id
type
tenant_id
schema_version
created_at
correlation_id
```

---

# 4. C02 — Identity, Security & Governance

**Priorité : P0**  
**Release : R0→R2**

## Epic C02-E01 — Enterprise Authentication

- OIDC/SAML ;
- SSO ;
- session sécurisée ;
- groups mapping.

## Epic C02-E02 — Authorization

Rôles MVP :

```text
USER
ANALYST
INVESTIGATOR
DOMAIN_OWNER
ADMIN
```

ABAC minimal :

```text
tenant
domain
classification
environment
```

## Epic C02-E03 — Security Trimming

**Acceptance Criteria**

- filtrage avant retrieval ;
- Search filtré ;
- Graph filtré ;
- Flore filtrée ;
- aucun accès cross-tenant.

## Epic C02-E04 — Audit

Tracer :

- authentification ;
- Evidence access ;
- Claim changes ;
- Agent Runs ;
- Tool calls ;
- Decisions ;
- administration.

## Epic C02-E05 — Agent Security Context

Chaque Agent Run possède :

```text
expert
mission
delegated_user
tenant
scope
tools
sources
expiry
```

---

# 5. C03 — Source Connectivity

**Priorité : P0**  
**Release : R1**

## Epic C03-E01 — Source Model

```yaml
Source:
  id:
  type:
  owner:
  status:
  sync_policy:
  classification:
```

## Epic C03-E02 — GitHub Connector

Features :

- authentification ;
- repository metadata ;
- clone/fetch ;
- commits ;
- branches ;
- incremental cursor ;
- health.

## Epic C03-E03 — Jira Connector

Features :

- projects ;
- issues ;
- changelog ;
- links ;
- incremental synchronization.

## Epic C03-E04 — Datadog Connector

Features :

- service mapping ;
- metrics ;
- traces references ;
- events ;
- temporal query.

## Epic C03-E05 — Confluence Connector

**P1**

- spaces ;
- pages ;
- page versions ;
- links.

## Epic C03-E06 — CMDB Connector

**P1**

- application identity ;
- ownership ;
- declared relations ;
- lifecycle.

## Epic C03-E07 — Connector SPI

Contract :

```text
discover()
snapshot()
changesSince()
fetch()
health()
permissions()
```

---

# 6. C04 — Artifact & Evidence Management

**Priorité : P0**  
**Release : R1**

## Epic C04-E01 — Artifact Model

Chaque Artifact possède :

```text
source
version
content_hash
locator
observed_at
classification
```

## Epic C04-E02 — Evidence Model

Chaque Evidence :

- référence une version d’Artifact ;
- possède un locator stable ;
- conserve la classification ;
- peut supporter ou contredire un Claim.

## Epic C04-E03 — Evidence Retrieval

**User Story**

En tant qu’utilisateur, je veux ouvrir la preuve d’un Claim afin de vérifier l’affirmation.

Features :

- preview ;
- source metadata ;
- excerpt ;
- security ;
- related Claims.

## Epic C04-E04 — Evidence Integrity

- hash validation ;
- locator validation ;
- stale Evidence ;
- missing Artifact.

---

# 7. C05 — Code Intelligence

**Priorité : P0**  
**Release : R1→R2**

## Epic C05-E01 — Repository Intake

- language detection ;
- modules ;
- build systems ;
- repository metadata.

## Epic C05-E02 — Structural Extraction

Extraire :

```text
files
symbols
classes
functions
imports
calls
dependencies
```

## Epic C05-E03 — Code Graph

- symbol nodes ;
- call edges ;
- dependency edges ;
- module relations ;
- versioning.

## Epic C05-E04 — Incremental Analysis

**Acceptance Criteria**

Pour un commit :

```text
diff
↓
affected symbols
↓
affected graph
↓
affected Claim candidates
```

sans réanalyse complète du repository.

## Epic C05-E05 — Code Retrieval Tools

```text
find_symbol
find_references
get_callers
get_callees
retrieve_code_slice
get_commit_diff
```

## Epic C05-E06 — Historical Change Clustering

Regrouper :

- commits ;
- Jira issues ;
- temporal proximity ;
- semantic similarity.

## Epic C05-E07 — Feature Reconstruction

**User Story**

En tant qu’architecte, je veux reconstruire les fonctionnalités ajoutées à une application afin d’en comprendre l’évolution métier.

Acceptance Criteria :

- changement technique vs feature ;
- dates ;
- Jira refs ;
- code refs ;
- Evidence ;
- confidence.

---

# 8. C06 — Twin Intelligence

**Priorité : P0**  
**Release : R1**

## Epic C06-E01 — Twin Model

- identity ;
- aliases ;
- type ;
- owner ;
- source manifest ;
- status ;
- health.

## Epic C06-E02 — Twin Birth

Workflow :

```text
Identify
↓
Connect
↓
Discover
↓
Extract
↓
Build initial Claims
↓
Resolve neighbors
↓
Generate living summary
```

## Epic C06-E03 — Twin Summary

Doit synthétiser :

- rôle ;
- capacités ;
- structure ;
- contexte métier ;
- relations ;
- Unknowns.

## Epic C06-E04 — Knowledge Health

Dimensions :

```text
technical
business
freshness
history
unknowns
contradictions
```

## Epic C06-E05 — Twin Experience

Page :

- summary ;
- relations ;
- Claims ;
- Evidence ;
- timeline ;
- Unknowns ;
- contradictions.

---

# 9. C07 — Claims & Knowledge

**Priorité : P0**  
**Release : R1**

## Epic C07-E01 — Claim Model

```text
subject
predicate
object
qualifiers
scope
origin
status
confidence
maturity
valid_from
valid_to
evidence
```

## Epic C07-E02 — Claim Validation

```text
schema
→ entity resolution
→ duplicate detection
→ evidence validation
→ conflict detection
→ confidence
```

## Epic C07-E03 — Claim Versioning

Support :

```text
superseded
historical
contested
invalidated
```

## Epic C07-E04 — Confidence Engine

MVP :

- Evidence strength ;
- source diversity ;
- freshness ;
- contradiction.

## Epic C07-E05 — Unknown

**User Story**

En tant qu’utilisateur, je veux connaître les zones que Méridian ne comprend pas encore afin de ne pas confondre absence de preuve et certitude.

## Epic C07-E06 — Contradiction

- detection ;
- persistence ;
- status ;
- resolution.

## Epic C07-E07 — Provenance

```text
Claim
→ Evidence
→ Artifact
→ Source
```

plus :

```text
AgentRun
Expert
Model
```

si nécessaire.

---

# 10. C08 — Mesh Intelligence

**Priorité : P0/P1**  
**Release : R2**

## Epic C08-E01 — Entity Resolution

- canonical identity ;
- aliases ;
- external IDs ;
- candidate match ;
- confirmation.

## Epic C08-E02 — Relationship Builder

Types initiaux :

```text
CALLS
DEPENDS_ON
READS
WRITES
SUPPORTS
OWNED_BY
PART_OF
```

## Epic C08-E03 — Cross-Twin Reconciliation

- temporal alignment ;
- scope alignment ;
- Evidence comparison ;
- confidence ;
- contradiction.

## Epic C08-E04 — Declared vs Observed

**User Story**

En tant qu’architecte, je veux confronter la structure officielle à ce que Méridian observe réellement.

## Epic C08-E05 — Mesh Query Tools

```text
get_neighbors
find_path
find_dependencies
get_impact_radius
```

---

# 11. C09 — Search & Retrieval

**Priorité : P0**  
**Release : R2**

## Epic C09-E01 — Global Search

Recherche :

```text
Twin
Claim
Domain
Opportunity
Investigation
Decision
Learning
```

## Epic C09-E02 — Hybrid Retrieval

```text
keyword
+ vector
+ graph
+ temporal
+ security
```

## Epic C09-E03 — Retrieval Ranking

Inputs :

- semantic relevance ;
- graph proximity ;
- confidence ;
- freshness ;
- source authority.

## Epic C09-E04 — Context Pack Builder

Doit produire un contexte :

- borné ;
- pertinent ;
- security-trimmed ;
- fingerprinté ;
- Evidence-aware.

---

# 12. C10 — Atlas

**Priorité : P0**  
**Release : R2**

## Epic C10-E01 — Canvas

- pan ;
- zoom ;
- fit ;
- select ;
- hover ;
- context rail.

## Epic C10-E02 — Twin Nodes

States :

```text
normal
selected
risk
opportunity
unknown
muted
```

## Epic C10-E03 — Domain Membranes

Types :

```text
declared
observed
proposed
hybrid
```

## Epic C10-E04 — Relations

Afficher :

- direction ;
- type ;
- confidence ;
- provenance state.

## Epic C10-E05 — Semantic Zoom

```text
Enterprise
→ Domain
→ Cluster
→ Twin
→ Relation detail
```

## Epic C10-E06 — Lasso

Actions :

- compare ;
- investigate ;
- ask Flore.

## Epic C10-E07 — Temporal Atlas

**P2**

- time scrubber ;
- before/after ;
- replay.

---

# 13. C11 — Flore

**Priorité : P0**  
**Release : R2**

## Epic C11-E01 — Conversation Session

- thread ;
- active entities ;
- scope ;
- temporal context ;
- summary.

## Epic C11-E02 — Context Resolver

Résout :

- surface courante ;
- selected Twin ;
- Atlas selection ;
- prior references ;
- time.

## Epic C11-E03 — Intent Resolver

MVP :

```text
LOOKUP
EXPLAIN
SUMMARIZE
EXPLORE
HISTORICAL_ANALYSIS
INVESTIGATE
REPORT
```

## Epic C11-E04 — Capability Router

Route vers :

- Knowledge ;
- Graph ;
- Expert ;
- Workflow ;
- UI action.

## Epic C11-E05 — Evidence-aware Answers

Toute réponse factuelle importante doit pouvoir exposer :

- Claims ;
- Evidence ;
- confidence ;
- Unknowns ;
- contradictions.

## Epic C11-E06 — Contextual UI Actions

```text
FOCUS_ATLAS
OPEN_TWIN
OPEN_EVIDENCE
CREATE_INVESTIGATION
```

## Epic C11-E07 — Trust Panel

---

# 14. C12 — Jobs & Durable Workflows

**Priorité : P0**  
**Release : R0→R1**

## Epic C12-E01 — Job Model

States :

```text
ACCEPTED
QUEUED
RUNNING
PARTIAL
WAITING
COMPLETED
FAILED
CANCELLED
```

## Epic C12-E02 — Durable Execution

Support :

- checkpoints ;
- retry ;
- resume ;
- partial failure ;
- human wait.

## Epic C12-E03 — SSE Progress

- stage ;
- progress ;
- partial finding ;
- completion ;
- reconnect.

## Epic C12-E04 — Cancellation

## Epic C12-E05 — Budget Manager

Limites :

- tokens ;
- model calls ;
- tools ;
- duration ;
- cost.

---

# 15. C13 — Discovery & Maturation

**Priorité : P1**  
**Release : R3**

## Epic C13-E01 — Signal Model

MVP detectors :

```text
metric anomaly
deployment/change
graph change
Claim change
manual signal
```

## Epic C13-E02 — Signal Deduplication

Fingerprint + cooldown.

## Epic C13-E03 — Situation Correlator

MVP :

```text
time
entity
graph proximity
shared change
```

## Epic C13-E04 — Situation Lifecycle

```text
CANDIDATE
QUALIFYING
MATURING
MATURE
DISMISSED
```

## Epic C13-E05 — Maturity Engine

Dimensions :

- Evidence ;
- persistence ;
- source diversity ;
- impact.

## Epic C13-E06 — Expression Engine

**User Story**

En tant qu’utilisateur, je veux comprendre pourquoi un phénomène mérite mon attention maintenant.

## Epic C13-E07 — Attention Ranking

- impact ;
- confidence ;
- novelty ;
- relevance.

---

# 16. C14 — Opportunities & Risks

**Priorité : P1**  
**Release : R3**

## Epic C14-E01 — Opportunity Model

Fields :

- why now ;
- value ;
- confidence ;
- maturity ;
- scope.

## Epic C14-E02 — Opportunity Patterns

MVP :

```text
capability overlap
low usage/high cost
manual friction
duplication
```

## Epic C14-E03 — Risk Model

- probability ;
- impact ;
- exposure ;
- propagation.

## Epic C14-E04 — Opportunity Experience

## Epic C14-E05 — Risk Experience

---

# 17. C15 — Investigation

**Priorité : P0/P1**  
**Release : R4**

## Epic C15-E01 — Investigation Model

- question ;
- scope ;
- type ;
- state ;
- owner ;
- timeline.

## Epic C15-E02 — Contextual Intake

**User Story**

En tant qu’utilisateur, je veux ouvrir une Investigation depuis Flore, Atlas ou une Opportunity sans perdre le contexte existant.

## Epic C15-E03 — Scope

- Twins ;
- domains ;
- processes ;
- time ;
- business scope.

## Epic C15-E04 — Hypotheses

States :

```text
OPEN
TESTING
STRENGTHENED
WEAKENED
REJECTED
CONFIRMED
```

## Epic C15-E05 — Evidence Board

```text
FOR
AGAINST
UNKNOWN
```

## Epic C15-E06 — Contradiction Stage

Obligatoire pour investigations significatives.

## Epic C15-E07 — Synthesis

Expose :

- known ;
- probable ;
- contested ;
- unknown ;
- impacts.

## Epic C15-E08 — Investigation Workspace

---

# 18. C16 — Expert Framework

**Priorité : P0/P1**  
**Release : R4**

## Epic C16-E01 — Expert Registry

MVP :

```text
Code Expert
Architecture Expert
Observability Expert
Contradictor
Evidence Auditor
Synthesis Expert
```

## Epic C16-E02 — Expert Definition

Définit :

- competencies ;
- sources ;
- tools ;
- evidence policy ;
- model policy ;
- output schema.

## Epic C16-E03 — Expert Selector

MVP :

- rules ;
- semantic skill match.

## Epic C16-E04 — Expert Run

Persist :

- version ;
- mission ;
- model ;
- tools ;
- cost ;
- trace ;
- contribution.

## Epic C16-E05 — Parallel Specialists

## Epic C16-E06 — Contradictor

Recherche activement :

- counter-evidence ;
- alternative hypotheses ;
- temporal conflict ;
- scope conflict.

## Epic C16-E07 — Evidence Auditor

---

# 19. C17 — Scenarios & Decision

**Priorité : P1**  
**Release : R5**

## Epic C17-E01 — Scenario Model

```text
actions
assumptions
value
risk
cost
time
reversibility
confidence
```

## Epic C17-E02 — Scenario Generation

Humain + Experts.

## Epic C17-E03 — Scenario Critic

## Epic C17-E04 — Scenario Comparison

**User Story**

En tant que décideur, je veux comparer plusieurs options sur des dimensions communes afin de rendre les compromis visibles.

## Epic C17-E05 — Recommendation

Objet distinct de Decision.

## Epic C17-E06 — Decision

- selected scenario ;
- rejected scenarios ;
- rationale ;
- approvers ;
- expected outcomes.

## Epic C17-E07 — Decision Snapshot

Capture :

- Claims ;
- Evidence ;
- hypotheses ;
- scenarios ;
- Unknowns ;
- contradictions.

## Epic C17-E08 — Decision Board

---

# 20. C18 — Continuous Improvement

**Priorité : P1/P2**  
**Release : R6**

## Epic C18-E01 — Initiative

Tracking léger lié à la Decision.

## Epic C18-E02 — Observation Plan

- baseline ;
- metrics ;
- expected outcomes ;
- observation window.

## Epic C18-E03 — Outcome

Expected vs Observed.

## Epic C18-E04 — Side Effects

Réutilise Discovery autour du scope impacté.

## Epic C18-E05 — Learning Candidate

## Epic C18-E06 — Learning

- statement ;
- conditions ;
- confidence ;
- Evidence ;
- applicability.

---

# 21. C19 — Transformation Memory

**Priorité : P2**  
**Release : R6/R7**

## Epic C19-E01 — Transformation Episode

```text
Situation
→ Investigation
→ Decision
→ Initiative
→ Outcome
→ Learning
```

## Epic C19-E02 — Similar Episode Search

## Epic C19-E03 — Pattern Discovery

**P3**

## Epic C19-E04 — Transformation Memory UI

---

# 22. C20 — Observability, Evaluation & Cost

**Priorité : P0**  
**Release : toutes**

## Epic C20-E01 — Platform Telemetry

- logs ;
- metrics ;
- traces.

## Epic C20-E02 — Cognitive Telemetry

- Claims ;
- Evidence coverage ;
- contradictions ;
- Expert disagreement ;
- Unknowns.

## Epic C20-E03 — Cost Attribution

Par :

```text
tenant
user
job
investigation
expert
model
twin
```

## Epic C20-E04 — Evaluation Harness

Datasets :

- golden Claims ;
- golden conversations ;
- TBT historical questions ;
- investigations.

## Epic C20-E05 — Prompt / Expert Regression

## Epic C20-E06 — Quality Dashboard

---

# 23. C21 — Administration & Product Operations

**Priorité : P2**  
**Release : R7**

Epics :

```text
Source Administration
Expert Administration
Policy Administration
User/Role Administration
Audit Explorer
```

---

# 24. C22 — SaaS & Tenant Management

**Priorité : P3**  
**Release : R8**

Epics :

```text
Tenant Provisioning
Tenant Quotas
Connector Self-Service
Branding
Usage/Billing Metrics
Customer Policies
```

---

# 24A. C23 — Business Capability & Process Intelligence

**Priorité : P1**  
**Release : R2→R4**

## Epic C23-E01 — Business Capability Model

Objets :

```text
Capability
Business Service
Business Rule
Product
```

## Epic C23-E02 — Process Model

Objets :

```text
Process
Process Step
Handoff
Exception
Manual Activity
```

## Epic C23-E03 — Capability-to-Application Mapping

Relations :

```text
Application SUPPORTS Capability
Process USES Capability
Capability REALIZED_BY Application
```

Les relations peuvent être :

```text
DECLARED
OBSERVED
INFERRED
CONTESTED
```

## Epic C23-E04 — Business Change Impact

**User Story**

En tant que Product Owner, je veux demander l’impact d’un nouveau besoin métier afin d’identifier les processus, règles, applications, données et équipes concernés avant de choisir une solution.

## Epic C23-E05 — Process Friction Detection

Signals :

- duration ;
- handoff ;
- exception ;
- manual rework ;
- repeated workaround.

---

# 24B. C24 — Customer & Employee Intelligence

**Priorité : P1**  
**Release : R3→R6**

## Epic C24-E01 — Journey Model

```text
Journey
Stage
Touchpoint
Channel
Segment
```

## Epic C24-E02 — Customer Friction

Méridian peut relier :

```text
abandon
contact volume
journey duration
business rule
process
application change
```

## Epic C24-E03 — Employee / Operational Friction

Analyser :

```text
manual work
rework
tool switching
handoffs
exceptions
```

## Epic C24-E04 — Work Displacement Detection

**User Story**

En tant que responsable opérations, je veux détecter quand une amélioration déplace du travail vers mon équipe afin d’éviter les optimisations locales.

## Epic C24-E05 — Cross-perspective Outcome

Comparer :

```text
Customer outcome
Employee outcome
Technical outcome
```

---

# 24C. C25 — Risk, Compliance & Control Intelligence

**Priorité : P1**  
**Release : R3→R5**

## Epic C25-E01 — Control & Policy Knowledge

Objets :

```text
Policy
Rule
Control
Obligation
Exception
```

## Epic C25-E02 — Rule Implementation Mapping

Relations entre :

```text
Rule
Process
Application
Code
Data
Channel
```

## Epic C25-E03 — Control Coverage / Contradiction

Détecter :

- règle appliquée différemment ;
- contrôle absent ;
- implémentation en double ;
- Evidence contradictoire.

## Epic C25-E04 — Risk Propagation

Utiliser Mesh pour :

```text
exposure
blast radius
critical dependencies
```

## Epic C25-E05 — Governed Risk Investigation

---

# 24D. C26 — Finance, Portfolio & Strategic Intelligence

**Priorité : P1/P2**  
**Release : R3→R6**

## Epic C26-E01 — Cost & Value Context

Associer aux entités :

```text
cost
usage
business criticality
strategic relevance
```

## Epic C26-E02 — Rationalization Opportunity

Détecter :

```text
high cost
low usage
capability overlap
few unique consumers
```

## Epic C26-E03 — Initiative / Portfolio Dependency

Relier :

```text
Initiative
Capability
Application
Domain
Outcome
```

## Epic C26-E04 — Realized Value

Expected vs Observed.

## Epic C26-E05 — Strategic Decision Review

Permettre :

> Quelles décisions ou investissements devraient être revisités à la lumière de nouveaux faits ?

---

# 24E. C27 — Enterprise Perspectives & Role Projections

**Priorité : P0/P1**  
**Release : R2→R4**

Cette Capability empêche Méridian de devenir implicitement un outil TI.

Le même Knowledge Mesh doit produire des projections adaptées au rôle.

## Epic C27-E01 — Role Context

Profils :

```text
Executive
Business/Product
Customer Experience
Operations/Employee
Risk/Compliance
Finance/Portfolio
Data
Architecture/Technology
Transformation
```

## Epic C27-E02 — Aujourd’hui personnalisé

Chaque profil voit :

> ce qui mérite son attention.

Pas simplement les mêmes cartes triées différemment.

## Epic C27-E03 — Atlas Perspective Layers

Layers :

```text
Applications
Capabilities
Processes
Journeys
Teams
Data
Risks
Opportunities
Initiatives
```

## Epic C27-E04 — Flore Role-aware Starters

Exemples :

### Métier

```text
Quel besoin est impacté ?
Quelles règles changent ?
```

### Client

```text
Où se situe la friction ?
Qu’est-ce qui explique l’abandon ?
```

### Opérations

```text
Où la charge manuelle augmente-t-elle ?
```

### Risk

```text
Quels contrôles ou expositions sont concernés ?
```

### Finance

```text
Où avons-nous coût élevé et faible valeur ?
```

## Epic C27-E05 — Shared-object multi-perspective view

Une même Situation doit pouvoir exposer :

```text
Business impact
Customer impact
Employee impact
Risk impact
Financial impact
Technology impact
```

sans créer six Situations distinctes.

---

# 25. Vertical Slice Mapping

## VS0 — Platform Skeleton

```text
C01 + C02 + C12 + C20
```

Résultat :

> Méridian est déployable, authentifié, observable et capable de gérer un Job.

## VS1 — One Source → One Claim

```text
C03 + C04 + C05 + C07
```

Résultat :

> un élément Git devient une Evidence puis un Claim consultable.

## VS2 — Twin Birth

```text
C03 + C05 + C06 + C07 + C12
```

Résultat :

> TBT naît et produit sa première compréhension.

## VS3 — Flore Explains TBT

```text
C07 + C09 + C11
```

Résultat :

> Flore répond à partir des Claims et Evidence.

## VS4 — Historical Feature Report

```text
C03 + C05 + C07 + C11 + C12 + C16
```

Résultat :

> analyse sur trois ans avec features et références de code.

## VS5 — Mesh & Atlas

```text
C06 + C08 + C10
```

Résultat :

> TBT est visible dans son contexte réel.

## VS6 — Situation Emerges

```text
C07 + C08 + C13 + C14
```

Résultat :

> un ensemble de signaux devient phénomène significatif.

## VS7 — Investigation

```text
C15 + C16 + C07 + C11
```

Résultat :

> plusieurs hypothèses et Experts construisent une synthèse.

## VS8 — Decision

```text
C17 + C15
```

Résultat :

> plusieurs scénarios sont comparés et une décision humaine est capturée.

## VS9 — Outcome & Learning

```text
C18 + C19
```

Résultat :

> expected vs observed produit un Learning.

---

## VS10 — Customer Journey Friction

Capabilities :

```text
C23 + C24 + C07 + C08 + C11 + C13 + C15 + C16
```

Résultat :

> une friction client est expliquée en reliant parcours, processus, règles, applications et charge opérationnelle.

## VS11 — Business Rule Change

Capabilities :

```text
C23 + C25 + C07 + C08 + C11 + C15 + C17
```

Résultat :

> une nouvelle règle métier/réglementaire est cartographiée jusqu’aux systèmes, processus et canaux concernés.

## VS12 — Operational Work Displacement

Capabilities :

```text
C23 + C24 + C13 + C14 + C18
```

Résultat :

> une optimisation qui déplace de la charge vers les opérations est détectée et mesurée.

## VS13 — Portfolio Rationalization

Capabilities :

```text
C26 + C06 + C08 + C14 + C15 + C17
```

Résultat :

> coût, usage, duplication de capability et dépendances alimentent une décision de rationalisation.

---

# 26. Dependency Graph

```text
C01 Platform
   │
   ├── C02 Security
   ├── C12 Jobs
   └── C20 Observability
          │
          ▼
      C03 Sources
          │
          ▼
      C04 Evidence
          │
          ▼
      C05 Code
          │
     ┌────┴─────┐
     ▼          ▼
 C06 Twin     C07 Claims
     │          │
     └────┬─────┘
          ▼
      C08 Mesh
     ┌────┴────┐
     ▼         ▼
 C10 Atlas   C09 Retrieval
               │
               ▼
            C11 Flore
               │
               ▼
        C13 Discovery
               │
               ▼
       C14 Opportunity
               │
               ▼
      C15 Investigation
               │
               ▼
        C16 Experts
               │
               ▼
        C17 Decision
               │
               ▼
       C18 Improvement
               │
               ▼
          C19 Memory
```

---

# 27. Critical Path

Il existe désormais **deux chemins critiques complémentaires**.

## Critical Path A — Knowledge Foundation

```text
Platform
→ Jobs
→ Sources
→ Evidence
→ Claims
→ Twins
→ Mesh
```

## Critical Path B — Enterprise Exploitation

```text
Business / Customer / Risk / Operations question
→ Role Perspective
→ Flore
→ Mesh / Claims
→ Situation / Opportunity
→ Investigation
→ Experts
→ Decision
→ Outcome
```

Le premier construit l’intelligence.

Le second prouve que cette intelligence sert plusieurs profils.

Un MVP qui ne réalise que le Path A est une plateforme de connaissance technique incomplète.

---

# 28. Technical Enablers

```text
EN-01 Correlation IDs — P0
EN-02 Schema Registry — P0
EN-03 Security Context Propagation — P0
EN-04 Feature Flags — P0/P1
EN-05 Evaluation Harness — P0
EN-06 Cost Tracking — P0
EN-07 Semantic Cache — P1
EN-08 Graph Projection Rebuild — P1
EN-09 Search Projection Rebuild — P1
EN-10 Retention & Archival — P2
```

---

# 29. Architecture Spikes

## SPIKE-01 — Code Graph Performance

Mesurer :

```text
repo size
initial indexing
incremental indexing
graph query latency
token cost
```

## SPIKE-02 — Historical Feature Reconstruction

Comparer :

```text
full-repo LLM scan
vs
change clustering + targeted graph/code retrieval
```

## SPIKE-03 — Graph Technology

Comparer l’implémentation actuelle à une cible property graph adaptée au Mesh.

## SPIKE-04 — SSE at Scale

Tester :

- reconnexion ;
- fan-out ;
- long jobs.

## SPIKE-05 — Agent Runtime

Comparer exécution directe, runtime managé et container.

## SPIKE-06 — Claim Confidence

Tester calibration et règles.

## SPIKE-07 — Security Trimming

Tester Graph + Search + Evidence.

---

# 30. Release R0 — Platform

**But :** rendre l’équipe capable de livrer.

Scope :

```text
App Shell
CI/CD
SSO
Audit baseline
Job Framework
SSE baseline
Tracing
Cost skeleton
```

**Exit Criteria**

> Un utilisateur authentifié peut lancer un Job de test, suivre sa progression et le retrouver après reprise du service.

---

# 31. Release R1 — Know

**But :** faire naître une connaissance vérifiable.

Scope :

```text
GitHub
Artifact
Evidence
Claim
Code Intelligence
Twin Birth
```

**Exit Criteria**

> TBT possède une identité, des Claims sourcés, des relations locales, des Unknowns et un résumé initial.

---

# 32. Release R2 — Understand

**But :** rendre la connaissance exploitable **par plusieurs profils**.

Scope :

```text
Flore
Search/Retrieval
Mesh
Atlas
Jira
Historical Feature Report
Trust Panel
Business Capability baseline
Process baseline
Role Perspectives
```

**Exit Criteria**

Le release n’est pas validé seulement parce qu’un architecte peut interroger TBT.

Il faut démontrer :

1. une question applicative sourcée ;
2. une question métier/processus utilisant le même Mesh ;
3. au moins deux profils utilisant Flore avec des contextes différents ;
4. Atlas permettant au minimum une vue Applications et une vue Capability/Process.

> **L’utilisateur peut interroger et naviguer dans une connaissance commune depuis plusieurs perspectives.**

---

# 33. Release R3 — Discover

**But :** faire émerger ce qui mérite l’attention **au niveau entreprise**, pas seulement technique.

Scope :

```text
Signal
Situation
Correlation
Maturity
Expression
Opportunity
Risk
Customer/Process signals
Operational friction signals
Portfolio signals
Role-aware Today
```

**Exit Criteria**

Méridian produit au moins :

- une Expression technique/transverse ;
- une Expression métier/client/opérations/risque ;
- une Opportunity ou Risk explicable ;
- une vue `Why now` ;
- une lecture multi-impact :

```text
business
customer
employee
risk
financial
technology
```

> **Méridian commence à dire ce qui mérite l’attention, quel que soit le point d’entrée.**

---

# 34. Release R4 — Investigate

Scope :

```text
Investigation
Hypotheses
Evidence Board
Expert Registry
Parallel Experts
Contradictor
Synthesis
```

**Exit Criteria**

> Une Situation peut être transformée en compréhension structurée avec plusieurs hypothèses et preuves pour/contre.

---

# 35. Release R5 — Decide

Scope :

```text
Scenarios
Scenario Critic
Comparison
Recommendation
Decision
Decision Snapshot
```

**Exit Criteria**

> Un humain peut comparer plusieurs options, comprendre les risques et enregistrer une décision traçable.

---

# 36. Release R6 — Learn

Scope :

```text
Initiative
Expected Outcome
Observed Outcome
Side Effects
Learning
Transformation Episode baseline
```

**Exit Criteria**

> Une décision produit un résultat mesurable et un apprentissage réutilisable.

---

# 37. Release R7 — Productize

Focus :

- administration ;
- policies ;
- richer evaluations ;
- production hardening ;
- UX refinement ;
- performance ;
- connector lifecycle ;
- reliability.

---

# 38. Release R8 — Enterprise / SaaS

Focus :

- tenant provisioning ;
- quotas ;
- connector self-service ;
- tenant policies ;
- branding ;
- usage/billing ;
- enterprise rollout.

---

# 39. MVP Cut Line

Le **MVP strict** s’arrête à R5, avec une preuve minimale de R6.

Mais il doit obligatoirement démontrer **deux Golden Paths**.

## Golden Path A — Application Intelligence

```text
TBT
→ Claims/Evidence
→ Flore
→ Mesh
→ Investigation
→ Decision
```

## Golden Path B — Enterprise Exploitation non-TI

Exemple recommandé :

```text
Mortgage Journey friction
→ Customer signal
→ Process / Operations
→ Applications / Rules
→ Investigation
→ Scenario
→ Decision
```

ou :

```text
Business rule change
→ affected processes/channels/apps
→ Risk
→ Investigation
→ Decision
```

## MUST

```text
Platform
Security
Jobs
Sources
Evidence
Claims
Twin
Mesh
Flore
Atlas
Role Perspectives
Business Capability / Process baseline
Situation
Investigation
Experts
Scenarios
Decision
Observability
Cost
```

## SHOULD

```text
Customer Journey
Operational Friction
Risk/Control mapping
Portfolio Rationalization
Opportunity
Outcome
Learning
```

## COULD

```text
Transformation Memory
Advanced Radar
Temporal Atlas
Pattern clusters
```

## WON'T — MVP initial

```text
Critical autonomous actions
Full enterprise ontology
All connectors
Full Swarm
Fully generalized Customer/Employee Twin products
Full SaaS self-service
```

---

# 40. Golden User Story — TBT historical features

**Story**

En tant qu’architecte, je veux demander :

> « Quelles fonctionnalités ont été ajoutées à TBT au cours des trois dernières années ? »

afin d’obtenir un rapport vérifiable avec les références de code.

**Acceptance Criteria**

1. TBT est correctement résolu.
2. La période est explicite.
3. Git et Jira sont interrogés.
4. Les changements sont regroupés.
5. Les changements techniques sont séparés des fonctionnalités.
6. Chaque fonctionnalité possède des Evidence.
7. Les références code sont précises.
8. Confidence est visible.
9. Les résultats partiels sont publiés.
10. Le traitement peut reprendre après interruption.
11. Le coût est tracé.
12. Le rapport est reproductible.

---

# 41. Golden User Story — Atlas

**Story**

En tant qu’architecte, je veux voir le voisinage de TBT dans Atlas afin de comprendre son contexte réel.

**Acceptance Criteria**

- sélection TBT ;
- voisins principaux ;
- relations ;
- direction ;
- confidence ;
- declared vs observed ;
- peek ;
- action Ask Flore.

---

# 42. Golden User Story — Investigation

**Story**

En tant qu’utilisateur, je veux transformer une Situation en Investigation sans reconstruire le contexte.

**Acceptance Criteria**

- trigger lié ;
- scope prérempli ;
- Evidence initiale conservée ;
- plusieurs hypothèses ;
- Expert team ;
- contradiction ;
- synthesis ;
- Unknowns.

---

# 43. Golden User Story — Decision

**Story**

En tant que décideur, je veux comparer plusieurs scénarios afin de rendre les compromis visibles avant de choisir.

**Acceptance Criteria**

- dimensions communes ;
- assumptions ;
- risques ;
- value ;
- cost ;
- time ;
- reversibility ;
- recommendation séparée ;
- décision humaine ;
- snapshot.

---

# 43A. Golden User Story — Customer Journey Friction

**Story**

En tant que responsable Produit / Expérience Client, je veux demander :

> « Pourquoi le taux d’abandon du renouvellement hypothécaire augmente-t-il ? »

afin de comprendre le phénomène de bout en bout.

**Acceptance Criteria**

1. Journey résolu.
2. Segment et période explicites.
3. métriques client récupérées.
4. Process Steps associés.
5. changements de règles et applications reliés.
6. charge opérationnelle analysée.
7. plusieurs hypothèses.
8. Evidence pour/contre.
9. impacts client, employé et technologie séparés.
10. Investigation lançable depuis Flore.

---

# 43B. Golden User Story — Operations

**Story**

En tant que responsable opérations, je veux savoir si une transformation a déplacé du travail manuel vers mon équipe.

**Acceptance Criteria**

- baseline opérationnelle ;
- changement lié ;
- manual work / rework ;
- processus concerné ;
- source applicative si pertinente ;
- Outcome expected vs observed ;
- Opportunity générable.

---

# 43C. Golden User Story — Risk / Compliance

**Story**

En tant que responsable risque, je veux voir où une règle critique est réellement appliquée afin d’identifier les implémentations incohérentes.

**Acceptance Criteria**

- Rule canonicalisée ;
- Process / App / Code mappings ;
- contradictions ;
- Unknowns ;
- blast radius ;
- Evidence ;
- governed Investigation.

---

# 43D. Golden User Story — Finance / Portfolio

**Story**

En tant que responsable portefeuille, je veux identifier les capacités coûteuses et dupliquées afin de prioriser les rationalisations sur la valeur plutôt que sur l’âge des applications.

**Acceptance Criteria**

- cost context ;
- usage ;
- capability overlap ;
- unique consumers ;
- business criticality ;
- Risk ;
- scénarios comparables.

---

# 44. Backlog Sequencing

Ordre recommandé :

```text
A. Platform
B. Evidence First
C. Twin Birth
D. Flore over Knowledge
E. Historical TBT
F. Mesh + Atlas
G. Discovery
H. Investigation
I. Decision
J. Learning
```

---

# 45. Why Evidence First

Sans Evidence :

- Claims deviennent fragiles ;
- Flore devient un chatbot ;
- Expert outputs deviennent difficiles à auditer ;
- Decision support devient peu crédible.

Donc :

> **Evidence avant sophistication agentique.**

---

# 46. Why Jobs Early

Les traitements lourds existent dès :

- indexing ;
- historical reconstruction ;
- reports ;
- investigations.

Le framework Job doit donc être construit très tôt.

---

# 47. Why Flore before Advanced Discovery

Flore permet de tester immédiatement :

> **la valeur de la connaissance accumulée.**

C’est le moyen le plus rapide de voir si le Twin sait réellement quelque chose d’utile.

---

# 48. Why Mesh before Full Opportunity Engine

La vraie différenciation commence lorsque Méridian peut dépasser une application isolée.

---

# 49. Why Investigation before Autonomous Action

La priorité est de démontrer :

- compréhension ;
- Evidence ;
- contradiction ;
- gouvernance.

L’agence externe vient beaucoup plus tard.

---

# 50. Definition of Ready

Une Story est Ready si :

```text
Value understood
Actor identified
Domain objects identified
Dependencies understood
Acceptance criteria written
Security considered
Observability considered
```

---

# 51. Definition of Done

Une Story est Done si :

```text
Functional acceptance passed
Unit tests
Integration tests
Security applied
Telemetry available
Loading/error/empty state
Documentation
Performance checked
AI cost checked if applicable
```

---

# 52. AI Definition of Done

Toute Story avec IA ajoute :

```text
Golden test
Evidence validation
Structured output validation
Unknown behavior tested
Prompt injection test where relevant
Token/cost telemetry
Model version recorded
```

---

# 53. Architecture Definition of Done

Pour un nouveau domain object :

- identity ;
- versioning ;
- events ;
- persistence ;
- security ;
- audit ;
- API contract.

---

# 54. Prioritization Formula

Conceptuellement :

```text
Priority =
(User Value × Strategic Fit × Learning Value)
/
(Complexity × Risk)
```

Ce score aide à arbitrer ; il ne remplace pas le jugement produit.

---

# 55. Learning Value

Une feature peut être prioritaire parce qu’elle répond à une inconnue majeure.

Exemple :

> Peut-on vraiment réduire l’analyse de repository de dizaines de minutes à un modèle incrémental ?

---

# 56. Product Risks à éliminer

Ordre :

```text
1 Evidence / Claim trust
2 Long processing & cost
3 Source access
4 Mesh value
5 Flore context quality
6 Atlas readability
7 Agent orchestration complexity
```

---

# 57. Risk — Traitements longs

Mitigation :

```text
deterministic extraction
incremental graph
hierarchical summaries
targeted retrieval
cache
Jobs
partial results
```

---

# 58. Risk — Agent explosion

Mitigation :

```text
small Expert Registry
Agent-as-Tool
parallel specialists
Contradictor
strict budgets
```

---

# 59. Risk — Atlas complexity

Mitigation :

```text
semantic zoom
LOD
viewport queries
domain membranes
controlled edges
```

---

# 60. Demo Golden Path

Une démo de référence peut suivre :

```text
1. Birth of TBT Twin
2. Flore: "What do you know about TBT?"
3. Atlas reveals dependencies
4. Historical feature question
5. Situation emerges
6. Investigation opens
7. Experts disagree / reconcile
8. Scenarios compared
9. Human decision
10. Outcome/Learning preview
```

La démo raconte une seule histoire ; elle ne visite pas chaque menu.

---

# 61. Production MVP vs Demo

La démo peut pré-calculer certains traitements lourds.

Le MVP, lui, doit posséder :

- vrai Job Model ;
- vraie Evidence ;
- vrais Claims ;
- vraie progression ;
- vraie reprise.

---

# 62. Technical Debt Policy

Dette acceptable :

- polish secondaire ;
- connecteurs non prioritaires ;
- certaines vues admin.

Dette interdite :

```text
Claim identity
Evidence lineage
tenant isolation
security trimming
workflow durability
audit
```

---

# 63. Team Shape

Équipe de départ indicative :

```text
Product / Domain Lead
Tech Lead / Architect
Backend / AI Engineers
Frontend Engineer
Knowledge / Data Engineer
Platform / DevOps
UX/UI support
```

Une petite équipe peut cumuler certains rôles.

---

# 64. Pilot Strategy

Déploiement progressif :

```text
TBT
↓
Application owners
↓
Small application cluster
↓
One domain
↓
Several domains
```

Ne pas onboarder des centaines d’applications avant d’avoir prouvé la valeur.

---

# 65. Pilot Metrics

## Product

```text
time to answer
time saved
user usefulness
investigations created
```

## Knowledge

```text
Evidence coverage
Claim acceptance
Unknown detection
Contradictions
```

## AI

```text
grounding
tool accuracy
latency
cost
```

## Platform

```text
job success
freshness
availability
```

---

# 66. Product Validation Questions

Après usage :

> Qu’avez-vous compris plus rapidement ?

> Qu’avez-vous découvert que vous n’auriez pas trouvé facilement ?

> Où n’avez-vous pas fait confiance à Méridian ?

> Quelle action avez-vous prise ensuite ?

---

# 67. MVP Success Statement

Le MVP est réussi si un utilisateur peut dire :

> **« Je peux poser à Méridian une question difficile sur une application, comprendre pourquoi la réponse est crédible, voir ses dépendances et lancer une investigation sans repartir de zéro. »**

Le signal encore plus fort est :

> **« Méridian m’a montré quelque chose d’important que je ne cherchais pas explicitement, m’a aidé à le comprendre et m’a permis de décider plus vite. »**

---

# 68. Traceability vers les documents d’architecture

```text
C06 Twin
→ Domain Model
→ Functional Architecture
→ Technical Architecture

C07 Claims
→ Knowledge & Claims Architecture

C13 Discovery
→ Discovery & Maturation Engine

C15 Investigation
→ Investigation & Decision Engine

C16 Experts
→ Agentic Architecture & Expert Framework

C11 Flore
→ Flore Conversational Architecture

C18 Learning
→ Continuous Improvement & Learning Model

C02 Security
→ Security, Governance & Trust Model
```

---

# 69. Backlog Governance

Revue régulière :

1. Est-ce lié à une boucle de valeur ?
2. Est-ce vraiment P0 ?
3. Quel risque cela réduit-il ?
4. Peut-on le démontrer ?
5. Quelle architecture est concernée ?
6. Quels critères de sortie ?
7. Peut-on le supprimer ?

---

# 70. Backlog Anti-patterns

## Horizontal delivery

```text
backend first
AI later
UI last
```

sans utilisateur avant plusieurs mois.

## All connectors first

Trop de coût avant la première valeur.

## Atlas before Knowledge

Belle carte vide.

## Expert before Evidence

Agent convaincant mais invérifiable.

## Full ontology before use case

Sur-conception.

## Swarm before orchestration discipline

Complexité prématurée.

## Everything P0

Absence réelle de priorité.

---

# 71. Release Summary

| Release | Objectif | Démonstration |
|---|---|---|
| R0 | Platform | Auth + Job + tracing |
| R1 | Know | Twin TBT + Claims + Evidence |
| R2 | Understand | Flore + Mesh + Atlas + historical report |
| R3 | Discover | Signal → Situation → Expression |
| R4 | Investigate | Hypothèses + Experts + contradiction |
| R5 | Decide | Scenarios + Decision |
| R6 | Learn | Expected vs Observed + Learning |
| R7 | Productize | Robustesse + admin + qualité |
| R8 | Enterprise/SaaS | Multi-tenant + self-service |

---

# 72. Capability Priority Summary

| Capability | Priority | Release |
|---|---:|---|
| Platform Foundation | P0 | R0 |
| Security & Governance | P0 | R0+ |
| Jobs & Workflows | P0 | R0 |
| Source Connectivity | P0 | R1 |
| Evidence | P0 | R1 |
| Code Intelligence | P0 | R1/R2 |
| Twin Intelligence | P0 | R1 |
| Claims & Knowledge | P0 | R1 |
| Search & Retrieval | P0 | R2 |
| Mesh | P0/P1 | R2 |
| Atlas | P0 | R2 |
| Flore | P0 | R2 |
| Discovery | P1 | R3 |
| Opportunities/Risks | P1 | R3 |
| Investigation | P0/P1 | R4 |
| Expert Framework | P0/P1 | R4 |
| Scenarios/Decision | P1 | R5 |
| Improvement | P1/P2 | R6 |
| Transformation Memory | P2 | R6/R7 |
| Observability/Evaluation/Cost | P0 | All |
| Administration | P2 | R7 |
| SaaS/Tenant | P3 | R8 |

---

# 73. Final Delivery Sequence

```text
PLATFORM
↓
SOURCES → EVIDENCE → CLAIMS
↓
TWINS + BUSINESS / PROCESS CONTEXT
↓
FLORE + ROLE PERSPECTIVES
↓
MESH + ATLAS
↓
APPLICATION + BUSINESS GOLDEN QUESTIONS
↓
DISCOVERY / MATURATION
↓
CUSTOMER / EMPLOYEE / RISK / PORTFOLIO PHENOMENA
↓
INVESTIGATION / EXPERTS
↓
SCENARIOS / DECISION
↓
OUTCOMES / LEARNING
```

C’est la séquence recommandée pour éviter deux échecs classiques :

1. construire une plateforme techniquement impressionnante sans usage clair ;
2. construire une démo IA spectaculaire sans fondation de connaissance durable.

---

# 74. Conclusion

Le backlog de Méridian doit rester l’expression exécutable de la vision.

Il ne doit pas devenir une liste infinie de fonctionnalités.

Le bon backlog optimise trois choses :

```text
VALUE
+
LEARNING
+
RISK REDUCTION
```

Chaque release doit produire une capacité visible.

Chaque vertical slice doit traverser le produit de bout en bout.

Chaque fonctionnalité cognitive doit rester reliée à :

```text
Evidence
Confidence
Security
Observability
Cost
```

La cible du MVP est claire :

> **construire une connaissance vérifiable à partir des Twins et autres dimensions de l’entreprise, puis permettre à plusieurs profils — métier, client, opérations, risque, finance, data et TI — de l’exploiter via Flore et le Mesh jusqu’à une décision humaine.**

À partir de là, Méridian n’est plus une idée.

Il devient un produit.

---

# 75. Prochain document

Le prochain document recommandé est :

> **MÉRIDIAN — Reference Use Cases & End-to-End Scenarios**

Ce document devra définir les scénarios canoniques utilisés simultanément pour :

- Product ;
- UX ;
- Architecture ;
- Backlog ;
- QA ;
- Evaluations IA ;
- démonstrations ;
- storytelling.

Scénarios de référence :

1. Naissance du Twin TBT.
2. Fonctionnalités ajoutées sur trois ans.
3. Impact de suppression de TBT.
4. Incident après changement.
5. Opportunity de rationalisation.
6. Friction client.
7. Friction employé.
8. Domain drift.
9. Décision stratégique.
10. Outcome et Learning.

Chaque scénario suivra :

```text
Trigger
↓
Sources
↓
Observations / Claims
↓
Mesh
↓
Flore / Experts
↓
Investigation
↓
Scenario / Decision
↓
Outcome / Learning
```

Ce sera la référence commune permettant de vérifier que **toutes les briques de Méridian racontent la même histoire produit**.
