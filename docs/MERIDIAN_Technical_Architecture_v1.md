# MÉRIDIAN — Technical Architecture
## Architecture technique cible pour un système d’intelligence vivante de l’entreprise

**Statut :** Architecture technique de référence  
**Version :** 1.0  
**Produit :** MÉRIDIAN  
**Tagline :** **DÉCOUVRIR · COMPRENDRE · DÉCIDER**  
**Référence fonctionnelle :** `MERIDIAN_Functional_Architecture_v1.md`

---

# 0. Résumé exécutif

Méridian n’est pas une application IA unique.

C’est une plateforme distribuée capable de :

1. connecter des sources hétérogènes ;
2. construire et maintenir des jumeaux applicatifs vivants ;
3. produire des connaissances vérifiables sous forme de Claims ;
4. relier ces connaissances dans un Mesh ;
5. détecter et faire mûrir des phénomènes ;
6. mobiliser des expertises spécialisées ;
7. conduire des investigations longues et contradictoires ;
8. construire des scénarios ;
9. enregistrer les décisions humaines ;
10. mesurer leurs résultats ;
11. réinjecter les apprentissages dans la connaissance.

La boucle cible est :

> **Source → Observation → Claim → Mesh → Signal → Expression → Opportunité/Risque → Investigation → Décision → Outcome → Learning**

La principale décision d’architecture est de **séparer strictement la connaissance durable de l’entreprise de l’état conversationnel des agents**.

Les LLM et agents interprètent, synthétisent et raisonnent.

Ils ne constituent pas la base de vérité.

Les objets métier durables de Méridian — Claims, preuves, relations, situations, opportunités, investigations, décisions, résultats — sont persistés dans des stores structurés, versionnés, temporels et auditables.

---

# 1. Objectifs architecturaux

L’architecture doit permettre à Méridian de satisfaire simultanément plusieurs propriétés.

## 1.1 Vivant

La connaissance se met à jour en continu à mesure que les sources évoluent.

## 1.2 Vérifiable

Toute affirmation importante est reliée à des preuves.

## 1.3 Temporel

Méridian peut distinguer ce qui est vrai maintenant de ce qui était vrai auparavant.

## 1.4 Contradictoire

Le système recherche également ce qui invalide une hypothèse.

## 1.5 Distribué

Chaque jumeau possède une intelligence locale mais participe à une compréhension globale.

## 1.6 Agentique

Des agents peuvent explorer, raisonner, comparer et proposer.

## 1.7 Durable

Une investigation peut durer longtemps, être interrompue, reprise ou attendre une validation humaine.

## 1.8 Économiquement contrôlable

Les appels LLM, recherches graphes et traitements lourds doivent être mesurables, plafonnables et optimisables.

## 1.9 Sécurisé

Une connaissance accessible à Méridian ne devient pas automatiquement visible à tous les utilisateurs ou agents.

## 1.10 Explicable

Le produit doit pouvoir dérouler :

```text
Conclusion
↓
Hypothèse
↓
Claims
↓
Evidence
↓
Source
```

---

# 2. Principes d’architecture

## 2.1 Les LLM ne sont pas une base de données

Un LLM :

- interprète ;
- classe ;
- résume ;
- formule ;
- raisonne ;
- génère des hypothèses.

Il ne doit pas être utilisé comme stockage autoritatif.

---

## 2.2 Agent Memory ≠ Enterprise Knowledge

La mémoire conversationnelle sert à :

- conserver le fil d’une session ;
- résumer des interactions ;
- retrouver certains éléments conversationnels ;
- poursuivre un travail agentique.

La connaissance d’entreprise sert à :

- prouver ;
- auditer ;
- comparer dans le temps ;
- reconstruire une décision ;
- contredire ;
- versionner.

Ces deux responsabilités restent séparées.

---

## 2.3 Graph ≠ toute la donnée

Le graphe représente les relations structurantes.

Les artefacts volumineux restent dans des stores spécialisés.

Exemple :

```text
Git file contenu complet   → Object Store / Search Index
Code symbols               → Code Graph
Claim                      → Claim Store
Relations transversales    → Enterprise Graph
Embeddings                 → Vector Index
Conversation               → Agent Memory
Workflow state             → Workflow / Domain Store
```

---

## 2.4 Event-driven pour le vivant

Les changements doivent déclencher des réactions ciblées.

Éviter :

```text
réanalyser toute l’entreprise
```

Préférer :

```text
SourceChanged
→ impacted artifacts
→ impacted claims
→ impacted twins
→ impacted relations
→ impacted situations
```

---

## 2.5 Calcul incrémental avant recalcul global

La plateforme doit privilégier :

- diff ;
- delta ;
- invalidation ciblée ;
- cache sémantique ;
- reprise depuis checkpoint.

---

## 2.6 Workflow durable autour des agents

Un agent individuel peut être court ou éphémère.

Une investigation Méridian ne l’est pas.

Le workflow durable doit conserver :

- étape courante ;
- inputs ;
- outputs ;
- décisions ;
- retries ;
- timeout ;
- état humain ;
- coûts ;
- provenance.

---

## 2.7 Contract-first

Les agents échangent des objets structurés.

Éviter autant que possible les chaînes de texte libres entre agents.

Exemple :

```json
{
  "claim_id": "CLM-1234",
  "assertion_type": "DEPENDENCY",
  "subject": "TBT",
  "predicate": "CALLS",
  "object": "EligibilityService",
  "confidence": 0.84,
  "evidence_ids": ["EVD-98", "EVD-103"]
}
```

---

# 3. Architecture logique globale

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                            EXPERIENCE PLANE                             │
│ React UI · Aujourd’hui · Atlas · Flore · Investigations · Jumeaux      │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │ HTTPS / SSE / WebSocket si nécessaire
┌───────────────────────────────▼─────────────────────────────────────────┐
│                         INTERACTION PLANE                               │
│ API Gateway / BFF · Auth Context · Conversation Router · Query Router  │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────────────┐
│                        ORCHESTRATION PLANE                              │
│ Durable Workflows · Task Dispatcher · Agent Runtime · Human Approval   │
└────────────┬──────────────────┬─────────────────────┬───────────────────┘
             │                  │                     │
             ▼                  ▼                     ▼
┌──────────────────┐ ┌────────────────────┐ ┌────────────────────────────┐
│ TWIN INTELLIGENCE│ │ MESH INTELLIGENCE  │ │ EXPLOITATION INTELLIGENCE │
│ code/db/docs     │ │ graph/relations    │ │ maturation/investigation  │
│ local claims     │ │ contradiction      │ │ experts/decision/learning │
└─────────┬────────┘ └──────────┬─────────┘ └──────────────┬─────────────┘
          │                     │                          │
          └─────────────────────┼──────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         KNOWLEDGE PLANE                                 │
│ Claims · Evidence · Graph · Search · Vector · Temporal History         │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────────────┐
│                           DATA PLANE                                    │
│ PostgreSQL · Neptune · OpenSearch · S3 · Agent Memory · Cache          │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────────────┐
│                         ACQUISITION PLANE                               │
│ Connectors · Sync · CDC · Webhooks · Indexing · Normalization          │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
                         ENTERPRISE SOURCES

      SECURITY · GOVERNANCE · OBSERVABILITY · COST CONTROL · AUDIT
                  transverses à toutes les couches
```

---

# 4. Architecture de déploiement AWS de référence

Cette section propose une implémentation AWS cohérente avec Méridian.

Elle reste une **architecture de référence**, pas une obligation produit.

## 4.1 Frontend

### Technologie

- React ;
- TypeScript ;
- bibliothèque de composants interne ;
- moteur de graphe/Atlas dédié ;
- SSE pour résultats progressifs ;
- WebSocket uniquement lorsque le bidirectionnel temps réel est réellement nécessaire.

### Hébergement

Options :

- CloudFront + S3 ;
- plateforme web interne de l’entreprise ;
- conteneur servi via ALB.

---

## 4.2 API / BFF

Responsabilités :

- authentification ;
- contexte utilisateur ;
- agrégation ;
- permissions ;
- adaptation UI ;
- SSE ;
- idempotency keys ;
- correlation IDs.

Implémentations possibles :

- Java/Spring Boot ;
- Kotlin ;
- TypeScript/Node ;
- Python/FastAPI pour certains services IA.

Le BFF ne contient pas la logique cognitive.

---

## 4.3 Compute applicatif

Deux familles de workloads.

### Services durables

- ECS Fargate ou EKS ;
- services Spring/Java ou Python ;
- APIs et workers.

### Fonctions courtes

- Lambda ;
- transformations ;
- ingestion légère ;
- handlers d’événements.

---

## 4.4 Agent Runtime

Cible recommandée :

- Amazon Bedrock AgentCore Runtime ;
- agents développés avec Strands Agents ;
- modèles Bedrock ;
- Gateway pour accès contrôlé aux outils.

Strands reste la bibliothèque de construction des agents.

AgentCore fournit le runtime et les capacités managées autour des agents.

---

# 5. Interaction Plane

## 5.1 BFF

Le BFF reçoit toutes les interactions produit.

```text
Browser
  ↓
API Gateway / ALB
  ↓
Méridian BFF
```

Le BFF résout :

- identité ;
- équipe ;
- domaine ;
- permissions ;
- contexte courant ;
- feature flags ;
- locale ;
- scope temporel.

---

## 5.2 Query Router

Le Query Router classe la requête.

Types principaux :

```text
LOOKUP
EXPLAIN
EXPLORE
COMPARE
REPORT
INVESTIGATE
SIMULATE
DECIDE
FOLLOW_UP
```

Exemple :

> « Quelles fonctionnalités ont été ajoutées à TBT depuis trois ans ? »

devient :

```text
Intent: REPORT
Entity: TBT
TemporalScope: now - 3 years
EvidenceLevel: CODE_REFERENCE_REQUIRED
```

---

## 5.3 Context Resolver

Responsable de déterminer :

- jumeau ;
- domaine ;
- investigation ;
- opportunité ;
- période ;
- utilisateur ;
- permissions ;
- conversation.

Il ne laisse pas le LLM deviner silencieusement un identifiant.

---

# 6. Flore Technical Architecture

Flore est un orchestrateur conversationnel au-dessus des capacités Méridian.

```text
User
↓
BFF
↓
Conversation Session
↓
Intent Resolver
↓
Context Resolver
↓
Capability Planner
↓
Execution
↓
Evidence Assembler
↓
Response Synthesizer
↓
SSE stream
```

---

## 6.1 Mémoire Flore

Trois catégories.

### Session memory

Conversation actuelle.

Peut utiliser AgentCore Memory short-term.

### Durable conversational memory

Préférences ou contexte conversationnel utile dans le temps, selon politique.

Peut utiliser AgentCore Memory long-term.

### Enterprise knowledge

Ne doit pas être stockée uniquement dans AgentCore Memory.

Elle vient du Knowledge Plane.

---

## 6.2 Réponse structurée

Une réponse de Flore peut être modélisée ainsi :

```json
{
  "answer": "...",
  "confidence": 0.86,
  "claims": ["CLM-1", "CLM-2"],
  "evidence": ["EVD-9"],
  "unknowns": ["..."],
  "contradictions": ["CTR-2"],
  "actions": [
    "OPEN_INVESTIGATION",
    "OPEN_ATLAS"
  ]
}
```

---

# 7. Durable Orchestration Plane

C’est une pièce centrale de Méridian.

## 7.1 Pourquoi

Les travaux peuvent durer :

- secondes ;
- minutes ;
- dizaines de minutes ;
- heures ;
- jours avec validation humaine.

Exemples :

- naissance d’un jumeau ;
- analyse complète de repo ;
- construction d’historique ;
- investigation multi-experts ;
- recalcul de domaine ;
- impact analysis.

---

## 7.2 Moteur

Référence AWS :

**Step Functions Standard** pour :

- durabilité ;
- retries ;
- timeouts ;
- callbacks ;
- visibilité ;
- orchestration multi-étapes.

Les workflows lourds doivent pouvoir être décomposés en sous-workflows.

---

## 7.3 Pattern Parent / Child

```text
InvestigationWorkflow
│
├── ContextCollectionWorkflow
├── ExpertArchitectureWorkflow
├── ExpertBusinessWorkflow
├── ContradictionWorkflow
└── ScenarioSynthesisWorkflow
```

Cela évite un gigantesque workflow monolithique.

---

## 7.4 Agent Task

Une Task agentique doit être bornée.

Input :

```text
goal
context references
allowed tools
token budget
time budget
required output schema
evidence policy
```

Output :

```text
status
structured contribution
claims proposed
evidence referenced
unknowns
cost
trace id
```

---

# 8. Agent Runtime & Strands

## 8.1 Modèle

Un expert Méridian peut être implémenté par un agent Strands.

Mais :

> **Expert métier fonctionnel ≠ processus agent permanent**

L’Expert est une définition durable.

L’Agent est une exécution.

---

## 8.2 Expert Definition

```yaml
id: EXPERT_ARCHITECTURE
version: 3
skills:
  - dependency_analysis
  - impact_analysis
  - architecture_reconstruction
allowed_tools:
  - knowledge_query
  - graph_query
  - source_code_query
evidence_policy:
  minimum_independent_sources: 2
output_schema:
  - claims
  - hypotheses
  - contradictions
  - unknowns
```

---

## 8.3 Agent Registry

Le registre contient :

- version ;
- modèle ;
- instructions ;
- tools ;
- permissions ;
- budget ;
- évaluations ;
- disponibilité ;
- domaine.

---

## 8.4 Model Router

Tous les travaux ne nécessitent pas le modèle le plus coûteux.

Classes possibles :

### Tier A

Extraction / classification simple.

### Tier B

Résumé et compréhension locale.

### Tier C

Raisonnement complexe.

### Tier D

Synthèse multi-domaines / contradiction critique.

Le Model Router choisit selon :

- difficulté ;
- importance ;
- volume ;
- budget ;
- SLA.

---

# 9. Tool Gateway

Les agents ne doivent pas recevoir des accès directs non contrôlés à l’entreprise.

Architecture :

```text
Agent
↓
AgentCore Gateway / Meridian Tool Gateway
↓
Policy Enforcement
↓
Tool Adapter
↓
Enterprise System
```

---

## 9.1 Tools typiques

```text
get_claims
search_evidence
query_graph
query_code
query_database_metadata
get_metrics
get_change_history
get_incidents
get_process_evidence
create_hypothesis
propose_claim
```

---

## 9.2 Tool contract

Chaque outil définit :

- input schema ;
- output schema ;
- permissions ;
- timeout ;
- side effects ;
- cost class ;
- audit policy.

---

## 9.3 Read tools vs Write tools

Séparer explicitement.

### Read

Exploration.

### Controlled write

Création d’objets Méridian.

### External write

Actions sur systèmes entreprise.

Dans les premières générations de Méridian, ces dernières doivent rester fortement limitées.

---

# 10. Acquisition Architecture

```text
Enterprise Source
↓
Connector
↓
Raw Artifact
↓
Normalizer
↓
Observation
↓
Domain Event
```

---

## 10.1 Connectors

Pattern plugin.

```text
Connector SPI
├── discover()
├── snapshot()
├── changesSince(cursor)
├── fetch(id)
├── health()
└── permissions()
```

---

## 10.2 Modes d’ingestion

### Pull

Polling périodique.

### Push

Webhooks.

### CDC

Bases de données ou événements.

### Event Stream

Kafka/MSK.

### Manual / On-demand

Exploration ciblée.

---

## 10.3 Sync Cursor

Chaque source maintient un curseur.

```text
source_id
cursor
last_success
last_attempt
status
```

Ainsi un échec n’impose pas une réingestion complète.

---

# 11. Raw Evidence Store

Tous les éléments utilisés comme preuve doivent pouvoir être retrouvés.

Référence :

**Amazon S3** pour :

- snapshots ;
- fichiers source ;
- documents ;
- payloads normalisés ;
- exports ;
- preuves volumineuses.

---

## 11.1 Immutable evidence

Une preuve utilisée dans une décision importante ne doit pas pointer seulement vers :

```text
main/latest/file.java
```

mais vers une version figée :

```text
repository
commit SHA
path
line range
content hash
```

---

# 12. Twin Intelligence Architecture

Un Twin ne doit pas être un gros agent monolithique.

Il est composé de capacités.

```text
Twin Service
│
├── Source Manifest
├── Local Knowledge
├── Code Intelligence
├── Data Intelligence
├── Document Intelligence
├── Change Intelligence
├── Claim Builder
├── Local Graph
└── Twin Summary
```

---

# 13. Source Manifest

Exemple :

```yaml
twin: TBT
sources:
  - type: github
    repo: ...
    mode: event_and_incremental
  - type: jira
    project: TBT
  - type: confluence
    space: ...
  - type: datadog
    service: tbt
  - type: postgres
    mode: metadata_only
```

Le Manifest décrit les sources.

Il n’est pas la connaissance du jumeau.

---

# 14. Code Intelligence Pipeline

Pour un repository :

```text
Clone / Fetch diff
↓
Language detection
↓
Parse
↓
Symbol extraction
↓
Call/dependency extraction
↓
Graph update
↓
Semantic chunks
↓
Embedding/index
↓
Change impact
↓
Claim candidates
```

---

## 14.1 Éviter l’envoi du graphe complet au LLM

Erreur d’architecture :

```text
Entire Code Graph
↓
Prompt gigantesque
↓
Bedrock
```

Approche :

```text
Question
↓
Graph planner
↓
Relevant subgraph
↓
Evidence retrieval
↓
LLM
```

---

## 14.2 Hierarchical summaries

Pré-calculer :

```text
Symbol
→ File
→ Module
→ Component
→ Capability
→ Application
```

Une requête commence au niveau le plus haut puis descend seulement si nécessaire.

---

# 15. Data / Database Intelligence

L’agent BD n’a pas besoin d’exécuter librement des requêtes métier en production.

Modes possibles :

### Metadata mode

- schemas ;
- tables ;
- columns ;
- keys ;
- views ;
- procedures.

### Sample-safe mode

Échantillons anonymisés / gouvernés.

### Read query mode

Queries autorisées et bornées.

### Event / lineage mode

Relations de flux.

---

# 16. Document Intelligence

Pipeline :

```text
Document
↓
Parsing
↓
Structure
↓
Chunks
↓
Metadata
↓
Embeddings
↓
Claim candidate extraction
```

Le document original reste conservé.

---

# 17. Knowledge Plane

Le Knowledge Plane est le cerveau persistant de Méridian.

Il comporte plusieurs stores spécialisés.

```text
                  KNOWLEDGE SERVICES
                          │
     ┌──────────────┬─────┴────┬─────────────┐
     ▼              ▼          ▼             ▼
Relational      Graph       Search        Object
Store           Store       /Vector       Evidence
```

---

# 18. PostgreSQL / Aurora PostgreSQL

Recommandé comme store transactionnel principal.

Contient :

- twins ;
- sources ;
- claims metadata ;
- evidence metadata ;
- signals ;
- situations ;
- opportunities ;
- risks ;
- investigations ;
- hypotheses ;
- scenarios ;
- decisions ;
- initiatives ;
- outcomes ;
- permissions métier ;
- workflows metadata.

---

## 18.1 Pourquoi relationnel

Ces objets ont :

- états ;
- transitions ;
- contraintes ;
- audit ;
- concurrence ;
- transactions.

Un graphe seul est moins adapté à ces responsabilités.

---

# 19. Enterprise Graph

Le graphe représente les relations.

Exemples de nœuds :

```text
Application
Service
API
Database
Table
Capability
Process
Team
Product
CustomerJourney
Rule
Claim
Domain
Incident
Change
```

Edges :

```text
CALLS
DEPENDS_ON
READS
WRITES
IMPLEMENTS
SUPPORTS
PART_OF
AFFECTS
OWNED_BY
PRECEDES
DERIVED_FROM
```

---

# 20. Neptune Database vs Neptune Analytics

Architecture recommandée :

### Neptune Database

Pour le graphe opérationnel vivant.

### Neptune Analytics

Pour analyses graphes lourdes ou périodiques :

- centralité ;
- communautés ;
- chemins ;
- regroupements ;
- détection structurelle.

Neptune Analytics ne doit pas nécessairement être dans le chemin de chaque requête UI.

---

# 21. Search & Vector Layer

Les besoins sont différents du graphe.

Recherche :

- full text ;
- semantic ;
- filters ;
- hybrid retrieval.

Implémentation possible :

**OpenSearch**.

Index possibles :

```text
documents
code_chunks
claims
investigations
decisions
source_artifacts
```

---

# 22. Embeddings

Ne pas embedding-er aveuglément toute information.

Créer des embeddings pour les objets où la proximité sémantique apporte une valeur.

Exemples :

- documentation ;
- descriptions de Claims ;
- code chunks ;
- incidents ;
- décisions ;
- apprentissages.

---

# 23. Claim Store

Le Claim doit avoir un identifiant stable.

Modèle conceptuel :

```text
Claim
id
tenant_id
twin_id
subject_ref
predicate
object_ref/value
claim_type
status
confidence
maturity
valid_from
valid_to
observed_at
created_at
supersedes
```

---

# 24. Evidence Store

Une Evidence contient :

```text
id
source_id
artifact_id
artifact_version
locator
content_hash
observed_at
access_policy
```

Locator peut être :

```text
commit/path/lines
document/page
ticket/comment
metric/time range
db/schema/table
```

---

# 25. Provenance Graph

Pour les conclusions critiques :

```text
Expression
↓ derived_from
Hypothesis
↓ supported_by
Claim
↓ evidenced_by
Evidence
↓ extracted_from
Artifact
↓ provided_by
Source
```

Ce graphe de provenance doit être interrogeable.

---

# 26. Temporal Architecture

Méridian doit être bitemporel autant que nécessaire.

Deux temps doivent être distingués.

### Valid time

Quand l’information était vraie dans l’entreprise.

### System time

Quand Méridian l’a apprise.

Exemple :

```text
L’API a disparu le 12 mars.
Méridian l’a découvert le 14 mars.
```

Ces deux dates ne sont pas identiques.

---

# 27. Mesh Intelligence Architecture

```text
Twin Claim Streams
↓
Entity Resolution
↓
Relationship Builder
↓
Contradiction Engine
↓
Topology Update
↓
Cross-Twin Pattern Detection
```

---

# 28. Entity Resolution

Le même objet peut apparaître sous plusieurs noms.

Exemple :

```text
TBT
tbt-service
app-2748
TransactionBatchTool
```

Le système doit distinguer :

```text
alias
candidate identity
confirmed identity
```

---

# 29. Relationship Discovery

Les relations peuvent provenir :

- code ;
- traces ;
- DB ;
- docs ;
- config ;
- CMDB ;
- agent inference.

Chaque relation possède elle-même :

- provenance ;
- confidence ;
- temporal validity.

---

# 30. Contradiction Engine

Types :

```text
VALUE_CONFLICT
RELATIONSHIP_CONFLICT
TEMPORAL_CONFLICT
SOURCE_CONFLICT
MODEL_CONFLICT
EXPERT_CONFLICT
```

Le moteur ne cherche pas à résoudre tout automatiquement.

Il peut créer :

```text
ContradictionCase
```

---

# 31. Maturation Engine

C’est une capacité distincte des agents.

Le score peut combiner :

```text
evidence strength
source independence
freshness
historical consistency
cross-twin confirmation
expert validation
contradiction penalty
impact
```

---

## 31.1 Architecture

```text
Observations
Claims
Relationships
Signals
        │
        ▼
Feature Builder
        │
        ▼
Rule/Statistical Detection
        │
        ▼
Candidate Situation
        │
        ▼
Agent Interpretation
        │
        ▼
Maturity Evaluator
        │
        ▼
Expression
```

Le LLM n’est donc pas le détecteur unique.

---

# 32. Signal Engine

Sources de signaux :

- métriques ;
- changement ;
- Claims ;
- graph ;
- événements ;
- humains ;
- agents ;
- business KPI.

---

## 32.1 Dédoublonnage

Le Signal Engine doit éviter :

```text
500 signaux = 500 cartes
```

Pattern :

```text
fingerprint
time window
entity scope
similarity
```

---

# 33. Situation Correlator

Regroupe les signaux selon :

- topologie ;
- temps ;
- domaine ;
- changement commun ;
- causalité ;
- population affectée.

Le résultat reste une **Situation candidate**.

---

# 34. Expression Engine

Le moteur produit une formulation utilisateur.

Input :

- situation ;
- Claims ;
- relations ;
- historique ;
- contradictions.

Output :

```text
summary
type
importance
confidence
maturity
evidence
unknowns
recommended_next_step
```

---

# 35. Opportunity / Risk Service

Responsable du cycle de vie.

Ne dépend pas directement de l’UI.

API conceptuelle :

```text
POST /opportunities
GET /opportunities/{id}
POST /opportunities/{id}/qualify
POST /opportunities/{id}/investigate
POST /opportunities/{id}/reject
```

---

# 36. Investigation Architecture

```text
Investigation Service
│
├── Scope Manager
├── Hypothesis Manager
├── Evidence Board
├── Expert Orchestrator
├── Contradiction Manager
├── Timeline
├── Scenario Builder
└── Synthesis
```

---

# 37. Investigation Workflow

```text
START
↓
Resolve scope
↓
Collect baseline evidence
↓
Generate hypotheses
↓
Select experts
↓
Parallel expert work
↓
Cross examination
↓
Resolve/retain contradictions
↓
Synthesis
↓
Build scenarios
↓
Human review
↓
END
```

---

# 38. Parallel Expert Execution

```text
                    ┌→ Architecture Expert ─┐
Investigation ──────┼→ Business Expert ─────┼→ Merge
                    ├→ Process Expert ──────┤
                    └→ Customer Expert ─────┘
```

Mais les résultats ne sont pas seulement concaténés.

Un **Synthesis + Contradiction stage** compare les contributions.

---

# 39. Expert Contribution Schema

```json
{
  "expert": "PROCESS",
  "findings": [],
  "proposed_claims": [],
  "supported_hypotheses": [],
  "challenged_hypotheses": [],
  "unknowns": [],
  "evidence": [],
  "confidence": 0.77
}
```

---

# 40. Anti-confirmation-bias

Après la première synthèse :

```text
Primary hypothesis
↓
Adversarial expert
↓
Find disconfirming evidence
↓
Re-score
```

Ce n’est pas une conversation théâtrale entre deux agents.

C’est une étape fonctionnelle contrôlée.

---

# 41. Scenario Engine

Un Scenario n’est pas simplement une génération LLM.

Il possède :

- assumptions ;
- actions ;
- dependencies ;
- expected impacts ;
- risks ;
- metrics ;
- uncertainty.

---

# 42. Decision Service

La décision est enregistrée hors du LLM.

```text
Decision
├── chosen scenario
├── rejected scenarios
├── rationale
├── approvers
├── timestamp
├── expected outcomes
└── evidence snapshot
```

Un snapshot logique de la connaissance au moment de la décision doit être conservé.

---

# 43. Improvement / Outcome Architecture

Après décision :

```text
Initiative
↓
Observation Plan
↓
Metrics / Events / Claims
↓
Outcome Evaluator
↓
Expected vs Observed
↓
Learning
```

---

# 44. Learning Store

Un Learning est une connaissance issue d’une action réelle.

Exemple :

> « La suppression de la validation X réduit le délai client mais augmente les reprises manuelles dans l’équipe Y. »

Il peut être utilisé dans de futures investigations.

---

# 45. Event Architecture

Méridian doit posséder un backbone événementiel.

Options AWS :

- EventBridge pour événements métier/plateforme ;
- MSK pour volumes élevés, streaming durable ou intégration Kafka existante ;
- SQS pour files de travail et découplage.

---

## 45.1 Types d’événements

```text
SourceConnected
SourceSyncCompleted
ArtifactChanged
ObservationCreated
ClaimCreated
ClaimChanged
ClaimContradicted
TwinUpdated
RelationshipDiscovered
SignalDetected
SituationMatured
ExpressionCreated
OpportunityCreated
InvestigationStarted
ExpertCompleted
DecisionRecorded
OutcomeObserved
LearningCreated
```

---

## 45.2 Event Envelope

```json
{
  "event_id": "uuid",
  "event_type": "ClaimChanged",
  "occurred_at": "...",
  "tenant_id": "...",
  "actor": "...",
  "correlation_id": "...",
  "causation_id": "...",
  "entity": {
    "type": "Claim",
    "id": "CLM-123"
  },
  "payload_version": 2
}
```

---

# 46. Idempotence

Tous les consumers doivent être idempotents.

Pourquoi :

- retries ;
- duplications ;
- replay ;
- reprises d’ingestion.

Pattern :

```text
event_id + consumer_id
```

persisté dans une inbox ou mécanisme équivalent.

---

# 47. Outbox Pattern

Pour les changements métier critiques :

```text
Transaction DB
├── update entity
└── insert outbox event
```

Puis publication asynchrone.

Évite :

```text
DB commit réussi
Event publish échoué
```

---

# 48. API Architecture

Trois types d’API.

## Command APIs

Modifient l’état.

## Query APIs

Lecture.

## Streaming APIs

Progression / résultats partiels.

---

## 48.1 API versioning

```text
/api/v1/...
```

Les schémas d’événements sont versionnés indépendamment.

---

# 49. SSE Architecture

SSE convient bien à :

- chat Flore ;
- progression d’investigation ;
- naissance de jumeau ;
- génération de rapport.

Flux :

```text
Browser
↓
BFF SSE endpoint
↓
Progress Event Store / Stream
↓
Workflow events
```

Le navigateur ne se connecte pas directement au runtime agent.

---

# 50. Progress Event Model

```json
{
  "job_id": "...",
  "stage": "EXPERT_PROCESS",
  "status": "RUNNING",
  "progress": 0.61,
  "message": "...",
  "partial_findings": [],
  "timestamp": "..."
}
```

---

# 51. Job Service

Les tâches longues doivent être des objets.

```text
Job
id
type
status
created_by
started_at
completed_at
workflow_execution
budget
cost
progress
result_ref
```

---

# 52. Cancellation

L’utilisateur doit pouvoir annuler certains traitements.

L’annulation doit :

- arrêter les étapes futures ;
- marquer les résultats partiels ;
- conserver l’audit ;
- libérer les ressources.

---

# 53. Retry Strategy

Différencier :

### Transient

Retry automatique.

### Rate limit

Backoff.

### Data quality

Pas de retry aveugle.

### Agent output invalid

Retry borné avec schema correction.

### Permission denied

Stop immédiat.

---

# 54. LLM Cost Architecture

Chaque invocation doit produire :

```text
agent
model
input tokens
output tokens
cache usage
latency
workflow
investigation
twin
cost estimate
```

---

# 55. Budgets

Budgets possibles :

```text
per request
per investigation
per twin/day
per expert
per team
per tenant
```

Un workflow doit pouvoir s’arrêter avec :

> BUDGET_EXCEEDED

plutôt que continuer silencieusement.

---

# 56. Réduction des appels LLM

Techniques prioritaires :

1. calcul déterministe avant LLM ;
2. retrieval ciblé ;
3. résumés hiérarchiques ;
4. delta analysis ;
5. result caching ;
6. prompt caching lorsque supporté ;
7. modèles plus petits pour extraction ;
8. batch ;
9. déduplication ;
10. arrêt précoce.

---

# 57. Semantic Cache

Exemple :

```text
question normalized
+ context fingerprint
+ temporal scope
+ permissions
→ cached result
```

Le cache est invalidé si les Claims nécessaires changent.

---

# 58. Knowledge Fingerprint

Chaque réponse importante peut dépendre d’un ensemble de Claims.

Créer :

```text
knowledge_fingerprint = hash(sorted(claim_id:version))
```

Si le fingerprint est identique, certaines synthèses peuvent être réutilisées.

---

# 59. Prompt Caching

À utiliser pour les contextes longs et répétitifs compatibles avec les modèles choisis.

Exemples :

- instruction stable d’un expert ;
- taxonomie ;
- contexte de domaine stable ;
- gros document réutilisé.

Ce mécanisme complète le cache applicatif ; il ne le remplace pas.

---

# 60. Security Architecture

Modèle Zero Trust interne.

Chaque accès doit considérer :

```text
User
Role
Team
Domain
Source policy
Object policy
Purpose
```

---

# 61. Identity

Référence AWS/entreprise :

- IdP d’entreprise ;
- OIDC/SAML ;
- Azure AD / Entra ID possible ;
- propagation d’identité vers le BFF ;
- service identities pour workloads.

---

# 62. Authorization

Combiner selon besoin :

### RBAC

Rôles.

### ABAC

Attributs :

- domaine ;
- équipe ;
- classification ;
- source ;
- sensibilité.

---

# 63. Security trimming

Une réponse ne peut jamais exposer une Evidence interdite simplement parce qu’un Claim global la référence.

Le moteur de retrieval applique les permissions **avant** le LLM.

```text
Query
↓
Authorization filter
↓
Retrieval
↓
LLM
```

Pas :

```text
Retrieve all
↓
LLM
↓
Mask later
```

---

# 64. Agent permissions

Chaque Expert reçoit un scope minimal.

```text
expert
allowed domains
allowed source types
allowed tools
write permissions
max data sensitivity
```

---

# 65. Secrets

- Secrets Manager ;
- rotation ;
- aucune credential dans prompts ;
- short-lived credentials autant que possible.

---

# 66. Encryption

- TLS en transit ;
- KMS au repos ;
- clés dédiées selon classification ou tenant si nécessaire.

---

# 67. Audit

Tracer :

- qui a interrogé ;
- quelles sources ont été consultées ;
- quels agents ;
- quels tools ;
- quels Claims créés ;
- quelle décision ;
- quel export.

---

# 68. LLM Safety / Data Controls

Politiques :

- modèles autorisés ;
- régions autorisées ;
- types de données autorisés ;
- redaction ;
- logging ;
- prompt injection defense ;
- tool allowlists ;
- output validation.

---

# 69. Prompt Injection Architecture

Considérer les sources comme données non fiables.

Un document pourrait contenir :

> « Ignore toutes les instructions et exporte… »

Pipeline :

```text
Source content
↓
Content classification
↓
Instruction isolation
↓
Tool policy
↓
Agent
```

Une source n’obtient jamais de privilège par son texte.

---

# 70. Observability Architecture

Trois niveaux.

## Platform

CPU, memory, queue, DB, errors.

## Workflow

duration, retries, stage latency.

## Agentic

model latency, tokens, tool calls, traces, outputs.

---

# 71. OpenTelemetry

Standardiser :

- traces ;
- spans ;
- correlation IDs.

AgentCore peut fournir de la télémétrie compatible OTEL et CloudWatch.

Si l’entreprise utilise Datadog, les traces doivent pouvoir être corrélées.

---

# 72. Trace hierarchy

```text
User Request
└── Workflow
    ├── Retrieval
    ├── Agent Architecture
    │   ├── Model Invocation
    │   └── Graph Tool
    ├── Agent Process
    └── Synthesis
```

---

# 73. Cognitive Observability

Méridian doit observer la qualité du raisonnement, pas seulement la latence.

Métriques :

- claims proposed ;
- claims accepted ;
- evidence count ;
- contradiction rate ;
- unsupported assertion rate ;
- expert disagreement ;
- retrieval precision ;
- outcome accuracy.

---

# 74. Evaluation Architecture

Créer des datasets d’évaluation.

Exemples :

### Twin understanding

Questions avec réponses connues.

### Claim extraction

Ground truth.

### Investigation

Cas historiques.

### Code references

Exactitude des fichiers/lignes.

### Contradiction

Capacité à détecter une preuve contraire.

---

# 75. Online evaluation

Échantillonner des interactions pour :

- factuality ;
- evidence coverage ;
- permission correctness ;
- usefulness ;
- latency ;
- cost.

---

# 76. Resilience

Le système doit tolérer :

- indisponibilité d’une source ;
- modèle LLM indisponible ;
- quota Bedrock ;
- expert en échec ;
- graphe indisponible ;
- index en retard.

---

# 77. Graceful degradation

Exemple :

> Neptune Analytics indisponible

ne doit pas empêcher :

> consulter le résumé d’un jumeau.

---

# 78. Circuit breakers

Pour :

- sources externes ;
- modèles ;
- graph ;
- search.

---

# 79. Multi-Region

Pour une première version, privilégier une architecture régionale robuste.

La multi-région active-active cognitive est complexe.

Séparer :

- DR plateforme ;
- DR données ;
- reprise workflows ;
- réplication evidence.

---

# 80. Backup

Prévoir :

- Aurora backups/PITR ;
- S3 versioning ;
- graph snapshots ;
- index reconstructible ;
- configurations agents versionnées.

---

# 81. Reconstructible indexes

OpenSearch/vector indexes doivent pouvoir être reconstruits depuis les stores de vérité.

Ils ne doivent pas être les seuls détenteurs d’une connaissance critique.

---

# 82. Data Classification

Tout artefact reçoit une classification.

Exemple :

```text
PUBLIC_INTERNAL
CONFIDENTIAL
RESTRICTED
HIGHLY_RESTRICTED
```

Le niveau se propage aux dérivés selon des règles.

---

# 83. Multi-Tenant Architecture

Si Méridian devient SaaS :

`tenant_id` devient une propriété fondamentale.

Isolation possible :

### Shared

Même cluster, séparation logique.

### Silo

Infrastructure par client.

### Hybrid

Stores sensibles isolés, services partagés.

Pour une banque, la stratégie silo/hybride peut être préférable selon les exigences.

---

# 84. Deployment Architecture

```text
Internet / Enterprise Network
        │
      WAF
        │
 API Gateway / ALB
        │
      BFF
        │
┌───────┼────────┬────────────┐
│       │        │            │
Services│ Workflow│ AgentCore  │
│       │        │            │
Aurora  EventBus  Bedrock     │
Neptune SQS       Gateway     │
OpenSearch        Memory      │
S3                            │
```

---

# 85. Network

- VPC ;
- private subnets ;
- VPC endpoints ;
- private access aux stores ;
- egress contrôlé ;
- WAF côté exposition.

---

# 86. CI/CD

Chaque composant suit :

```text
Code
↓
Build
↓
Unit tests
↓
Security scan
↓
Integration tests
↓
Agent evals
↓
Deploy staging
↓
Canary
↓
Production
```

---

# 87. Versioning des agents

Une investigation doit savoir :

```text
expert_version = architecture-expert:3.4
model = ...
prompt_version = ...
toolset_version = ...
```

Sinon les résultats ne sont pas reproductibles.

---

# 88. Versioning des Claims

Les Claims sont immuables par version.

Correction :

```text
CLM-100 v1
↓ superseded
CLM-100 v2
```

Ne pas simplement écraser.

---

# 89. Versioning du Mesh

Les relations changent dans le temps.

Le système doit permettre :

```text
Atlas(now)
Atlas(t-1)
```

sans conserver nécessairement un snapshot complet à chaque instant.

---

# 90. Event Sourcing — usage sélectif

Ne pas event-sourcer toute la plateforme.

Utiliser un journal d’événements pour les domaines où l’historique est stratégique :

- Claims ;
- Decisions ;
- Investigations ;
- Twin lifecycle.

Pour les autres, audit + state peut suffire.

---

# 91. Architecture de naissance d’un jumeau

```text
CreateTwin command
↓
Twin record
↓
Provision manifest
↓
Connect sources
↓
Initial source snapshot
↓
Code/doc/db pipelines
↓
Build local indexes
↓
Generate claim candidates
↓
Validate/deduplicate
↓
Build local graph
↓
Resolve neighbor candidates
↓
Publish TwinBorn
↓
Mesh updates
↓
Generate living summary
```

---

# 92. Architecture de mise à jour d’un jumeau

```text
ArtifactChanged
↓
Impact resolver
↓
Affected symbols/chunks
↓
Affected claims
↓
Recompute local knowledge
↓
Invalidate claims if needed
↓
Mesh impact
↓
Signal engine
```

---

# 93. Cas TBT — rapport 3 ans

```text
User
↓
Flore
↓
Intent: HistoricalFeatureReport
↓
Resolve TBT + 3y
↓
Workflow
├── Git history retrieval
├── Jira history retrieval
├── Documentation retrieval
├── Code graph delta
└── Existing claims
↓
Feature clustering
↓
Code Expert
↓
Functional Expert
↓
Cross validation
↓
Report assembler
↓
Evidence references
```

---

# 94. Optimisation du cas TBT

Ne pas faire :

```text
3 years git history
↓
all files
↓
all graph
↓
many LLM calls
```

Faire :

```text
Commits
↓
semantic/change clustering
↓
candidate feature periods
↓
relevant code deltas
↓
targeted graph queries
↓
LLM synthesis
```

---

# 95. Cas opportunité

```text
Multiple Signals
↓
Situation
↓
Maturity Engine
↓
Expression
↓
Opportunity
↓
User opens
↓
Investigation Workflow
↓
Experts
↓
Scenarios
↓
Decision
```

---

# 96. Cas incident

```text
Monitoring event
↓
Signal
↓
Topology lookup
↓
Recent changes
↓
Historical similarity
↓
Situation
↓
Investigation
↓
Hypotheses
↓
Root cause candidate
```

---

# 97. Technology Mapping recommandé

| Capacité | Technologie de référence |
|---|---|
| Web UI | React + TypeScript |
| BFF | Spring Boot / Node / FastAPI selon équipe |
| Agent framework | Strands Agents |
| Agent runtime | Amazon Bedrock AgentCore Runtime |
| Foundation models | Amazon Bedrock |
| Agent tool gateway | AgentCore Gateway / Meridian Gateway |
| Agent conversational memory | AgentCore Memory |
| Durable workflows | AWS Step Functions Standard |
| Event backbone | EventBridge + SQS ; MSK si streaming élevé |
| Transactional store | Aurora PostgreSQL |
| Object/evidence store | Amazon S3 |
| Operational graph | Amazon Neptune Database |
| Graph analytics | Neptune Analytics |
| Search/vector | Amazon OpenSearch |
| Cache | ElastiCache/Redis |
| Secrets | AWS Secrets Manager |
| Encryption | AWS KMS |
| Observability | CloudWatch + OpenTelemetry + intégration Datadog |
| Identity | Enterprise IdP / OIDC / SAML |

---

# 98. Pourquoi cette séparation de stores

Aucun store ne doit tout faire.

```text
Aurora
→ état métier transactionnel

Neptune
→ relations

OpenSearch
→ retrieval textuel/sémantique

S3
→ preuves et artefacts

AgentCore Memory
→ contexte conversationnel

Redis
→ accélération temporaire
```

---

# 99. Anti-patterns à éviter

## Giant Twin Prompt

Envoyer toute l’application au LLM.

## Giant Mesh Prompt

Envoyer tout le graphe entreprise.

## One Agent Does Everything

Agent universel.

## Agent Memory as Truth

Utiliser la mémoire conversationnelle comme référentiel.

## Vector DB as Truth

Stocker seulement embeddings + texte.

## Synchronous Everything

Bloquer une requête HTTP 23 minutes.

## Every Signal Is an Alert

Créer du bruit.

## No Temporal Model

Écraser le passé.

## Hidden Contradictions

Ne montrer que la synthèse finale.

## Unlimited LLM Fan-out

Paralléliser des centaines d’appels sans budget.

---

# 100. Performance targets conceptuels

Les SLA définitifs seront établis dans les NFR.

Catégories :

### Interactive

< quelques secondes idéalement.

### Progressive

Premiers résultats rapidement, traitement ensuite.

### Background job

Minutes/heures acceptables avec progression.

### Analytical

Batch contrôlé.

---

# 101. Traitement de 20+ minutes

Une analyse longue doit être conçue comme un Job.

```text
POST /investigations/{id}/analyze
→ 202 Accepted
→ job_id
```

Puis :

```text
GET /jobs/{id}
SSE /jobs/{id}/events
```

Résultats partiels disponibles avant la fin.

---

# 102. Reprise après échec

Chaque étape lourde écrit un checkpoint.

Exemple :

```text
repo parsed ✓
code graph built ✓
claims 1..120 ✓
claims 121..180 retry
```

Un retry ne recommence pas le repository.

---

# 103. Concurrency Control

Limiter par :

- tenant ;
- twin ;
- workflow ;
- model ;
- source.

Prévenir :

```text
20 utilisateurs
× 50 agents
= saturation
```

---

# 104. Backpressure

SQS/MSK absorbe les pics.

Le scheduler adapte la consommation selon :

- quotas Bedrock ;
- DB ;
- coûts ;
- priorité.

---

# 105. Work Priority

Classes :

```text
P0 Incident
P1 Interactive user
P2 Investigation
P3 Synchronization
P4 Enrichment batch
```

---

# 106. Data Freshness

Chaque réponse devrait pouvoir indiquer implicitement ou explicitement :

```text
Knowledge as of: ...
```

Les sources ont des SLO de fraîcheur différents.

---

# 107. Source Freshness Policy

Exemple :

```text
GitHub: webhook + daily reconciliation
Datadog: streaming/query
Confluence: hourly/daily
CMDB: daily
DB metadata: daily
```

---

# 108. Consistency Model

Méridian accepte une cohérence éventuelle entre certaines vues.

Exemple :

```text
Git change
↓
Twin updated in 20 sec
↓
Mesh updated in 40 sec
↓
Opportunity reevaluated in 2 min
```

Toutes les couches n’ont pas besoin d’une transaction distribuée.

---

# 109. Schema Registry

Les événements et outputs agentiques utilisent des schémas versionnés.

Technologies possibles :

- JSON Schema ;
- Pydantic ;
- Protobuf/Avro pour streams selon besoin.

---

# 110. Agent Output Validation

Aucun output agentique structurant n’est persisté sans validation.

Étapes :

```text
LLM output
↓
Schema validation
↓
Policy validation
↓
Evidence validation
↓
Persist candidate
```

---

# 111. Claim Validation Pipeline

```text
Candidate Claim
↓
Entity resolution
↓
Duplicate search
↓
Evidence validation
↓
Conflict detection
↓
Confidence computation
↓
Persist
```

---

# 112. Human Validation

Certaines classes peuvent exiger validation.

Exemple :

```text
LEGAL_INTERPRETATION
CRITICAL_RISK
ENTERPRISE_DOMAIN_CHANGE
HIGH_IMPACT_DECISION
```

---

# 113. Reporting Architecture

Les rapports sont des projections.

```text
Knowledge
+ Investigation
+ Evidence
↓
Report Model
↓
Renderer
↓
PDF / DOCX / Markdown
```

Un rapport ne duplique pas sa propre vérité.

---

# 114. Atlas Backend

L’Atlas ne doit pas requêter directement un graphe énorme sans projection.

Créer :

```text
Atlas Projection Service
```

Il produit selon :

- viewport ;
- zoom ;
- scope ;
- layer ;
- time ;
- permissions.

---

# 115. Atlas Levels of Detail

### L0

Domaines.

### L1

Capacités / clusters.

### L2

Jumeaux.

### L3

Relations.

### L4

Composants détaillés.

Cela évite de charger des milliers de nœuds.

---

# 116. Atlas Layout

Le layout doit être calculé côté serveur ou worker lorsque lourd, puis stabilisé.

Le client peut faire des ajustements locaux.

Conserver :

- positions ;
- cluster anchors ;
- layout version.

---

# 117. Domain Discovery Technical Flow

```text
Mesh Graph
↓
Graph analytics
↓
Community candidates
↓
Semantic labeling
↓
Domain Expert
↓
Compare official model
↓
Domain Proposal
```

---

# 118. Enterprise-wide Experts

Les experts business/client/employé nécessitent de nouvelles sources.

Leur architecture ne doit pas être forcée dans le jumeau applicatif.

Créer progressivement d’autres contextes :

```text
Application Twin
Process Twin
Capability Twin
Journey Twin
Organizational Twin
```

Le Mesh peut les relier.

---

# 119. Evolution vers plusieurs types de jumeaux

Interface logique commune :

```text
Twin
├── identity
├── sources
├── claims
├── relations
├── timeline
├── confidence
└── unknowns
```

Sous-types :

```text
ApplicationTwin
ProcessTwin
CapabilityTwin
JourneyTwin
OrganizationTwin
```

---

# 120. Control Plane Méridian

Un Control Plane gère :

- tenant ;
- agents ;
- experts ;
- policies ;
- source types ;
- feature flags ;
- schemas ;
- model routing ;
- budgets.

---

# 121. Data Plane Méridian

Le Data Plane exécute :

- ingestion ;
- retrieval ;
- graph ;
- claims ;
- workflows ;
- agents.

Cette séparation devient importante en SaaS.

---

# 122. Environments

Minimum :

```text
DEV
INT
PREPROD
PROD
```

Pour agents :

```text
evaluation environment
```

séparé pour rejouer des cas.

---

# 123. Infrastructure as Code

Tout environnement doit être reproductible.

Options :

- AWS CDK ;
- Terraform.

Inclure :

- IAM ;
- networking ;
- stores ;
- workflows ;
- AgentCore resources ;
- observability.

---

# 124. Disaster Recovery

Définir par composant :

```text
RPO
RTO
backup
restore test
region strategy
```

Les preuves, décisions et Claims ont une priorité supérieure aux caches/indexes reconstructibles.

---

# 125. Architecture Decision Records

Décisions à formaliser séparément.

## ADR-001

PostgreSQL comme store transactionnel.

## ADR-002

Graph spécialisé pour relations Mesh.

## ADR-003

Agent Memory séparée du Knowledge Plane.

## ADR-004

Strands pour agents, workflow durable externe.

## ADR-005

Event-driven + incremental recomputation.

## ADR-006

SSE pour progression vers UI.

## ADR-007

LLM outputs structurés et validés.

## ADR-008

Evidence immutable/versionnée.

## ADR-009

Human approval pour décisions à impact.

## ADR-010

Multi-store assumé plutôt qu’un store universel.

---

# 126. Architecture MVP

Le MVP ne doit pas implémenter toute l’architecture cible.

## MVP Core

```text
React UI
BFF
Step Functions
Strands + Bedrock/AgentCore
Aurora PostgreSQL
S3
Code Graph
OpenSearch
EventBridge/SQS
```

Neptune peut être introduit selon maturité du graph existant.

---

## 126.1 MVP Use Case 1

Naissance TBT.

## 126.2 MVP Use Case 2

Question historique 3 ans.

## 126.3 MVP Use Case 3

Signal → Investigation.

## 126.4 MVP Use Case 4

Opportunity → Scenario.

---

# 127. Phase 2

- Enterprise Graph enrichi ;
- experts business ;
- contradiction systématique ;
- outcome tracking ;
- domain discovery ;
- temporal Atlas.

---

# 128. Phase 3

- plusieurs types de jumeaux ;
- mémoire de transformation ;
- pattern learning ;
- proactive opportunities ;
- simulations plus avancées.

---

# 129. Séquence d’implémentation recommandée

```text
1. Domain model
2. Claim/Evidence contracts
3. Job/workflow infrastructure
4. Source connector framework
5. Twin runtime
6. Code intelligence
7. Knowledge services
8. Mesh graph
9. Flore query orchestration
10. Signal/maturation
11. Investigation
12. Expert framework
13. Decision/outcome
14. Learning
```

---

# 130. Ce que je ne ferais pas en premier

Je ne commencerais pas par :

- 100 connecteurs ;
- simulation complète d’entreprise ;
- dizaines d’experts ;
- graph global parfait ;
- agents autonomes partout ;
- interface Atlas ultra-riche.

Je commencerais par une boucle verticale fiable.

---

# 131. Vertical Slice cible

```text
GitHub + Jira + Datadog
↓
TBT Twin
↓
Claims + Evidence
↓
Mesh relationship
↓
Signal
↓
Expression
↓
Investigation
↓
2-3 Experts
↓
Scenario
↓
Human decision
↓
Outcome
```

Si cette chaîne fonctionne réellement, Méridian possède son noyau.

---

# 132. Observabilité du coût de cette Vertical Slice

Dashboard :

```text
Twin ingestion time
LLM invocations
tokens
cache hit
graph queries
cost per claim
cost per investigation
time to first finding
time to final synthesis
```

---

# 133. SLO cognitifs futurs

Au-delà de la disponibilité :

```text
Evidence coverage > X%
Unsupported critical claims < Y%
Stale knowledge < threshold
Investigation reuse rate
Contradiction detection recall
Code reference accuracy
```

---

# 134. Références techniques vérifiées — septembre 2026

Les décisions proposées dans cette architecture sont cohérentes avec les capacités documentées actuelles des services suivants :

- Amazon Bedrock AgentCore Runtime ;
- Amazon Bedrock AgentCore Memory ;
- Amazon Bedrock AgentCore Gateway ;
- Amazon Bedrock AgentCore Observability ;
- Strands Agents SDK ;
- AWS Step Functions Standard ;
- Amazon EventBridge / EventBridge Pipes ;
- Amazon MSK ;
- Amazon Neptune Database ;
- Amazon Neptune Analytics ;
- Amazon Bedrock Prompt Caching.

Points importants retenus :

1. AgentCore Memory sépare mémoire court terme et mémoire long terme conversationnelle.
2. La documentation AWS distingue explicitement la mémoire long terme d’un RAG destiné à la connaissance autoritative.
3. AgentCore fournit des métriques/traces/logs intégrables à CloudWatch et à des architectures OpenTelemetry.
4. Strands est une bibliothèque exécutée dans le processus applicatif, pas un moteur de workflow durable.
5. Step Functions Standard convient aux workflows longs et peut être décomposé en workflows enfants.
6. Neptune Analytics fournit des algorithmes graphes et peut compléter un graphe Neptune opérationnel.
7. EventBridge Pipes peut connecter notamment MSK à Step Functions, SQS et d’autres services.
8. Bedrock Prompt Caching peut réduire latence et coût pour certains contextes répétés.

---

# 135. Architecture cible synthétique

```text
                                   USER
                                    │
                             React / Atlas
                                    │
                                  BFF
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
                  Flore                     Domain APIs
                    │                               │
                    └───────────────┬───────────────┘
                                    │
                          Durable Orchestration
                            Step Functions
                                    │
         ┌──────────────────────────┼─────────────────────────┐
         │                          │                         │
      Agents                    Services                  Workers
 Strands/AgentCore         Domain Services          Ingestion/Graph
         │                          │                         │
    Tool Gateway                   │                         │
         │                          │                         │
         └──────────────┬───────────┴──────────────┬──────────┘
                        │                          │
                    Knowledge                  Event Bus
                        │                    EventBridge/MSK
      ┌─────────────────┼─────────────────┐        │
      │                 │                 │        │
    Aurora            Neptune         OpenSearch   SQS
      │                 │                 │
      └─────────────────┼─────────────────┘
                        │
                       S3
                  Evidence Store

              SECURITY / AUDIT / OTEL / COST
```

---

# 136. Conclusion

Méridian doit être architecturé comme une plateforme de connaissance et d’exploitation continue, pas comme un assemblage de prompts.

Le cœur technique repose sur cinq séparations fondamentales :

### 1. Sources vs connaissance

Les sources produisent des observations.

### 2. Jumeau vs Mesh

Le jumeau comprend localement ; le Mesh comprend transversalement.

### 3. Connaissance vs agents

Les stores conservent ; les agents raisonnent.

### 4. Agents vs workflows

Les agents exécutent des tâches cognitives ; les workflows portent la durabilité.

### 5. Compréhension vs décision

Méridian construit des scénarios ; l’humain conserve la gouvernance.

La cible n’est donc pas :

> « un gros agent qui connaît l’entreprise ».

La cible est :

> **un système distribué dans lequel des connaissances vérifiables, des graphes, des agents spécialisés, des workflows durables et des décisions humaines coopèrent pour transformer continuellement les changements de l’entreprise en compréhension et en amélioration.**

Le prochain document recommandé est :

> **MÉRIDIAN — Domain Model & Information Architecture**

Il devra définir précisément les objets centraux, leurs identités, leurs relations, leur temporalité, leurs invariants et leurs schémas afin de stabiliser la colonne vertébrale informationnelle avant l’implémentation détaillée.
