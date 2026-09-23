# MÉRIDIAN — Agentic Architecture & Expert Framework
## Architecture des agents, système d’experts spécialisés, orchestration, contradiction et gouvernance cognitive

**Statut :** Architecture agentique de référence  
**Version :** 1.0  
**Produit :** MÉRIDIAN  
**Tagline :** **DÉCOUVRIR · COMPRENDRE · DÉCIDER**

---

# 0. Objet du document

Ce document définit l’architecture agentique de Méridian.

Il répond à la question :

> **Comment Méridian transforme-t-il des capacités IA génériques en un système d’experts spécialisés, gouvernés, vérifiables et mobilisables selon les situations réelles de l’entreprise ?**

Le document complète :

- la Product Vision ;
- le Product Blueprint ;
- la Functional Architecture ;
- la Technical Architecture ;
- le Domain Model & Information Architecture.

Il formalise :

- la différence entre Agent, Expert, Skill et Tool ;
- le catalogue d’experts ;
- le contrat d’expertise ;
- la sélection dynamique des experts ;
- les patterns multi-agents ;
- l’orchestration ;
- les missions ;
- les budgets ;
- la mémoire ;
- le contexte ;
- la contradiction ;
- l’évaluation ;
- les sorties structurées ;
- la confiance ;
- les droits ;
- la collaboration humaine ;
- la création et l’évolution des expertises.

Le principe fondamental est :

> **Un Expert Méridian n’est pas un persona LLM. C’est une capacité cognitive gouvernée, dotée de méthodes, de preuves, d’outils, de limites et de responsabilités explicites.**

---

# 1. Pourquoi Méridian a besoin d’un Expert Framework

La fondation de Méridian découvre et maintient une représentation vivante de l’entreprise.

Mais la connaissance seule ne suffit pas.

Une même réalité peut être interprétée différemment selon la question.

Exemple :

> « Une application effectue 2 000 appels supplémentaires par heure. »

L’Expert Performance peut y voir :

> une dérive de charge.

L’Expert Architecture :

> une nouvelle dépendance ou un mauvais découpage.

L’Expert Processus :

> une étape métier supplémentaire.

L’Expert Client :

> une augmentation potentielle du temps de parcours.

L’Expert Finance :

> un coût opérationnel supplémentaire.

Le rôle de l’architecture agentique n’est donc pas d’ajouter des agents partout.

Il est de déterminer :

> **quelle expertise doit regarder quelle partie de la réalité, avec quelles preuves, pour répondre à quelle question.**

---

# 2. Principes agentiques

## 2.1 Spécialiser avant de multiplier

Créer vingt agents génériques portant des noms différents ne produit pas vingt expertises.

La spécialisation doit être réelle.

Elle doit porter sur :

- compétences ;
- méthodes ;
- outils ;
- sources ;
- ontologies ;
- critères de preuve ;
- contraintes ;
- outputs.

---

## 2.2 L’agent ne possède pas la vérité

L’agent consomme la connaissance de Méridian.

Il produit :

- observations interprétées ;
- hypothèses ;
- objections ;
- propositions de Claims ;
- scénarios.

Il ne modifie jamais silencieusement la vérité autoritative.

---

## 2.3 Preuve obligatoire pour les affirmations importantes

Une contribution d’expert doit pouvoir dire :

```text
Finding
↓
Claim(s)
↓
Evidence
```

Une conclusion sans preuve peut rester une hypothèse, mais ne doit pas devenir un Claim mature.

---

## 2.4 L’expert peut dire « je ne sais pas »

Le système doit préférer :

> information insuffisante

à :

> réponse plausible inventée.

---

## 2.5 L’orchestration doit être proportionnelle à la difficulté

Un lookup simple ne doit pas déclencher six experts.

Inversement, une décision d’entreprise complexe ne doit pas être confiée à une seule invocation LLM.

---

## 2.6 Contradiction avant consensus artificiel

L’objectif n’est pas que les agents « se mettent d’accord ».

L’objectif est de comprendre :

- où ils convergent ;
- où ils divergent ;
- pourquoi ;
- quelles preuves manquent.

---

## 2.7 Humain aux points de gouvernance

L’humain doit pouvoir :

- confirmer ;
- contester ;
- arrêter ;
- modifier le périmètre ;
- ajouter une expertise ;
- arbitrer ;
- décider.

---

# 3. Concepts fondamentaux

Méridian doit distinguer clairement les concepts suivants.

---

## 3.1 Agent

Un Agent est une **instance d’exécution cognitive**.

Il possède temporairement :

- objectif ;
- contexte ;
- outils ;
- budget ;
- instructions ;
- mémoire de travail.

Un Agent naît pour accomplir une mission.

Il peut ensuite disparaître.

---

## 3.2 Expert

Un Expert est une **capacité spécialisée durable**.

Exemple :

```text
Expert Architecture
Expert Parcours Client
Expert Processus
Expert Résilience
Expert Hypothèque
```

Il définit comment un Agent spécialisé doit travailler.

---

## 3.3 Skill

Une Skill est une compétence réutilisable.

Exemples :

```text
dependency_analysis
root_cause_analysis
business_rule_extraction
journey_friction_analysis
impact_analysis
historical_feature_reconstruction
```

Plusieurs experts peuvent partager une Skill.

---

## 3.4 Tool

Un Tool permet d’agir ou de consulter une capacité externe.

Exemples :

```text
query_graph
search_claims
search_code
retrieve_incidents
compare_metrics
create_hypothesis
propose_claim
```

---

## 3.5 Mission

Une Mission représente un travail cognitive assigné à un ou plusieurs experts.

Exemple :

> Déterminer si l’augmentation des reprises manuelles est causée par le changement du service d’admissibilité.

---

## 3.6 Contribution

Une Contribution est le résultat structuré d’un Expert.

Elle n’est pas nécessairement la conclusion de l’investigation.

---

# 4. Modèle conceptuel

```text
Investigation
     │
     ▼
Mission
     │
     ▼
Expert Selection
     │
     ├──────────────┐
     ▼              ▼
Expert A         Expert B
     │              │
     ▼              ▼
Agent Run        Agent Run
     │              │
     └──────┬───────┘
            ▼
     Contributions
            │
            ▼
      Contradiction
            │
            ▼
        Synthesis
            │
            ▼
         Scenario
```

---

# 5. Expert Definition

Chaque Expert doit être défini comme une ressource versionnée.

```yaml
ExpertDefinition:
  id:
  version:
  name:
  domain:
  purpose:
  competencies:
  supported_questions:
  skills:
  allowed_tools:
  allowed_sources:
  required_context:
  methods:
  evidence_policy:
  contradiction_policy:
  output_schema:
  model_policy:
  budget_policy:
  autonomy_level:
  security_policy:
  stopping_rules:
  evaluation_suite:
```

---

# 6. Exemple — Expert Architecture

```yaml
id: EXP-ARCHITECTURE
version: 4
name: Enterprise Application Architecture Expert

purpose:
  Comprendre les structures, dépendances, responsabilités
  et impacts architecturaux.

competencies:
  - dependency_analysis
  - impact_analysis
  - topology_analysis
  - architecture_reconstruction
  - modernization_analysis

allowed_tools:
  - query_mesh
  - query_code_graph
  - search_claims
  - retrieve_architecture_docs
  - retrieve_changes

evidence_policy:
  critical_findings:
    minimum_evidence: 2
    independent_sources_preferred: true

output_schema:
  - findings
  - proposed_claims
  - hypotheses
  - risks
  - contradictions
  - unknowns
```

---

# 7. Exemple — Expert Processus

L’Expert Processus se concentre sur :

- séquence de travail ;
- étapes manuelles ;
- transferts ;
- délais ;
- duplication ;
- rework ;
- contournements ;
- automatisation possible.

Sources :

- process model ;
- traces applicatives ;
- tickets ;
- activités ;
- documentation ;
- contributions humaines.

---

# 8. Exemple — Expert Client

L’Expert Client se concentre sur :

- parcours ;
- délais ;
- abandons ;
- frictions ;
- canaux ;
- plaintes ;
- impacts des changements ;
- segments.

Il ne doit pas disposer arbitrairement de données individuelles sensibles.

L’accès est gouverné par :

- agrégation ;
- minimisation ;
- classification ;
- finalité.

---

# 9. Exemple — Expert Employé

L’objectif n’est pas de surveiller les individus.

L’expert examine le **travail**.

Il peut comprendre :

- nombre d’étapes ;
- changements d’outil ;
- double saisie ;
- interruptions ;
- reprises ;
- transfert entre équipes ;
- activités à faible valeur.

---

# 10. Taxonomie initiale d’experts

## 10.1 Experts TI

```text
Architecture
Code
Database
Data
Performance
Resilience
Security
Cloud
Legacy
Observability
Quality
Integration
Modernization
FinOps
```

---

## 10.2 Experts métier

Dans une banque, exemples :

```text
Payments
Credit
Mortgage
Fraud
Risk
Compliance
Finance
Operations
Products
Distribution
```

---

## 10.3 Experts transverses

```text
Process
Customer Journey
Employee Experience
Transformation
Strategy
Cost / Value
Regulatory
Decision Analysis
```

---

## 10.4 Meta-experts

Certaines expertises portent sur le raisonnement lui-même.

```text
Contradictor
Evidence Auditor
Scope Analyst
Scenario Critic
Synthesis Expert
```

Ces Meta-experts sont particulièrement importants.

---

# 11. Expert Registry

Tous les Experts sont enregistrés dans un catalogue.

Le Registry contient :

```text
Expert ID
Version
Status
Capabilities
Skills
Model policy
Tool policy
Security scope
Evaluation score
Cost profile
Latency profile
Reliability
```

---

# 12. Lifecycle d’un Expert

```text
DRAFT
↓
EVALUATION
↓
APPROVED
↓
ACTIVE
↓
DEPRECATED
↓
RETIRED
```

Une nouvelle version peut coexister temporairement avec l’ancienne.

---

# 13. Expert Selection

L’Expert Selector détermine quelles expertises sont nécessaires.

Inputs :

```text
question
situation type
entities
domain
current hypotheses
missing knowledge
risk level
user role
budget
```

---

# 14. Sélection déterministe + sémantique

Ne pas demander uniquement au LLM :

> « quels agents dois-je appeler ? »

Combiner :

### Rules

Exemple :

```text
PERFORMANCE_SIGNAL → Performance Expert
```

### Domain mapping

```text
Mortgage Process → Mortgage Expert
```

### Semantic matching

La question ressemble aux compétences déclarées d’un Expert.

### Dynamic escalation

Un Expert découvre qu’une autre compétence est nécessaire.

---

# 15. Expert Selection Score

Exemple :

```text
score =
  skill_match
+ domain_match
+ entity_match
+ historical_success
+ evidence_availability
- cost_penalty
- latency_penalty
```

---

# 16. Minimum Expert Set

L’orchestrateur cherche d’abord le plus petit ensemble capable de traiter la question.

Exemple :

Question simple :

> Pourquoi TBT appelle X ?

Experts :

```text
Code
Architecture
```

Pas besoin de Finance ou Client.

---

# 17. Dynamic Escalation

L’analyse peut découvrir un nouveau besoin.

Exemple :

```text
Performance Expert
↓
détecte nouvelle règle métier
↓
request_expertise(BUSINESS)
↓
Business Expert ajouté
```

L’escalade doit être justifiée et tracée.

---

# 18. Mission Planner

Le Mission Planner transforme une question en missions.

Exemple :

Question :

> Pourquoi les renouvellements hypothécaires prennent-ils plus de temps ?

Missions :

```text
M1 — vérifier évolution du parcours
M2 — vérifier changements applicatifs
M3 — analyser étapes manuelles
M4 — comparer avant/après
M5 — chercher explications concurrentes
```

---

# 19. Mission Contract

```yaml
Mission:
  id:
  goal:
  scope:
  input_refs:
  required_output:
  evidence_requirement:
  allowed_experts:
  budget:
  deadline:
  priority:
  stopping_rule:
```

---

# 20. Mission Scope

Le Scope doit être explicite.

Exemple :

```yaml
scope:
  twins:
    - APP-2748
    - APP-8821
  domains:
    - Mortgage
  time:
    from: 2026-08-01
    to: 2026-09-09
  geography:
    - Canada
```

---

# 21. Patterns multi-agents

Méridian ne doit pas utiliser un seul pattern partout.

Il doit choisir selon la nature du travail.

Patterns principaux :

1. **Agent as Tool**
2. **Graph**
3. **Workflow**
4. **Swarm**
5. **Parallel Specialists**
6. **Debate / Adversarial Review**
7. **Hierarchical Delegation**

---

# 22. Pattern — Agent as Tool

Un orchestrateur principal appelle les experts comme outils.

```text
Orchestrator
├── Architecture Expert
├── Process Expert
├── Client Expert
└── Risk Expert
```

Recommandé lorsque :

- le sujet est bien cadré ;
- l’orchestrateur connaît les expertises nécessaires ;
- le contrôle doit rester central.

C’est le pattern par défaut de Méridian.

---

# 23. Pattern — Graph

Le chemin entre agents est explicite.

```text
Scope Expert
↓
Architecture Expert
↓
Process Expert
↓
Contradictor
↓
Synthesizer
```

Recommandé pour :

- séquences reproductibles ;
- processus cognitifs connus ;
- investigations réglementées.

---

# 24. Pattern — Workflow

Le Workflow organise des tâches dépendantes ou parallèles.

```text
Collect
├→ Architecture
├→ Business
└→ Process
↓
Contradiction
↓
Synthesis
```

Recommandé pour :

- investigations ;
- rapports ;
- traitements longs ;
- scénarios.

Le workflow durable Méridian reste externe au runtime éphémère des agents.

---

# 25. Pattern — Swarm

Un Swarm permet plus d’autonomie entre experts.

À réserver à des problèmes exploratoires lorsque :

- la décomposition n’est pas connue ;
- plusieurs perspectives doivent se découvrir mutuellement ;
- l’espace de recherche est ouvert.

Ne pas l’utiliser comme pattern par défaut.

Risques :

- coût ;
- boucle ;
- bavardage agent-agent ;
- convergence artificielle ;
- difficulté d’audit.

---

# 26. Pattern — Parallel Specialists

Pattern très utile.

```text
                ┌→ Architecture
Investigation ──┼→ Process
                ├→ Business
                └→ Customer
                       ↓
                     Merge
```

Les experts travaillent sur le même corpus ou des scopes spécifiques.

---

# 27. Pattern — Adversarial Review

Après une première hypothèse :

```text
Hypothesis
↓
Contradictor
↓
Search disconfirming evidence
↓
Re-score
```

Objectif :

> éviter le biais de confirmation.

---

# 28. Pattern — Hierarchical Delegation

```text
Lead Expert
├── Specialist A
├── Specialist B
└── Specialist C
```

Pertinent lorsqu’une expertise possède de nombreuses sous-spécialités.

Exemple :

```text
Security Expert
├── IAM
├── Network
├── Application Security
└── Data Security
```

---

# 29. Pattern Selector

L’orchestrateur choisit le pattern selon :

```text
complexity
uncertainty
number_of_domains
need_for_parallelism
need_for_reproducibility
risk
budget
deadline
```

---

# 30. Orchestrator

L’Orchestrator est responsable de :

- comprendre l’objectif ;
- créer les missions ;
- sélectionner les experts ;
- choisir le pattern ;
- distribuer le contexte ;
- suivre les budgets ;
- gérer les échecs ;
- déclencher contradiction ;
- produire une synthèse.

Il ne remplace pas les Experts.

---

# 31. Orchestrator State

```yaml
OrchestrationState:
  investigation_id:
  missions:
  selected_experts:
  current_stage:
  completed_tasks:
  pending_tasks:
  claims_created:
  hypotheses:
  contradictions:
  unknowns:
  token_cost:
  monetary_cost:
  elapsed_time:
```

---

# 32. Durable orchestration

Les investigations peuvent dépasser la durée d’un process agent.

La durabilité appartient au workflow.

Exemple :

```text
Step Functions / Durable Engine
↓
Invoke Agent
↓
Persist Contribution
↓
Next Step
```

L’Agent n’a pas besoin de rester vivant.

---

# 33. Agent Run

Chaque exécution est identifiée.

```yaml
AgentRun:
  id:
  expert_id:
  expert_version:
  mission_id:
  workflow_id:
  model:
  started_at:
  ended_at:
  status:
  input_refs:
  output_ref:
  tool_calls:
  token_usage:
  cost:
  trace_id:
```

---

# 34. Runtime isolation

Chaque Agent Run doit recevoir uniquement :

- les outils autorisés ;
- les sources autorisées ;
- le scope demandé ;
- le minimum de données nécessaires.

Pas d’accès implicite au Mesh global.

---

# 35. Context Assembly

L’un des plus grands risques est d’envoyer trop de contexte au LLM.

Pipeline :

```text
Mission
↓
Context Need Analysis
↓
Knowledge Query
↓
Graph Traversal
↓
Evidence Retrieval
↓
Context Ranking
↓
Context Pack
↓
Agent
```

---

# 36. Context Pack

```yaml
ContextPack:
  mission:
  entities:
  relevant_claims:
  evidence_refs:
  relevant_relationships:
  historical_cases:
  domain_context:
  constraints:
  unknowns:
```

---

# 37. Progressive Disclosure

Ne pas fournir toutes les preuves immédiatement.

L’Agent peut demander :

```text
expand_claim(CLM-100)
retrieve_neighbors(APP-2748)
get_evidence(EVD-91)
```

Cela réduit les tokens.

---

# 38. Context Fingerprint

Chaque Context Pack possède :

```text
hash(claim versions + evidence versions + scope)
```

Permet :

- cache ;
- reproduction ;
- invalidation.

---

# 39. Memory Model

Quatre mémoires distinctes.

---

## 39.1 Working Memory

Contexte temporaire de l’Agent Run.

Durée courte.

---

## 39.2 Conversation Memory

Historique conversationnel de Flore.

---

## 39.3 Expert Memory

Connaissances de travail spécifiques à l’expertise.

Exemple :

- stratégies qui fonctionnent ;
- patterns reconnus ;
- lexique spécialisé.

Cette mémoire reste gouvernée et ne remplace pas les Claims.

---

## 39.4 Enterprise Knowledge

Le référentiel durable de Méridian.

```text
Claims
Evidence
Relationships
Decisions
Learning
```

C’est la source autoritative.

---

# 40. Expert Memory Safety

Une mémoire d’Expert peut contenir :

> « les incidents de ce type sont souvent causés par X »

mais cela reste un **prior**.

Elle ne peut pas convertir cette habitude en vérité du cas courant sans preuve.

---

# 41. Tool Architecture

Les Tools doivent être petits, contrôlables et composables.

Catégories :

```text
KNOWLEDGE
GRAPH
SEARCH
SOURCE
ANALYSIS
DOMAIN
WORKFLOW
WRITE
```

---

# 42. Knowledge Tools

Exemples :

```text
get_twin
get_claim
search_claims
get_evidence
get_unknowns
get_contradictions
get_learning
```

---

# 43. Graph Tools

```text
get_neighbors
find_path
find_dependencies
find_impact_radius
find_related_capabilities
compare_topologies
```

---

# 44. Code Tools

```text
find_symbol
find_references
get_callers
get_callees
retrieve_code_slice
get_commit_diff
get_feature_history
```

---

# 45. Investigation Tools

```text
create_hypothesis
support_hypothesis
challenge_hypothesis
propose_claim
request_expert
create_unknown
create_scenario
```

---

# 46. Tool Gateway

Les agents accèdent aux tools via un Gateway gouverné.

```text
Agent
↓
Tool Gateway
↓
Policy
↓
Authorization
↓
Tool
↓
Source / Meridian Service
```

---

# 47. Tool policy

Chaque tool définit :

```yaml
ToolPolicy:
  roles:
  expert_types:
  allowed_scopes:
  sensitivity:
  rate_limit:
  max_result_size:
  side_effect:
  approval_required:
```

---

# 48. Tool outputs

Les tools doivent retourner des références, pas toujours tout le contenu.

Mauvais :

```text
get_repository() → 40 MB
```

Meilleur :

```text
search_code() → top 10 refs
retrieve_code_slice(ref)
```

---

# 49. Output contract d’un Expert

Structure de référence :

```yaml
ExpertContribution:
  summary:
  findings:
  proposed_claims:
  supported_hypotheses:
  challenged_hypotheses:
  contradictions:
  unknowns:
  risks:
  opportunities:
  evidence_refs:
  confidence:
  reasoning_summary:
  recommended_next_steps:
```

---

# 50. Finding

```yaml
Finding:
  statement:
  importance:
  confidence:
  claim_refs:
  evidence_refs:
```

---

# 51. Proposed Claim

```yaml
ProposedClaim:
  subject_ref:
  predicate:
  object:
  claim_type:
  evidence_refs:
  confidence:
  valid_time:
```

Un `ProposedClaim` passe ensuite dans le Claim Validation Pipeline.

---

# 52. Reasoning Summary

Méridian n’a pas besoin de conserver une chaîne de pensée privée.

Il conserve plutôt :

- justification ;
- preuves ;
- hypothèses ;
- étapes de décision pertinentes ;
- alternatives examinées.

Cela suffit à l’audit produit.

---

# 53. Confidence de l’expert

L’Expert fournit une confiance, mais elle n’est pas finale.

Le système recalcule la confiance selon :

- evidence quality ;
- agreement ;
- contradictions ;
- historique de performance de l’expert.

---

# 54. Expert Reliability

Méridian doit mesurer les experts dans le temps.

Exemples :

```text
claim acceptance rate
evidence coverage
false positive rate
historical outcome accuracy
contradiction discovery rate
latency
cost
```

---

# 55. Reliability by Task

Un Expert peut être excellent sur une tâche et moyen sur une autre.

Exemple :

```text
Architecture Expert:
dependency_analysis = 0.94
cost_estimation = 0.62
```

Le selector doit en tenir compte.

---

# 56. Contradictor Expert

Le Contradictor reçoit :

- hypothèse ;
- preuves ;
- conclusion provisoire.

Sa mission :

> trouver la meilleure objection possible.

Il recherche :

- preuves contraires ;
- causalités alternatives ;
- biais de sélection ;
- données manquantes ;
- erreurs temporelles.

---

# 57. Evidence Auditor

Le Evidence Auditor vérifie :

- la preuve existe ;
- elle est accessible ;
- elle supporte réellement l’affirmation ;
- la version est correcte ;
- elle n’est pas obsolète ;
- plusieurs Claims ne réutilisent pas une preuve hors contexte.

---

# 58. Scope Analyst

Avant une investigation complexe, le Scope Analyst peut déterminer :

- entités ;
- période ;
- domaines ;
- utilisateurs affectés ;
- sources nécessaires.

---

# 59. Scenario Critic

Pour chaque scénario :

> qu’est-ce qui pourrait mal tourner ?

Analyse :

- hypothèses ;
- dépendances ;
- irréversibilité ;
- conséquences secondaires ;
- inconnues.

---

# 60. Synthesis Expert

Le Synthesizer ne doit pas simplement concaténer les contributions.

Il doit construire :

```text
Agreements
Disagreements
Evidence strength
Remaining unknowns
Most plausible explanation
Alternative explanations
```

---

# 61. Cross Examination

Pattern :

```text
Expert A contribution
↓
Expert B critique
↓
Expert A response
↓
Evidence Auditor
↓
Synthesis
```

À utiliser seulement lorsque l’impact justifie le coût.

---

# 62. Stopping Rules

Un système multi-agent doit savoir s’arrêter.

Exemples :

```text
goal_satisfied
confidence_threshold_reached
no_new_evidence
budget_exhausted
time_limit
human_stop
critical_unknown
repeated_cycle_detected
```

---

# 63. Loop Detection

Détecter :

- même tool appelé plusieurs fois ;
- mêmes Claims retournés ;
- même question déléguée ;
- mêmes hypothèses reformulées.

Pattern :

```text
mission fingerprint
+ context fingerprint
+ action history
```

---

# 64. Budget Policy

Chaque Mission possède des plafonds.

```yaml
Budget:
  max_duration:
  max_model_calls:
  max_tokens:
  max_tool_calls:
  max_cost:
  max_experts:
```

---

# 65. Budget Escalation

Si le budget est atteint :

```text
STOP
PARTIAL_RESULT
REQUEST_MORE_BUDGET
ESCALATE_TO_HUMAN
```

Ne pas dépasser automatiquement.

---

# 66. Model Policy

L’Expert ne choisit pas librement le modèle.

```yaml
ModelPolicy:
  default_tier:
  allowed_models:
  max_context:
  temperature:
  fallback_models:
```

---

# 67. Model Routing

Exemple :

```text
Extraction → small/fast model
Classification → small model
Local reasoning → medium
Cross-domain synthesis → strong reasoning model
Critical contradiction → strong reasoning model
```

---

# 68. Deterministic Before Generative

Avant le LLM :

- SQL ;
- graph query ;
- code parsing ;
- statistiques ;
- règles ;
- diff ;
- calcul.

Le LLM intervient quand il faut :

- interpréter ;
- relier ;
- formuler ;
- générer des hypothèses.

---

# 69. Agent autonomy levels

Proposition :

```text
L0 — Answer only
L1 — Read tools
L2 — Propose domain objects
L3 — Create low-risk Meridian objects
L4 — Trigger governed workflows
L5 — External action with approval
```

---

# 70. Autonomy par Expert

Exemple :

```text
Code Expert → L2
Process Expert → L2
Contradictor → L1
Flore Orchestrator → L4
External Change Agent → L5
```

---

# 71. Human Approval

Exiger validation pour :

- décision ;
- modification critique ;
- création d’initiative externe ;
- certains Claims sensibles ;
- changements de domaine d’entreprise ;
- accès supplémentaire.

---

# 72. Agent Identity

Chaque Agent Run doit porter :

```text
agent_id
expert_id
mission_id
user_on_behalf_of
tenant_id
scope
```

Cela permet un audit précis.

---

# 73. User Delegation

Lorsqu’un agent agit au nom d’un utilisateur :

> les droits de l’agent ne peuvent pas dépasser les droits autorisés pour cette mission.

---

# 74. Security Trimming

Le retrieval doit filtrer **avant** le contexte LLM.

```text
Query
↓
Identity + Scope
↓
Authorization Filter
↓
Retrieval
↓
Context
↓
Agent
```

---

# 75. Prompt Injection Defense

Le contenu des Sources est considéré non fiable.

Séparer :

```text
SYSTEM INSTRUCTIONS
TOOLS
MISSION
SOURCE CONTENT
```

Une instruction dans un document n’est jamais une instruction système.

---

# 76. Sensitive Data

Un Expert ne reçoit que les données nécessaires à sa mission.

Pour les experts Client et Employé :

- agrégation ;
- pseudonymisation ;
- minimisation ;
- purpose limitation.

---

# 77. Expert disagreement

Un désaccord ne doit pas automatiquement être résolu par majorité.

Exemple :

```text
Architecture: 0.82
Process: 0.76
Customer: 0.43
```

Le système examine :

- domaine de compétence ;
- qualité des preuves ;
- scope.

---

# 78. Disagreement object

Un désaccord significatif peut devenir :

```yaml
ExpertDisagreement:
  issue:
  contribution_refs:
  competing_claims:
  evidence:
  resolution_status:
```

---

# 79. Expert handoff

Un Expert peut demander :

```text
REQUEST_EXPERT
```

avec :

```yaml
ExpertRequest:
  needed_skill:
  reason:
  question:
  relevant_refs:
  priority:
```

---

# 80. Handoff minimal

Ne pas transmettre toute la conversation.

Transmettre :

- mission ;
- findings pertinents ;
- Claims ;
- Evidence refs ;
- unknowns.

---

# 81. Flore et les Experts

Flore n’est pas un super-expert.

Elle est principalement :

- interface ;
- context resolver ;
- orchestrateur ;
- synthétiseur conversationnel.

Pour une question spécialisée, Flore délègue.

---

# 82. Flore direct answer

Flore peut répondre directement lorsque :

- connaissance déjà mature ;
- simple retrieval ;
- synthèse courte ;
- aucune investigation nécessaire.

---

# 83. Flore investigation escalation

Exemple :

```text
User: Pourquoi le parcours X ralentit ?
↓
Flore searches
↓
Evidence insufficient
↓
Flore proposes investigation
↓
User accepts
↓
Investigation Orchestrator
```

---

# 84. Proactive Expert Invocation

Méridian peut mobiliser des Experts sans question utilisateur lorsqu’une Situation mûrit.

Exemple :

```text
Signal cluster
↓
Situation
↓
Maturity threshold
↓
Architecture Expert quick check
↓
Expression
```

Mais ce mode doit être budgété.

---

# 85. Lightweight Expertise

Pour la maturation continue, utiliser des expertises légères.

Différence :

```text
Quick Expert Check
vs
Full Investigation
```

---

# 86. Investigation levels

Proposition :

### L1 — Triage

1 expert, faible coût.

### L2 — Focused

2-3 experts.

### L3 — Cross-domain

4-6 experts + contradiction.

### L4 — Strategic

multiples domaines + scénarios + revue humaine.

---

# 87. Expert Teams

Des équipes préconfigurées peuvent exister.

Exemple :

```text
INCIDENT_TEAM
- Observability
- Performance
- Architecture
- Contradictor

MODERNIZATION_TEAM
- Architecture
- Legacy
- Data
- Process
- Finance

CUSTOMER_FRICTION_TEAM
- Journey
- Process
- Application
- Product
```

---

# 88. Teams ≠ exécution automatique

L’équipe est un template.

L’orchestrateur peut :

- retirer ;
- ajouter ;
- remplacer.

---

# 89. Investigation plan

Avant lancement complexe :

```yaml
InvestigationPlan:
  question:
  missions:
  experts:
  pattern:
  budget:
  expected_duration_class:
  approval_points:
```

---

# 90. Progressive Results

Le système publie les résultats fiables dès qu’ils arrivent.

Exemple :

```text
✓ architecture complete
✓ 3 dependencies confirmed
● process analysis
○ customer analysis
```

---

# 91. Partial Contribution

Une Contribution peut avoir :

```text
PARTIAL
COMPLETE
FAILED
BLOCKED
```

---

# 92. Failure Handling

Un Expert peut échouer.

L’orchestrateur décide :

```text
retry
fallback model
alternate expert
continue without
human escalation
```

---

# 93. No single point of cognitive failure

Une investigation critique ne devrait pas dépendre d’un seul modèle ou d’un seul Expert pour tous les faits.

---

# 94. Evaluation Framework

Chaque Expert possède une suite d’évaluation.

Types :

```text
unit cognitive tests
golden cases
tool-use tests
evidence tests
security tests
adversarial tests
historical replay
```

---

# 95. Golden Cases

Exemple Expert Code :

```text
Question:
Quelle méthode déclenche la validation X ?

Expected:
specific symbol
specific call path
specific evidence
```

---

# 96. Historical Replay

Rejouer de vraies situations historiques :

- incident ;
- migration ;
- changement ;
- investigation.

Comparer :

```text
what expert predicted
vs
what actually happened
```

---

# 97. Evaluation dimensions

```text
Correctness
Evidence coverage
Relevance
Tool selection
Cost
Latency
Safety
Calibration
Unknown recognition
Contradiction ability
```

---

# 98. Calibration

Un Expert bien calibré doit avoir :

```text
confidence 0.9
```

seulement lorsqu’il est réellement souvent correct dans ces cas.

---

# 99. AgentCore / runtime observability

L’architecture doit tracer au minimum :

- Agent Run ;
- sessions ;
- latency ;
- errors ;
- model calls ;
- tool calls ;
- token usage ;
- gateway access ;
- memory interactions.

Ces traces doivent être corrélées aux objets Méridian.

---

# 100. Cognitive Trace

Exemple :

```text
INV-1024
└── Mission M1
    └── Architecture Expert v4
        ├── query_mesh
        ├── retrieve_code
        ├── proposed CLM-88
        └── contribution EXC-22
```

---

# 101. Agent Observability

Dashboard par Expert :

```text
runs
success
failures
avg latency
avg cost
tool distribution
accepted claims
rejected claims
contradictions found
```

---

# 102. Quality Gate

Avant activation d’un nouvel Expert :

```text
schema compliance
minimum evaluation score
security review
tool review
cost benchmark
prompt injection tests
```

---

# 103. Expert Versioning

Une investigation garde :

```text
Expert Architecture v4.2
```

Même si v5 est déployée plus tard.

---

# 104. Prompt Versioning

Conserver :

```text
expert definition version
system instruction version
skill version
tool contract version
model
```

---

# 105. Expert Evolution

Le système peut suggérer :

> cet Expert échoue fréquemment sur ce type de question.

Mais la modification de l’Expert reste gouvernée.

---

# 106. Learning from Outcomes

Les Outcomes peuvent alimenter l’évaluation.

Exemple :

Expert Strategy recommande :

> scénario B.

Résultat réel :

> scénario B n’atteint pas le gain attendu.

Cela ne signifie pas automatiquement que l’Expert était mauvais.

Analyser :

- hypothèses ;
- changement de contexte ;
- exécution ;
- erreurs de prédiction.

---

# 107. Expert Training Data

Méridian doit être prudent avant d’utiliser automatiquement ses interactions comme données d’entraînement.

Préférer :

- curated examples ;
- approved Learnings ;
- synthetic evals ;
- historical validated cases.

---

# 108. Skills

Une Skill doit être versionnée indépendamment lorsque possible.

Exemple :

```yaml
Skill:
  id: impact_analysis
  version: 3
  input_contract:
  output_contract:
  method:
  required_tools:
  evaluation_suite:
```

---

# 109. Skill composition

Expert Architecture :

```text
dependency_analysis
+ impact_analysis
+ topology_analysis
```

Expert Modernization :

```text
dependency_analysis
+ capability_overlap
+ migration_analysis
+ risk_analysis
```

---

# 110. Expert Factory

À terme, Méridian peut proposer un assistant pour créer un Expert.

Workflow :

```text
Define purpose
↓
Select skills
↓
Select sources
↓
Select tools
↓
Define evidence policy
↓
Generate draft
↓
Evaluation
↓
Human approval
↓
Registry
```

---

# 111. No auto-production expert

Un Expert généré ne passe jamais directement en production.

---

# 112. Domain Ontologies

Les Experts métier peuvent s’appuyer sur des ontologies.

Exemple :

```text
Mortgage
Loan
Application
Approval
Renewal
Risk
Rate
Customer
Advisor
```

L’ontologie fournit un langage partagé.

---

# 113. Ontology vs Claim

L’ontologie dit :

> quels concepts existent.

Le Claim dit :

> ce qui est vrai dans l’entreprise.

---

# 114. Expert Local Knowledge

Un Expert peut posséder :

- glossaire ;
- méthodes ;
- patterns ;
- règles métier génériques ;
- normes.

Mais la connaissance spécifique à l’entreprise vient de Méridian.

---

# 115. External Knowledge

Certains experts peuvent consulter des sources externes gouvernées.

Exemple :

- normes ;
- documentation fournisseur ;
- réglementation.

L’origine externe doit rester visible.

---

# 116. Business Experts

Un Expert métier doit pouvoir relier :

```text
business concept
↔ process
↔ application
↔ data
↔ customer
```

C’est là que Méridian dépasse le jumeau applicatif.

---

# 117. Process Expert

Architecture conceptuelle :

```text
Process evidence
+ application events
+ claims
+ human model
↓
Process reconstruction
↓
Declared vs observed comparison
↓
Friction analysis
↓
Opportunity
```

---

# 118. Customer Journey Expert

```text
Journey model
+ channel events
+ delays
+ abandon
+ incidents
+ process
↓
Journey interpretation
```

---

# 119. Employee Experience Expert

```text
Process
+ manual tasks
+ rework
+ tool switching
+ support tickets
↓
Work friction model
```

Ne doit pas produire de notation individuelle des employés.

---

# 120. Strategy Expert

Inputs :

- Opportunities ;
- Risks ;
- Capabilities ;
- costs ;
- dependencies ;
- Decisions ;
- Outcomes.

Outputs :

- strategic scenarios ;
- trade-offs ;
- assumptions ;
- uncertainties.

---

# 121. Decision Analysis Expert

Peut aider à comparer des scénarios.

Critères :

```text
value
cost
risk
time
reversibility
customer impact
employee impact
architecture impact
regulatory impact
confidence
```

---

# 122. Investigation Example — TBT historical features

Question :

> Quelles fonctionnalités ont été ajoutées à TBT au cours des trois dernières années ?

Plan :

```text
Historical Scope Expert
↓
Code Expert
+ Change History Expert
+ Functional Expert
↓
Evidence Auditor
↓
Synthesis
```

---

# 123. TBT Expert Missions

```text
M1: cluster commits into candidate changes
M2: link Jira issues to changes
M3: identify user-visible/business functionality
M4: locate code evidence
M5: distinguish technical refactor from feature
M6: cross-validate timeline
```

---

# 124. TBT output

```yaml
Feature:
  name:
  period:
  description:
  confidence:
  jira_refs:
  commits:
  code_refs:
  supporting_claims:
  classification:
    BUSINESS_FEATURE | TECHNICAL_CHANGE | UNCERTAIN
```

---

# 125. Investigation Example — Remove TBT

Question :

> Que se passerait-il si TBT disparaissait dans 18 mois ?

Experts :

```text
Architecture
Data
Process
Business
Operations
Risk
Finance
```

Contradictor obligatoire.

---

# 126. Scenario synthesis

Exemple :

```text
Scenario A — Replace
Scenario B — Decompose
Scenario C — Retain and modernize
```

Le Synthesizer expose :

- valeur ;
- risques ;
- dépendances ;
- inconnues ;
- confiance.

---

# 127. Proactive Opportunity Example

Méridian découvre :

```text
duplicate capabilities
+ low usage
+ high maintenance
```

Quick Expert Team :

```text
Architecture
Finance
Business
```

Output :

> Opportunity candidate.

Pas encore une recommandation de suppression.

---

# 128. Incident Expert Team

Pattern :

```text
Signal
↓
Observability Expert
↓
Performance Expert
├→ Architecture Expert
└→ Change Expert
↓
Contradictor
↓
Root Cause Candidates
```

---

# 129. Cognitive Events

Événements possibles :

```text
ExpertRequested
ExpertStarted
ExpertCompleted
ExpertFailed
ClaimProposed
HypothesisSupported
HypothesisChallenged
ContradictionRaised
UnknownCreated
BudgetThresholdReached
HumanReviewRequested
```

---

# 130. Event payload minimal

```yaml
event_id:
investigation_id:
mission_id:
expert_id:
event_type:
timestamp:
correlation_id:
payload_ref:
```

---

# 131. Agent Write Boundary

Les agents ne doivent pas écrire directement dans toutes les tables.

Pattern :

```text
Agent
↓
Proposed Domain Command
↓
Validation Service
↓
Policy
↓
Domain Aggregate
```

---

# 132. Example — propose_claim

```text
Agent
↓
propose_claim()
↓
Claim Validation
↓
Duplicate Detection
↓
Evidence Validation
↓
Persist as PROPOSED
```

---

# 133. Human contributions

Un humain peut intervenir comme Expert humain.

Exemple :

```text
Application Owner Contribution
```

Elle possède :

- provenance ;
- authority level ;
- date ;
- scope.

---

# 134. Human vs AI disagreement

Si un propriétaire applicatif contredit un Expert :

Méridian ne doit pas toujours privilégier automatiquement l’humain ni l’IA.

Il compare :

- authority ;
- evidence ;
- temporal context.

---

# 135. Governance Board

Pour les environnements complexes, un comité peut gouverner :

- catalogue d’Experts ;
- autonomie ;
- sources ;
- tools ;
- qualité ;
- coûts ;
- modèles.

---

# 136. Expert Marketplace interne

À terme, les équipes peuvent proposer des Experts.

Mais ils restent dans un Registry gouverné.

Exemple :

```text
Payments Expert — Team Payments
Fraud Rules Expert — Fraud Domain
Mainframe Expert — Legacy Center
```

---

# 137. Certification d’Expert

Niveaux possibles :

```text
EXPERIMENTAL
CERTIFIED
CRITICAL_USE_APPROVED
```

---

# 138. Cross-domain experts

Certains experts peuvent travailler au niveau Mesh.

Exemple :

```text
Enterprise Architect Expert
```

Mais leur accès est plus sensible.

---

# 139. Local Twin Experts

Certains experts peuvent être attachés à un Twin.

Exemple :

```text
TBT Functional Expert
```

Il peut être construit progressivement à partir :

- Claims ;
- historique ;
- lexique ;
- règles.

---

# 140. Generic vs Local Expert

```text
Generic Code Expert
+
TBT Context
=
TBT-specific execution
```

Éviter de créer un modèle séparé pour chaque application.

---

# 141. Expert Context Adapters

Adapter le contexte selon le type.

```text
ArchitectureContextAdapter
ProcessContextAdapter
CustomerContextAdapter
```

Chaque adapter produit un Context Pack spécialisé.

---

# 142. Expert Knowledge Boundary

Un Expert ne doit pas prétendre être compétent hors de son domaine.

Le `supported_questions` sert aussi à refuser ou déléguer.

---

# 143. Unknown-first behavior

Si les preuves sont insuffisantes :

```yaml
status: INSUFFICIENT_EVIDENCE
unknowns:
  - ...
recommended_next_step:
  - connect_source(...)
```

C’est un bon résultat.

---

# 144. Evidence-first prompting

Les prompts système doivent insister sur :

```text
1. retrieve evidence
2. state findings
3. cite refs
4. mark uncertainty
5. propose claims
```

---

# 145. Tool-use-first

Pour une question factuelle disponible dans les tools :

> Tool avant mémoire du modèle.

---

# 146. Expert Response Layers

Une contribution doit permettre plusieurs niveaux d’affichage.

### Executive

Conclusion.

### Analyst

Hypothèses + preuves.

### Technical

Claims + Evidence refs + Tool results.

---

# 147. Synthesis Layers

Même principe pour l’investigation.

```text
Summary
Findings
Disagreements
Evidence
Unknowns
Scenarios
```

---

# 148. Cost-aware orchestration

Avant chaque délégation :

```text
expected_information_gain
vs
expected_cost
```

Un Expert supplémentaire doit apporter une vraie valeur.

---

# 149. Information Gain

Approximation possible :

```text
high impact unknown
+ expert relevance
+ evidence availability
```

---

# 150. Stop when marginal value is low

Exemple :

Les quatre premiers Experts convergent fortement.

Le cinquième apporterait peu de valeur.

Méridian peut arrêter.

---

# 151. Priority queue

Les Agent Runs utilisent des priorités.

```text
P0 Incident
P1 User interactive
P2 Investigation
P3 Opportunity maturation
P4 Background enrichment
```

---

# 152. Concurrency

Limiter :

- experts par investigation ;
- Agent Runs par tenant ;
- requêtes modèle ;
- requêtes source ;
- tool fan-out.

---

# 153. Rate Limits

Une source Jira ou GitHub ne doit pas être saturée par dix Experts identiques.

Le Tool Gateway mutualise et cache.

---

# 154. Shared Retrieval

Pattern :

```text
Evidence Collector
↓
Shared Evidence Set
↓
Multiple Experts
```

Évite de refaire la même recherche.

---

# 155. Shared State

Le shared state contient seulement les informations nécessaires.

Ne pas utiliser une grande conversation globale comme shared state.

---

# 156. Investigation Knowledge Board

Objet commun :

```text
Claims
Hypotheses
Evidence
Unknowns
Contradictions
Findings
```

Les Experts lisent/écrivent via des commandes contrôlées.

---

# 157. Knowledge Board consistency

Les writes sont versionnés.

Deux Experts peuvent proposer des Claims contradictoires.

Le système ne fait pas « last write wins ».

---

# 158. Parallel Merge

À la fin du parallélisme :

```text
normalize
deduplicate
resolve references
detect conflict
score
```

avant synthèse LLM.

---

# 159. Meta-cognitive checks

Avant finalisation :

```text
Do we have enough evidence?
Did we test alternatives?
Are important unknowns unresolved?
Are permissions satisfied?
Is confidence calibrated?
```

---

# 160. Investigation Ready Gate

Une Investigation devient `READY_FOR_DECISION` seulement si :

- synthèse disponible ;
- scénarios disponibles ;
- unknowns critiques exposés ;
- contradictions critiques traitées ou explicitement non résolues ;
- evidence coverage suffisante.

---

# 161. Expert Architecture de référence

```text
                         INVESTIGATION / FLORE
                                  │
                                  ▼
                         MISSION ORCHESTRATOR
                                  │
                 ┌────────────────┼────────────────┐
                 │                │                │
                 ▼                ▼                ▼
          EXPERT SELECTOR   PATTERN SELECTOR   BUDGET MANAGER
                 │                │                │
                 └────────────────┼────────────────┘
                                  ▼
                         DURABLE WORKFLOW
                                  │
              ┌───────────────────┼───────────────────┐
              │                   │                   │
              ▼                   ▼                   ▼
         EXPERT AGENT        EXPERT AGENT        META EXPERT
              │                   │                   │
              └─────────────┬─────┴─────────────┬─────┘
                            ▼                   ▼
                       TOOL GATEWAY       KNOWLEDGE BOARD
                            │                   │
              ┌─────────────┼─────────────┐     │
              ▼             ▼             ▼     │
            Graph         Search        Sources │
              │             │             │     │
              └─────────────┴─────────────┴─────┘
                            │
                            ▼
                    CLAIM / EVIDENCE LAYER
```

---

# 162. AWS / Strands mapping de référence

Une implémentation possible :

```text
Agent definition
→ Strands Agent

Multi-agent local pattern
→ Strands Graph / Swarm / Agent-as-Tool selon cas

Hosted execution
→ Amazon Bedrock AgentCore Runtime

Tool access
→ AgentCore Gateway / Meridian Tool Gateway

Conversational memory
→ AgentCore Memory

Observability
→ AgentCore Observability + CloudWatch + OTEL

Durable workflow
→ AWS Step Functions Standard

Models
→ Amazon Bedrock

Business state
→ Meridian domain services / PostgreSQL

Knowledge
→ Claims / Graph / Search / Evidence stores
```

---

# 163. Important distinction Strands / Workflow durable

Strands fournit des primitives d’agents et plusieurs patterns multi-agents.

Mais Méridian doit maintenir séparément la durabilité métier :

```text
Workflow persisted state
≠
Agent in-process state
```

Une investigation doit survivre à :

- restart ;
- agent crash ;
- timeout ;
- approbation humaine ;
- interruption.

---

# 164. AgentCore Gateway

Le Gateway peut être utilisé comme frontière gouvernée entre agents et capacités.

Objectifs :

- auth ;
- policy ;
- centralisation ;
- observabilité ;
- exposition contrôlée de tools/runtimes.

---

# 165. AgentCore Observability

Les métriques techniques ne suffisent pas.

Méridian ajoute ses propres attributs :

```text
investigation.id
mission.id
expert.id
expert.version
twin.id
domain.id
claim.ids
```

---

# 166. Agent Evaluations

L’évaluation doit devenir un pipeline CI/CD des Experts.

```text
Expert change
↓
Offline eval
↓
Security eval
↓
Tool-use eval
↓
Historical replay
↓
Canary
↓
Production
```

---

# 167. CI/CD Expert

Exemple :

```text
expert.yaml changed
↓
schema validation
↓
golden tests
↓
agent evaluations
↓
cost benchmark
↓
security tests
↓
approval
↓
registry publish
```

---

# 168. Canary

Nouvelle version :

```text
10% low-risk missions
```

Comparer :

- qualité ;
- coût ;
- latence.

---

# 169. Rollback

Le Registry doit pouvoir revenir immédiatement à une version précédente.

---

# 170. Metrics principales

## Qualité

```text
accepted_claim_rate
evidence_coverage
unknown_detection
contradiction_detection
historical_accuracy
```

## Opérations

```text
latency
failure_rate
tool_error_rate
```

## Économie

```text
tokens
cost_per_run
cost_per_investigation
```

---

# 171. North Star agentique

La métrique principale ne doit pas être :

> nombre d’agents exécutés.

Mais plutôt :

> **combien de compréhension fiable chaque dollar et chaque minute de calcul produisent-ils ?**

---

# 172. Anti-patterns

## Persona Agents

> « Tu es un expert bancaire. »

Sans tools, méthodes ni preuves.

## Agent Explosion

Un agent par micro-tâche.

## Swarm Everywhere

Autonomie excessive.

## Shared Giant Context

Tous les agents reçoivent tout.

## Unbounded Delegation

Un agent crée indéfiniment d’autres agents.

## LLM as Arbiter

Le modèle décide seul qui a raison.

## No Evidence Contract

Conclusions impossibles à auditer.

## No Budget

Coût exponentiel.

## Expert = Model

Changer de modèle détruit l’identité de l’expertise.

## Hidden Unknowns

Le système invente pour compléter.

---

# 173. MVP Expert Framework

Le MVP n’a pas besoin de trente Experts.

Commencer avec :

```text
Code Expert
Architecture Expert
Process Expert
Contradictor
Evidence Auditor
Synthesis Expert
```

Puis ajouter un Expert métier lié au cas pilote.

---

# 174. MVP patterns

Implémenter d’abord :

```text
Agent as Tool
Parallel Specialists
Adversarial Review
Durable Workflow
```

Le Swarm peut attendre.

---

# 175. MVP Tool Set

```text
search_claims
query_graph
search_code
get_code_slice
get_changes
get_evidence
create_hypothesis
propose_claim
request_expert
```

---

# 176. MVP use case 1 — TBT

Question historique des trois années.

Démontre :

- Code Expert ;
- Architecture/Functional Expert ;
- evidence ;
- synthèse ;
- rapport.

---

# 177. MVP use case 2 — Investigation

Signal transversal.

Démontre :

- sélection Expert ;
- hypothèse ;
- contradiction ;
- preuve ;
- scénario.

---

# 178. MVP use case 3 — Opportunité

Montre que Méridian ne se limite pas aux incidents.

---

# 179. Phase 2

Ajouter :

```text
Business Expert
Customer Journey Expert
Data Expert
Risk Expert
Scenario Critic
```

---

# 180. Phase 3

Ajouter :

- Expert Marketplace ;
- Domain-created Experts ;
- richer Expert Memory ;
- dynamic teams ;
- proactive expert discovery ;
- strategic simulations.

---

# 181. Critères de succès

Le framework est réussi si :

1. un Expert peut être remplacé sans changer le Domain Model ;
2. une investigation peut survivre à un Agent crash ;
3. toute conclusion importante possède des preuves ;
4. deux Experts peuvent être en désaccord sans perdre l’information ;
5. le coût est mesurable et plafonné ;
6. les droits sont appliqués avant retrieval ;
7. une nouvelle expertise peut être ajoutée sans modifier tout Méridian ;
8. les résultats sont reproductibles par version ;
9. les Experts peuvent explicitement déclarer les inconnues ;
10. la décision reste humaine.

---

# 182. Questions d’architecture à approfondir

Le document suivant devra préciser certains mécanismes cognitifs.

Notamment :

- structure exacte du Claim ;
- calcul de confiance ;
- fusion de Claims ;
- temporalité ;
- provenance ;
- contradiction ;
- knowledge retrieval ;
- Graph RAG ;
- comment un Claim mûrit ;
- comment la connaissance locale devient Mesh knowledge.

Ces sujets seront développés dans :

> **MÉRIDIAN — Knowledge & Claims Architecture**

---

# 183. Références techniques de conception

Cette architecture est compatible avec les capacités contemporaines suivantes :

- Strands Agents : patterns multi-agents de type Graph, Swarm et Workflow ainsi que spécialisation/collaboration ;
- Amazon Bedrock AgentCore Runtime : exécution d’agents ;
- AgentCore Gateway : frontière gouvernée d’accès à des tools et runtimes ;
- AgentCore Memory : mémoire conversationnelle court et long terme ;
- AgentCore Observability : métriques, traces et logs intégrables à l’observabilité AWS/OTEL ;
- AgentCore Evaluations : évaluation automatisée des comportements agentiques ;
- AWS Step Functions Standard : orchestration durable autour des exécutions cognitives.

Le framework Méridian reste volontairement découplé de ces implémentations.

Les concepts `Expert`, `Mission`, `Contribution`, `Evidence`, `Claim` et `Investigation` appartiennent à Méridian.

Ils ne doivent pas devenir des concepts propriétaires d’un fournisseur cloud.

---

# 184. Conclusion

L’architecture agentique de Méridian ne consiste pas à créer un réseau de personnages IA.

Elle consiste à créer une **organisation cognitive gouvernée**.

Chaque Expert possède :

> **un domaine + des compétences + des méthodes + des tools + des preuves + des limites + une politique de confiance.**

L’Orchestrator ne cherche pas à faire travailler le plus grand nombre d’agents.

Il cherche à mobiliser :

> **le plus petit ensemble d’expertises capable de réduire significativement l’incertitude.**

Le système agentique suit alors cette logique :

```text
Question / Situation
↓
Mission
↓
Scope
↓
Expert Selection
↓
Evidence Retrieval
↓
Expert Work
↓
Contradiction
↓
Synthesis
↓
Claims / Unknowns / Scenarios
↓
Human Decision
```

Cette architecture permet à Méridian de passer progressivement :

> d’un système qui **connaît les applications**

à un système qui peut mobiliser des expertises TI, métier, client, employé et stratégique pour :

> **comprendre l’entreprise comme un système vivant et exploiter cette compréhension pour l’améliorer.**

---

# 185. Prochain document

Le prochain document recommandé est :

> **MÉRIDIAN — Knowledge & Claims Architecture**

Il doit maintenant approfondir le véritable cerveau informationnel de Méridian :

- Claim ontology ;
- Evidence model ;
- confidence ;
- maturity ;
- provenance ;
- temporal knowledge ;
- contradiction ;
- reconciliation ;
- local Twin knowledge ;
- Mesh knowledge ;
- Graph RAG ;
- retrieval ;
- knowledge lifecycle ;
- claim invalidation ;
- claim propagation ;
- knowledge quality.

C’est ce document qui expliquera précisément comment Méridian passe :

> **de données dispersées à une connaissance exploitable et digne de confiance.**
