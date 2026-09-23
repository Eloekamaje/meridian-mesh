# MÉRIDIAN — Non-Functional Requirements & Quality Architecture
## Exigences non fonctionnelles, SLO/SLA, performance, résilience, coûts, observabilité et qualité IA

**Statut :** Architecture qualité de référence  
**Version :** 1.0  
**Produit :** MÉRIDIAN  
**Tagline :** **DÉCOUVRIR · COMPRENDRE · DÉCIDER**

---

# 0. Objet du document

Ce document formalise les exigences non fonctionnelles de Méridian.

Il répond à la question :

> **Quelles qualités mesurables Méridian doit-il garantir pour être crédible, utilisable et exploitable à grande échelle dans une grande entreprise ?**

Les documents précédents définissent :

- ce que Méridian fait ;
- comment il comprend ;
- comment il raisonne ;
- comment il interagit ;
- comment il protège les données.

Ce document définit maintenant :

- à quelle vitesse ;
- avec quelle disponibilité ;
- avec quelle robustesse ;
- à quel coût ;
- avec quelle observabilité ;
- avec quelle qualité de réponse ;
- sous quelles limites de charge ;
- avec quelles garanties de reprise.

Le principe fondamental est :

> **Une architecture n’est pas complète tant que ses qualités attendues ne sont pas explicites, mesurables et vérifiables.**

---

# 1. Quality Attributes

Les attributs de qualité principaux de Méridian sont :

```text
Performance
Availability
Scalability
Resilience
Durability
Consistency
Security
Observability
Cost Efficiency
Maintainability
Extensibility
Portability
Usability
Accessibility
AI Quality
Explainability
Auditability
```

---

# 2. Priorisation des qualités

Toutes les qualités ne sont pas équivalentes.

Pour Méridian, l’ordre de priorité recommandé est :

```text
1. Trust / Correctness
2. Security
3. Availability
4. Explainability
5. Performance
6. Resilience
7. Cost Efficiency
8. Scalability
9. Maintainability
10. Extensibility
```

---

# 3. Principe qualité

Le produit doit favoriser :

> **la réponse correcte et explicable**

avant :

> **la réponse instantanée mais douteuse.**

---

# 4. Classes de workload

Méridian possède plusieurs types de workload.

## Interactive Read

Exemple :

```text
open twin
search claim
ask simple Flore question
```

## Interactive Analysis

Exemple :

```text
why this opportunity?
compare two twins
```

## Long-running Analysis

Exemple :

```text
3-year feature reconstruction
cross-domain investigation
```

## Background Discovery

Exemple :

```text
continuous source sync
signal maturation
```

## Batch / Reconciliation

Exemple :

```text
graph rebuild
knowledge replay
```

---

# 5. Workload classes and latency

Proposition cible :

```text
Interactive Read        < 1 s perceived
Interactive Analysis    < 5 s first useful response
Long Analysis           < 2 s job acknowledgement
Background              asynchronous
Batch                    asynchronous
```

---

# 6. Perceived latency

Pour les interactions complexes, la perception compte plus que le temps total.

Pattern :

```text
request
↓
acknowledge quickly
↓
show progress
↓
publish partial findings
↓
complete
```

---

# 7. API latency SLOs

Cibles initiales :

## Read APIs

```text
p50 < 300 ms
p95 < 800 ms
p99 < 1500 ms
```

hors dépendances externes lentes.

## Write APIs

```text
p95 < 1200 ms
```

---

# 8. Flore latency

## Simple retrieval

```text
first token / first useful block < 2 s target
```

## Moderate analysis

```text
first useful result < 5 s
```

## Heavy analysis

```text
job accepted < 2 s
progress visible < 3 s
```

---

# 9. Atlas latency

Objectifs :

```text
initial shell < 2 s
visible viewport data < 3 s
pan/zoom 60 fps target
selection response < 150 ms
```

---

# 10. Semantic zoom

Atlas doit charger progressivement :

```text
L0 domains
L1 clusters
L2 twins
L3 relations
L4 details
```

---

# 11. Large graph handling

Méridian ne doit jamais charger l’intégralité du Mesh dans le navigateur.

Techniques :

```text
viewport query
LOD
clustering
graph projection
pagination
progressive edge loading
```

---

# 12. Graph query budgets

Chaque requête interactive impose :

```text
max_nodes
max_edges
max_depth
timeout
```

---

# 13. Long-running jobs

Un Job long doit être un objet de premier rang.

```yaml
Job:
  id:
  type:
  state:
  progress:
  stages:
  created_at:
  started_at:
  updated_at:
  result_ref:
  retry_policy:
  cancellation_supported:
```

---

# 14. Job states

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

---

# 15. Long job UX

Aucun traitement de 20+ minutes ne doit être représenté par un spinner générique.

---

# 16. Long job progression

Exemple :

```text
✓ repository indexed
✓ 287 changes clustered
✓ Jira links resolved
● functional validation
○ final synthesis
```

---

# 17. Partial publish

Les résultats fiables peuvent être publiés avant completion.

---

# 18. Checkpointing

Les traitements lourds doivent posséder des checkpoints.

---

# 19. Resume

Après panne :

```text
resume from checkpoint
```

et non recommencer depuis zéro.

---

# 20. Cancellation

Tout Job long non critique doit être annulable.

---

# 21. Retry policy

Types :

```text
technical retry
model fallback
source retry
workflow compensation
human intervention
```

---

# 22. Idempotence

Les commandes asynchrones doivent être idempotentes autant que possible.

---

# 23. Availability

Le produit doit distinguer plusieurs niveaux de service.

---

# 24. Core platform availability

Cible initiale :

```text
99.9%
```

pour :

- UI ;
- BFF ;
- Knowledge reads ;
- Investigation state ;
- Job state.

---

# 25. Critical enterprise tier

À terme :

```text
99.95%+
```

selon contexte contractuel.

---

# 26. Dependency-aware availability

L’indisponibilité d’une source externe ne doit pas rendre Méridian entièrement indisponible.

---

# 27. Graceful degradation

Exemple :

```text
GitHub unavailable
↓
existing Claims still readable
↓
freshness warning
↓
new sync delayed
```

---

# 28. Degraded modes

```text
FULL
READ_ONLY
STALE_KNOWLEDGE
NO_AGENTIC_ANALYSIS
NO_EXTERNAL_SOURCES
```

---

# 29. Resilience principle

Les composants doivent échouer de manière isolée.

---

# 30. Failure domains

Séparer :

- interaction ;
- orchestration ;
- knowledge ;
- source ingestion ;
- agent runtime ;
- search ;
- graph.

---

# 31. Circuit breakers

Utiliser pour :

- source APIs ;
- model providers ;
- search ;
- graph ;
- external tools.

---

# 32. Bulkheads

Limiter la propagation d’un problème.

Exemple :

```text
one tenant heavy investigation
≠
whole platform slowdown
```

---

# 33. Queue isolation

Files séparées selon :

```text
interactive
investigation
background
low priority
```

---

# 34. Backpressure

Le système doit ralentir ou refuser proprement avant saturation.

---

# 35. Rate limiting

Par :

```text
tenant
user
agent
tool
source
workflow
```

---

# 36. Scalability dimensions

Méridian doit scaler selon :

```text
number of twins
number of sources
number of claims
graph size
events/sec
concurrent users
concurrent jobs
LLM calls
```

---

# 37. Horizontal scalability

Favoriser composants stateless pour :

- BFF ;
- query APIs ;
- workers ;
- connectors ;
- agent runners.

---

# 38. Stateful services

États durables dans stores spécialisés.

---

# 39. Target scale classes

## Pilot

```text
10–100 twins
10^5 claims
small team
```

## Enterprise

```text
100–5,000 twins
10^7+ claims
many teams
```

## Large enterprise / SaaS

```text
multi-tenant
10^4+ twins
10^8 relations / observations class
```

---

# 40. Scale strategy

Ne pas optimiser prématurément pour le maximum.

Construire des contrats permettant l’évolution.

---

# 41. Event throughput

Le bus événementiel doit absorber des pics.

---

# 42. Event classes

```text
source events
knowledge events
signal events
workflow events
audit events
```

---

# 43. Event ordering

L’ordre global n’est pas nécessaire.

L’ordre par aggregate ou key peut l’être.

---

# 44. Event durability

Les événements critiques ne doivent pas être perdus.

---

# 45. Delivery semantics

Conception recommandée :

```text
at-least-once
+
idempotent consumers
```

pour majorité des workflows.

---

# 46. Outbox

Utiliser Outbox pattern pour synchroniser transactions et événements critiques.

---

# 47. Consistency model

Méridian accepte plusieurs niveaux de cohérence.

## Strong consistency

Pour :

- Decision ;
- permissions ;
- Claim state transition critique.

## Eventual consistency

Pour :

- search projection ;
- Atlas projection ;
- feed ;
- aggregates.

---

# 48. Consistency UX

Si projection pas encore à jour :

le produit doit pouvoir le signaler.

---

# 49. Knowledge consistency

Un Claim validé est autoritatif dans le Claim Store.

---

# 50. Graph consistency

Graph = projection.

Une légère latence est acceptable.

---

# 51. Search consistency

OpenSearch = projection reconstructible.

---

# 52. Durability

Les objets critiques :

```text
Claims
Evidence metadata
Decisions
Audit
Learnings
```

doivent être durablement stockés.

---

# 53. Backup

Cibles initiales :

```text
daily full / continuous where supported
point-in-time recovery for core DB
versioning for object store
```

---

# 54. RPO

Proposition :

## Core domain state

```text
RPO <= 5 min
```

## Search/graph projections

```text
reconstructible
```

---

# 55. RTO

Proposition :

## Core product

```text
RTO <= 1 h
```

## Critical tier

plus strict selon besoin.

---

# 56. DR tiers

```text
Tier 1 — reconstructible
Tier 2 — recoverable
Tier 3 — critical
```

---

# 57. Disaster recovery principle

Ne pas répliquer inutilement des projections reconstructibles si le coût est élevé.

---

# 58. Data integrity

Toute Evidence critique doit posséder :

```text
hash
version
locator
```

---

# 59. Integrity checks

Détecter :

- corrupted artifact ;
- missing source ;
- invalid locator ;
- mismatched hash.

---

# 60. Security quality

Les SLO sécurité doivent inclure :

```text
0 cross-tenant leaks
0 unauthorized tool execution
100% critical actions audited
100% secrets outside prompts/logs
```

---

# 61. Security response latency

Révocation critique :

```text
effective within minutes
```

---

# 62. Permission propagation

Changement de droit doit invalider caches rapidement.

---

# 63. Observability architecture

Trois niveaux.

## Platform observability

CPU, memory, latency, errors.

## Workflow observability

jobs, stages, queues.

## Cognitive observability

Claims, Evidence, experts, confidence, contradictions.

---

# 64. Standard telemetry

Utiliser :

```text
logs
metrics
traces
events
```

---

# 65. Distributed tracing

Chaque requête possède :

```text
trace_id
```

corrélé avec :

```text
conversation_id
job_id
investigation_id
agent_run_id
```

---

# 66. Trace hierarchy

```text
User Request
└── BFF
    └── Orchestrator
        ├── Knowledge Query
        ├── Graph Query
        ├── Agent Run
        └── Tool Calls
```

---

# 67. Cognitive metrics

```text
claims proposed
claims accepted
claims invalidated
evidence coverage
unsupported assertions
contradictions discovered
expert disagreement
unknowns created
```

---

# 68. AI latency metrics

Par :

```text
model
expert
task
tenant
```

---

# 69. AI token metrics

```text
input tokens
output tokens
cache hit
cost estimate
```

---

# 70. Cost observability

Chaque coût significatif doit pouvoir être attribué à :

```text
tenant
user
workflow
investigation
expert
twin
```

---

# 71. Cost budgets

Budgets possibles :

```text
per request
per investigation
per twin/day
per team
per tenant
```

---

# 72. Cost alerts

Exemples :

```text
unexpected model spend
runaway workflow
source ingestion spike
```

---

# 73. Cost efficiency principle

Le plus gros volume doit être traité sans LLM.

---

# 74. Deterministic first

Priorité :

```text
parse
query
calculate
filter
cluster
retrieve
```

avant :

```text
generate
reason
```

---

# 75. LLM call minimization

Techniques :

- targeted retrieval ;
- hierarchical summaries ;
- semantic cache ;
- prompt cache ;
- batching ;
- dedupe ;
- early stop ;
- incremental updates.

---

# 76. Semantic cache

Clé possible :

```text
normalized question
+ context fingerprint
+ temporal scope
+ permission scope
```

---

# 77. Cache safety

Le cache doit inclure permissions et tenant.

---

# 78. Cache invalidation

Basée sur :

```text
knowledge fingerprint
source freshness
policy change
permission change
```

---

# 79. Code intelligence performance

Éviter :

```text
entire graph
→ giant prompt
```

---

# 80. Code analysis target flow

```text
Question
↓
Relevant modules
↓
Relevant subgraph
↓
Relevant code
↓
LLM
```

---

# 81. Initial repository analysis

La première indexation peut être lourde.

Elle doit être :

- durable ;
- parallélisable ;
- checkpointée ;
- réutilisable.

---

# 82. Incremental analysis

Après premier index :

```text
commit delta
↓
affected symbols
↓
affected claims
```

---

# 83. Repository update SLO

Cible indicative :

```text
small commit → knowledge update in minutes
```

pas refaire 20 minutes d’analyse globale.

---

# 84. Freshness requirements

Par Source :

```text
runtime     near real-time
Git         minutes
Jira        minutes/hours
Confluence  hours
CMDB        hours/day
```

---

# 85. Freshness metadata

Toujours exposer :

```text
last sync
last successful observation
stale
```

---

# 86. Data ingestion reliability

Connector failures doivent être isolés.

---

# 87. Connector SLO

Mesures :

```text
sync success rate
lag
error rate
cursor correctness
```

---

# 88. Connector replay

Supporter reprise depuis cursor/checkpoint.

---

# 89. Search quality

Métriques :

```text
precision@k
recall@k
MRR
relevance feedback
```

---

# 90. Retrieval quality

Pour Knowledge RAG :

```text
claim relevance
evidence relevance
security correctness
temporal correctness
```

---

# 91. AI quality architecture

La qualité IA est un NFR de premier rang.

---

# 92. AI quality dimensions

```text
correctness
evidence grounding
calibration
tool selection
context resolution
consistency
safety
unknown recognition
```

---

# 93. Grounding SLO

Pour conclusions importantes :

```text
100% must expose supporting evidence or explicit uncertainty
```

---

# 94. Unsupported assertion target

Pour Claims matures :

```text
near zero
```

---

# 95. Citation correctness

Les références doivent réellement supporter l’affirmation.

---

# 96. Confidence calibration

Le score affiché doit être calibré.

---

# 97. Unknown recognition

Le système doit être évalué sur sa capacité à répondre :

```text
insufficient evidence
```

---

# 98. Hallucination rate

Mesurer sur golden datasets.

---

# 99. Agent tool-use quality

Mesurer :

```text
correct tool
correct parameters
unnecessary calls
failed calls
```

---

# 100. Agent loop quality

Mesurer :

```text
repeated calls
delegation loops
time to stop
```

---

# 101. Investigation quality

NFR :

- hypothesis diversity ;
- evidence coverage ;
- contradiction coverage ;
- decision readiness.

---

# 102. Report quality

Rapports doivent être :

- reproductibles ;
- référencés ;
- versionnés ;
- complets selon scope.

---

# 103. Human-perceived quality

Mesures :

```text
useful
too vague
too technical
missing evidence
wrong context
```

---

# 104. Evaluation datasets

Méridian doit maintenir :

```text
golden questions
golden claims
golden investigations
historical incidents
historical feature reconstructions
```

---

# 105. Offline evaluation

Avant release.

---

# 106. Online evaluation

En production via sampling et feedback.

---

# 107. Regression gates

Un changement de modèle/prompt/Expert ne doit pas dégrader les métriques critiques.

---

# 108. Quality thresholds

Exemple :

```text
evidence grounding >= 98%
schema compliance >= 99.9%
security policy compliance = 100%
```

Les valeurs finales dépendent du périmètre.

---

# 109. Maintainability

Le produit doit éviter les composants monolithiques.

---

# 110. Modular boundaries

```text
Source
Twin
Knowledge
Mesh
Discovery
Investigation
Decision
Learning
Experience
```

---

# 111. Contract-first APIs

Tous les services utilisent contracts versionnés.

---

# 112. Schema evolution

Backward compatibility lorsque possible.

---

# 113. Versioning

```text
API version
event schema version
Claim schema version
Expert version
prompt version
model version
```

---

# 114. Upgradeability

Un service doit pouvoir évoluer sans migration globale du produit.

---

# 115. Extensibility

Ajouter une nouvelle Source ne doit pas exiger de modifier le coeur.

---

# 116. Connector SPI

Contract stable.

---

# 117. Expert extensibility

Nouvel Expert via Registry + Skill + Tools.

---

# 118. New Twin types

L’architecture doit supporter progressivement :

```text
Application
Process
Capability
Journey
Organization
Product
```

---

# 119. New Claim types

Via ontology/predicate registry.

---

# 120. New UI surfaces

Basées sur ViewModels/projections.

---

# 121. Portability

Méridian doit rester conceptuellement découplé des services propriétaires.

---

# 122. Cloud abstraction principle

Ne pas créer une abstraction artificielle de tout.

Mais isoler les dépendances stratégiques.

---

# 123. Portable domain logic

Doit rester indépendante du provider :

```text
Claim
Investigation
Decision
Learning
```

---

# 124. Replaceable components

Idéalement :

```text
model provider
vector search
graph engine
event broker
object store
```

avec effort contrôlé.

---

# 125. Usability

Les utilisateurs non techniques doivent pouvoir comprendre :

- Why now ;
- Impact ;
- Confidence ;
- Unknowns ;
- Decision.

---

# 126. Cognitive load

Limiter :

- nombre de cartes ;
- nombre de badges ;
- actions simultanées.

---

# 127. Attention NFR

Aujourd’hui doit prioriser quelques éléments significatifs.

---

# 128. Accessibility

Cible :

```text
WCAG 2.2 AA
```

pour surfaces standards.

---

# 129. Atlas accessibility

Fournir vue alternative structurée.

---

# 130. Keyboard accessibility

Support complet sur composants standards.

---

# 131. Localization

Architecture prête pour :

```text
FR
EN
```

et extensible.

---

# 132. Internationalization

Ne pas coder en dur :

- dates ;
- nombres ;
- devises ;
- libellés.

---

# 133. Timezones

Tous les timestamps internes normalisés.

Affichage selon utilisateur.

---

# 134. Data volume observability

Mesurer :

```text
artifacts
claims
edges
signals
situations
investigations
```

---

# 135. Capacity planning

Définir seuils :

```text
warning
scale
hard limit
```

---

# 136. Storage growth

Prévoir compaction / archival.

---

# 137. Raw artifact retention

Ne pas garder toutes les données indéfiniment sans besoin.

---

# 138. Projection rebuild time

Un index Search/Graph doit être reconstructible dans une fenêtre acceptable.

---

# 139. Data lifecycle

```text
hot
warm
archive
delete
```

---

# 140. Audit retention

Plus longue que certaines traces techniques.

---

# 141. Operational readiness

Avant production :

- dashboards ;
- alerts ;
- runbooks ;
- on-call ;
- DR plan ;
- security contacts.

---

# 142. Runbooks

Minimum :

```text
model outage
search outage
graph outage
source outage
workflow backlog
cost spike
security event
```

---

# 143. Health endpoints

Chaque service expose :

```text
liveness
readiness
dependency health
```

---

# 144. Dependency health

Ne pas marquer service entièrement unhealthy si une dépendance non critique échoue.

---

# 145. SLO dashboard

Doit montrer :

```text
availability
latency
error
job success
freshness
AI quality
cost
```

---

# 146. Error budgets

Pour services critiques.

---

# 147. Error budget policy

Si budget brûlé :

- réduire releases ;
- corriger fiabilité.

---

# 148. Alerting philosophy

Alertes opérationnelles doivent être actionnables.

---

# 149. No alert storms

Dedup et grouping également côté plateforme.

---

# 150. Deployment strategy

Préférer :

```text
rolling
blue/green
canary
```

selon composant.

---

# 151. Agent canary

Nouvelle version d’Expert sur faible trafic.

---

# 152. Model canary

Comparer qualité/coût/latence.

---

# 153. Rollback

Rapide.

---

# 154. Database migration

Zero/low downtime lorsque possible.

---

# 155. Event schema migration

Compatibilité producteurs/consommateurs.

---

# 156. Performance testing

Types :

```text
load
stress
spike
soak
```

---

# 157. Atlas performance tests

Tester grands graphes.

---

# 158. Search performance tests

Tester :

- millions de Claims ;
- filtres security ;
- temporal filters.

---

# 159. Workflow stress tests

Tester nombreuses investigations concurrentes.

---

# 160. Model provider outage test

Méridian doit rester partiellement utilisable.

---

# 161. Source outage test

Même principe.

---

# 162. Chaos testing

À terme :

- service kill ;
- queue delay ;
- network partition ;
- model timeout.

---

# 163. Cost load tests

Un test de charge doit mesurer aussi la facture.

---

# 164. Performance budgets

Chaque feature peut posséder :

```text
latency budget
token budget
tool-call budget
```

---

# 165. Front-end performance

Objectifs :

- bundle maîtrisé ;
- lazy loading ;
- virtualization ;
- memoization Atlas.

---

# 166. Browser compatibility

Cibler navigateurs entreprise modernes.

---

# 167. Memory usage client

Atlas ne doit pas saturer le navigateur.

---

# 168. SSE scalability

Connexions longues doivent être contrôlées.

---

# 169. SSE reconnection

Support :

```text
last_event_id
```

ou équivalent.

---

# 170. SSE idle cleanup

Nettoyer connexions abandonnées.

---

# 171. Multi-tab behavior

Éviter duplication inutile de jobs/streams.

---

# 172. API pagination

Obligatoire pour listes importantes.

---

# 173. Bulk export

Asynchrone pour gros volumes.

---

# 174. Report generation

Toujours job-based si lourd.

---

# 175. Report reproducibility

Stocker snapshot source.

---

# 176. Search query timeout

Les requêtes complexes doivent être bornées.

---

# 177. Graph query timeout

Même principe.

---

# 178. Query guardrails

Bloquer :

```text
unbounded traversal
full tenant scan interactive
```

---

# 179. Operational limits

Documenter limites produit.

---

# 180. Tenant quotas

Exemples :

```text
concurrent jobs
daily LLM spend
source sync concurrency
storage
```

---

# 181. Quota UX

Informer avant blocage.

---

# 182. Fairness between tenants

Un tenant ne doit pas monopoliser les ressources.

---

# 183. Priority scheduling

P0/P1 avant background.

---

# 184. Aging

Éviter starvation des jobs basse priorité.

---

# 185. Queue SLO

Mesurer temps d’attente.

---

# 186. Interactive queue

Doit rester très courte.

---

# 187. Background queue

Peut absorber retard contrôlé.

---

# 188. Freshness SLO

Exemple :

```text
95% Git changes reflected < 10 min
95% runtime signals reflected < 2 min
```

selon architecture finale.

---

# 189. Knowledge propagation latency

Mesurer :

```text
Source change
→ Claim updated
→ Mesh projection updated
→ UI visible
```

---

# 190. Time to Meaning

Mesurer :

```text
first signal
→ meaningful expression
```

---

# 191. Time to Investigation Readiness

Mesurer :

```text
investigation opened
→ ready for decision
```

---

# 192. Time to Learning

Mesurer :

```text
decision
→ validated learning
```

---

# 193. North Star quality metric

Proposition :

> **Réduire la distance entre la réalité observable de l’entreprise et une compréhension fiable, exploitable et actionnable.**

---

# 194. Service Level Indicators

SLIs principaux :

```text
latency
availability
freshness
job completion
error rate
evidence grounding
security correctness
cost
```

---

# 195. SLO catalog

Chaque service doit posséder ses SLOs.

---

# 196. Example — Knowledge API SLO

```text
Availability: 99.9%
p95 latency: < 800 ms
Error rate: < 0.5%
```

---

# 197. Example — Job Orchestrator SLO

```text
Accepted request persistence: 99.99%
No lost jobs
Recovery from worker failure
```

---

# 198. Example — Flore SLO

```text
Simple answer first useful response < 2s p50
< 5s p95
```

selon dépendances.

---

# 199. Example — Source sync SLO

```text
Git p95 freshness < 10 min
```

---

# 200. AI SLOs

Proposition initiale :

```text
structured output compliance >= 99.5%
evidence presence for major factual claims = 100%
permission compliance = 100%
```

---

# 201. AI quality is contextual

Ne pas imposer un score unique.

---

# 202. Quality gates per use case

Exemple :

```text
simple summary
```

peut tolérer moins de profondeur qu’une :

```text
decision recommendation
```

---

# 203. Risk-based quality

Plus l’impact est élevé, plus le standard augmente.

---

# 204. Critical decision support

Exiger :

- contradiction ;
- evidence completeness ;
- human review.

---

# 205. Operational data model

Conserver :

```text
ServiceSLO
SLOMeasurement
ErrorBudget
CapacityLimit
QualityMetric
```

---

# 206. SLO ownership

Chaque SLO a un owner.

---

# 207. Quality ownership

Exemple :

```text
Platform → availability
Knowledge → grounding
AI Platform → model quality
Product → usability
Security → access correctness
```

---

# 208. Quality reviews

Revue périodique.

---

# 209. Release readiness

Une release ne passe pas si :

- SLO critique dégradé ;
- AI regression ;
- security test échoue.

---

# 210. Architecture Decision Records

Les décisions impactant les NFR doivent être documentées.

---

# 211. ADR examples

```text
Graph database choice
Workflow engine
Search engine
SSE vs WebSocket
Multi-region strategy
```

---

# 212. Known trade-offs

## Correctness vs latency

Préférer correctness pour analyses critiques.

## Freshness vs cost

Toutes les Sources n’ont pas besoin d’être realtime.

## Availability vs consistency

Projections peuvent être eventually consistent.

## Cost vs depth

Escalation progressive.

---

# 213. MVP NFR profile

Pour le MVP :

```text
Availability: 99.5–99.9 target
simple API p95 < 1s
Flore first useful response < 5s
job acknowledgment < 2s
all long jobs resumable
all factual outputs evidence-backed
security trimming mandatory
cost traceability mandatory
```

---

# 214. MVP scale

Cible initiale :

```text
20–100 twins
hundreds of repositories/sources combined
100k–1M claims class
small concurrent user population
```

---

# 215. MVP resilience

Support :

```text
worker restart
source failure
model timeout
job retry
partial degraded mode
```

---

# 216. MVP DR

PITR core DB + versioned evidence store.

---

# 217. MVP observability

Obligatoire dès le début.

---

# 218. MVP cost controls

Budgets par Job / Investigation.

---

# 219. Phase 2

Renforcer :

- tenant quotas ;
- multi-region ;
- advanced autoscaling ;
- richer evaluation ;
- SLO automation.

---

# 220. Phase 3

Ajouter :

- enterprise-scale graph partitioning ;
- predictive capacity ;
- deeper multi-region resilience ;
- automated quality adaptation.

---

# 221. Anti-patterns

## Spinner for 20 minutes

Inacceptable.

## Recompute whole repository

Inefficace.

## No cost attribution

Impossible à gouverner.

## Search/Graph treated as authority

Erreur.

## No graceful degradation

Fragile.

## Single queue for everything

Saturation.

## AI quality only by user likes

Insuffisant.

## Latency only metric

Réducteur.

## No freshness SLO

Connaissance obsolète invisible.

## Optimize scale before product fit

Gaspillage.

---

# 222. Critères d’acceptation globaux

Méridian est prêt pour un usage sérieux si :

1. les lectures principales sont interactives ;
2. les traitements longs sont asynchrones, résumables et annulables ;
3. aucune panne de Source ne coupe tout le produit ;
4. les projections peuvent être reconstruites ;
5. les coûts IA sont attribuables et budgétés ;
6. toutes les conclusions importantes sont ancrées dans des preuves ;
7. la sécurité est appliquée avant retrieval ;
8. la fraîcheur est visible ;
9. les SLOs sont instrumentés ;
10. les changements IA sont testés contre des datasets de référence.

---

# 223. Architecture qualité synthétique

```text
                    USER EXPERIENCE
                           │
            ┌──────────────┼──────────────┐
            ▼              ▼              ▼
        LATENCY        AVAILABILITY    TRUST
            │              │              │
            ▼              ▼              ▼
      QUERY BUDGETS    RESILIENCE      EVIDENCE
            │              │              │
            └──────────────┼──────────────┘
                           ▼
                      PLATFORM
       ┌──────────────┬────┼────┬─────────────┐
       ▼              ▼         ▼             ▼
   KNOWLEDGE        WORKFLOW    AGENTS       SOURCES
       │              │         │             │
       └──────────────┴────┬────┴─────────────┘
                           ▼
                    OBSERVABILITY
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
             SLO          COST        QUALITY
```

---

# 224. Quality philosophy

Méridian doit être optimisé pour :

> **une intelligence fiable, disponible et économiquement soutenable.**

Pas pour :

> le maximum de tokens,
> le maximum d’agents,
> le maximum de graphes,
> le maximum d’automatisation.

La bonne architecture est celle qui produit :

> **le maximum de compréhension utile avec le minimum de complexité et de coût nécessaires.**

---

# 225. Conclusion

Les exigences non fonctionnelles ne sont pas une annexe technique.

Elles déterminent directement si Méridian peut devenir un vrai produit.

La vision impose des exigences particulières :

```text
connaissance vivante
→ freshness

preuves
→ integrity

agents
→ cost + observability

Mesh
→ scalability

investigations
→ durable workflows

Flore
→ interactive latency

decisions
→ auditability

learning
→ long-term durability
```

Le système doit donc être conçu pour être simultanément :

- fiable ;
- mesurable ;
- résilient ;
- performant ;
- explicable ;
- extensible ;
- économiquement contrôlable.

---

# 226. Prochain document

Le prochain document recommandé est :

> **MÉRIDIAN — MVP Definition & Delivery Roadmap**

Il devra transformer toute l’architecture en plan exécutable :

```text
Vision
↓
Capabilities
↓
MVP
↓
Vertical Slices
↓
Milestones
↓
Backlog
↓
Delivery
```

Il devra répondre précisément :

- ce qu’on construit maintenant ;
- ce qu’on reporte ;
- quelle valeur doit être démontrée ;
- quelles vertical slices livrer ;
- dans quel ordre ;
- avec quels critères de sortie.

Ce sera le document qui fera passer Méridian **de l’architecture au produit livrable**.
