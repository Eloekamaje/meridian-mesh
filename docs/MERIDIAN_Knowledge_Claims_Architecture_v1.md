# MÉRIDIAN — Knowledge & Claims Architecture
## Architecture de la connaissance, Claims, preuves, temporalité, maturation, contradiction et propagation dans le Mesh

**Statut :** Architecture de connaissance de référence  
**Version :** 1.0  
**Produit :** MÉRIDIAN  
**Tagline :** **DÉCOUVRIR · COMPRENDRE · DÉCIDER**

---

# 0. Objet du document

Ce document définit le **cerveau informationnel de Méridian**.

Il répond à la question :

> **Comment Méridian transforme-t-il des données dispersées en connaissances fiables, sourcées, temporelles, contradictoires et exploitables ?**

Il complète :

- la Product Vision ;
- le Product Blueprint ;
- la Functional Architecture ;
- la Technical Architecture ;
- le Domain Model & Information Architecture ;
- l’Agentic Architecture & Expert Framework.

Le cœur de cette architecture est le **Claim**.

Le Claim est l’unité de connaissance explicite de Méridian.

Il permet au système de distinguer :

- ce qui a été observé ;
- ce qui a été interprété ;
- ce qui est affirmé ;
- ce qui est prouvé ;
- ce qui est contesté ;
- ce qui était vrai avant ;
- ce qui est encore vrai maintenant.

Le cycle général est :

> **Source → Artifact → Observation → Evidence → Claim → Maturation → Reconciliation → Mesh Knowledge → Exploitation**

---

# 1. Principes fondamentaux

## 1.1 La connaissance ne doit jamais être un texte opaque

Méridian ne doit pas stocker uniquement :

> « TBT dépend de Service X et semble critique. »

Il doit pouvoir représenter séparément :

```text
Claim 1:
TBT CALLS ServiceX

Claim 2:
ServiceX SUPPORTS CapabilityY

Claim 3:
TBT IS_CRITICAL_FOR ProcessZ
```

Avec pour chacun :

- preuves ;
- dates ;
- provenance ;
- confiance ;
- contradictions ;
- statut.

---

## 1.2 Une source n’est pas une vérité

GitHub peut être exact sur le code.

La CMDB peut être officielle sur l’organisation.

Datadog peut refléter le comportement réel.

Confluence peut refléter l’intention.

Ces sources peuvent être en désaccord.

Méridian doit conserver ce désaccord.

---

## 1.3 Une preuve n’est pas une conclusion

Une Evidence peut supporter un Claim.

Mais le Claim reste une affirmation interprétée.

---

## 1.4 Un Claim peut être faux, obsolète ou partiellement vrai

Le modèle doit supporter :

```text
VALID
PARTIALLY_VALID
CONTESTED
INVALIDATED
HISTORICAL
UNKNOWN
```

---

## 1.5 Le temps est natif

Une connaissance peut être :

> vraie du 1er janvier au 14 juin.

Puis fausse après.

Méridian ne doit pas écraser le passé.

---

## 1.6 La contradiction est une information

Une contradiction n’est pas seulement une erreur à corriger.

Elle peut révéler :

- changement récent ;
- documentation obsolète ;
- comportement inattendu ;
- différence de scope ;
- dette organisationnelle.

---

# 2. Architecture cognitive globale

```text
ENTERPRISE SOURCES
       │
       ▼
   ARTIFACTS
       │
       ▼
  OBSERVATIONS
       │
       ▼
    EVIDENCE
       │
       ▼
 CLAIM CANDIDATES
       │
       ▼
 CLAIM VALIDATION
       │
       ▼
  LOCAL KNOWLEDGE
       │
       ▼
 CROSS-TWIN RECONCILIATION
       │
       ▼
   MESH KNOWLEDGE
       │
       ▼
 MATURATION / EXPRESSION
       │
       ▼
 OPPORTUNITY / INVESTIGATION / DECISION
```

---

# 3. Les niveaux de connaissance

Méridian doit distinguer plusieurs niveaux.

## Niveau 0 — Donnée brute

Exemple :

```text
ligne de code
log
ticket
champ DB
métrique
```

## Niveau 1 — Observation

> Un appel HTTP vers `/eligibility` est présent dans le code.

## Niveau 2 — Evidence

> Ce commit contient un appel vers `EligibilityService`.

## Niveau 3 — Claim

> TBT appelle EligibilityService.

## Niveau 4 — Relation / connaissance structurée

```text
TBT ─CALLS→ EligibilityService
```

## Niveau 5 — Connaissance contextualisée

> TBT appelle EligibilityService pour une étape de validation du lot.

## Niveau 6 — Connaissance transverse

> Le parcours X dépend indirectement de TBT via EligibilityService.

## Niveau 7 — Expression

> Une dépendance critique non documentée semble exister dans le parcours X.

---

# 4. Source

Une Source représente l’origine externe.

Exemples :

```text
GitHub
Jira
Confluence
Datadog
Splunk
Oracle
PostgreSQL
CMDB
ServiceNow
Human Contribution
```

Une Source possède :

```yaml
Source:
  id:
  type:
  system:
  owner:
  authority:
  freshness_policy:
  access_policy:
  classification:
  reliability_profile:
```

---

# 5. Authority d’une Source

Toutes les sources ne sont pas autoritatives pour les mêmes faits.

Exemple :

```text
GitHub
→ autoritatif sur le code

CMDB
→ déclaratif sur ownership / inventory

Runtime traces
→ autoritatif sur comportement observé

Confluence
→ contexte / intention / architecture documentée
```

Méridian doit donc utiliser une notion de :

```text
Authority by ClaimType
```

---

# 6. Source Reliability Profile

Une Source peut être historiquement plus ou moins fiable.

```yaml
ReliabilityProfile:
  source_id:
  claim_type:
  historical_accuracy:
  freshness_score:
  completeness_score:
  contradiction_rate:
```

Ce score ne remplace jamais les preuves du cas courant.

---

# 7. Artifact

Un Artifact est l’unité récupérée.

Exemples :

```text
Git file
Commit
PR
Jira ticket
Confluence page
Trace
Log segment
DB schema
Table metadata
Metric series
```

---

# 8. Artifact Version

Une Evidence importante doit référencer une version stable.

```yaml
ArtifactVersion:
  artifact_id:
  version:
  content_hash:
  observed_at:
  source_cursor:
  immutable_ref:
```

---

# 9. Observation

## 9.1 Définition

Une Observation représente un fait extrait avec faible interprétation.

Exemple :

> `PaymentService.java` contient un appel à `EligibilityClient.check()`.

---

## 9.2 Structure

```yaml
Observation:
  id:
  observation_type:
  subject_ref:
  value:
  observed_at:
  artifact_ref:
  extractor:
  extraction_confidence:
```

---

# 10. Extraction Confidence

L’extraction peut être :

```text
DETERMINISTIC
HIGH
MEDIUM
LOW
```

Exemple :

AST parser :

```text
DETERMINISTIC
```

LLM extraction :

```text
MEDIUM/HIGH selon validation
```

---

# 11. Evidence

Une Evidence est une Observation rendue exploitable pour une affirmation.

```yaml
Evidence:
  id:
  observation_ref:
  artifact_ref:
  locator:
  evidence_type:
  relevance:
  validity:
  access_policy:
```

---

# 12. Evidence Type

```text
CODE
RUNTIME
DOCUMENT
TICKET
DATABASE
METRIC
TRACE
LOG
HUMAN
EXTERNAL_REFERENCE
```

---

# 13. Evidence Locator

Exemples :

```text
git://repo/commit/path#L140-L166
jira://TBT-918
confluence://page/22901#section-3
trace://service/tbt/span/...
metric://tbt.latency?p95&from=...
db://schema/table/column
```

---

# 14. Evidence Strength

La force d’une Evidence dépend de :

- pertinence ;
- spécificité ;
- fraîcheur ;
- autorité ;
- indépendance ;
- stabilité.

---

# 15. Evidence Independence

Deux preuves issues du même document ne sont pas nécessairement indépendantes.

Exemple :

```text
Jira ticket
Confluence page copiée du Jira
```

Ne doivent pas compter comme deux sources indépendantes fortes.

---

# 16. Evidence Bundle

Une affirmation peut être supportée par un bundle.

```yaml
EvidenceBundle:
  id:
  evidence_refs:
  independence_groups:
  coverage:
  strength:
```

---

# 17. Claim Candidate

Un Claim Candidate est une affirmation proposée mais non encore validée.

Sources :

- extractor ;
- jumeau ;
- expert ;
- humain ;
- Mesh.

---

# 18. Claim Grammar

Forme de base :

```text
Subject
Predicate
Object
Qualifier
Time
Scope
```

Exemple :

```text
TBT
CALLS
EligibilityService
purpose=VALIDATE_BATCH
valid_from=2025-04-12
scope=Production
```

---

# 19. Claim Structure

```yaml
Claim:
  id:
  version:
  claim_type:
  subject_ref:
  predicate:
  object_ref_or_value:
  qualifiers:
  scope:
  origin:
  status:
  maturity:
  confidence:
  valid_from:
  valid_to:
  observed_at:
  discovered_at:
  evidence_refs:
  contradiction_refs:
  supersedes:
```

---

# 20. Claim Types

Familles principales :

## Structure

```text
DEPENDS_ON
CALLS
READS
WRITES
PUBLISHES
CONSUMES
OWNED_BY
PART_OF
```

## Fonction

```text
IMPLEMENTS
SUPPORTS_CAPABILITY
EXECUTES_RULE
PROVIDES_FUNCTION
```

## Métier

```text
BUSINESS_RULE
PROCESS_STEP
DECISION_RULE
ELIGIBILITY_RULE
```

## Temps

```text
CHANGED_AT
INTRODUCED_AT
DEPRECATED_AT
```

## Impact

```text
AFFECTS_CUSTOMER
AFFECTS_EMPLOYEE
AFFECTS_PROCESS
CREATES_RISK
```

---

# 21. Claim Qualifiers

Les Qualifiers évitent de multiplier artificiellement les predicates.

Exemple :

```yaml
qualifiers:
  environment: PROD
  purpose: VALIDATION
  channel: MOBILE
  customer_segment: RETAIL
```

---

# 22. Claim Scope

Un Claim peut être vrai seulement dans un certain scope.

```yaml
Scope:
  environment:
  geography:
  domain:
  channel:
  customer_segment:
  business_unit:
```

---

# 23. Claim Origin

```text
OBSERVED
INFERRED
DECLARED
HUMAN_CONFIRMED
EXPERT_PROPOSED
MESH_DERIVED
```

---

# 24. Claim Status

Cycle recommandé :

```text
CANDIDATE
↓
PROPOSED
↓
SUPPORTED
↓
STRENGTHENED
↓
MATURE
```

Branches :

```text
CONTESTED
INVALIDATED
HISTORICAL
```

---

# 25. Claim Maturity

La maturité représente le degré d’élaboration.

Proposition :

```text
M0 RAW
M1 EXTRACTED
M2 EVIDENCED
M3 CORRELATED
M4 CROSS_VALIDATED
M5 MATURE
```

---

# 26. Claim Confidence

La confiance exprime :

> à quel point Méridian estime que le Claim est crédible.

Score :

```text
0.00 → 1.00
```

Mais l’UI peut préférer :

```text
Faible
Moyenne
Élevée
Très élevée
```

---

# 27. Confidence Architecture

Le score ne doit pas être produit uniquement par le LLM.

Pipeline :

```text
Evidence Features
+ Source Reliability
+ Cross-Source Agreement
+ Temporal Consistency
+ Expert Validation
- Contradictions
- Staleness
- Ambiguity
↓
Confidence Engine
```

---

# 28. Exemple de Confidence Formula

Conceptuellement :

```text
confidence =
    evidence_strength
  × source_diversity
  × freshness
  × consistency
  × scope_match
  - contradiction_penalty
```

Ce n’est pas nécessairement une formule linéaire.

---

# 29. Confidence Calibration

Le score doit être calibré sur des cas historiques.

Exemple :

Si les Claims à 0.8 sont vrais seulement 55 % du temps, le système est mal calibré.

---

# 30. Confidence by Claim Type

La confiance doit être calibrée différemment selon le type.

Exemple :

```text
CALLS
```

est souvent détectable de manière déterministe.

```text
SUPPORTS_BUSINESS_CAPABILITY
```

nécessite davantage d’interprétation.

---

# 31. Claim Validation Pipeline

```text
Candidate Claim
↓
Schema validation
↓
Entity resolution
↓
Duplicate detection
↓
Evidence validation
↓
Scope validation
↓
Temporal validation
↓
Conflict detection
↓
Confidence computation
↓
Persist as PROPOSED/SUPPORTED
```

---

# 32. Duplicate Detection

Deux Claims peuvent être :

```text
EXACT_DUPLICATE
SEMANTIC_DUPLICATE
SUBSUMED
OVERLAPPING
DISTINCT
```

---

# 33. Claim Merge

Exemple :

```text
Claim A:
TBT CALLS EligibilityService
confidence 0.72

Claim B:
TBT CALLS EligibilityService
confidence 0.81
```

Ils ne doivent pas nécessairement rester deux objets.

Le système peut créer une version renforcée.

---

# 34. Claim Supersession

Exemple :

```text
CLM-100 v1
TBT CALLS OldService
```

Puis :

```text
CLM-100 v2
TBT CALLS NewService
```

Le v1 devient historique si le changement est temporel.

---

# 35. Claim Invalidation

Un Claim peut être invalidé lorsque :

- preuve source supprimée ;
- erreur d’extraction ;
- entité mal résolue ;
- contradiction décisive ;
- validation humaine contraire.

---

# 36. Invalidation Propagation

Lorsqu’un Claim critique est invalidé :

```text
ClaimInvalidated
↓
Affected Relationships
↓
Affected Twin Summary
↓
Affected Situations
↓
Affected Opportunities
↓
Affected Investigations
```

---

# 37. Knowledge Dependency Graph

Méridian doit connaître :

> quels objets dépendent de quels Claims.

Exemple :

```text
Opportunity OPP-7
depends_on
CLM-10
CLM-11
CLM-14
```

Cela permet l’invalidation incrémentale.

---

# 38. Knowledge Fingerprint

Une synthèse peut être liée à :

```text
hash(
  CLM-10:v3
  CLM-11:v2
  CLM-14:v7
)
```

Si une version change, la synthèse peut devenir stale.

---

# 39. Staleness

Tout objet dérivé peut être :

```text
FRESH
POTENTIALLY_STALE
STALE
```

---

# 40. Claim Freshness

La fraîcheur dépend du type.

Exemple :

```text
Architecture relation:
fresh for days/weeks

Runtime behavior:
fresh for minutes/hours

Ownership:
fresh for days

Regulatory rule:
fresh until new version
```

---

# 41. Temporal Knowledge

Chaque Claim important porte :

```text
valid_from
valid_to
observed_at
discovered_at
```

---

# 42. Valid Time vs System Time

Exemple :

```text
Dependency removed on June 10
Méridian learns it on June 12
```

Alors :

```text
valid_to = June 10
discovered_at = June 12
```

---

# 43. Temporal Query

Méridian doit pouvoir répondre :

> Que croyions-nous le 9 juin ?

et :

> Que savons-nous aujourd’hui de ce qui était vrai le 9 juin ?

Ce sont deux questions différentes.

---

# 44. Claim Timeline

```text
v1 PROPOSED
↓
v2 SUPPORTED
↓
v3 MATURE
↓
v4 HISTORICAL
```

---

# 45. Relationship as Projection

Une Relationship dans le Graph est souvent une projection d’un ou plusieurs Claims.

Exemple :

```text
TBT ─CALLS→ ServiceX
```

provient de :

```text
CLM-100
CLM-101
```

---

# 46. Edge Metadata

```yaml
GraphEdge:
  from:
  type:
  to:
  source_claim_refs:
  confidence:
  valid_from:
  valid_to:
```

---

# 47. Local Knowledge

Chaque Twin maintient une connaissance locale.

```text
Twin Local Knowledge
├── Claims about self
├── outgoing relationships
├── incoming known relationships
├── business capabilities
├── rules
├── history
├── unknowns
└── contradictions
```

---

# 48. Local Claim Ownership

Un Twin peut être le producteur principal d’un Claim.

Exemple :

```text
TBT claims:
TBT CALLS X
```

Mais X peut également observer :

```text
X RECEIVES_FROM TBT
```

Le Mesh rapproche les deux.

---

# 49. Cross-Twin Confirmation

Exemple :

Twin TBT :

```text
TBT CALLS X
```

Twin X :

```text
X RECEIVES_REQUEST_FROM TBT
```

Runtime traces :

```text
TBT → X
```

Le Mesh peut renforcer la relation.

---

# 50. Cross-Twin Conflict

Twin A :

```text
A CALLS B
```

Twin B :

```text
B reports no observed calls from A
```

Ce n’est pas automatiquement une contradiction fatale.

Possible :

- environnement différent ;
- période différente ;
- code mort ;
- feature flag.

---

# 51. Reconciliation Engine

Pipeline :

```text
Claims
↓
Entity Alignment
↓
Predicate Normalization
↓
Scope Alignment
↓
Temporal Alignment
↓
Evidence Comparison
↓
Agreement / Conflict / Partial Match
```

---

# 52. Reconciliation Result

```text
CONFIRMED
PARTIALLY_CONFIRMED
CONFLICTING
DIFFERENT_SCOPE
DIFFERENT_TIME
UNRESOLVED
```

---

# 53. Contradiction

Structure :

```yaml
Contradiction:
  id:
  claim_refs:
  contradiction_type:
  scope:
  temporal_scope:
  severity:
  explanation:
  status:
```

---

# 54. Contradiction Types

```text
VALUE_CONFLICT
RELATIONSHIP_CONFLICT
TEMPORAL_CONFLICT
SCOPE_CONFLICT
SOURCE_CONFLICT
MODEL_CONFLICT
EXPERT_CONFLICT
```

---

# 55. Contradiction Resolution

Résolutions :

```text
CLAIM_A_WINS
CLAIM_B_WINS
BOTH_VALID
TEMPORAL_SPLIT
SCOPE_SPLIT
MERGED
UNRESOLVED
```

---

# 56. Example — Temporal Split

CMDB :

```text
A DEPENDS_ON B
```

Runtime :

```text
No traffic after June 14
```

Resolution :

```text
A DEPENDS_ON B
valid_to = June 14
```

---

# 57. Unknown Architecture

Un Unknown est une connaissance explicite de ce qui manque.

```yaml
Unknown:
  id:
  entity_ref:
  question:
  importance:
  blocking:
  created_at:
  source_gap:
  resolution_strategy:
```

---

# 58. Unknown Types

```text
MISSING_SOURCE
AMBIGUOUS_ENTITY
UNKNOWN_PURPOSE
UNKNOWN_OWNER
UNKNOWN_IMPACT
UNKNOWN_RULE
UNKNOWN_CONSUMER
```

---

# 59. Knowledge Gap

Un ensemble d’Unknowns peut former un Knowledge Gap.

Exemple :

> le jumeau possède une bonne compréhension technique mais une faible compréhension métier.

---

# 60. Twin Knowledge Health

Dimensions :

```text
source coverage
claim coverage
evidence coverage
freshness
unknown density
contradiction density
temporal depth
cross-twin validation
```

---

# 61. Knowledge Health ≠ single score

L’UI doit exposer les dimensions principales.

Exemple :

```text
Technical understanding: High
Business understanding: Medium
Runtime freshness: High
Historical depth: Low
Contradictions: 3
Critical unknowns: 2
```

---

# 62. Maturation of Knowledge

La maturation ne se limite pas au Claim.

Elle opère à plusieurs niveaux.

```text
Claim maturity
Twin maturity
Situation maturity
Opportunity maturity
Investigation maturity
```

---

# 63. Claim Maturation Rules

Exemple :

Un Claim peut passer à `M4 CROSS_VALIDATED` si :

- au moins deux Evidence indépendantes ;
- pas de contradiction critique non expliquée ;
- entity resolution confirmée ;
- scope connu.

---

# 64. Maturity Engine

Le moteur de maturité est principalement déterministe/configurable.

Le LLM peut fournir des signaux mais ne décide pas seul.

---

# 65. Knowledge Quality Policies

Exemples :

```text
Critical dependency claim
→ requires runtime or code evidence

Business rule
→ requires code/doc/business evidence

Customer impact
→ requires customer/process evidence
```

---

# 66. Claim Policy Registry

```yaml
ClaimPolicy:
  claim_type:
  minimum_evidence:
  required_source_types:
  max_staleness:
  human_validation:
  minimum_confidence_for_mature:
```

---

# 67. Provenance

Chaque Claim doit pouvoir être retracé.

```text
Claim
↓
Evidence
↓
Observation
↓
Artifact
↓
Source
```

Mais aussi :

```text
Claim
↓
AgentRun
↓
Expert
↓
Workflow
```

---

# 68. Provenance Object

```yaml
Provenance:
  created_by_type:
  created_by_ref:
  workflow_ref:
  agent_run_ref:
  model_ref:
  tool_refs:
  source_refs:
  created_at:
```

---

# 69. Model Provenance

Pour les Claims proposés par IA :

```text
model
model version
prompt/expert version
tool context fingerprint
```

Doivent être conservés pour audit.

---

# 70. Human Provenance

Une contribution humaine doit conserver :

```text
author
role
authority level
time
scope
```

---

# 71. Human Claim

Un humain peut déclarer :

> TBT est propriétaire de la règle X.

Méridian l’enregistre comme :

```text
origin=DECLARED/HUMAN
```

Pas comme observation automatique.

---

# 72. Declared vs Observed

Exemple :

```text
Declared:
Team A owns Application X

Observed:
Team B performs 92% of changes
```

Méridian conserve les deux.

Cela peut produire une Expression organisationnelle.

---

# 73. Ontology Layer

Méridian a besoin d’une couche d’ontologie légère.

Elle définit :

- types d’entités ;
- types de Claims ;
- relations ;
- propriétés ;
- contraintes.

---

# 74. Ontology vs Knowledge

L’ontologie définit :

> ce qui peut être exprimé.

Les Claims définissent :

> ce que Méridian croit vrai.

---

# 75. Ontology Versioning

L’ontologie évolue.

Exemple :

```text
BUSINESS_RULE v1
```

peut être enrichi.

Les Claims historiques gardent leur compatibilité.

---

# 76. Predicate Registry

Exemple :

```yaml
Predicate:
  id: CALLS
  subject_types:
    - APPLICATION
    - SERVICE
  object_types:
    - SERVICE
    - API
  inverse: RECEIVES_FROM
  transitive: false
  temporal: true
```

---

# 77. Inverse Relations

Si :

```text
A CALLS B
```

on peut projeter :

```text
B RECEIVES_FROM A
```

Mais ce dernier peut être dérivé et non stocké comme Claim indépendant.

---

# 78. Derived Claims

Certains Claims peuvent être dérivés.

Exemple :

```text
A DEPENDS_ON B
B DEPENDS_ON C
```

peut suggérer :

```text
A INDIRECTLY_DEPENDS_ON C
```

Mais il faut distinguer :

```text
DIRECT
DERIVED
```

---

# 79. Inference Rules

Une inference rule doit être versionnée.

```yaml
InferenceRule:
  id:
  version:
  input_patterns:
  output_claim:
  confidence_policy:
```

---

# 80. LLM Inference vs Deterministic Inference

### Deterministic

Graph rules.

### LLM-assisted

Compréhension métier.

Les deux doivent être marqués différemment.

---

# 81. Business Rule Claims

Exemple :

```text
If customer age < 18
then reject application
```

Structure :

```yaml
BusinessRuleClaim:
  condition:
  action:
  exceptions:
  scope:
  evidence:
```

---

# 82. Rule Normalization

Deux règles exprimées différemment peuvent être équivalentes.

Le système peut créer une représentation normalisée.

---

# 83. Process Claims

Exemple :

```text
Step A PRECEDES Step B
```

ou :

```text
Process P REQUIRES manual validation
```

---

# 84. Customer Impact Claims

Exemple :

```text
Change X INCREASES checkout delay
```

Doit exiger des Evidence appropriées.

---

# 85. Employee Impact Claims

Exemple :

```text
Process X CREATES manual rework
```

Ne doit pas être inféré uniquement depuis un commentaire isolé.

---

# 86. Claim Granularity

Éviter les Claims trop larges.

Mauvais :

> TBT est une application complexe et importante.

Meilleur :

```text
TBT SUPPORTS Capability X
TBT DEPENDS_ON Y
TBT has 17 active consumers
TBT participates in Process Z
```

---

# 87. Atomic Claim Principle

Un Claim doit idéalement être testable individuellement.

---

# 88. Composite Knowledge

Les synthèses peuvent combiner plusieurs Claims.

Exemple :

> TBT est critique pour le processus X.

Peut être une synthèse de :

```text
TBT SUPPORTS Step A
Step A required by Process X
No alternate provider exists
```

---

# 89. Expression vs Claim

Une Expression est narrative et contextuelle.

Un Claim est atomique et durable.

---

# 90. Twin Summary

Le résumé vivant du jumeau est une projection.

```text
TwinSummary
based_on_claim_versions
generated_at
stale
```

---

# 91. Summary Generation

```text
Mature Claims
+ Important Unknowns
+ Contradictions
+ Recent Changes
↓
Summary Generator
```

---

# 92. Summary Update

Ne pas régénérer le résumé à chaque micro-change.

Utiliser :

```text
importance threshold
knowledge fingerprint
time window
```

---

# 93. Mesh Knowledge

Le Mesh Knowledge est la connaissance qui dépasse un Twin.

Exemples :

- dépendance inter-applications ;
- capacité partagée ;
- processus ;
- domaine émergent ;
- propagation ;
- contradiction inter-jumeaux.

---

# 94. Mesh Promotion

Un Claim local peut être promu au Mesh lorsqu’il :

- implique plusieurs entités ;
- est cross-validé ;
- est important transversalement.

---

# 95. Local vs Mesh Namespace

Exemple :

```text
local://TBT/claim/123
mesh://claim/9842
```

Conceptuellement utile pour distinguer portée.

---

# 96. Promotion Flow

```text
Local Claim
↓
Cross-Twin match
↓
Reconciliation
↓
Mesh Claim Candidate
↓
Validation
↓
Mesh Knowledge
```

---

# 97. Mesh Claim

Un Mesh Claim peut agréger plusieurs Claims locaux.

```yaml
MeshClaim:
  id:
  supporting_claim_refs:
  subject:
  predicate:
  object:
  confidence:
  scope:
  temporal_validity:
```

---

# 98. Mesh Contradictor

Le Mesh doit rechercher activement :

- Claims opposés ;
- topologies incompatibles ;
- modèles déclarés divergents ;
- versions temporelles concurrentes.

---

# 99. Knowledge Discovery Pipeline

```text
Source Change
↓
Artifact Delta
↓
Observations
↓
Claim Candidates
↓
Validation
↓
Local Knowledge Update
↓
Mesh Reconciliation
↓
Knowledge Events
```

---

# 100. Incremental Knowledge Update

Ne pas recalculer tout le jumeau.

Pattern :

```text
changed artifact
↓
affected symbols
↓
affected observations
↓
affected claims
↓
affected relationships
↓
affected summaries
```

---

# 101. Knowledge Event Types

```text
ObservationCreated
EvidenceCreated
ClaimProposed
ClaimSupported
ClaimStrengthened
ClaimContested
ClaimInvalidated
ClaimSuperseded
ContradictionDetected
ContradictionResolved
UnknownCreated
UnknownResolved
MeshClaimCreated
```

---

# 102. Event Causation

Chaque événement possède :

```text
correlation_id
causation_id
```

Cela permet de reconstruire :

> quel changement a créé quel Claim.

---

# 103. Graph RAG Architecture

Le Graph RAG sert à récupérer un contexte relationnel pertinent.

Il ne doit pas être une simple exportation du graphe complet.

---

# 104. Graph RAG Pipeline

```text
Question
↓
Entity Resolution
↓
Intent / Relation Need
↓
Graph Query Planning
↓
Subgraph Retrieval
↓
Evidence Expansion
↓
Semantic Retrieval
↓
Context Pack
↓
LLM
```

---

# 105. Graph Query Planner

Le Planner détermine :

- starting nodes ;
- edge types ;
- depth ;
- temporal scope ;
- domain scope ;
- max nodes ;
- evidence requirements.

---

# 106. Bounded Subgraph

Chaque requête impose :

```text
max_depth
max_nodes
max_edges
max_tokens
```

---

# 107. Path Queries

Exemples :

```text
find_path(TBT, CustomerJourneyX)
find_dependencies(TBT, depth=2)
find_impact(ChangeX)
```

---

# 108. Hybrid Retrieval

Combiner :

```text
Graph
+
Keyword
+
Vector
+
Temporal filters
+
Security filters
```

---

# 109. Retrieval Ranking

Score possible :

```text
semantic relevance
graph proximity
claim confidence
freshness
source authority
temporal match
```

---

# 110. Evidence Expansion

Le système récupère d’abord les Claims.

Puis seulement les Evidence nécessaires.

Cela réduit les tokens.

---

# 111. Hierarchical Retrieval

```text
Application Summary
↓
Capability Claims
↓
Detailed Claims
↓
Evidence
↓
Raw Artifact
```

Le LLM descend seulement si besoin.

---

# 112. Historical Retrieval

Pour une question historique :

> fonctionnalités ajoutées depuis trois ans

la recherche doit être :

```text
time-aware
version-aware
change-aware
```

---

# 113. Historical Claim Reconstruction

Pipeline :

```text
Commits
+ Jira
+ docs
↓
Change clusters
↓
Feature candidates
↓
Functional Claims
↓
Timeline
```

---

# 114. Knowledge Compression

Méridian doit éviter que la connaissance croisse uniquement sous forme de texte.

Compression par :

- atomic Claims ;
- relations ;
- summaries ;
- hierarchy ;
- deduplication.

---

# 115. Knowledge Compaction

Les observations anciennes peuvent être compactées tout en conservant :

- preuves critiques ;
- historique ;
- hashes ;
- lineage.

---

# 116. Knowledge Retention

Différents niveaux :

```text
Raw Artifact retention
Observation retention
Evidence retention
Claim retention
Decision retention
```

Décisions et Claims historiques peuvent avoir une rétention longue.

---

# 117. Security in Knowledge

Chaque objet porte :

```text
classification
access_policy
source_policy
derived_policy
```

---

# 118. Derived Security

Un Claim dérivé de données sensibles doit suivre une politique.

Exemple :

```text
Restricted Evidence
↓
Aggregated Claim
```

peut parfois être moins sensible, mais seulement si la politique l’autorise.

---

# 119. Security-Truncated Claim

Un utilisateur peut voir :

> une dépendance existe

sans voir :

> les données sensibles qui la prouvent.

Le système doit être capable de produire une vue filtrée.

---

# 120. Knowledge API

Exemples :

```text
GET /claims/{id}
GET /claims/{id}/evidence
GET /claims/{id}/history
GET /claims/{id}/contradictions
GET /twins/{id}/knowledge
POST /claims/proposals
POST /claims/{id}/contest
```

---

# 121. Knowledge Query API

Exemple conceptuel :

```yaml
KnowledgeQuery:
  entities:
  claim_types:
  predicates:
  time:
  confidence_min:
  maturity_min:
  scope:
  include_evidence:
```

---

# 122. Claim Explain API

```text
GET /claims/{id}/explain
```

Retourne :

```text
statement
status
confidence
maturity
evidence
contradictions
timeline
provenance
```

---

# 123. Knowledge Change Impact API

```text
GET /claims/{id}/dependents
```

Permet de savoir :

> si ce Claim est invalidé, qu’est-ce qui doit être réévalué ?

---

# 124. Human Review

Certains Claims nécessitent revue humaine.

Exemples :

```text
Legal interpretation
Critical risk
Enterprise domain mapping
High impact business rule
```

---

# 125. Review States

```text
NOT_REQUIRED
PENDING
APPROVED
REJECTED
NEEDS_REVISION
```

---

# 126. Human Contest

Un humain peut contester un Claim.

La contestation devient elle-même une donnée traçable.

---

# 127. Review Evidence

Le reviewer doit voir :

- affirmation ;
- preuves ;
- source ;
- contradictions ;
- historique.

---

# 128. Knowledge Learning

Les Outcomes produisent des Learnings.

Ces Learnings peuvent :

- renforcer un Claim ;
- invalider une hypothèse ;
- améliorer une règle de maturation ;
- devenir contexte historique.

---

# 129. Learning Reuse

Lors d’une nouvelle investigation :

```text
Situation
↓
similar historical cases
↓
Learning retrieval
```

Mais l’ancien cas ne devient pas automatiquement vérité du nouveau.

---

# 130. Similarity of Cases

Comparer :

- topology ;
- claim pattern ;
- signal pattern ;
- domain ;
- temporal structure ;
- outcome.

---

# 131. Knowledge Feedback Loop

```text
Decision
↓
Initiative
↓
Outcome
↓
Learning
↓
Knowledge
↓
Future Investigation
```

---

# 132. Claim Quality Metrics

```text
evidence coverage
source diversity
staleness
contradiction rate
invalidated rate
human correction rate
```

---

# 133. Twin Knowledge Metrics

```text
claims count
mature claims
critical unknowns
cross-twin confirmations
historical depth
freshness
```

---

# 134. Mesh Knowledge Metrics

```text
cross-domain claims
reconciled relationships
unresolved contradictions
emerging domains
knowledge propagation latency
```

---

# 135. Unsupported Claim Rate

Une métrique critique :

```text
claims without sufficient evidence
/
all active claims
```

Doit tendre vers zéro pour les Claims matures.

---

# 136. Claim Calibration Metrics

Comparer :

```text
confidence
vs
later validation / invalidation
```

---

# 137. Knowledge Observability

Dashboard :

```text
new claims/hour
strengthened claims
invalidated claims
stale claims
critical contradictions
unknowns
reconciliation backlog
```

---

# 138. Claim Lineage UI

Exemple :

```text
TBT CALLS EligibilityService
Confidence: 91%
Maturity: M5

Supported by:
✓ GitHub commit ...
✓ Runtime trace ...
✓ Config ...

Contradictions:
None

Valid since:
2025-11-02
```

---

# 139. Knowledge Timeline UI

L’utilisateur peut voir :

```text
2025-11-02 Claim proposed
2025-11-03 runtime confirmed
2025-11-05 cross-twin confirmed
2026-04-18 implementation changed
2026-04-18 old Claim historical
```

---

# 140. Unknown UI

Exemple :

> **Nous ne savons pas encore**
>
> Quel système remplace TBT en cas d’indisponibilité prolongée.

Action :

```text
Investigate
Connect source
Ask owner
```

---

# 141. Contradiction UI

```text
Declared model:
A → B

Observed model:
A → C

Possible explanations:
- migration underway
- documentation stale
- environment difference
```

---

# 142. Knowledge Trust Panel

Chaque réponse importante de Flore peut exposer :

```text
Confidence
Maturity
Sources
Claims
Contradictions
Unknowns
Freshness
```

---

# 143. Flore Retrieval Policy

Flore doit privilégier :

1. Mature Claims.
2. Supported Claims.
3. Historical Learnings.
4. Raw Evidence if needed.
5. General model knowledge only when clearly separated.

---

# 144. No silent fallback

Si Meridian Knowledge ne contient pas la réponse, Flore ne doit pas utiliser silencieusement une connaissance générique comme si elle venait de l’entreprise.

---

# 145. Answer Provenance

Une réponse peut segmenter :

```text
According to Meridian
According to external reference
Inference
Unknown
```

---

# 146. Report Knowledge Architecture

Un rapport est basé sur :

```text
Claim snapshot
+ Evidence
+ Timeline
+ Contradictions
```

Il doit rester reproductible.

---

# 147. Decision Snapshot

Une décision capture la version des Claims utilisés.

Ainsi, même si le savoir évolue, on peut comprendre le raisonnement historique.

---

# 148. Knowledge Snapshot

```yaml
KnowledgeSnapshot:
  id:
  captured_at:
  claim_versions:
  relationship_versions:
  ontology_version:
  context:
```

---

# 149. Knowledge Schema Versioning

Les schemas évoluent.

Chaque objet conserve :

```text
schema_version
```

---

# 150. Migration

Une migration de schéma ne doit pas faire perdre l’historique sémantique.

---

# 151. Claim Storage Strategy

Référence :

### Relational Store

Autorité du Claim.

### Graph Store

Projection des relations.

### Search Index

Recherche.

### Object Store

Evidence brute.

---

# 152. Why not Graph-only

Un graph seul gère moins bien :

- transaction métier ;
- workflow ;
- versioning complexe ;
- audit ;
- states.

---

# 153. Why not Vector-only

Un vector store ne fournit pas naturellement :

- identité stable ;
- temporalité ;
- causalité ;
- contradiction ;
- preuve structurée.

---

# 154. Claim Service

Responsabilités :

```text
create proposal
validate
version
strengthen
contest
invalidate
explain
retrieve history
```

---

# 155. Evidence Service

Responsabilités :

```text
register evidence
validate locator
retrieve
apply security
check integrity
```

---

# 156. Reconciliation Service

Responsabilités :

```text
match claims
compare
detect conflicts
merge
cross-validate
promote to Mesh
```

---

# 157. Knowledge Quality Service

Responsabilités :

```text
staleness
coverage
confidence calibration
policy compliance
quality metrics
```

---

# 158. Ontology Service

Responsabilités :

```text
entity types
predicate registry
constraints
schema versions
mapping
```

---

# 159. Knowledge Event Service

Publie :

```text
ClaimChanged
KnowledgeStale
ContradictionRaised
UnknownResolved
MeshKnowledgeUpdated
```

---

# 160. Example — Code Claim

Source :

```text
GitHub
```

Observation :

```text
EligibilityClient.check() called
```

Evidence :

```text
commit SHA + lines
```

Claim :

```text
TBT CALLS EligibilityService
```

Cross-validation :

```text
Datadog trace confirms
```

Maturity :

```text
M5
```

---

# 161. Example — Business Rule

Source 1 :

```text
Java condition
```

Source 2 :

```text
Confluence rule
```

Source 3 :

```text
Jira requirement
```

Claim :

```text
Applications over amount X REQUIRE manual review
```

Possible contradiction :

```text
runtime cases show exceptions
```

---

# 162. Example — Customer Friction

Observations :

```text
delay +25%
abandon +8%
manual review +17%
```

Claims :

```text
Process step X increased duration
```

Expression :

> Une friction semble émerger.

La phrase n’est pas le Claim.

---

# 163. Example — Deprecated App

Claims :

```text
A SUPPORTED Capability1
A SUPPORTED Capability2
B now SUPPORTS Capability1
C now SUPPORTS Capability2
A has low active consumers
```

Expression :

> Une opportunité de rationalisation existe.

---

# 164. TBT Historical Features

Knowledge architecture :

```text
Commits
↓
Change Observations
↓
Feature Claim Candidates
↓
Jira/Docs Evidence
↓
Functional Expert
↓
Feature Claims
↓
Timeline
```

---

# 165. Feature Claim

```yaml
FeatureClaim:
  capability:
  introduced_at:
  description:
  code_refs:
  issue_refs:
  confidence:
  classification:
```

---

# 166. Change vs Feature

Le système doit distinguer :

```text
TECHNICAL_CHANGE
FUNCTIONAL_CHANGE
BUSINESS_FEATURE
UNKNOWN
```

---

# 167. Historical Feature Report

Construit à partir de Feature Claims, pas directement depuis les commits.

---

# 168. Knowledge Discovery Budget

Toutes les sources ne doivent pas être analysées à profondeur maximale immédiatement.

Utiliser :

```text
priority
importance
knowledge gap
user demand
```

---

# 169. Lazy Enrichment

Un Twin peut avoir :

```text
basic claims
```

puis approfondir une zone lors d’une question.

---

# 170. Active Knowledge Acquisition

Lorsqu’un Unknown devient bloquant :

```text
Unknown
↓
Acquisition Planner
↓
Source / Expert / Human
↓
New Evidence
```

---

# 171. Knowledge Acquisition Planner

Peut décider :

```text
query source
connect source
request expert
ask human
wait for runtime evidence
```

---

# 172. Epistemic Status

Chaque réponse importante peut être marquée :

```text
OBSERVED
SUPPORTED
INFERRED
SPECULATIVE
UNKNOWN
```

---

# 173. Claim Explanation Template

```text
Claim:
TBT CALLS EligibilityService

Status:
MATURE

Confidence:
0.91

Why:
- code call
- runtime trace
- config

Against:
- none

Valid since:
...

Scope:
PROD
```

---

# 174. Knowledge Governance

Un comité ou rôle peut gouverner :

- ontology ;
- Claim policies ;
- confidence thresholds ;
- source authority ;
- critical Claim types ;
- retention.

---

# 175. Domain-specific Claim Policies

Exemple :

```text
Security claim
```

peut exiger plus de validation que :

```text
code ownership claim
```

---

# 176. Expert Influence

Un Expert ne modifie pas directement confidence de manière arbitraire.

Il apporte :

- Evidence ;
- validation ;
- objection ;
- context.

Le Confidence Engine recalcule.

---

# 177. Human Influence

Même principe.

Une validation humaine peut avoir un poids, mais reste traçable.

---

# 178. Knowledge Replay

Pour audit :

```text
replay events
```

afin de reconstruire l’évolution d’un Claim.

---

# 179. Reproducibility

Une analyse importante doit conserver :

```text
claim versions
evidence versions
ontology version
expert versions
time
```

---

# 180. Knowledge DR

Priorités de restauration :

1. Claims
2. Evidence metadata
3. Decisions
4. Provenance
5. Graph projections
6. Search indexes

Les index peuvent être reconstruits.

---

# 181. Knowledge Testing

Tests :

```text
claim deduplication
temporal split
conflict detection
evidence invalidation
cross-twin merge
security propagation
stale detection
```

---

# 182. Golden Claim Sets

Créer des ensembles validés pour :

- dependencies ;
- business rules ;
- features ;
- ownership ;
- process steps.

---

# 183. Evaluation of Extractors

Mesurer :

```text
precision
recall
evidence correctness
entity resolution accuracy
```

---

# 184. Evaluation of Reconciliation

Mesurer :

```text
correct merges
false merges
missed conflicts
temporal resolution accuracy
```

---

# 185. MVP Knowledge Architecture

Le MVP doit supporter :

```text
Source
Artifact
Evidence
Claim
Relationship
Confidence
Maturity
Version
Contradiction
Unknown
```

---

# 186. MVP Claim Types

Commencer avec :

```text
CALLS
DEPENDS_ON
READS
WRITES
IMPLEMENTS
BUSINESS_RULE
FUNCTIONALITY
OWNED_BY
```

---

# 187. MVP Sources

```text
GitHub
Jira
Confluence
Datadog
CMDB
```

selon disponibilité.

---

# 188. MVP Confidence

Commencer simple :

```text
evidence count
source diversity
freshness
contradiction
```

Puis calibrer.

---

# 189. MVP Maturity

```text
M1 Extracted
M2 Evidenced
M3 Correlated
M4 Cross-validated
```

`M5 Mature` peut nécessiter davantage de recul.

---

# 190. MVP Graph RAG

```text
Entity resolve
↓
2-hop graph
↓
top Claims
↓
Evidence expansion
↓
LLM
```

Pas besoin d’un planner très complexe au départ.

---

# 191. Phase 2

Ajouter :

- bitemporal queries ;
- advanced reconciliation ;
- Claim policy registry ;
- Learnings ;
- historical replay ;
- derived Claims ;
- ontology evolution.

---

# 192. Phase 3

Ajouter :

- proactive knowledge acquisition ;
- richer causal Claims ;
- organizational and customer Claims ;
- automated confidence calibration ;
- broader enterprise ontologies.

---

# 193. Architecture cible synthétique

```text
                      SOURCES
                         │
                         ▼
                     ARTIFACTS
                         │
                         ▼
                    OBSERVATIONS
                         │
                         ▼
                      EVIDENCE
                         │
                         ▼
                CLAIM CANDIDATE ENGINE
                         │
                         ▼
                  CLAIM VALIDATION
                         │
             ┌───────────┴───────────┐
             ▼                       ▼
       LOCAL TWIN KNOWLEDGE     CONTRADICTIONS
             │                       │
             └───────────┬───────────┘
                         ▼
                  RECONCILIATION
                         │
                         ▼
                   MESH KNOWLEDGE
                         │
        ┌────────────────┼─────────────────┐
        ▼                ▼                 ▼
     GRAPH RAG       MATURATION       INVESTIGATION
        │                │                 │
        └────────────────┴─────────────────┘
                         ▼
                EXPRESSION / DECISION
                         │
                         ▼
                      LEARNING
                         │
                         └────────────→ KNOWLEDGE
```

---

# 194. Anti-patterns critiques

## Text-only Knowledge

Tout garder sous forme de résumés.

## LLM Memory as Knowledge

Confondre mémoire agent et vérité.

## No Evidence Locator

Impossible d’auditer.

## No Time

Écraser le passé.

## Single Confidence Number Without Explanation

Score opaque.

## Merge Everything

Fusionner des Claims de scopes différents.

## Ignore Contradictions

Forcer le consensus.

## Graph as Authority

Prendre la projection pour la vérité.

## Vector Search as Truth

Confondre similarité et factualité.

## Every Inference Becomes Mature

Absence de maturation.

---

# 195. Critères de succès

L’architecture Knowledge & Claims est réussie si Méridian peut répondre à :

1. Qu’est-ce que tu sais ?
2. Pourquoi le sais-tu ?
3. Depuis quand ?
4. Est-ce encore vrai ?
5. Qui ou quoi l’a affirmé ?
6. Quelle preuve existe ?
7. Existe-t-il une contradiction ?
8. Quel est ton niveau de confiance ?
9. Quelle partie reste inconnue ?
10. Quelles décisions ont utilisé cette connaissance ?
11. Que se passe-t-il si ce Claim devient faux ?

---

# 196. Conclusion

Le véritable cerveau de Méridian n’est pas le LLM.

Il est constitué par :

> **les Claims, les preuves, la temporalité, la provenance, la contradiction et les mécanismes de maturation.**

Les modèles IA sont les mécanismes qui aident Méridian à :

- découvrir ;
- interpréter ;
- rapprocher ;
- proposer ;
- expliquer.

Mais la connaissance durable vit hors des modèles.

La chaîne fondamentale est :

```text
DATA
↓
OBSERVATION
↓
EVIDENCE
↓
CLAIM
↓
RECONCILIATION
↓
KNOWLEDGE
↓
EXPRESSION
↓
DECISION
↓
LEARNING
```

C’est cette architecture qui permet à Méridian de construire une représentation de l’entreprise qui soit :

- vivante ;
- explicable ;
- temporelle ;
- contradictoire ;
- vérifiable ;
- améliorable.

---

# 197. Prochain document

Le prochain document recommandé est :

> **MÉRIDIAN — Discovery & Maturation Engine**

Il devra détailler comment Méridian passe concrètement de :

```text
Observations
↓
Signals
↓
Situations candidates
↓
Maturation
↓
Expressions
↓
Opportunities / Risks
```

et surtout comment le système distingue :

> **ce qui est simplement observé**

de :

> **ce qui mérite réellement l’attention humaine.**

Ce document sera central pour éviter que Méridian ne devienne un système d’alertes bruyant.
