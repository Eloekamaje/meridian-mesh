# MÉRIDIAN — MVP Definition & Delivery Roadmap
## Définition du MVP, vertical slices, séquencement de livraison, critères de sortie et trajectoire produit

**Statut :** Plan de livraison de référence  
**Version :** 1.0  
**Produit :** MÉRIDIAN  
**Tagline :** **DÉCOUVRIR · COMPRENDRE · DÉCIDER**

---

# 0. Objet du document

Ce document transforme la vision, les architectures et les modèles de Méridian en un plan exécutable.

Il répond à la question :

> **Quel est le plus petit produit Méridian capable de démontrer une valeur réelle, de manière crédible, extensible et mesurable ?**

Le MVP ne doit pas chercher à reproduire toute la vision.

Il doit prouver les mécanismes centraux :

```text
Connecter
↓
Découvrir
↓
Structurer
↓
Comprendre
↓
Faire émerger
↓
Investiguer
↓
Décider
↓
Mesurer
```

Le principe fondamental est :

> **Le MVP doit démontrer une boucle de valeur complète, pas une collection de features partielles.**

---

# 1. Définition stratégique du MVP

Le MVP de Méridian doit prouver cinq choses.

## 1.1 Méridian peut découvrir une application

À partir de plusieurs Sources.

## 1.2 Méridian peut transformer les données en connaissance fiable

Claims + Evidence + Confidence + Temporalité.

## 1.3 Le Mesh apporte une compréhension transverse

Relations, dépendances, contradictions, voisinage.

## 1.4 Flore permet d’exploiter cette connaissance

Questions, explications, navigation, investigations.

## 1.5 Méridian peut transformer une découverte en décision

Situation → Investigation → Scénarios → Decision.

---

# 2. Ce que le MVP n’est pas

Le MVP n’est pas :

- une plateforme complète d’entreprise ;
- une CMDB IA ;
- un assistant de code ;
- un simple Graph RAG ;
- un dashboard d’incidents ;
- un moteur multi-agent expérimental ;
- une démo vidéo figée.

Il doit être un **produit opérationnel réduit mais cohérent**.

---

# 3. Thèse du MVP

> **Si Méridian peut comprendre TBT de manière vérifiable, relier cette compréhension à son environnement, détecter un sujet significatif et conduire une investigation structurée jusqu’à une décision, alors le cœur du produit est démontré.**

---

# 4. MVP North Star

La métrique principale du MVP :

> **Temps nécessaire pour passer d’une question complexe sur une application à une réponse exploitable, sourcée et suffisamment fiable pour décider d’une prochaine action.**

---

# 5. Core Value Loop

La boucle MVP :

```text
Source
↓
Twin
↓
Claims
↓
Mesh
↓
Signal / Situation
↓
Flore
↓
Investigation
↓
Scenario
↓
Decision
```

---

# 6. Vertical Slice de référence

Le Vertical Slice principal doit être construit autour d’une application réelle.

Exemple :

```text
TBT
```

Sources :

```text
GitHub
Jira
Confluence
Datadog
CMDB
```

---

# 7. Vertical Slice #1 — Naissance du Twin

Objectif :

> créer un Twin TBT à partir de Sources réelles et produire une première compréhension fiable.

Étapes :

```text
Connect source
↓
Discover artifacts
↓
Extract code structure
↓
Build Claims
↓
Attach Evidence
↓
Resolve neighbors
↓
Publish Twin Summary
```

---

# 8. Critères de sortie VS1

Le slice est réussi si :

1. le Twin existe avec identité stable ;
2. au moins 3 types de Sources sont connectés ;
3. des Claims sont générés ;
4. les Claims ont Evidence et provenance ;
5. un résumé vivant est produit ;
6. les principales dépendances sont visibles ;
7. les Unknowns sont explicités.

---

# 9. Vertical Slice #2 — Question historique complexe

Question de référence :

> **Quelles fonctionnalités ont été ajoutées à TBT au cours des trois dernières années, avec les références de code ?**

Ce cas démontre :

- résolution d’intention ;
- scope temporel ;
- analyse Git ;
- regroupement de changements ;
- liaison Jira ;
- interprétation fonctionnelle ;
- Evidence ;
- génération de rapport.

---

# 10. Critères de sortie VS2

Le slice est réussi si :

- les changements techniques sont distingués des fonctionnalités ;
- chaque fonctionnalité possède un niveau de confiance ;
- les références de code sont spécifiques ;
- l’analyse est incrémentale ;
- le résultat est reproductible ;
- le traitement long expose sa progression.

---

# 11. Vertical Slice #3 — Relation Mesh

Objectif :

> démontrer que Méridian comprend TBT dans son environnement.

Exemple :

```text
TBT
↓
Eligibility Service
↓
Process
↓
Domain
```

---

# 12. Valeur VS3

L’utilisateur peut poser :

> Qui dépend de TBT ?

> Quelles capacités métier seraient affectées ?

> Cette relation est-elle déclarée ou observée ?

---

# 13. Critères de sortie VS3

- relations inter-Twins ;
- provenance ;
- declared vs observed ;
- cross-validation ;
- visualisation Atlas ;
- temporalité minimale.

---

# 14. Vertical Slice #4 — Situation émergente

Exemple :

```text
new dependency
+ latency increase
+ recent deployment
```

Méridian crée :

```text
Signal
↓
Situation candidate
↓
Maturation
↓
Expression
```

---

# 15. Critères de sortie VS4

Le système doit :

- dédupliquer ;
- corréler ;
- expliquer pourquoi les Signals sont regroupés ;
- montrer confidence et maturity ;
- éviter de créer directement une Investigation pour tout.

---

# 16. Vertical Slice #5 — Investigation

Question :

> Pourquoi cette situation apparaît-elle ?

Workflow :

```text
Scope
↓
Hypotheses
↓
Architecture Expert
↓
Code / Observability Expert
↓
Contradictor
↓
Synthesis
```

---

# 17. Critères de sortie VS5

- 2+ hypothèses ;
- Evidence pour et contre ;
- au moins 2 Experts ;
- contradiction explicite ;
- Unknowns ;
- synthèse structurée ;
- progression durable.

---

# 18. Vertical Slice #6 — Decision

À partir de l’Investigation :

```text
Scenario A
Scenario B
Scenario C
```

L’utilisateur compare :

- impact ;
- risque ;
- coût ;
- temps ;
- réversibilité.

---

# 19. Critères de sortie VS6

- scénarios structurés ;
- comparaison claire ;
- recommandation distincte de la décision ;
- décision humaine ;
- Decision Snapshot ;
- expected outcomes.

---

# 20. Vertical Slice #7 — Outcome Loop

Version MVP simple.

Exemple :

```text
Decision
↓
Initiative
↓
Metric
↓
Observed outcome
↓
Learning
```

---

# 21. Critères de sortie VS7

- baseline ;
- expected ;
- observed ;
- différence ;
- Learning ;
- nouveau Signal possible.

---

# 22. MVP Product Scope

Le MVP doit inclure les capacités suivantes.

---

# 23. P0 — Core Knowledge

```text
Twin
Source
Artifact
Evidence
Claim
Relationship
Unknown
Contradiction
```

---

# 24. P0 — Source Connectors

Minimum :

```text
GitHub
Jira
Datadog
```

Confluence / CMDB selon accessibilité.

---

# 25. P0 — Code Intelligence

Minimum :

```text
repo clone/fetch
language detection
AST/symbol extraction
dependency extraction
change diff
code search
code refs
```

---

# 26. P0 — Claim Engine

Support :

```text
create
validate
version
evidence
confidence
status
```

---

# 27. P0 — Mesh

Support :

```text
relationships
cross-twin linking
basic reconciliation
declared vs observed
```

---

# 28. P0 — Flore

Support :

```text
contextual chat
entity resolution
simple lookup
explain
historical analysis
investigation creation
report generation
```

---

# 29. P0 — Atlas

Support :

```text
domains
twins
relations
focus
layers
selection
basic temporal info
```

---

# 30. P0 — Investigation

Support :

```text
scope
hypotheses
Evidence
Experts
Contradiction
Synthesis
```

---

# 31. P0 — Scenarios & Decision

Support :

```text
scenario
comparison
recommendation
human decision
snapshot
```

---

# 32. P0 — Jobs

Obligatoire :

```text
job_id
progress
partial result
retry
cancel
resume
SSE
```

---

# 33. P0 — Security

Minimum :

```text
SSO
tenant_id
RBAC
source permissions
security trimming
audit
```

---

# 34. P0 — Observability

Minimum :

```text
logs
traces
metrics
agent runs
tool calls
token/cost
```

---

# 35. P1 — Discovery & Maturation

Après Core Loop stable.

```text
Signals
Situations
Correlation
Maturity
Expression
Opportunity
Risk
```

---

# 36. P1 — Opportunity

Simple lifecycle :

```text
Detected
Qualified
Investigating
Decided
```

---

# 37. P1 — Continuous Improvement

Version minimale :

```text
Expected Outcome
Observed Outcome
Learning
```

---

# 38. P1 — Trust Panel

Visible dans :

- Flore ;
- Claim ;
- Twin ;
- Investigation.

---

# 39. P2 — Advanced UX

```text
before/after Atlas
Transformation Memory
advanced Radar
saved views
pattern clusters
```

---

# 40. Explicitly Deferred

À ne pas construire dans le MVP initial :

- Swarm générique ;
- Marketplace complet d’Experts ;
- multi-region complexe ;
- process mining complet ;
- customer digital twin ;
- employee digital twin ;
- autonomous external actions ;
- full causal inference engine ;
- predictive strategy engine.

---

# 41. Why defer Swarm

Le Swarm augmente :

- complexité ;
- coût ;
- audit difficulty.

Le MVP peut prouver la valeur avec :

```text
Agent-as-Tool
+
parallel Experts
+
contradiction
```

---

# 42. Why defer full enterprise ontology

Commencer par une ontologie minimale.

Ajouter au fur et à mesure.

---

# 43. Why defer full proactive discovery

Le moteur de découverte doit d’abord être calibré sur peu de use cases.

---

# 44. Architecture MVP

```text
React
↓
BFF
↓
Domain Services
↓
Workflow Engine
↓
Agent Runtime
↓
Knowledge / Graph / Search
↓
Sources
```

---

# 45. Reference technical stack

Option AWS :

```text
Frontend
→ React + TypeScript

BFF
→ Spring Boot / Kotlin / Java / Node

Workflow
→ Step Functions Standard

Agent
→ Strands + Bedrock / AgentCore

Transactional store
→ Aurora PostgreSQL

Evidence
→ S3

Search
→ OpenSearch

Graph
→ Neptune or existing graph engine

Events
→ EventBridge + SQS
```

---

# 46. Keep MVP architecture reversible

Le MVP ne doit pas enfermer :

- Claim Model ;
- Expert Model ;
- Workflow ;
- Domain logic ;

dans des APIs propriétaires.

---

# 47. Delivery principles

## 47.1 Vertical slices first

Ne pas construire :

> tous les Sources

puis :

> tout le Knowledge

puis :

> toute l’UI.

Construire bout en bout.

---

# 48. Thin slice strategy

Chaque slice doit traverser :

```text
UI
API
Domain
Workflow
Knowledge
Source
```

---

# 49. Slice 0 — Platform Skeleton

Objectif :

- repo ;
- CI/CD ;
- environments ;
- authentication ;
- tracing ;
- basic UI shell.

---

# 50. Slice 1 — One Source to One Claim

Exemple :

```text
GitHub file
↓
Observation
↓
Evidence
↓
Claim
↓
UI
```

C’est le premier milestone technique réel.

---

# 51. Slice 2 — Twin Birth

Ajoute :

- source manifest ;
- initial discovery ;
- Twin Summary ;
- neighbors.

---

# 52. Slice 3 — Flore over Knowledge

Ajoute :

- lookup ;
- explain ;
- evidence.

---

# 53. Slice 4 — Historical report

Ajoute :

- long job ;
- workflow ;
- code refs ;
- Jira.

---

# 54. Slice 5 — Mesh

Ajoute relations cross-app.

---

# 55. Slice 6 — Situation

Ajoute Signal + correlation.

---

# 56. Slice 7 — Investigation

Ajoute hypothèses + Experts + contradiction.

---

# 57. Slice 8 — Decision

Ajoute scenarios + Decision.

---

# 58. Slice 9 — Outcome

Ajoute mesure minimale.

---

# 59. Delivery Waves

Proposition :

```text
Wave 0 — Foundations
Wave 1 — Know
Wave 2 — Understand
Wave 3 — Investigate
Wave 4 — Decide
Wave 5 — Learn
```

---

# 60. Wave 0 — Foundations

Objectifs :

- architecture ;
- CI/CD ;
- identity ;
- observability ;
- job framework ;
- event envelope ;
- domain skeleton.

---

# 61. Wave 0 Exit Criteria

- environment ready ;
- service templates ;
- tracing ;
- audit baseline ;
- deployment repeatable.

---

# 62. Wave 1 — Know

Objectifs :

```text
Sources
Twin
Artifacts
Evidence
Claims
```

---

# 63. Wave 1 Exit Criteria

L’utilisateur peut ouvrir TBT et voir une compréhension initiale sourcée.

---

# 64. Wave 2 — Understand

Objectifs :

```text
Mesh
Atlas
Flore
Historical analysis
```

---

# 65. Wave 2 Exit Criteria

L’utilisateur peut poser une question complexe et naviguer dans les dépendances.

---

# 66. Wave 3 — Investigate

Objectifs :

```text
Signal
Situation
Investigation
Experts
Contradiction
```

---

# 67. Wave 3 Exit Criteria

Un phénomène réel peut être investigué de manière structurée.

---

# 68. Wave 4 — Decide

Objectifs :

```text
Scenario
Decision Board
Decision Snapshot
```

---

# 69. Wave 4 Exit Criteria

Une décision peut être prise avec preuves et alternatives.

---

# 70. Wave 5 — Learn

Objectifs :

```text
Expected Outcome
Observed Outcome
Learning
```

---

# 71. Wave 5 Exit Criteria

Le système ferme une première boucle.

---

# 72. Roadmap horizon

Le roadmap peut être organisé en trois horizons.

---

# 73. Horizon A — MVP

But :

> prouver le coeur.

---

# 74. Horizon B — Productization

But :

- fiabilité ;
- gouvernance ;
- multi-team ;
- meilleure UX ;
- qualité.

---

# 75. Horizon C — Enterprise / SaaS

But :

- multi-tenant ;
- self-service Sources ;
- Expert Marketplace ;
- extensibilité ;
- advanced learning.

---

# 76. MVP Duration Principle

Le planning doit être basé sur :

- équipe ;
- dépendances ;
- accessibilité des Sources.

Ne pas promettre un calendrier arbitraire.

---

# 77. Team Shape

Équipe idéale minimale :

```text
1 Product / Domain Lead
1 Tech Lead / Architect
2 Backend / AI Engineers
1 Frontend Engineer
1 Data / Knowledge Engineer
0.5 DevOps / Platform
0.5 UX/UI
```

Certaines personnes peuvent cumuler plusieurs rôles.

---

# 78. Product Lead responsibilities

- scope ;
- use cases ;
- value ;
- feedback ;
- prioritization.

---

# 79. Tech Lead responsibilities

- architecture ;
- contracts ;
- boundaries ;
- technical quality.

---

# 80. AI / Knowledge Engineer

- Claims ;
- retrieval ;
- Agents ;
- evaluations.

---

# 81. Frontend

- Atlas ;
- Flore ;
- investigation surfaces.

---

# 82. Platform

- deployment ;
- observability ;
- security ;
- workflows.

---

# 83. UX/UI

Même part-time au départ, indispensable pour éviter une interface outil interne.

---

# 84. Backlog structure

Le backlog doit être organisé par :

```text
Capability
↓
Epic
↓
Vertical Slice
↓
Story
↓
Acceptance Criteria
```

---

# 85. Capability map MVP

```text
C1 Source Connectivity
C2 Twin Intelligence
C3 Claims & Evidence
C4 Mesh
C5 Flore
C6 Atlas
C7 Discovery
C8 Investigation
C9 Decision
C10 Learning
C11 Security
C12 Platform
```

---

# 86. Epic — Source Connectivity

Stories :

- GitHub connector ;
- Jira connector ;
- Source manifest ;
- sync cursor ;
- health ;
- permission.

---

# 87. Epic — Claims

Stories :

- Claim schema ;
- Evidence model ;
- versioning ;
- confidence ;
- provenance ;
- API.

---

# 88. Epic — Twin

Stories :

- creation ;
- birth workflow ;
- summary ;
- knowledge health ;
- relations.

---

# 89. Epic — Code Intelligence

Stories :

- language detection ;
- symbol graph ;
- dependency extraction ;
- diff ;
- relevant code retrieval.

---

# 90. Epic — Mesh

Stories :

- entity resolution ;
- cross-twin links ;
- relation confidence ;
- graph projection.

---

# 91. Epic — Flore

Stories :

- context resolver ;
- intent ;
- tools ;
- trust ;
- jobs.

---

# 92. Epic — Investigation

Stories :

- scope ;
- hypothesis ;
- Expert run ;
- contradiction ;
- synthesis.

---

# 93. Epic — Decision

Stories :

- scenarios ;
- comparison ;
- snapshot ;
- approval.

---

# 94. Definition of Ready

Une Story est Ready si :

- user value claire ;
- domain object identifié ;
- acceptance criteria ;
- security impact ;
- observability impact.

---

# 95. Definition of Done

Une Story est Done si :

- functional tests ;
- unit tests ;
- observability ;
- security ;
- docs ;
- UX state ;
- error state ;
- performance acceptable.

---

# 96. Feature flags

Utiliser pour activer progressivement :

- new Experts ;
- new detectors ;
- new Atlas layers ;
- new model routing.

---

# 97. Experimentation

Les éléments IA doivent pouvoir être A/B ou canary testés techniquement.

---

# 98. Evaluation before release

Chaque capacité IA possède :

```text
golden cases
expected outputs
evidence checks
cost
latency
```

---

# 99. MVP Golden Cases

Minimum :

1. TBT dependency.
2. TBT feature history.
3. Unknown relation.
4. Contradictory evidence.
5. Signal after change.
6. Investigation with two hypotheses.
7. Scenario comparison.

---

# 100. Demo Golden Path

Une démo parfaite doit suivre une seule histoire cohérente.

---

# 101. Demo Act 1 — Birth

Créer TBT.

---

# 102. Demo Act 2 — Understand

Flore :

> Que sais-tu de TBT ?

---

# 103. Demo Act 3 — Explore

Atlas révèle voisins.

---

# 104. Demo Act 4 — Historical question

> Quelles fonctionnalités ont été ajoutées ?

---

# 105. Demo Act 5 — Situation

Méridian détecte un phénomène.

---

# 106. Demo Act 6 — Investigate

Ouverture Investigation.

---

# 107. Demo Act 7 — Decide

Comparer scénarios.

---

# 108. Demo Act 8 — Learn

Afficher un Outcome simulé ou historique.

---

# 109. Demo data strategy

Si certaines Sources réelles sont indisponibles, combiner :

```text
real application
+
realistic simulated context
```

Mais distinguer clairement ce qui est simulé.

---

# 110. Demo reliability

La démo doit être déterministe autant que possible.

---

# 111. Avoid live dependency fragility

Pré-cacher :

- Evidence ;
- graph ;
- initial Claims.

---

# 112. Live AI boundaries

Laisser live :

- contextual conversation ;
- explanation ;
- selective analysis.

---

# 113. Demo fallback

Prévoir résultats pré-calculés pour traitements longs.

---

# 114. Production MVP vs Jury Demo

Ne pas confondre.

La Demo peut simuler davantage.

Le MVP produit doit conserver architecture réelle.

---

# 115. Technical debt policy

Accepter dette limitée pour :

- styling ;
- optional connectors.

Ne pas accepter dette sur :

- Claim identity ;
- provenance ;
- security ;
- workflow durability.

---

# 116. Architecture runway

Avant d’ajouter beaucoup de features, stabiliser :

```text
Domain contracts
Job framework
Evidence
Security context
Events
```

---

# 117. The dangerous shortcut

Ne jamais construire :

```text
LLM
↓
JSON
↓
UI
```

comme architecture principale.

---

# 118. The correct shortcut

Même MVP :

```text
Source
↓
Evidence
↓
Claim
↓
Projection
↓
UI
```

---

# 119. MVP Data Model Minimum

```text
Tenant
Source
Artifact
Evidence
Twin
Claim
Relationship
Signal
Situation
Investigation
Hypothesis
ExpertContribution
Scenario
Decision
Job
```

---

# 120. Optional MVP Data Model

```text
Opportunity
Outcome
Learning
```

si scope le permet.

---

# 121. API Minimum

```text
/twins
/claims
/evidence
/relationships
/jobs
/flore
/investigations
/scenarios
/decisions
```

---

# 122. Event Minimum

```text
SourceSynced
ArtifactChanged
ClaimCreated
RelationshipDiscovered
JobProgressed
SignalDetected
SituationCreated
InvestigationOpened
DecisionRecorded
```

---

# 123. Security Minimum

- authenticated ;
- authorized ;
- audited ;
- tenant-scoped.

---

# 124. NFR Minimum

- async long jobs ;
- partial progress ;
- retries ;
- tracing ;
- cost metrics.

---

# 125. Build vs Buy

Build core differentiators :

```text
Claim Model
Twin Intelligence
Mesh logic
Maturation
Investigation orchestration
Flore context
Transformation Memory
```

---

# 126. Use existing platforms for

```text
identity
workflow
storage
search
observability
LLM runtime
```

---

# 127. Productization risks

Principaux risques :

```text
too much LLM
too much scope
weak evidence
slow processing
Atlas complexity
source access
unclear value
```

---

# 128. Risk — Too much LLM

Mitigation :

- deterministic extraction ;
- reuse ;
- context packs ;
- caching.

---

# 129. Risk — Slow Graph analysis

Mitigation :

- bounded queries ;
- hierarchical summaries ;
- incremental graph.

---

# 130. Risk — Source access

Mitigation :

- start with Git/Jira ;
- mocks only at edges ;
- connector contracts stable.

---

# 131. Risk — Atlas complexity

Mitigation :

- semantic zoom ;
- limited nodes ;
- viewport query ;
- clear domain membrane.

---

# 132. Risk — Weak business value

Mitigation :

Demonstrate :

```text
time saved
understanding depth
decision quality
```

---

# 133. Risk — Agent complexity

Mitigation :

Start with:

```text
2-3 Experts
+ Contradictor
```

---

# 134. Risk — Knowledge drift

Mitigation :

- freshness ;
- incremental sync ;
- versioning.

---

# 135. Dependency map

Critical dependencies :

```text
Identity
Source access
Workflow
LLM provider
Graph/Search
```

---

# 136. External dependency strategy

Toujours prévoir :

- timeout ;
- retry ;
- degraded mode.

---

# 137. Release milestones

Proposition :

```text
M0 Platform
M1 Twin
M2 Flore
M3 Mesh
M4 Situation
M5 Investigation
M6 Decision
M7 Learning
```

---

# 138. Milestone M0

Demo :

> login + shell + trace + empty Atlas.

---

# 139. Milestone M1

Demo :

> TBT Twin born from Git.

---

# 140. Milestone M2

Demo :

> Flore answers evidence-backed questions.

---

# 141. Milestone M3

Demo :

> dependencies visible in Atlas.

---

# 142. Milestone M4

Demo :

> Situation emerges.

---

# 143. Milestone M5

Demo :

> Investigation with Experts.

---

# 144. Milestone M6

Demo :

> Scenarios + Decision.

---

# 145. Milestone M7

Demo :

> Outcome + Learning.

---

# 146. Exit Criteria MVP global

Le MVP est considéré valide si :

1. un Twin peut naître de Sources réelles ;
2. les Claims sont sourcés ;
3. Flore peut expliquer avec Evidence ;
4. une question historique complexe est traitable ;
5. le Mesh montre des relations utiles ;
6. une Situation peut émerger ;
7. une Investigation structure plusieurs hypothèses ;
8. plusieurs Experts peuvent contribuer ;
9. des scénarios sont comparables ;
10. une décision humaine peut être capturée.

---

# 147. Success metrics MVP

## Product

```text
time to answer complex question
user usefulness score
investigation time saved
```

## Knowledge

```text
evidence coverage
claim acceptance
unknown detection
```

## AI

```text
grounding
tool accuracy
cost
latency
```

## Platform

```text
job success
availability
freshness
```

---

# 148. User validation

Tester avec :

- architecte ;
- app owner ;
- analyste ;
- manager.

---

# 149. Interview questions

Après usage :

> Qu’as-tu compris plus vite ?

> Qu’est-ce que tu n’aurais pas trouvé seul ?

> Quelle partie te semble peu fiable ?

> Quelle action ferais-tu ensuite ?

---

# 150. Evidence of Product-Market Fit interne

Signaux :

- utilisateurs reviennent ;
- utilisent Flore sans accompagnement ;
- lancent investigations ;
- partagent des résultats ;
- demandent de nouveaux Twins.

---

# 151. Evidence of Technical Fit

- traitement incrémental ;
- coût maîtrisé ;
- résultats reproductibles ;
- workflow durable.

---

# 152. Evidence of Trust

- utilisateur ouvre Evidence ;
- accepte Claims ;
- utilise résultat dans décision.

---

# 153. Product telemetry MVP

Mesurer :

```text
Twin opened
Flore asked
Evidence opened
Investigation started
Scenario compared
Decision recorded
```

---

# 154. Prioritization framework

Score possible :

```text
User Value
× Strategic Fit
× Learning Value
÷ Complexity
```

---

# 155. Learning Value

Un item peut être prioritaire même sans grande valeur immédiate s’il réduit un risque d’architecture majeur.

---

# 156. Core vs differentiator

## Core infrastructure

Nécessaire mais non différenciateur.

## Differentiator

```text
Claims
Mesh
Maturation
Investigation
Transformation Memory
```

---

# 157. Avoid polishing infrastructure too early

Le produit doit atteindre rapidement un slice visible.

---

# 158. First visible milestone

Idéalement :

```text
Twin + Claims + Atlas + Flore
```

très tôt.

---

# 159. First value milestone

Question réelle répondue.

---

# 160. First differentiation milestone

Situation / Opportunity détectée.

---

# 161. First decision milestone

Investigation → scenarios.

---

# 162. First learning milestone

Outcome → Learning.

---

# 163. MVP UX scope

Pages :

```text
Today
Atlas
Twin
Investigation
Decision
Flore panel
```

Opportunity peut être une page simple.

---

# 164. MVP Today

Très simple :

```text
Top situations
Active investigations
Recent outcomes
```

---

# 165. MVP Atlas

Prioriser :

- navigation ;
- focus ;
- context.

Pas toutes les couches avancées.

---

# 166. MVP Flore

Prioriser :

- contextual ;
- evidence ;
- action.

---

# 167. MVP Investigation

Prioriser :

- Hypotheses ;
- Evidence ;
- Experts ;
- Synthesis.

---

# 168. MVP Decision

Prioriser comparaison.

---

# 169. MVP accessibility

Minimum WCAG AA sur surfaces standards.

---

# 170. MVP security

Pas de raccourci.

---

# 171. Delivery governance

Réunion hebdomadaire produit/architecture.

---

# 172. Architecture review

Les changements importants :

- Domain Model ;
- Claims ;
- agent boundaries ;
- security ;
- workflow.

---

# 173. ADR discipline

Documenter décisions irréversibles.

---

# 174. Demo every slice

Chaque Vertical Slice doit terminer par une démonstration utilisateur.

---

# 175. Feedback loop

```text
Build
↓
Demo
↓
Observe
↓
Adjust
```

Méridian doit être construit selon sa propre philosophie.

---

# 176. Backlog health

Le backlog doit garder :

```text
Now
Next
Later
```

---

# 177. No giant roadmap fiction

Le roadmap doit évoluer selon :

- feedback ;
- qualité ;
- access Sources ;
- coûts.

---

# 178. Product backlog principles

Prioriser :

- value loops ;
- trust ;
- speed ;
- learning.

---

# 179. MVP completion is not product completion

Après MVP :

> productization.

---

# 180. Productization phase

Objectifs :

- robustness ;
- permissions ;
- admin ;
- source lifecycle ;
- evaluations ;
- better Atlas ;
- operations.

---

# 181. SaaS readiness phase

Ajouter :

```text
tenant provisioning
self-service connectors
billing metrics
quota
customer configuration
```

---

# 182. Enterprise rollout

Séquence recommandée :

```text
1 application
↓
1 domain
↓
several domains
↓
enterprise
```

---

# 183. Expansion strategy

Ne pas onboarding 500 applications d’un coup.

---

# 184. Domain pilot

Après TBT :

sélectionner 5–15 applications reliées.

---

# 185. Domain-level value

Démontrer :

- hidden dependencies ;
- duplicated capabilities ;
- opportunity ;
- impact analysis.

---

# 186. Enterprise-scale value

Démontrer :

- transformation ;
- portfolio ;
- cross-domain patterns.

---

# 187. SaaS evolution

Le produit peut évoluer vers :

> **Enterprise Intelligence Mesh as a Service**

mais le MVP doit d’abord prouver la connaissance et l’exploitation.

---

# 188. SaaS boundaries to preserve now

Même MVP :

- tenant_id ;
- connector abstraction ;
- Expert registry ;
- portable domain model ;
- policy boundaries.

---

# 189. Commercialization readiness

Plus tard :

```text
packaging
pricing
onboarding
support
compliance
```

---

# 190. Product editions possible

Future:

```text
Discover
Understand
Decide
Enterprise
```

À ne pas figer dans le MVP.

---

# 191. ROI demonstration

Le pilote doit chercher des preuves quantitatives.

Exemple :

```text
historical analysis:
days → hours/minutes

impact analysis:
multiple meetings → one structured investigation
```

---

# 192. Time Saved

Mesurer comparativement.

---

# 193. Decision Confidence

Question utilisateur :

> « Auriez-vous pris la même décision sans Méridian ? »

---

# 194. Knowledge Reuse

Mesurer combien de Claims sont réutilisés dans plusieurs analyses.

---

# 195. Avoid vanity demo

Une carte jolie sans loop de valeur n’est pas suffisante.

---

# 196. Demo scoring rubric

```text
Value          30%
Trust          25%
Understanding  20%
Experience     15%
Technical wow  10%
```

---

# 197. Architecture scoring rubric

```text
Evidence
Durability
Security
Incrementality
Extensibility
Cost
```

---

# 198. MVP decision gate

Avant de continuer vers Productization, répondre oui à :

> les utilisateurs comprennent-ils la valeur ?

> les Claims sont-ils assez fiables ?

> les traitements sont-ils soutenables ?

> le coût est-il maîtrisable ?

> la navigation est-elle claire ?

---

# 199. If MVP fails

Identifier quelle hypothèse est fausse :

```text
value
trust
latency
source access
architecture
UX
```

---

# 200. Kill criteria

Une feature peut être arrêtée si :

- faible usage ;
- faible valeur ;
- coût élevé ;
- duplication.

---

# 201. Refactor criteria

Refactor quand :

- workflows non durables ;
- Claims ambigus ;
- source coupling ;
- LLM cost explodes.

---

# 202. Technical milestones by dependency

Ordre conseillé :

```text
Identity
↓
Job Framework
↓
Source
↓
Evidence
↓
Claim
↓
Twin
↓
Flore
↓
Mesh
↓
Signal
↓
Investigation
↓
Decision
```

---

# 203. Why Job Framework early

Parce que :

- repo analysis ;
- reports ;
- investigations ;

seront longs dès le début.

---

# 204. Why Evidence before AI sophistication

Parce que sans preuve :

> tout le reste est une démo fragile.

---

# 205. Why Flore before advanced Discovery

Flore permet de tester rapidement la valeur de la connaissance.

---

# 206. Why Mesh before full Opportunity

Parce que la différenciation vient du transverse.

---

# 207. Why Investigation before autonomous action

Parce que la compréhension et la confiance doivent être prouvées avant l’agence.

---

# 208. Technical Spike backlog

Spikes importants :

```text
code graph performance
incremental indexing
Claim confidence
security trimming Graph
SSE scale
AgentCore runtime
```

---

# 209. Spike success criteria

Chaque Spike doit terminer par :

- conclusion ;
- benchmark ;
- recommendation ;
- ADR.

---

# 210. Performance benchmarks

Pour code :

```text
repo size
index time
incremental time
question latency
token cost
```

---

# 211. LLM benchmark

Comparer :

```text
small model
medium
strong model
```

selon tâche.

---

# 212. Agent benchmark

Mesurer :

```text
single Expert
parallel Experts
with Contradictor
```

---

# 213. MVP observability dashboard

Minimum widgets :

```text
jobs
tokens
cost
source freshness
claim creation
errors
```

---

# 214. MVP knowledge dashboard

```text
Twin coverage
Claim maturity
Unknowns
Contradictions
```

---

# 215. MVP admin

Très limité :

- Sources ;
- Experts ;
- users/roles ;
- policies.

---

# 216. Feature completeness philosophy

Une feature P0 doit être complète sur son slice.

Exemple :

`Claim` sans Evidence n’est pas P0 completed.

---

# 217. Testing pyramid

```text
unit
contract
integration
end-to-end
AI evaluations
```

---

# 218. End-to-end tests

Minimum :

```text
Git change
→ Claim
→ Flore answer

Signal
→ Situation
→ Investigation
```

---

# 219. Security tests

- tenant isolation ;
- restricted Evidence ;
- tool authorization.

---

# 220. AI tests

- hallucination ;
- evidence ;
- unknown recognition ;
- prompt injection.

---

# 221. UX tests

- find TBT ;
- ask Flore ;
- inspect Evidence ;
- launch Investigation.

---

# 222. Load tests

Focus :

- Atlas ;
- Search ;
- SSE ;
- Jobs.

---

# 223. Production readiness checklist

```text
SLOs
Dashboards
Alerts
Runbooks
Backup
DR
Security review
AI evals
Cost budgets
Support model
```

---

# 224. Pilot rollout

Phases :

```text
internal team
↓
application owners
↓
domain users
↓
selected decision-makers
```

---

# 225. Pilot feedback cadence

Court.

Exemple :

```text
weekly usage review
biweekly product review
```

---

# 226. Pilot questions

> Quelle question avez-vous posée ?

> Combien de temps aurait-elle pris autrement ?

> Avez-vous utilisé la preuve ?

> Avez-vous fait quelque chose ensuite ?

---

# 227. MVP success statement

Le MVP est réussi si un utilisateur peut dire :

> **“Je peux poser à Méridian une question difficile sur une application, comprendre pourquoi la réponse est crédible, voir les dépendances concernées et lancer une investigation sans repartir de zéro.”**

---

# 228. Stronger success statement

Encore mieux :

> **“Méridian m’a montré quelque chose d’important que je ne cherchais pas explicitement, m’a aidé à le comprendre et m’a permis de prendre une décision plus vite.”**

---

# 229. Delivery roadmap synthetic view

```text
FOUNDATION
  │
  ▼
ONE SOURCE → ONE CLAIM
  │
  ▼
TWIN BIRTH
  │
  ▼
FLORE + EVIDENCE
  │
  ▼
MESH + ATLAS
  │
  ▼
SIGNAL → SITUATION
  │
  ▼
INVESTIGATION
  │
  ▼
SCENARIOS → DECISION
  │
  ▼
OUTCOME → LEARNING
```

---

# 230. MVP scope final

## MUST

```text
Twin
Sources
Evidence
Claims
Mesh
Atlas
Flore
Jobs
Investigation
Decision
Security
Observability
```

## SHOULD

```text
Signal
Situation
Opportunity
Outcome
Learning
```

## COULD

```text
Transformation Memory
Advanced Radar
Advanced temporal Atlas
Expert Marketplace
```

## WON'T — initial MVP

```text
Autonomous critical actions
Full enterprise ontology
All source connectors
Full Swarm
Customer/Employee twins
```

---

# 231. MVP roadmap by value

```text
VALUE 1 — Know what exists
VALUE 2 — Understand why
VALUE 3 — See what matters
VALUE 4 — Investigate
VALUE 5 — Decide
VALUE 6 — Learn
```

---

# 232. Product delivery philosophy

Le meilleur ordre de livraison est celui qui réduit le plus vite les risques fondamentaux.

Les risques fondamentaux de Méridian sont :

1. Peut-on construire une connaissance fiable ?
2. Peut-on l’exploiter rapidement ?
3. Peut-on maintenir des performances soutenables ?
4. Le Mesh ajoute-t-il une vraie valeur ?
5. Les utilisateurs font-ils confiance au système ?

Le roadmap doit être optimisé autour de ces questions.

---

# 233. Conclusion

Le MVP de Méridian ne doit pas chercher à impressionner par la quantité.

Il doit impressionner par la cohérence du parcours.

Un produit crédible doit permettre :

```text
Connecter une Source
↓
Faire naître un Twin
↓
Créer des Claims vérifiables
↓
Relier les Twins dans le Mesh
↓
Poser une question à Flore
↓
Faire émerger une Situation
↓
Lancer une Investigation
↓
Comparer des Scénarios
↓
Capturer une Décision
↓
Observer un Résultat
```

Ce parcours prouve le coeur de la vision.

Une fois cette boucle stable, Méridian peut s’étendre :

- à d’autres applications ;
- à des domaines ;
- aux processus ;
- aux parcours ;
- aux équipes ;
- à l’entreprise entière.

---

# 234. Prochain document

Le prochain document recommandé est :

> **MÉRIDIAN — Product Backlog & Capability Map**

Il devra transformer ce roadmap en structure de delivery détaillée :

- Capability Map ;
- Epics ;
- Features ;
- User Stories ;
- Technical Stories ;
- Enablers ;
- Dependencies ;
- Priorities ;
- Acceptance Criteria ;
- MVP / P1 / P2 ;
- Release mapping.

Ce sera le document utilisable directement pour **alimenter le backlog produit et organiser l’exécution de l’équipe**.
