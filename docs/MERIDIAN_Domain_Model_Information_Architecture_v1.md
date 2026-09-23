# MÉRIDIAN — Domain Model & Information Architecture
## Modèle de domaine, objets vivants, relations, temporalité et architecture de l’information

**Statut :** Modèle de domaine de référence  
**Version :** 1.0  
**Produit :** MÉRIDIAN  
**Tagline :** **DÉCOUVRIR · COMPRENDRE · DÉCIDER**

---

# 0. Objet du document

Ce document définit la colonne vertébrale informationnelle de Méridian.

Il répond à la question :

> **Quels sont les objets fondamentaux de Méridian, comment sont-ils identifiés, reliés, versionnés, maturés et utilisés dans le temps ?**

Il complète :

- la Product Vision ;
- le Product Blueprint ;
- la Functional Architecture ;
- la Technical Architecture.

Il ne décrit pas encore les détails d’implémentation physique des bases de données.

Il stabilise d’abord le langage du produit.

---

# 1. Principes du modèle de domaine

## 1.1 Tout ce qui est important devient un objet explicite

Méridian ne doit pas cacher ses concepts centraux dans des blobs JSON ou dans la mémoire d’un agent.

Les objets majeurs doivent être identifiables, interrogeables et traçables.

## 1.2 Un objet possède une identité stable

Exemple :

```text
Twin = TWN-2748
Claim = CLM-48219
Investigation = INV-1024
Opportunity = OPP-771
Decision = DEC-42
```

L’identité ne dépend pas du texte affiché.

## 1.3 Le temps est une dimension native

Toute connaissance importante doit pouvoir répondre :

- quand a-t-elle été observée ?
- quand Méridian l’a-t-il apprise ?
- depuis quand est-elle valide ?
- jusqu’à quand ?
- quelle version était connue à une date donnée ?

## 1.4 Toute conclusion doit être reliée à ses preuves

La chaîne canonique est :

```text
Expression
↓
Hypothesis
↓
Claim
↓
Evidence
↓
Artifact
↓
Source
```

## 1.5 L’incertitude fait partie du modèle

Les objets peuvent porter :

- confidence ;
- maturity ;
- uncertainty ;
- contradiction ;
- unknowns.

## 1.6 Le modèle humain et le modèle découvert coexistent

Méridian doit distinguer :

```text
DECLARED
OBSERVED
INFERRED
PROPOSED
CONFIRMED
```

Cela vaut pour :

- relations ;
- domaines ;
- capacités ;
- dépendances ;
- processus.

---

# 2. Carte du domaine

Les objets de Méridian peuvent être regroupés en huit familles.

```text
1. IDENTITÉ & STRUCTURE
   Twin · Domain · Capability · Application · Process · Journey · Team

2. SOURCES & PREUVES
   Source · Artifact · Observation · Evidence

3. CONNAISSANCE
   Claim · Relationship · Unknown · Contradiction

4. ÉMERGENCE
   Signal · Situation · Expression · Opportunity · Risk

5. INVESTIGATION
   Investigation · Hypothesis · Expert · ExpertContribution

6. DÉCISION
   Scenario · Decision · Initiative

7. RÉSULTAT & APPRENTISSAGE
   Outcome · Learning

8. INTERACTION & GOUVERNANCE
   UserContext · Scope · Permission · Annotation · Subscription
```

---

# 3. Aggregate Roots principaux

Les Aggregate Roots recommandés sont :

- Twin
- Claim
- Situation
- Opportunity
- Risk
- Investigation
- Decision
- Initiative
- Learning
- Source
- Domain

Tous les objets ne doivent pas être modifiés indépendamment.

---

# 4. Twin

## 4.1 Définition

Un Twin représente une entité de l’entreprise dont Méridian maintient une représentation vivante.

Un Twin n’est donc pas limité à l’application.

## 4.2 Types

```text
APPLICATION
PROCESS
CAPABILITY
JOURNEY
ORGANIZATION
PRODUCT
DATA_DOMAIN
```

Le premier type implémenté peut être `APPLICATION`.

## 4.3 Structure

```yaml
Twin:
  id:
  tenant_id:
  type:
  canonical_name:
  aliases:
  description:
  status:
  lifecycle_state:
  confidence:
  maturity:
  created_at:
  updated_at:
  valid_from:
  valid_to:
  source_manifest_id:
  domain_refs:
  owner_refs:
  claim_refs:
  relationship_refs:
  unknown_refs:
```

## 4.4 Invariants

1. Un Twin possède une identité stable.
2. Un Twin peut changer de nom sans changer d’identité.
3. Un Twin peut appartenir à plusieurs domaines.
4. Un Twin peut exister avec un niveau de connaissance faible.
5. Un Twin ne doit jamais être considéré complet par défaut.
6. Toute information détaillée sur le Twin doit être portée par des Claims ou relations traçables.

---

# 5. ApplicationTwin

## 5.1 Attributs spécifiques

```yaml
ApplicationTwin:
  application_id:
  technology_stack:
  criticality:
  repositories:
  runtime_services:
  databases:
  interfaces:
  business_capabilities:
  owning_team:
```

## 5.2 Connaissance attendue

Un ApplicationTwin peut connaître :

- rôle ;
- fonctionnalités ;
- règles ;
- flux ;
- dépendances ;
- données ;
- API ;
- événements ;
- historique ;
- incidents ;
- changements ;
- équipes ;
- voisins.

---

# 6. Domain

## 6.1 Définition

Un Domain représente un regroupement cohérent d’entités.

Il peut être :

```text
DECLARED
DISCOVERED
PROPOSED
HYBRID
```

## 6.2 Structure

```yaml
Domain:
  id:
  name:
  domain_type:
  origin:
  description:
  member_refs:
  parent_domain_ref:
  confidence:
  validity:
  evidence_refs:
```

## 6.3 Règle importante

Un domaine découvert ne remplace jamais automatiquement le domaine officiel.

Méridian conserve la divergence.

---

# 7. Capability

Une Capability représente ce que l’entreprise sait faire.

Exemple :

> Évaluer l’admissibilité d’un client.

Elle peut être supportée par plusieurs applications et processus.

```yaml
Capability:
  id:
  name:
  description:
  supported_by:
  process_refs:
  product_refs:
  customer_journey_refs:
  confidence:
```

---

# 8. Source

## 8.1 Définition

Une Source est un système externe fournissant de l’information à Méridian.

## 8.2 Types

```text
GIT
ISSUE_TRACKER
DOCUMENTATION
CMDB
MONITORING
LOGGING
DATABASE
EVENT_STREAM
CRM
SERVICE_MANAGEMENT
HUMAN
```

## 8.3 Structure

```yaml
Source:
  id:
  type:
  external_system:
  connection_ref:
  access_policy:
  sync_policy:
  owner:
  health:
  last_sync:
  classification:
```

---

# 9. Artifact

## 9.1 Définition

Un Artifact est une unité récupérée depuis une Source.

Exemples :

- fichier ;
- commit ;
- ticket ;
- document ;
- table ;
- métrique ;
- incident ;
- log segment ;
- événement.

```yaml
Artifact:
  id:
  source_id:
  external_id:
  artifact_type:
  version:
  content_hash:
  location:
  observed_at:
  classification:
  raw_content_ref:
```

---

# 10. Observation

## 10.1 Définition

Une Observation représente un fait directement observé.

Elle doit éviter l’interprétation forte.

Exemple :

> La latence p95 de X est passée de 420 ms à 880 ms.

```yaml
Observation:
  id:
  observed_entity_ref:
  observation_type:
  value:
  unit:
  observed_at:
  artifact_ref:
  source_ref:
  confidence:
```

---

# 11. Evidence

## 11.1 Définition

Une Evidence est un élément utilisé pour supporter ou contredire un Claim ou une Hypothesis.

```yaml
Evidence:
  id:
  artifact_ref:
  locator:
  excerpt_hash:
  evidence_type:
  supports:
  contradicts:
  observed_at:
  validity:
  access_policy:
```

## 11.2 Locator

Exemples :

```text
git://repo/commit/path#L120-L146
doc://confluence/page/section
db://schema/table/column
metric://service/latency?from=...&to=...
ticket://jira/TBT-481
```

---

# 12. Claim

## 12.1 Définition

Un Claim est une affirmation explicite, vérifiable et versionnée.

## 12.2 Forme logique

```text
SUBJECT — PREDICATE — OBJECT
```

Exemple :

```text
TBT — CALLS — EligibilityService
```

## 12.3 Structure

```yaml
Claim:
  id:
  version:
  subject_ref:
  predicate:
  object_ref_or_value:
  claim_type:
  status:
  origin:
  confidence:
  maturity:
  valid_from:
  valid_to:
  observed_at:
  discovered_at:
  evidence_refs:
  contradiction_refs:
  supersedes:
```

## 12.4 Status

```text
OBSERVED
PROPOSED
SUPPORTED
STRENGTHENED
MATURE
CONTESTED
INVALIDATED
HISTORICAL
```

---

# 13. ClaimType

Types possibles :

```text
DEPENDENCY
CAPABILITY
BUSINESS_RULE
DATA_FLOW
OWNERSHIP
PROCESS_STEP
API_USAGE
CHANGE
FUNCTIONALITY
RISK
BEHAVIOR
CUSTOMER_IMPACT
EMPLOYEE_IMPACT
```

---

# 14. Relationship

## 14.1 Définition

Une Relationship relie deux entités.

Exemples :

```text
DEPENDS_ON
CALLS
READS
WRITES
SUPPORTS
OWNED_BY
PART_OF
AFFECTS
PRECEDES
DERIVED_FROM
```

## 14.2 Structure

```yaml
Relationship:
  id:
  from_ref:
  type:
  to_ref:
  origin:
  confidence:
  valid_from:
  valid_to:
  evidence_refs:
```

---

# 15. Unknown

Un Unknown représente explicitement un manque de connaissance.

Exemple :

> Nous savons que TBT communique avec X, mais nous ne connaissons pas encore le rôle exact de cet échange.

```yaml
Unknown:
  id:
  entity_ref:
  question:
  importance:
  discovered_at:
  status:
  resolution_refs:
```

---

# 16. Contradiction

## 16.1 Définition

Une Contradiction exprime un conflit entre deux éléments de connaissance.

## 16.2 Types

```text
VALUE_CONFLICT
RELATIONSHIP_CONFLICT
SOURCE_CONFLICT
TEMPORAL_CONFLICT
MODEL_CONFLICT
EXPERT_CONFLICT
```

## 16.3 Structure

```yaml
Contradiction:
  id:
  left_ref:
  right_ref:
  type:
  severity:
  status:
  detected_at:
  resolution:
  resolved_at:
```

---

# 17. Signal

## 17.1 Définition

Un Signal est un événement ou changement pouvant devenir significatif.

```yaml
Signal:
  id:
  signal_type:
  entity_refs:
  observed_at:
  source_refs:
  intensity:
  confidence:
  fingerprint:
  status:
```

---

# 18. Situation

## 18.1 Définition

Une Situation regroupe plusieurs signaux ou observations semblant appartenir au même phénomène.

```yaml
Situation:
  id:
  title:
  status:
  signal_refs:
  entity_refs:
  temporal_window:
  maturity:
  confidence:
  candidate_causes:
  impact_refs:
  expression_ref:
```

## 18.2 États

```text
CANDIDATE
QUALIFYING
MATURING
MATURE
DISMISSED
MERGED
ARCHIVED
```

---

# 19. Expression

## 19.1 Définition

Une Expression est la formulation humaine d’un phénomène suffisamment mature.

```yaml
Expression:
  id:
  situation_ref:
  title:
  summary:
  expression_type:
  importance:
  maturity:
  confidence:
  claim_refs:
  hypothesis_refs:
  evidence_refs:
  contradiction_refs:
  unknown_refs:
  next_actions:
```

---

# 20. Opportunity

## 20.1 Définition

Une Opportunity représente une possibilité d’amélioration.

```yaml
Opportunity:
  id:
  expression_ref:
  opportunity_type:
  title:
  status:
  potential_value:
  affected_entities:
  confidence:
  maturity:
  owner_ref:
  investigation_ref:
```

## 20.2 Types

```text
AUTOMATION
SIMPLIFICATION
MODERNIZATION
RATIONALIZATION
COST_REDUCTION
CUSTOMER_EXPERIENCE
EMPLOYEE_EXPERIENCE
PROCESS_OPTIMIZATION
DATA_OPTIMIZATION
CONSOLIDATION
```

## 20.3 États

```text
DETECTED
MATURING
QUALIFIED
INVESTIGATING
SCENARIOS_AVAILABLE
DECIDED
INITIATED
MEASURED
LEARNED
REJECTED
DORMANT
```

---

# 21. Risk

Structure proche de `Opportunity`.

Attributs spécifiques :

```yaml
Risk:
  probability:
  severity:
  exposure:
  propagation:
  controls:
  time_horizon:
```

---

# 22. Investigation

## 22.1 Définition

Une Investigation est un espace structuré de compréhension.

```yaml
Investigation:
  id:
  title:
  question:
  trigger_ref:
  scope:
  status:
  opened_at:
  owner_ref:
  hypothesis_refs:
  expert_contribution_refs:
  evidence_refs:
  contradiction_refs:
  scenario_refs:
  synthesis_ref:
```

## 22.2 États

```text
OPEN
SCOPING
COLLECTING
ANALYZING
CONTRADICTING
SYNTHESIZING
SCENARIO_BUILDING
READY_FOR_DECISION
DECIDED
CLOSED
REOPENED
```

---

# 23. Hypothesis

## 23.1 Définition

Une Hypothesis est une explication possible à tester.

```yaml
Hypothesis:
  id:
  investigation_ref:
  statement:
  status:
  confidence:
  supporting_claims:
  opposing_claims:
  supporting_evidence:
  opposing_evidence:
  owner_expert_ref:
```

## 23.2 États

```text
OPEN
STRENGTHENED
WEAKENED
REJECTED
CONFIRMED
```

---

# 24. Expert

## 24.1 Définition

Un Expert est une capacité spécialisée de raisonnement.

```yaml
Expert:
  id:
  expert_type:
  domain:
  competencies:
  allowed_sources:
  allowed_tools:
  methods:
  evidence_policy:
  limits:
  version:
```

---

# 25. ExpertContribution

Une exécution d’Expert produit une contribution.

```yaml
ExpertContribution:
  id:
  investigation_ref:
  expert_ref:
  execution_ref:
  findings:
  proposed_claim_refs:
  supported_hypothesis_refs:
  challenged_hypothesis_refs:
  evidence_refs:
  unknowns:
  confidence:
  created_at:
```

---

# 26. Scenario

## 26.1 Définition

Une option d’action.

```yaml
Scenario:
  id:
  investigation_ref:
  title:
  description:
  assumptions:
  actions:
  dependencies:
  expected_impacts:
  risks:
  estimated_cost:
  reversibility:
  confidence:
```

---

# 27. Decision

## 27.1 Définition

Une décision humaine enregistrée.

```yaml
Decision:
  id:
  investigation_ref:
  selected_scenario_ref:
  rejected_scenario_refs:
  rationale:
  approver_refs:
  decided_at:
  evidence_snapshot_ref:
  expected_outcomes:
  status:
```

## 27.2 Invariant critique

Une Decision ne doit jamais être réécrite silencieusement.

Toute correction doit produire une nouvelle version ou une décision de remplacement.

---

# 28. Initiative

## 28.1 Définition

Une Initiative traduit une décision en action suivie.

```yaml
Initiative:
  id:
  decision_ref:
  title:
  status:
  owner_ref:
  scope:
  action_refs:
  expected_outcomes:
  observation_plan_ref:
  start_at:
  target_end_at:
```

---

# 29. Outcome

## 29.1 Définition

Un Outcome représente ce qui est observé après une action.

```yaml
Outcome:
  id:
  initiative_ref:
  metric:
  expected_value:
  observed_value:
  delta:
  observed_at:
  interpretation:
  confidence:
```

---

# 30. Learning

## 30.1 Définition

Un Learning est une connaissance généralisable issue d’une expérience réelle.

```yaml
Learning:
  id:
  source_outcome_refs:
  statement:
  scope:
  confidence:
  applicable_conditions:
  related_claim_refs:
  created_at:
```

---

# 31. Cycle complet des objets vivants

```text
Source
↓
Artifact
↓
Observation
↓
Claim
↓
Signal
↓
Situation
↓
Expression
├── Opportunity
└── Risk
     ↓
Investigation
↓
Hypothesis
↓
ExpertContribution
↓
Scenario
↓
Decision
↓
Initiative
↓
Outcome
↓
Learning
↓
Claim / Signal / future Investigation
```

---

# 32. La notion de maturité

La maturité représente l’avancement de la compréhension.

Exemple générique :

```text
0 — RAW
1 — OBSERVED
2 — CORRELATED
3 — INTERPRETED
4 — CROSS_VALIDATED
5 — MATURE
```

La maturité ne doit pas être interprétée comme vérité.

---

# 33. La notion de confiance

`confidence` exprime la crédibilité.

Exemple :

```text
0.00 → 1.00
```

Sources possibles du calcul :

- nombre de preuves ;
- indépendance ;
- fraîcheur ;
- cohérence ;
- validation croisée ;
- contradiction ;
- validation humaine ;
- historique de fiabilité.

---

# 34. Maturité vs confiance

Exemple :

```text
Situation A
maturity = 0.95
confidence = 0.58
```

Cela signifie :

> L’analyse est avancée, mais les preuves restent contradictoires.

---

# 35. Provenance

Toute donnée dérivée doit pouvoir exposer :

```text
who
what
when
from where
how
```

```yaml
Provenance:
  created_by:
  created_at:
  source_refs:
  workflow_ref:
  agent_execution_ref:
  model_ref:
  tool_refs:
```

---

# 36. Temporalité

Méridian distingue :

### Observed time
Quand le fait a été observé.

### Valid time
Quand il était vrai dans l’entreprise.

### System time
Quand Méridian l’a appris.

### Processing time
Quand un traitement l’a utilisé.

---

# 37. Bitemporalité

Exemple :

```text
La dépendance a cessé d’exister le 10 mars.
Méridian le découvre le 12 mars.
```

Alors :

```text
valid_to = 2026-03-10
discovered_at = 2026-03-12
```

---

# 38. Versioning

Les objets nécessitant un historique fort :

- Claim ;
- Relationship ;
- Domain ;
- Decision ;
- ExpertDefinition ;
- TwinSummary.

Pattern :

```text
entity_id = CLM-100
version = 4
supersedes = CLM-100:v3
```

---

# 39. Identité et Entity Resolution

Un objet d’entreprise peut posséder plusieurs alias.

```yaml
EntityIdentity:
  canonical_id:
  canonical_name:
  aliases:
  external_ids:
  identity_confidence:
```

---

# 40. Exemple TBT

```text
Canonical:
APP-2748

Aliases:
- TBT
- tbt
- transaction-batch-tool
- service-tbt

External IDs:
- CMDB:2748
- GitHub:tbt
- Datadog:service:tbt
```

---

# 41. Résolution d’identité

États :

```text
CANDIDATE
PROBABLE
CONFIRMED
REJECTED
```

Une fusion d’identité doit être réversible.

---

# 42. Information Architecture

Le produit ne doit pas exposer directement les tables techniques.

L’information est organisée autour de quatre niveaux.

## 42.1 Niveau 1 — Attention

Ce qui mérite attention.

Objets :

- Opportunity ;
- Risk ;
- Situation ;
- Decision pending ;
- Outcome.

Surface principale :

**Aujourd’hui**

## 42.2 Niveau 2 — Compréhension

Pourquoi cela compte.

Objets :

- Expression ;
- Investigation ;
- Hypothesis ;
- Scenario.

## 42.3 Niveau 3 — Connaissance

Ce que Méridian sait.

Objets :

- Twin ;
- Claim ;
- Relationship ;
- Domain ;
- Learning.

## 42.4 Niveau 4 — Preuve

Pourquoi Méridian le sait.

Objets :

- Evidence ;
- Artifact ;
- Source.

---

# 43. Navigation sémantique

Chaque objet doit permettre de descendre ou remonter.

Exemple :

```text
Opportunity
→ Investigation
→ Hypothesis
→ Claim
→ Evidence
→ Source
```

Et inversement :

```text
Source
→ Claims produits
→ Situations affectées
→ Opportunités
→ Decisions
```

---

# 44. Atlas comme projection informationnelle

Atlas ne contient pas un modèle métier séparé.

Il projette :

- Twins ;
- Domains ;
- Relationships ;
- Situations ;
- Risks ;
- Opportunities.

La carte est donc une **vue** du Domain Model.

---

# 45. Feed comme projection temporelle

Le Feed est une projection de changements :

```text
ClaimChanged
TwinUpdated
RelationshipDiscovered
OpportunityCreated
DecisionRecorded
OutcomeObserved
```

---

# 46. Flore comme projection conversationnelle

Flore ne stocke pas une vérité différente.

Elle compose une réponse à partir du modèle.

```text
User question
↓
Entity resolution
↓
Relevant domain objects
↓
Evidence
↓
Synthesis
```

---

# 47. Search Model

Tout objet indexable possède un `SearchDocument`.

```yaml
SearchDocument:
  entity_type:
  entity_id:
  title:
  summary:
  keywords:
  domain_refs:
  twin_refs:
  temporal_scope:
  security_scope:
  embedding:
```

---

# 48. Projection vs source de vérité

```text
Aurora/PostgreSQL → état autoritatif
Neptune → projection relationnelle
OpenSearch → projection de recherche
Atlas → projection visuelle
Flore response → projection conversationnelle
Report → projection documentaire
```

---

# 49. Règles d’intégrité

## IR-01
Aucun Claim `MATURE` sans Evidence.

## IR-02
Une Evidence référence toujours un Artifact ou une Source humaine traçable.

## IR-03
Une Decision doit référencer une Investigation ou une justification explicite.

## IR-04
Un Outcome doit référencer une Initiative.

## IR-05
Un Learning doit référencer au moins un Outcome ou une Investigation historique.

## IR-06
Une Opportunity doit avoir une Expression ou une création humaine explicitement tracée.

## IR-07
Toute relation inférée doit avoir `confidence + origin`.

## IR-08
Un Unknown ne doit pas disparaître sans résolution ou justification.

---

# 50. Suppression

La suppression physique doit être rare pour les objets historiques.

Préférer :

```text
ACTIVE
INACTIVE
SUPERSEDED
ARCHIVED
REDACTED
```

---

# 51. Data Retention

La rétention varie selon le type.

### Evidence
Selon politique source.

### Decisions
Longue durée.

### Agent execution logs
Durée plus courte.

### Search projections
Reconstructibles.

---

# 52. Security Classification

Chaque objet peut hériter d’une classification.

```text
PUBLIC_INTERNAL
CONFIDENTIAL
RESTRICTED
HIGHLY_RESTRICTED
```

Un Claim construit à partir d’une Evidence `RESTRICTED` ne devient pas automatiquement public.

Il faut une politique de dérivation.

---

# 53. Tenant boundary

En mode SaaS :

```text
tenant_id
```

est obligatoire pour tous les Aggregate Roots.

Aucune relation ne traverse deux tenants.

---

# 54. Scope

```yaml
Scope:
  twin_refs:
  domain_refs:
  team_refs:
  temporal_scope:
  geography:
  organization_scope:
```

Il est utilisé dans :

- Flore ;
- investigations ;
- experts ;
- recherche ;
- permissions.

---

# 55. Annotation humaine

Les humains peuvent :

- confirmer ;
- commenter ;
- corriger ;
- contester ;
- ajouter une preuve.

```yaml
HumanAnnotation:
  id:
  target_ref:
  author_ref:
  annotation_type:
  content:
  created_at:
  authority_level:
```

---

# 56. Authority Level

Toutes les contributions humaines ne sont pas équivalentes.

```text
USER_NOTE
DOMAIN_EXPERT
APPLICATION_OWNER
RISK_APPROVER
SYSTEM_OF_RECORD
```

---

# 57. Événements de domaine

## Twin

```text
TwinCreated
TwinSourceConnected
TwinKnowledgeUpdated
TwinRelationshipDiscovered
TwinArchived
```

## Claim

```text
ClaimProposed
ClaimSupported
ClaimStrengthened
ClaimContested
ClaimInvalidated
```

## Opportunity

```text
OpportunityDetected
OpportunityQualified
OpportunityRejected
OpportunityInvestigationStarted
```

## Investigation

```text
InvestigationOpened
HypothesisAdded
ExpertContributionAdded
InvestigationReadyForDecision
```

## Decision

```text
DecisionRecorded
DecisionSuperseded
```

## Initiative

```text
InitiativeStarted
OutcomeObserved
```

## Learning

```text
LearningCreated
LearningReused
```

---

# 58. Exemple complet — opportunité

```text
OBS-120
latence en hausse

OBS-121
reprises manuelles en hausse

CLM-900
le parcours P dépend du service X

SIG-81
dégradation temporelle détectée

SIT-33
corrélation parcours P / service X

EXP-14
friction progressive dans le parcours

OPP-7
simplification potentielle du processus

INV-11
investigation ouverte

HYP-4
validation X est la cause

EXC-21
expert processus

SCN-3
supprimer validation

DEC-2
scénario 3 retenu

INI-2
modification déployée

OUT-2
délai -11 %

LRN-4
amélioration client mais reprise manuelle +4 %
```

---

# 59. Exemple complet — TBT

```text
Twin: APP-2748
Name: TBT

Claim:
TBT IMPLEMENTS Validation de lot

Evidence:
git commit + code lines

Relationship:
TBT CALLS EligibilityService

Domain:
Traitement transactionnel

Unknown:
Rôle exact de LegacyQueue

Signal:
nouvelle dépendance découverte

Expression:
changement d’architecture émergent

Investigation:
impact de suppression TBT

Scenario:
migration progressive

Decision:
retain scenario B

Outcome:
migration réduit dépendance X

Learning:
les consommateurs batch historiques sont plus nombreux que la CMDB ne l’indiquait
```

---

# 60. Bounded contexts informationnels

```text
Source Context
→ Source, Artifact, Observation

Twin Context
→ Twin, TwinSummary

Knowledge Context
→ Claim, Evidence, Relationship, Unknown, Contradiction

Signal Context
→ Signal, Situation, Expression

Opportunity Context
→ Opportunity, Risk

Investigation Context
→ Investigation, Hypothesis

Expertise Context
→ Expert, ExpertContribution

Decision Context
→ Scenario, Decision, Initiative

Learning Context
→ Outcome, Learning
```

---

# 61. Références entre bounded contexts

Utiliser principalement des IDs.

Éviter des aggregates géants.

Exemple :

```text
Investigation
  hypothesis_refs[]
  evidence_refs[]
  scenario_refs[]
```

et non l’ensemble des objets imbriqués en mémoire.

---

# 62. Duplication contrôlée

Certaines données peuvent être copiées dans des projections pour performance.

Exemple :

```text
OpportunityCard
title
impact_summary
confidence
domain_names
```

Mais la source canonique reste `Opportunity + Domain`.

---

# 63. Snapshot

Un snapshot est utile lors de :

- décision ;
- rapport officiel ;
- audit ;
- clôture investigation.

Il représente l’état connu à un instant donné.

```yaml
DecisionEvidenceSnapshot:
  decision_id:
  captured_at:
  claim_versions:
  evidence_refs:
  scenario_versions:
  investigation_version:
```

Cela permet de comprendre une décision même si Méridian apprend ensuite de nouveaux faits.

---

# 64. Derived objects

Certains objets sont dérivés :

- TwinSummary ;
- OpportunityScore ;
- InvestigationSummary ;
- DomainProposal ;
- SearchDocument.

Ils doivent être recalculables.

---

# 65. Objets autoritatifs vs projections

## Autoritatifs

- Claim ;
- Evidence ;
- Investigation ;
- Decision ;
- Outcome.

## Projections

- résumé ;
- recherche ;
- Atlas layout ;
- feed card ;
- dashboard aggregate.

---

# 66. Information freshness

Chaque objet dérivé doit pouvoir indiquer :

```text
generated_at
based_on_versions
stale
```

---

# 67. Unknown propagation

Un Unknown critique peut limiter confidence.

Exemple :

```text
Hypothesis confidence = 0.82
Critical unknown = customer segment impact

Decision recommendation confidence reduced to 0.65
```

---

# 68. Contradiction resolution

Résolutions possibles :

```text
LEFT_WINS
RIGHT_WINS
TEMPORAL_SPLIT
BOTH_VALID_DIFFERENT_SCOPE
UNRESOLVED
MERGED
```

---

# 69. Temporal split

Exemple :

```text
CMDB: A DEPENDS_ON B
Trace: no longer observed

Resolution:
relation valide jusqu’au 14 juin
inactive après le 14 juin
```

---

# 70. Data lineage

Une connaissance dérivée doit maintenir une lignée.

```text
Source
→ Artifact
→ Observation
→ Claim
→ Expression
→ Decision
```

Cela permet audit et suppression gouvernée.

---

# 71. Graph model de haut niveau

```text
(Twin)-[:SUPPORTS]->(Capability)
(Twin)-[:PART_OF]->(Domain)
(Twin)-[:CALLS]->(Twin)
(Process)-[:USES]->(Capability)
(Journey)-[:TOUCHES]->(Process)
(Claim)-[:ABOUT]->(Twin)
(Claim)-[:SUPPORTED_BY]->(Evidence)
(Investigation)-[:TESTS]->(Hypothesis)
(Decision)-[:SELECTS]->(Scenario)
(Learning)-[:DERIVED_FROM]->(Outcome)
```

---

# 72. Relation entre Claim et Graph

Le graphe ne remplace pas le Claim.

Exemple :

```text
Edge:
TBT CALLS ServiceX

Claim:
affirmation avec preuves, dates, confiance, provenance.
```

L’edge est une projection de la connaissance structurée.

---

# 73. Relation entre Expression et Claim

Une Expression synthétise plusieurs Claims.

Elle ne doit pas devenir elle-même la source de vérité.

---

# 74. Relation entre Learning et Claim

Un Learning peut proposer un nouveau Claim.

Mais il reste identifiable comme connaissance issue d’une expérience.

---

# 75. Data Contracts

Tous les contrats échangés entre services doivent contenir :

```text
id
type
version
tenant
timestamp
correlation_id
schema_version
```

---

# 76. Naming conventions

Préfixes possibles :

```text
TWN
SRC
ART
OBS
EVD
CLM
REL
UNK
CTR
SIG
SIT
EXP
OPP
RSK
INV
HYP
EXC
SCN
DEC
INI
OUT
LRN
DOM
CAP
```

---

# 77. URI interne

Forme possible :

```text
meridian://twin/TWN-2748
meridian://claim/CLM-100
meridian://investigation/INV-44
```

Pratique pour navigation et références inter-objets.

---

# 78. API resource model

Exemples :

```text
GET /twins/{id}
GET /claims/{id}
GET /opportunities/{id}
GET /investigations/{id}
GET /decisions/{id}
```

Sous-ressources :

```text
/twins/{id}/claims
/investigations/{id}/hypotheses
/claims/{id}/evidence
```

---

# 79. Recherche transversale

Recherche par :

- terme ;
- type ;
- domaine ;
- jumeau ;
- temps ;
- confiance ;
- statut ;
- owner.

---

# 80. Information Architecture — page Twin

```text
Twin
├── Summary
├── Capabilities
├── Claims
├── Relationships
├── Timeline
├── Sources
├── Unknowns
├── Contradictions
└── Activity
```

---

# 81. Information Architecture — Opportunity

```text
Opportunity
├── Why now
├── Potential value
├── Evidence
├── Affected area
├── Confidence
├── Unknowns
├── Investigation
└── History
```

---

# 82. Information Architecture — Investigation

```text
Investigation
├── Question
├── Summary
├── Timeline
├── Hypotheses
├── Evidence
├── Experts
├── Contradictions
├── Scenarios
└── Decision
```

---

# 83. Information Architecture — Decision

```text
Decision
├── Selected scenario
├── Rationale
├── Evidence snapshot
├── Approvers
├── Expected outcomes
├── Initiative
└── Observed outcomes
```

---

# 84. Information Architecture — Learning

```text
Learning
├── What happened
├── Where
├── Under what conditions
├── Evidence
├── Confidence
├── Related decisions
└── Reuse history
```

---

# 85. Maturité d’un Twin

Un Twin peut exposer :

```text
Source coverage
Claim coverage
Relationship coverage
Temporal depth
Unknown count
Contradiction count
Freshness
Confidence
```

Ne pas réduire cela à un seul score opaque.

---

# 86. Maturité d’une Opportunity

Critères :

- preuves suffisantes ;
- impact identifiable ;
- périmètre compris ;
- inconnues tolérables ;
- valeur plausible.

---

# 87. Maturité d’une Investigation

Critères :

- question cadrée ;
- hypothèses testées ;
- contradictions examinées ;
- scénarios construits ;
- incertitudes explicites.

---

# 88. Lifecycle global

```text
DISCOVER
→ KNOW
→ CORRELATE
→ EXPRESS
→ INVESTIGATE
→ DECIDE
→ OBSERVE
→ LEARN
```

---

# 89. Anti-patterns du modèle

## Claim comme texte libre uniquement

Impossible à relier correctement.

## Écraser les Claims

Perte historique.

## Confondre Observation et interprétation

Risque de faux faits.

## Stocker tout dans le graphe

Responsabilités mélangées.

## Supprimer les contradictions après résolution

Perte de traçabilité.

## Mélanger Opportunity et Investigation

Une opportunité peut exister sans investigation.

## Decision sans snapshot

Impossible d’expliquer le contexte historique.

## Learning comme résumé vague

Doit être relié aux résultats.

---

# 90. Minimum Viable Domain Model

Pour le MVP :

```text
Twin
Source
Artifact
Evidence
Claim
Relationship
Signal
Situation
Expression
Opportunity
Investigation
Hypothesis
ExpertContribution
Scenario
Decision
Outcome
```

`Learning` peut suivre immédiatement.

---

# 91. Ordre d’implémentation du modèle

```text
1. Identity + IDs
2. Source / Artifact / Evidence
3. Twin
4. Claim
5. Relationship
6. Temporal/version model
7. Signal/Situation/Expression
8. Opportunity
9. Investigation/Hypothesis
10. Scenario/Decision
11. Outcome/Learning
```

---

# 92. Tests de cohérence du modèle

Le modèle doit pouvoir répondre à ces questions :

1. Pourquoi Méridian croit-il que TBT dépend de X ?
2. Quand cette dépendance est-elle apparue ?
3. Est-elle toujours valide ?
4. Qui ou quoi l’a confirmée ?
5. Existe-t-il une contradiction ?
6. Quelle investigation l’a utilisée ?
7. Quelle décision a été prise sur cette base ?
8. Quel résultat a été observé après cette décision ?
9. Quel apprentissage en a été tiré ?

Si une de ces réponses devient impossible, le modèle est incomplet.

---

# 93. Vue conceptuelle finale

```text
ENTERPRISE REALITY
      │
      ▼
Source
      │
      ▼
Artifact
      │
      ▼
Observation
      │
      ▼
Evidence ───────┐
                ▼
              Claim
                │
          ┌─────┴─────┐
          ▼           ▼
    Relationship    Unknown
          │
          ▼
        Signal
          │
          ▼
      Situation
          │
          ▼
      Expression
        /       \
       ▼         ▼
Opportunity    Risk
       \         /
        ▼       ▼
      Investigation
          │
      Hypothesis
          │
     ExpertContribution
          │
       Scenario
          │
       Decision
          │
      Initiative
          │
       Outcome
          │
       Learning
          │
          └──────────────→ enrichit future Claims / Signals
```

---

# 94. Conclusion

Le Domain Model de Méridian doit préserver une distinction claire entre :

- ce qui est observé ;
- ce qui est affirmé ;
- ce qui est interprété ;
- ce qui est supposé ;
- ce qui est décidé ;
- ce qui est réellement obtenu.

Cette séparation est fondamentale.

Elle empêche Méridian de devenir un système dans lequel une réponse générée par un agent se transforme silencieusement en vérité.

La structure fondamentale est :

> **Observation → Evidence → Claim → Expression → Investigation → Decision → Outcome → Learning**

Et autour de cette chaîne vivent :

- les Twins ;
- les Relationships ;
- les Domains ;
- les Unknowns ;
- les Contradictions ;
- les Experts ;
- les Opportunities ;
- les Risks.

Le prochain document recommandé est :

> **MÉRIDIAN — Agentic Architecture & Expert Framework**

Il devra définir précisément comment sont construits les experts, comment ils sont sélectionnés, comment ils raisonnent, comment ils utilisent les outils et la connaissance, comment ils se contredisent, comment ils produisent des sorties structurées et comment Méridian contrôle leur coût, leur confiance et leur autonomie.
