# MÉRIDIAN — Investigation & Decision Engine
## Investigation structurée, hypothèses, contradiction, scénarios et décision gouvernée

**Statut :** Architecture fonctionnelle et technique de référence  
**Version :** 1.0  
**Produit :** MÉRIDIAN  
**Tagline :** **DÉCOUVRIR · COMPRENDRE · DÉCIDER**

---

# 0. Objet du document

Ce document définit le moteur qui permet à Méridian de passer :

```text
Expression / Opportunity / Risk
↓
Investigation
↓
Hypotheses
↓
Evidence
↓
Experts
↓
Contradiction
↓
Synthesis
↓
Scenarios
↓
Decision
```

Il répond à la question :

> **Comment Méridian transforme-t-il un phénomène suffisamment mature en une décision humaine éclairée, comparable, explicable et traçable ?**

Ce moteur se situe au cœur de l’exploitation de Méridian.

Le Discovery & Maturation Engine détermine :

> **ce qui mérite l’attention.**

L’Investigation & Decision Engine détermine :

> **ce qu’il faut comprendre pour pouvoir décider.**

---

# 1. Principes fondamentaux

## 1.1 Une investigation n’est pas un ticket

Une Investigation n’est pas simplement :

- un incident ;
- une tâche ;
- un document ;
- un chat ;
- un rapport.

C’est un **dossier vivant de compréhension**.

Elle contient :

- une question ;
- un périmètre ;
- des hypothèses ;
- des preuves ;
- des contradictions ;
- des experts ;
- des inconnues ;
- des scénarios ;
- une synthèse ;
- éventuellement une décision.

---

## 1.2 Toute investigation doit commencer par une question

Exemples :

> Pourquoi la durée du parcours X augmente-t-elle ?

> Que se passerait-il si TBT était retiré ?

> Cette opportunité de rationalisation est-elle réelle ?

> Quelle option minimise le risque client ?

Une investigation sans question claire risque de devenir une collecte infinie d’informations.

---

## 1.3 Comprendre avant de recommander

Méridian ne doit pas produire immédiatement une recommandation.

Le cycle doit être :

```text
Question
↓
Scope
↓
Hypotheses
↓
Evidence
↓
Contradiction
↓
Understanding
↓
Scenarios
↓
Decision
```

---

## 1.4 L’hypothèse est distincte du Claim

Un Claim exprime une connaissance.

Une Hypothesis exprime une explication à tester.

Exemple :

```text
Claim:
TBT appelle EligibilityService.

Hypothesis:
La nouvelle règle d’admissibilité est la cause principale de la hausse des délais.
```

---

## 1.5 La contradiction est obligatoire pour les sujets importants

Toute investigation significative doit chercher :

> ce qui pourrait invalider l’hypothèse dominante.

---

## 1.6 Méridian prépare la décision mais ne la prend pas

Méridian peut :

- comparer ;
- simuler ;
- expliquer ;
- recommander ;
- exposer les risques.

Mais la décision significative reste humaine.

---

# 2. Entrées du moteur

Une Investigation peut être créée depuis :

```text
Expression
Opportunity
Risk
Signal externe
Twin
Domain
Atlas
Flore
Human request
```

---

# 3. Architecture globale

```text
TRIGGER
  │
  ▼
INVESTIGATION INTAKE
  │
  ▼
SCOPE & QUESTION
  │
  ▼
BASELINE KNOWLEDGE
  │
  ▼
HYPOTHESIS ENGINE
  │
  ▼
EXPERT ORCHESTRATION
  │
  ├──────────────┐
  ▼              ▼
EVIDENCE      CONTRADICTION
  │              │
  └──────┬───────┘
         ▼
     SYNTHESIS
         │
         ▼
     SCENARIOS
         │
         ▼
 DECISION READINESS
         │
         ▼
   HUMAN DECISION
         │
         ▼
     INITIATIVE
```

---

# 4. Investigation Intake

Le moteur commence par identifier :

- la question ;
- le trigger ;
- les entités concernées ;
- la période ;
- l’impact pressenti ;
- l’urgence ;
- le niveau de gouvernance.

---

# 5. Investigation object

```yaml
Investigation:
  id:
  title:
  question:
  trigger_ref:
  type:
  scope:
  status:
  priority:
  owner_ref:
  opened_at:
  target_decision_date:
  hypothesis_refs:
  evidence_refs:
  contradiction_refs:
  expert_contribution_refs:
  scenario_refs:
  synthesis_ref:
  decision_ref:
```

---

# 6. Types d’investigation

```text
ROOT_CAUSE
IMPACT_ANALYSIS
OPPORTUNITY_VALIDATION
RISK_ASSESSMENT
MODERNIZATION
RATIONALIZATION
BUSINESS_PROCESS
CUSTOMER_FRICTION
EMPLOYEE_FRICTION
HISTORICAL_RECONSTRUCTION
STRATEGIC_OPTION
CHANGE_IMPACT
```

---

# 7. Investigation levels

## L1 — Triage

Objectif :

> déterminer rapidement si le sujet mérite plus d’analyse.

Caractéristiques :

- faible coût ;
- 1 expert ;
- peu de sources ;
- réponse rapide.

## L2 — Focused

- 2 à 3 experts ;
- périmètre limité ;
- quelques hypothèses.

## L3 — Cross-domain

- plusieurs experts ;
- contradiction obligatoire ;
- scénarios.

## L4 — Strategic

- multi-domaines ;
- enjeux forts ;
- coûts/risques/clients/employés ;
- revue humaine renforcée.

---

# 8. Status lifecycle

```text
OPEN
↓
SCOPING
↓
COLLECTING
↓
ANALYZING
↓
CONTRADICTING
↓
SYNTHESIZING
↓
SCENARIO_BUILDING
↓
READY_FOR_DECISION
↓
DECIDED
↓
CLOSED
```

Branches :

```text
BLOCKED
PAUSED
CANCELLED
REOPENED
```

---

# 9. Scope

Le Scope est un objet explicite.

```yaml
InvestigationScope:
  twin_refs:
  domain_refs:
  process_refs:
  journey_refs:
  team_refs:
  temporal_scope:
  geography:
  business_scope:
  security_scope:
```

---

# 10. Scope discipline

L’investigation ne doit pas commencer par :

> tout analyser.

Elle doit définir :

```text
what is included
what is excluded
what remains unknown
```

---

# 11. Scope expansion

Le Scope peut s’élargir si une preuve le justifie.

Exemple :

```text
TBT investigation
↓
dependency to EligibilityService
↓
scope expands to Eligibility domain
```

Toute expansion doit être justifiée.

---

# 12. Scope contraction

Une investigation peut aussi réduire son périmètre.

---

# 13. Baseline

Avant les hypothèses, Méridian construit une baseline.

Elle rassemble :

- Claims matures ;
- relations ;
- timeline ;
- changements récents ;
- incidents historiques ;
- Learnings ;
- Unknowns ;
- contradictions existantes.

---

# 14. Baseline Snapshot

```yaml
BaselineSnapshot:
  investigation_id:
  captured_at:
  claim_versions:
  relationship_versions:
  source_refs:
  knowledge_fingerprint:
```

---

# 15. Hypothesis Engine

Le moteur génère ou reçoit des hypothèses.

Sources :

- humain ;
- Expert ;
- historique ;
- pattern ;
- Flore ;
- Discovery Engine.

---

# 16. Hypothesis object

```yaml
Hypothesis:
  id:
  investigation_ref:
  statement:
  category:
  status:
  confidence:
  supporting_claim_refs:
  opposing_claim_refs:
  supporting_evidence_refs:
  opposing_evidence_refs:
  unknown_refs:
  created_by:
  created_at:
```

---

# 17. Hypothesis categories

```text
CAUSE
IMPACT
DEPENDENCY
RISK
OPPORTUNITY
ASSUMPTION
ALTERNATIVE
```

---

# 18. Hypothesis lifecycle

```text
OPEN
↓
TESTING
↓
STRENGTHENED
```

Branches :

```text
WEAKENED
REJECTED
CONFIRMED
UNRESOLVED
```

---

# 19. Hypothesis graph

Les hypothèses peuvent être reliées.

Exemple :

```text
H1: rule X increases latency
  ↓ supports
H2: latency causes manual rework
  ↓ supports
H3: rework increases customer waiting
```

---

# 20. Competing hypotheses

Le moteur doit conserver plusieurs explications.

Exemple :

```text
H1 deployment regression
H2 traffic increase
H3 external dependency slowdown
H4 business rule change
```

---

# 21. Hypothesis ranking

Score possible :

```text
evidence_strength
+ explanatory_power
+ temporal_fit
+ topology_fit
+ historical_fit
- contradictions
```

---

# 22. Evidence Board

L’investigation possède un tableau de preuves.

```text
Evidence supporting H1
Evidence against H1
Evidence supporting H2
...
```

---

# 23. Evidence state

Une Evidence peut être :

```text
AVAILABLE
REQUESTED
MISSING
STALE
RESTRICTED
INVALID
```

---

# 24. Evidence gaps

Le moteur identifie :

> quelles preuves manquent pour départager les hypothèses.

---

# 25. Evidence request

Exemple :

```yaml
EvidenceRequest:
  question:
  evidence_type:
  source_types:
  target_entity:
  priority:
  blocking:
```

---

# 26. Expert orchestration

L’Investigation Engine s’appuie sur l’Expert Framework.

Pipeline :

```text
Investigation question
↓
Mission Planner
↓
Expert Selector
↓
Parallel / Sequential Execution
↓
Contributions
```

---

# 27. Mission decomposition

Exemple :

Question :

> Que se passerait-il si TBT était supprimé ?

Missions :

```text
M1 dependencies
M2 business capabilities
M3 data impact
M4 operational impact
M5 customer impact
M6 migration alternatives
```

---

# 28. Expert teams

Exemples :

## Incident

```text
Observability
Performance
Architecture
Change
Contradictor
```

## Rationalization

```text
Architecture
Business
Finance
Process
Risk
```

## Customer friction

```text
Journey
Process
Application
Product
Customer
```

---

# 29. Expert contribution

```yaml
ExpertContribution:
  expert_ref:
  mission_ref:
  findings:
  proposed_claims:
  supported_hypotheses:
  challenged_hypotheses:
  unknowns:
  risks:
  opportunities:
  evidence_refs:
  confidence:
```

---

# 30. Shared Investigation Knowledge Board

Les Experts ne doivent pas échanger seulement via chat.

Ils travaillent sur un Knowledge Board commun.

```text
Claims
Hypotheses
Evidence
Unknowns
Contradictions
Findings
```

---

# 31. Knowledge Board writes

Pattern :

```text
Expert
↓
Proposed update
↓
Validation
↓
Knowledge Board
```

---

# 32. Contradiction Engine

Le moteur cherche activement :

- preuve contraire ;
- hypothèse alternative ;
- différence de scope ;
- erreur temporelle ;
- biais de confirmation.

---

# 33. Contradiction object

```yaml
InvestigationContradiction:
  id:
  investigation_ref:
  target_ref:
  opposing_ref:
  type:
  severity:
  status:
  resolution:
```

---

# 34. Contradiction types

```text
EVIDENCE_CONFLICT
EXPERT_DISAGREEMENT
TEMPORAL_CONFLICT
SCOPE_CONFLICT
MODEL_CONFLICT
CAUSAL_CONFLICT
```

---

# 35. Contradictor workflow

```text
Dominant Hypothesis
↓
Collect supporting evidence
↓
Ask Contradictor
↓
Search opposing evidence
↓
Generate alternatives
↓
Re-score
```

---

# 36. Evidence Auditor

Le Evidence Auditor vérifie :

- existence ;
- version ;
- source ;
- scope ;
- lien réel avec l’affirmation ;
- fraîcheur.

---

# 37. Cross-examination

Pour les investigations sensibles :

```text
Expert A
↓
Expert B critique
↓
Expert A clarification
↓
Evidence Auditor
↓
Synthesis
```

---

# 38. No forced consensus

Si le désaccord persiste :

```text
UNRESOLVED DISAGREEMENT
```

doit être conservé dans la synthèse.

---

# 39. Unknowns

L’investigation doit exposer ses inconnues.

Exemples :

```text
unknown consumer
unknown business exception
unknown customer segment
missing cost data
```

---

# 40. Critical Unknown

Un Unknown peut bloquer :

- conclusion ;
- scénario ;
- décision.

---

# 41. Investigation progress

La progression doit refléter le travail réel.

Exemple :

```text
✓ Scope complete
✓ Baseline built
✓ 4 hypotheses created
✓ Architecture Expert complete
● Process Expert running
○ Contradiction
○ Synthesis
○ Scenarios
```

---

# 42. Partial findings

Les findings fiables peuvent être publiés avant la fin.

---

# 43. Investigation timeline

Tout événement important est historisé.

```text
opened
scope changed
hypothesis added
evidence added
expert completed
contradiction raised
scenario created
decision recorded
```

---

# 44. Synthesis Engine

Le moteur de synthèse doit répondre :

1. Que savons-nous ?
2. Que pensons-nous probablement ?
3. Qu’est-ce qui est contesté ?
4. Que ne savons-nous pas ?
5. Quelles sont les conséquences ?
6. Quelles options existent ?

---

# 45. Synthesis object

```yaml
InvestigationSynthesis:
  summary:
  confirmed_findings:
  probable_findings:
  rejected_hypotheses:
  unresolved_hypotheses:
  contradictions:
  unknowns:
  impacts:
  recommendations_for_next_step:
  confidence:
```

---

# 46. Synthesis layers

## Executive

Décisionnaire.

## Analyst

Hypothèses et preuves.

## Technical

Claims et Evidence détaillées.

---

# 47. Readiness for scenarios

Une investigation ne doit pas passer aux scénarios trop tôt.

Gate :

```text
question understood
scope stable enough
key hypotheses tested
critical contradictions exposed
key unknowns known
```

---

# 48. Scenario

Un Scenario représente une option d’action cohérente.

Il ne s’agit pas juste d’une recommandation textuelle.

---

# 49. Scenario object

```yaml
Scenario:
  id:
  investigation_ref:
  title:
  description:
  assumptions:
  actions:
  affected_entities:
  dependencies:
  expected_impacts:
  risks:
  estimated_cost:
  implementation_complexity:
  reversibility:
  time_to_value:
  confidence:
```

---

# 50. Scenario generation

Les scénarios peuvent venir :

- humains ;
- experts ;
- patterns historiques ;
- moteur agentique.

---

# 51. Scenario diversity

Méridian doit éviter trois variantes presque identiques.

Un bon ensemble de scénarios doit représenter des choix réellement différents.

Exemple :

```text
A — Optimize current
B — Replace component
C — Redesign process
D — Do nothing / defer
```

---

# 52. Baseline scenario

Toujours considérer :

```text
DO NOTHING
```

ou :

```text
CONTINUE CURRENT STATE
```

pour mesurer le coût d’inaction.

---

# 53. Scenario assumptions

Chaque scénario expose ses hypothèses.

Exemple :

```text
Service X can handle +40%
Team Y can migrate in 6 months
No regulatory blocker
```

---

# 54. Scenario risk

Risques par scénario :

```text
technical
business
customer
employee
financial
regulatory
operational
```

---

# 55. Scenario impact

Impacts attendus :

```text
cost
time
quality
resilience
customer
employee
strategic
```

---

# 56. Reversibility

Dimension essentielle.

```text
HIGH
MEDIUM
LOW
IRREVERSIBLE
```

---

# 57. Time to value

Le système doit distinguer :

```text
fast local improvement
vs
long strategic transformation
```

---

# 58. Scenario Critic

Chaque scénario important passe par un critic.

Mission :

> identifier ce qui pourrait faire échouer ce scénario.

---

# 59. Counterfactual analysis

Méridian peut poser :

> Que se passe-t-il si nous ne faisons rien ?

> Que se passe-t-il si l’hypothèse principale est fausse ?

---

# 60. Scenario comparison

Tableau standard :

```text
Scenario
Value
Cost
Risk
Time
Reversibility
Customer Impact
Employee Impact
Confidence
```

---

# 61. Weighted comparison

L’utilisateur peut définir des priorités.

Exemple :

```text
Risk: 30%
Customer: 25%
Cost: 20%
Time: 15%
Reversibility: 10%
```

---

# 62. No hidden ranking

Si Méridian recommande un scénario, les critères doivent être visibles.

---

# 63. Decision readiness

Une Investigation devient `READY_FOR_DECISION` lorsque :

- scénarios comparables ;
- preuves suffisantes ;
- inconnues critiques exposées ;
- contradictions explicites ;
- décisionnaire identifié.

---

# 64. Decision Readiness Score

Dimensions :

```text
evidence completeness
scenario completeness
risk coverage
unknown severity
stakeholder coverage
confidence
```

---

# 65. Decision Gate

Pour les décisions critiques :

```text
Human review required
```

---

# 66. Decision object

```yaml
Decision:
  id:
  investigation_ref:
  selected_scenario_ref:
  rejected_scenario_refs:
  rationale:
  decision_maker_refs:
  decided_at:
  decision_type:
  confidence_at_decision:
  evidence_snapshot_ref:
  assumptions:
  expected_outcomes:
  review_date:
```

---

# 67. Decision types

```text
APPROVE
REJECT
DEFER
PILOT
INVESTIGATE_MORE
ACCEPT_RISK
STOP
```

---

# 68. Decision rationale

Le rationale doit être humainement compréhensible.

Exemple :

> Scénario B retenu car il réduit le risque client sans imposer une migration complète de TBT.

---

# 69. Rejected scenarios

Conserver les options rejetées.

Pourquoi ?

Parce que six mois plus tard, le contexte peut changer.

---

# 70. Decision Snapshot

Capture :

```text
Claims
Evidence
Hypotheses
Scenarios
Unknowns
Contradictions
```

au moment de la décision.

---

# 71. Decision versioning

Une décision peut être superseded.

```text
DEC-100 v1
↓
DEC-100 v2
```

ou liée à une nouvelle décision.

---

# 72. Decision assumptions

Les hypothèses ayant justifié la décision doivent être conservées.

---

# 73. Assumption monitoring

Après décision, Méridian peut surveiller :

> les hypothèses sont-elles toujours vraies ?

---

# 74. Decision expiration

Certaines décisions peuvent avoir :

```text
review_date
valid_until
```

---

# 75. From Decision to Initiative

Une décision peut générer une Initiative.

```text
Decision
↓
Initiative
↓
Actions
↓
Observation Plan
```

---

# 76. Initiative object

```yaml
Initiative:
  id:
  decision_ref:
  title:
  owner:
  status:
  scope:
  milestones:
  affected_entities:
  expected_outcomes:
  observation_plan_ref:
```

---

# 77. Observation Plan

Définit comment on saura si la décision fonctionne.

```yaml
ObservationPlan:
  metrics:
  signals:
  comparison_baseline:
  observation_window:
  expected_ranges:
  side_effect_watch:
```

---

# 78. Outcome handoff

Le moteur d’investigation transmet ensuite au Continuous Improvement Engine.

---

# 79. Investigation reuse

Une investigation historique peut être utilisée comme précédent.

---

# 80. Similar Investigation Retrieval

Comparer :

```text
question
topology
domain
signal pattern
hypotheses
```

---

# 81. Reuse is context, not answer

Une ancienne investigation ne doit pas imposer sa conclusion au nouveau cas.

---

# 82. Investigation templates

Exemples :

```text
Incident
Impact analysis
Rationalization
Process friction
Customer friction
Migration
Risk assessment
```

---

# 83. Template contents

```text
default experts
required evidence
hypothesis prompts
contradiction policy
scenario dimensions
decision gate
```

---

# 84. Investigation Intake UI

```text
Question
Trigger
Scope
Urgency
Expected decision
```

---

# 85. Investigation workspace UI

```text
┌──────────────────────────────────────┐
│ Investigation title                  │
│ Status · Confidence · Owner          │
├──────────────────────────────────────┤
│ Summary                              │
│ Hypotheses                           │
│ Evidence                             │
│ Experts                              │
│ Contradictions                       │
│ Timeline                             │
│ Scenarios                            │
│ Decision                             │
└──────────────────────────────────────┘
```

---

# 86. Hypothesis UI

Chaque hypothèse affiche :

```text
statement
confidence
support
against
status
owner
```

---

# 87. Evidence UI

Regrouper par :

- hypothèse ;
- source ;
- temps ;
- support/against.

---

# 88. Contradiction UI

Afficher les désaccords comme objets explicites.

---

# 89. Expert UI

L’utilisateur voit :

```text
Expert
Mission
Status
Finding summary
Evidence count
Confidence
```

Pas les prompts internes.

---

# 90. Scenario UI

Comparaison côte à côte.

---

# 91. Decision UI

Doit montrer :

```text
chosen scenario
why
who
when
expected outcomes
review date
```

---

# 92. Flore in investigation

Flore devient le copilote de l’investigation.

Questions :

> Qu’est-ce qui manque ?

> Quelle hypothèse est la plus forte ?

> Quels experts sont en désaccord ?

> Compare les scénarios A et C.

> Qu’est-ce qui pourrait invalider notre conclusion ?

---

# 93. Flore actions

```text
add hypothesis
request expert
expand scope
request evidence
build scenario
prepare decision summary
```

---

# 94. Flore cannot decide

Même si l’utilisateur demande :

> choisis à ma place

Flore peut recommander mais doit identifier que la décision reste humaine.

---

# 95. Investigation APIs

```text
POST /investigations
GET /investigations/{id}
POST /investigations/{id}/start
POST /investigations/{id}/pause
POST /investigations/{id}/close
POST /investigations/{id}/scope
```

---

# 96. Hypothesis APIs

```text
POST /investigations/{id}/hypotheses
POST /hypotheses/{id}/support
POST /hypotheses/{id}/challenge
POST /hypotheses/{id}/reject
```

---

# 97. Expert APIs

```text
POST /investigations/{id}/experts/request
GET /investigations/{id}/contributions
```

---

# 98. Scenario APIs

```text
POST /investigations/{id}/scenarios
GET /investigations/{id}/scenarios
POST /scenarios/{id}/compare
```

---

# 99. Decision APIs

```text
POST /investigations/{id}/decision
GET /decisions/{id}
POST /decisions/{id}/supersede
```

---

# 100. Event model

```text
InvestigationOpened
ScopeChanged
HypothesisCreated
HypothesisStrengthened
HypothesisRejected
EvidenceAdded
ExpertRequested
ExpertCompleted
ContradictionRaised
SynthesisUpdated
ScenarioCreated
InvestigationReadyForDecision
DecisionRecorded
```

---

# 101. Investigation workflow technical architecture

```text
Investigation Service
↓
Durable Workflow
├── Baseline Collector
├── Hypothesis Engine
├── Expert Orchestrator
├── Evidence Auditor
├── Contradictor
├── Synthesis
├── Scenario Engine
└── Decision Gate
```

---

# 102. Durable workflow

Les investigations doivent survivre :

- restart ;
- crash ;
- timeout ;
- attente humaine ;
- plusieurs jours.

---

# 103. Workflow checkpoint

Chaque étape conserve :

```text
input refs
output refs
status
cost
trace
```

---

# 104. Human callback

Pattern :

```text
workflow
↓
WAIT_FOR_HUMAN
↓
approval / decision
↓
resume
```

---

# 105. Parallel experts

Les experts peuvent être parallélisés.

---

# 106. Shared retrieval

Éviter que chaque expert refasse la même collecte.

```text
Baseline Evidence Collector
↓
Shared Evidence Set
↓
Experts
```

---

# 107. Late evidence

Une preuve peut arriver après synthèse.

Alors :

```text
new evidence
↓
affected hypotheses
↓
re-score
↓
synthesis stale
```

---

# 108. Synthesis invalidation

La synthèse doit être liée au fingerprint de connaissance.

---

# 109. Scenario invalidation

Si une hypothèse critique change, un scénario peut devenir stale.

---

# 110. Decision after stale scenario

Le système doit empêcher ou signaler :

> décision basée sur scénario obsolète.

---

# 111. Budget model

Chaque investigation porte :

```text
max experts
max duration
max cost
max LLM calls
max source queries
```

---

# 112. Cost by stage

Tracer :

```text
baseline
experts
contradiction
synthesis
scenarios
```

---

# 113. Escalation

Si budget atteint :

```text
PARTIAL
REQUEST_MORE_BUDGET
HUMAN_DECISION
```

---

# 114. Investigation priority

```text
P0 critical incident
P1 executive decision
P2 user investigation
P3 opportunity analysis
P4 background exploration
```

---

# 115. SLA classes

```text
FAST_TRIAGE
STANDARD
DEEP
STRATEGIC
```

---

# 116. Fast triage

Objectif :

> produire rapidement une orientation.

Pas une conclusion finale.

---

# 117. Deep investigation

Plus de preuves, experts, contradiction.

---

# 118. Strategic investigation

Peut inclure :

- Finance ;
- Client ;
- Employee ;
- Risk ;
- Strategy ;
- Architecture.

---

# 119. Decision policy

Certaines décisions doivent imposer :

```text
minimum evidence
required experts
required approvers
required risk review
```

---

# 120. Decision Policy Registry

```yaml
DecisionPolicy:
  decision_type:
  minimum_investigation_level:
  required_roles:
  required_evidence:
  required_risk_review:
  snapshot_required:
```

---

# 121. Governance

Le moteur doit permettre :

- ownership ;
- approvers ;
- segregation of duties ;
- audit ;
- policy versioning.

---

# 122. Segregation of duties

Exemple :

L’Expert qui recommande n’est pas l’humain qui approuve.

---

# 123. Decision transparency

Toute décision doit pouvoir répondre :

1. Quelle question ?
2. Quelles preuves ?
3. Quelles hypothèses ?
4. Quels scénarios ?
5. Pourquoi ce choix ?
6. Quelles inconnues ?
7. Quel risque accepté ?

---

# 124. Accepted Risk

Une décision peut explicitement accepter un risque.

```yaml
AcceptedRisk:
  risk_ref:
  rationale:
  owner:
  review_date:
```

---

# 125. Deferred decision

Un `DEFER` doit aussi avoir :

- raison ;
- trigger de réévaluation ;
- date.

---

# 126. Decision watch

Après une décision différée, Méridian peut surveiller :

> quand les conditions changent.

---

# 127. Confidence at decision time

Conserver :

```text
confidence_at_decision
```

---

# 128. Decision quality metrics

À long terme :

```text
decision outcome success
assumption failure rate
reversal rate
unexpected effect rate
```

---

# 129. Investigation quality metrics

```text
time to understanding
time to decision
evidence coverage
hypothesis diversity
contradiction coverage
reuse rate
```

---

# 130. Hypothesis quality metrics

```text
confirmed
rejected
unresolved
```

---

# 131. Scenario quality metrics

```text
scenario diversity
risk completeness
assumption completeness
outcome predictiveness
```

---

# 132. Human feedback

Les utilisateurs peuvent qualifier :

```text
useful
too broad
missing evidence
wrong hypothesis
good scenario
decision unsupported
```

---

# 133. Auditability

Pour chaque étape :

```text
actor
time
input
output
evidence
version
policy
```

---

# 134. Reproducibility

Une investigation importante conserve :

```text
claim versions
expert versions
model versions
policy versions
tool versions
```

---

# 135. Security

L’investigation ne crée pas un bypass des droits.

Les experts utilisent le même security trimming.

---

# 136. Security-scoped synthesis

Deux utilisateurs peuvent voir des synthèses différentes selon leurs droits.

Mais le système doit indiquer que certaines preuves sont restreintes.

---

# 137. Restricted evidence

Exemple :

```text
3 supporting evidences
1 restricted
```

---

# 138. Confidential decision

La décision elle-même peut avoir une classification.

---

# 139. Failure modes

## No evidence

Status :

```text
BLOCKED_BY_EVIDENCE
```

## Expert failed

Retry / alternate / continue.

## Contradictions unresolved

Still can be `READY_FOR_DECISION` only if policy permits.

## Human unavailable

Pause.

---

# 140. Investigation cancellation

L’annulation conserve :

- historique ;
- raison ;
- résultats partiels.

---

# 141. Reopen

Une investigation peut être réouverte si :

- nouvelle preuve ;
- outcome inattendu ;
- décision remise en question.

---

# 142. Investigation lineage

Une investigation peut créer une nouvelle investigation.

Exemple :

```text
INV-100
↓ discovers employee issue
INV-101
```

---

# 143. Sub-investigations

Les sujets complexes peuvent être décomposés.

```text
Main Investigation
├── Technical
├── Business
└── Customer
```

---

# 144. Parent-child synthesis

Le parent agrège les synthèses, pas tous les détails bruts.

---

# 145. Scenario portfolios

Pour les transformations complexes, plusieurs scénarios peuvent être combinés.

---

# 146. Decision sequence

Une décision stratégique peut produire plusieurs décisions tactiques.

---

# 147. Example — Incident

```text
Signal
↓
Investigation
↓
H1 recent deployment
H2 traffic spike
H3 downstream issue
↓
Experts
↓
H2 rejected
H1 strengthened
↓
Scenario
rollback / patch / throttle
↓
Human decision
```

---

# 148. Example — Rationalization

```text
Opportunity:
Application A low value
↓
Investigation
↓
Architecture + Finance + Business
↓
Claims:
few consumers
capability duplicated
cost high
↓
Scenarios:
retire / merge / retain
↓
Decision
```

---

# 149. Example — Customer friction

```text
Expression
↓
Investigation
↓
Process + Journey + Application
↓
Hypothesis:
manual validation causes delay
↓
Contradictor:
seasonality?
↓
Evidence:
no
↓
Scenario:
remove / automate / redesign
```

---

# 150. Example — TBT removal

Question :

> Que se passerait-il si TBT était retiré dans 18 mois ?

Experts :

```text
Architecture
Data
Business
Process
Operations
Risk
Finance
```

Outputs :

- dependencies ;
- missing alternatives ;
- customer impact ;
- migration complexity ;
- cost ;
- scenarios.

---

# 151. TBT scenarios

```text
A — Replace TBT with new platform
B — Decompose capabilities gradually
C — Retain and modernize
D — Delay retirement
```

---

# 152. TBT Decision Board

Le Decision Board pourrait montrer :

```text
Value
Risk
Migration effort
Time
Reversibility
Confidence
Unknowns
```

---

# 153. Example — Historical feature reconstruction

Ce type d’investigation peut se terminer sans Decision.

Résultat :

```text
Validated report
```

Toutes les investigations ne nécessitent donc pas une décision.

---

# 154. Investigation outcome types

```text
DECISION
REPORT
KNOWLEDGE_UPDATE
NO_ACTION
NEW_INVESTIGATION
OPPORTUNITY
RISK
```

---

# 155. Product principle

Une Investigation doit produire un résultat exploitable.

Sinon elle doit être :

```text
BLOCKED
CANCELLED
NO_CONCLUSION
```

de manière explicite.

---

# 156. Decision Board

Surface produit dédiée.

```text
Question
Current recommendation
Scenario comparison
Key evidence
Critical unknowns
Contradictions
Approvers
```

---

# 157. Recommendation

Une recommandation de Méridian est un objet distinct de la Decision.

```yaml
Recommendation:
  preferred_scenario_ref:
  rationale:
  confidence:
  assumptions:
  generated_at:
```

---

# 158. Recommendation can change

Avant la décision, de nouvelles preuves peuvent modifier la recommandation.

---

# 159. Human override

Un décideur peut sélectionner un scénario non recommandé.

Le système conserve la raison.

---

# 160. Human override is not an error

La décision humaine peut intégrer des informations non présentes dans Méridian.

---

# 161. Decision learning hook

À la décision :

```text
expected outcomes
+
review date
+
observation plan
```

doivent idéalement être obligatoires.

---

# 162. Avoid decision graveyard

Une décision sans Outcome suivi détruit la boucle d’apprentissage.

---

# 163. Handoff to Continuous Improvement

```text
Decision
↓
Initiative
↓
Observation Plan
↓
Continuous Improvement Engine
```

---

# 164. Technical component map

```text
Investigation Service
Scope Service
Hypothesis Service
Evidence Board
Expert Orchestrator
Contradiction Service
Synthesis Service
Scenario Service
Decision Service
Policy Service
```

---

# 165. Data stores

Autoritatif :

```text
PostgreSQL/Aurora
```

Graph references :

```text
Neptune
```

Evidence :

```text
S3 + Search
```

---

# 166. Event-driven integration

Le moteur consomme :

```text
ExpressionCreated
OpportunityQualified
RiskRaised
ClaimChanged
NewEvidenceAvailable
```

---

# 167. Event-driven invalidation

Exemple :

```text
ClaimInvalidated
↓
Investigation affected
↓
Synthesis stale
↓
Decision warning
```

---

# 168. SSE

Les investigations longues publient :

```text
stage
progress
new finding
new contradiction
expert complete
```

---

# 169. Job model

Chaque analyse lourde devient un Job.

---

# 170. Job cancellation

Support requis.

---

# 171. Observability

Tracer :

```text
investigation duration
expert duration
evidence retrieval
hypothesis count
contradictions
scenario count
cost
time to first finding
```

---

# 172. Cognitive observability

Mesurer aussi :

```text
unsupported finding
evidence coverage
expert disagreement
rejected hypothesis
```

---

# 173. Cost observability

```text
cost per investigation
cost per expert
cost per scenario
```

---

# 174. Investigation replay

Un environnement d’évaluation doit pouvoir rejouer une investigation historique.

---

# 175. Golden investigations

Cas validés pour :

- incident ;
- rationalisation ;
- impact ;
- friction ;
- changement.

---

# 176. Evaluation

Comparer :

```text
root cause accuracy
evidence quality
scenario quality
decision usefulness
```

---

# 177. MVP

Le MVP Investigation & Decision doit supporter :

```text
Investigation
Scope
Hypothesis
Evidence
2-3 Experts
Contradiction
Synthesis
Scenario
Decision
```

---

# 178. MVP workflows

## Workflow 1

Incident.

## Workflow 2

Opportunity validation.

## Workflow 3

Impact analysis.

---

# 179. MVP scenario dimensions

```text
value
risk
cost
time
reversibility
```

---

# 180. MVP Decision

Capture :

```text
selected scenario
rationale
approver
expected outcomes
```

---

# 181. Phase 2

Ajouter :

- sub-investigations ;
- richer scenario simulation ;
- decision policies ;
- stakeholder views ;
- accepted risk ;
- historical reuse.

---

# 182. Phase 3

Ajouter :

- strategic investigations ;
- scenario portfolios ;
- causal models ;
- richer counterfactual reasoning ;
- decision quality learning.

---

# 183. Anti-patterns

## Investigation = chat

Perte de structure.

## One hypothesis

Biais.

## No contradiction

Confirmation.

## Evidence as attachments only

Pas de lien structuré.

## Experts without missions

Travail redondant.

## Scenario = paragraph

Impossible à comparer.

## Recommendation = Decision

Perte de gouvernance.

## Decision without snapshot

Perte d’audit.

## Decision without expected outcome

Pas d’apprentissage.

## Unlimited investigation

Coût infini.

---

# 184. Critères de succès

Le moteur est réussi si :

1. chaque investigation possède une question claire ;
2. les hypothèses sont explicites ;
3. les preuves pour et contre sont visibles ;
4. plusieurs expertises peuvent collaborer sans perdre la structure ;
5. une hypothèse dominante est activement contestée ;
6. les Unknowns restent visibles ;
7. les scénarios sont comparables ;
8. les recommandations sont explicables ;
9. la décision reste humaine ;
10. toute décision importante possède un snapshot et des outcomes attendus.

---

# 185. Architecture cible synthétique

```text
           EXPRESSION / OPPORTUNITY / RISK
                         │
                         ▼
                  INVESTIGATION
                         │
                         ▼
                       SCOPE
                         │
                         ▼
                      BASELINE
                         │
                         ▼
                    HYPOTHESES
                         │
            ┌────────────┼────────────┐
            ▼            ▼            ▼
         EXPERTS       EVIDENCE   CONTRADICTION
            │            │            │
            └────────────┴────────────┘
                         │
                         ▼
                     SYNTHESIS
                         │
                         ▼
                     SCENARIOS
                         │
                         ▼
                DECISION READINESS
                         │
                         ▼
                  HUMAN DECISION
                         │
                         ▼
                    INITIATIVE
                         │
                         ▼
              CONTINUOUS IMPROVEMENT
```

---

# 186. Conclusion

Le Investigation & Decision Engine transforme une compréhension émergente en décision gouvernée.

Il impose une discipline :

> **ne pas confondre signal, hypothèse, preuve, conclusion et décision.**

Méridian doit être capable de dire :

> Voici ce que nous savons.

> Voici ce que nous pensons.

> Voici ce qui contredit cette hypothèse.

> Voici ce que nous ignorons encore.

> Voici les options possibles.

> Voici les conséquences probables de chaque option.

Puis l’humain décide.

La valeur du moteur ne réside donc pas dans une IA qui « donne la bonne réponse ».

Elle réside dans sa capacité à construire un espace de décision où :

- les preuves sont visibles ;
- les hypothèses sont testées ;
- les désaccords sont conservés ;
- les scénarios sont comparables ;
- les risques sont explicites ;
- la décision peut être reconstruite des mois plus tard.

---

# 187. Prochain document

Le prochain document recommandé est :

> **MÉRIDIAN — Continuous Improvement & Learning Model**

Il doit formaliser la boucle après décision :

```text
Decision
↓
Initiative
↓
Observation Plan
↓
Outcome
↓
Expected vs Observed
↓
Learning
↓
New Claims / Signals / Opportunities
```

C’est ce document qui donnera tout son sens au mot **vivant** dans Méridian.

Sans lui, Méridian aide à décider.

Avec lui, Méridian apprend réellement des conséquences des décisions.
