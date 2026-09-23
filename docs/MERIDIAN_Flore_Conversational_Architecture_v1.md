# MÉRIDIAN — Flore Conversational Architecture
## Architecture conversationnelle, résolution de contexte, routage cognitif, mémoire, outils, preuves et escalade vers investigation

**Statut :** Architecture conversationnelle de référence  
**Version :** 1.0  
**Produit :** MÉRIDIAN  
**Copilote :** **Flore**  
**Tagline Méridian :** **DÉCOUVRIR · COMPRENDRE · DÉCIDER**

---

# 0. Objet du document

Ce document définit l’architecture conversationnelle de Flore.

Il répond à la question :

> **Comment Flore devient-elle l’interface conversationnelle de l’entreprise vivante, sans se réduire à un chatbot générique ?**

Flore doit permettre à l’utilisateur de parler à Méridian en langage naturel tout en conservant :

- le contexte ;
- la précision ;
- la preuve ;
- les permissions ;
- la temporalité ;
- la continuité ;
- la capacité d’agir.

Flore doit pouvoir :

- répondre à une question simple ;
- naviguer dans les Twins ;
- interroger le Mesh ;
- expliquer une Situation ;
- ouvrir une Investigation ;
- mobiliser des Experts ;
- comparer des scénarios ;
- produire un rapport ;
- suivre une décision ;
- expliquer un Learning.

Le principe central est :

> **Flore ne “connaît” pas l’entreprise dans sa mémoire.  
> Elle sait comment mobiliser Méridian pour retrouver, comprendre et exploiter la connaissance pertinente.**

---

# 1. Rôle de Flore

Flore est avant tout :

```text
CONVERSATIONAL INTERFACE
+
CONTEXT RESOLVER
+
CAPABILITY ROUTER
+
KNOWLEDGE ORCHESTRATOR
+
EVIDENCE-AWARE SYNTHESIZER
```

Elle n’est pas :

- le Mesh ;
- un Twin ;
- le Claim Store ;
- l’Investigation Engine ;
- le système de décision.

---

# 2. Position dans l’architecture globale

```text
USER
  │
  ▼
FLORE UI
  │
  ▼
CONVERSATION SESSION
  │
  ▼
INTENT RESOLVER
  │
  ▼
CONTEXT RESOLVER
  │
  ▼
CAPABILITY ROUTER
  │
  ├─────────────┬─────────────┬─────────────┐
  ▼             ▼             ▼             ▼
KNOWLEDGE     GRAPH         EXPERTS      WORKFLOWS
  │             │             │             │
  └─────────────┴─────────────┴─────────────┘
                │
                ▼
        EVIDENCE ASSEMBLY
                │
                ▼
        RESPONSE SYNTHESIS
                │
                ▼
             SSE STREAM
```

---

# 3. Flore UX principle

Flore doit être :

- accessible partout ;
- contextuelle ;
- non intrusive ;
- précise ;
- actionnable.

Elle ne doit jamais forcer l’utilisateur à reformuler tout le contexte.

---

# 4. Conversation Context

Chaque tour doit connaître :

```yaml
ConversationContext:
  user_ref:
  tenant_id:
  active_surface:
  active_entity_refs:
  active_scope:
  temporal_scope:
  active_investigation_ref:
  active_decision_ref:
  selected_atlas_area:
  permissions:
  conversation_summary:
```

---

# 5. Surface-aware behavior

Le comportement de Flore dépend de l’endroit où elle est ouverte.

## Depuis Atlas

Priorité :

- topologie ;
- domaines ;
- relations ;
- propagation.

## Depuis un Twin

Priorité :

- rôle ;
- historique ;
- Claims ;
- dépendances ;
- Unknowns.

## Depuis une Opportunity

Priorité :

- pourquoi ;
- valeur ;
- preuves ;
- prochain pas.

## Depuis une Investigation

Priorité :

- hypothèses ;
- Experts ;
- contradictions ;
- scénarios.

## Depuis une Decision

Priorité :

- trade-offs ;
- hypothèses ;
- outcomes attendus ;
- risques.

---

# 6. Context hierarchy

Le contexte est résolu selon :

```text
Explicit user mention
↓
Selected entity
↓
Current surface
↓
Conversation history
↓
User default scope
```

Les mentions explicites gagnent toujours.

---

# 7. Context ambiguity

Si deux entités sont plausibles :

```text
TBT application
TBT program
```

Flore doit utiliser le contexte disponible avant de demander clarification.

---

# 8. Entity Resolution

Pipeline :

```text
User utterance
↓
Named entity extraction
↓
Alias matching
↓
Mesh identity resolution
↓
Permission filtering
↓
Resolved entity refs
```

---

# 9. Temporal Resolution

Flore doit résoudre :

```text
today
yesterday
last 3 years
before deployment
since incident
```

en périodes explicites.

---

# 10. Scope Resolution

Exemples :

```text
my team
this domain
the whole Mesh
TBT and its direct neighbors
```

---

# 11. Intent taxonomy

Familles principales :

```text
LOOKUP
EXPLAIN
SUMMARIZE
COMPARE
EXPLORE
HISTORICAL_ANALYSIS
IMPACT_ANALYSIS
ROOT_CAUSE
REPORT
INVESTIGATE
SCENARIO_ANALYSIS
DECISION_SUPPORT
WATCH
FOLLOW_UP
ADMIN_ACTION
```

---

# 12. LOOKUP

Exemple :

> Qui est propriétaire de TBT ?

Réponse principalement par retrieval.

---

# 13. EXPLAIN

Exemple :

> Pourquoi Méridian dit que cette dépendance est critique ?

Nécessite :

- Claim ;
- Evidence ;
- contexte ;
- confidence.

---

# 14. SUMMARIZE

Exemple :

> Résume-moi TBT.

Peut utiliser Twin Summary + Claims récents.

---

# 15. COMPARE

Exemple :

> Compare la vue déclarée et la vue observée de ce domaine.

Nécessite plusieurs projections.

---

# 16. HISTORICAL_ANALYSIS

Exemple :

> Quelles fonctionnalités ont été ajoutées à TBT depuis trois ans ?

Déclenche potentiellement un workflow long.

---

# 17. IMPACT_ANALYSIS

Exemple :

> Que se passerait-il si on supprimait TBT ?

Peut devenir Investigation.

---

# 18. REPORT

Exemple :

> Fais-moi un rapport détaillé avec références de code.

Doit produire un objet Report, pas seulement une réponse chat.

---

# 19. INVESTIGATE

Exemple :

> Lance une investigation là-dessus.

Action explicite.

---

# 20. SCENARIO_ANALYSIS

Exemple :

> Compare les scénarios A et C.

---

# 21. DECISION_SUPPORT

Exemple :

> Quelle option minimise le risque client ?

---

# 22. Intent confidence

Chaque intent possède :

```text
confidence
```

Si faible :

- utiliser contexte ;
- proposer interprétation ;
- éviter action destructive.

---

# 23. Intent chaining

Une requête peut contenir plusieurs intentions.

Exemple :

> Explique-moi cette opportunité et lance une investigation.

Chaîne :

```text
EXPLAIN
↓
INVESTIGATE
```

---

# 24. Capability Router

Le Router transforme l’intention en capacité.

Exemple :

```text
LOOKUP
→ Knowledge Query

HISTORICAL_ANALYSIS
→ Historical Analysis Workflow

INVESTIGATE
→ Investigation Engine

REPORT
→ Report Workflow
```

---

# 25. Capability Registry

```yaml
Capability:
  id:
  supported_intents:
  required_context:
  required_permissions:
  execution_mode:
  output_schema:
  cost_class:
```

---

# 26. Execution modes

```text
INLINE
TOOL_CALL
AGENT
WORKFLOW
HUMAN_CONFIRMATION
```

---

# 27. INLINE

Pour :

- retrieval simple ;
- réponse immédiate.

---

# 28. TOOL_CALL

Pour :

- graph query ;
- Claim lookup ;
- evidence retrieval.

---

# 29. AGENT

Pour :

- interprétation complexe ;
- synthèse spécialisée.

---

# 30. WORKFLOW

Pour :

- analyse longue ;
- rapport ;
- investigation ;
- multi-expert.

---

# 31. Human confirmation

Pour :

- décision ;
- action externe ;
- certains changements gouvernés.

---

# 32. Request lifecycle

```text
Receive
↓
Authenticate
↓
Resolve Context
↓
Resolve Intent
↓
Plan
↓
Authorize
↓
Execute
↓
Assemble Evidence
↓
Synthesize
↓
Stream / Persist
```

---

# 33. Conversation Session

Une session porte :

```yaml
ConversationSession:
  id:
  user_ref:
  started_at:
  active_scope:
  active_entities:
  short_term_memory_ref:
  long_term_memory_policy:
  last_intents:
```

---

# 34. Short-term memory

Contient :

- tours récents ;
- références actives ;
- variables conversationnelles.

---

# 35. Long-term conversational memory

Peut conserver :

- préférences d’affichage ;
- projets suivis ;
- habitudes utiles.

Mais ne doit pas contenir toute la connaissance d’entreprise.

---

# 36. Enterprise Knowledge

Toujours récupérée via :

- Knowledge Plane ;
- Mesh ;
- Investigation ;
- Transformation Memory.

---

# 37. Conversation summary

Pour éviter un historique énorme :

```text
conversation turns
↓
rolling summary
```

---

# 38. Summary rules

Le résumé conversationnel doit préserver :

- décisions utilisateur ;
- références ;
- contexte ;
- objectifs en cours.

---

# 39. Tool-use principle

Si une information d’entreprise existe dans Méridian :

> **Tool / Knowledge retrieval avant connaissance générale du modèle.**

---

# 40. Tool categories

```text
knowledge
graph
code
source
investigation
decision
learning
navigation
report
```

---

# 41. Knowledge Tools

```text
search_claims
get_claim
get_evidence
get_twin_summary
get_unknowns
get_contradictions
```

---

# 42. Graph Tools

```text
get_neighbors
find_path
get_domain
get_impact_radius
compare_topologies
```

---

# 43. Code Tools

```text
search_code
get_symbol
get_callers
get_commit_diff
get_feature_history
```

---

# 44. Investigation Tools

```text
create_investigation
add_hypothesis
request_expert
get_investigation_status
compare_scenarios
```

---

# 45. Decision Tools

```text
get_decision
get_expected_outcomes
record_decision
request_review
```

`record_decision` peut nécessiter gouvernance humaine.

---

# 46. Learning Tools

```text
find_similar_episodes
get_learning
compare_outcomes
```

---

# 47. Navigation Tools

```text
open_atlas
focus_twin
open_opportunity
open_investigation
```

---

# 48. Report Tools

```text
create_report_job
get_report_status
download_report
```

---

# 49. Plan generation

Pour requêtes complexes, Flore construit un plan d’exécution.

Exemple :

```text
Question:
Latest features added to TBT in 3 years

Plan:
1 resolve TBT
2 set temporal scope
3 retrieve feature Claims
4 inspect Git/Jira history
5 validate code references
6 synthesize report
```

---

# 50. Plan visibility

L’utilisateur ne doit pas voir un plan technique inutile.

Il peut voir une progression utile :

```text
Reviewing 3 years of changes
Linking issues to code
Validating feature evidence
Preparing report
```

---

# 51. Context Pack

Les exécutions agentiques utilisent un Context Pack.

```yaml
ContextPack:
  task:
  entity_refs:
  relevant_claims:
  evidence_refs:
  relationships:
  timeline:
  unknowns:
  current_surface:
  permissions:
```

---

# 52. Context budget

Chaque Context Pack possède une limite.

Ne jamais injecter le Mesh complet.

---

# 53. Progressive retrieval

Pattern :

```text
Summary
↓
Claims
↓
Subgraph
↓
Evidence
↓
Raw artifact
```

---

# 54. Evidence-aware response

Toute réponse importante doit identifier ses supports.

Structure interne :

```yaml
FloreResponse:
  answer:
  findings:
  claim_refs:
  evidence_refs:
  confidence:
  maturity:
  contradictions:
  unknowns:
  actions:
```

---

# 55. Response layers

## Layer 1

Réponse directe.

## Layer 2

Pourquoi.

## Layer 3

Preuves.

## Layer 4

Détail technique.

---

# 56. Trust Panel integration

Chaque réponse significative peut ouvrir :

```text
Confidence
Maturity
Sources
Evidence
Contradictions
Unknowns
Freshness
```

---

# 57. Epistemic language

Flore doit distinguer :

```text
Méridian knows
Evidence strongly suggests
A plausible explanation is
We do not yet know
```

---

# 58. No silent invention

Si la donnée n’est pas dans Méridian :

Flore doit le dire.

---

# 59. External knowledge separation

Si une connaissance générale externe est utilisée :

```text
Enterprise knowledge
vs
General reference knowledge
```

doit rester distingué.

---

# 60. Conversation thread continuity

Flore doit comprendre :

> Et depuis quand ?

si le tour précédent parlait d’une dépendance.

---

# 61. Referential memory

Le contexte conserve :

```text
last_entity
last_claim
last_investigation
last_scenario
```

---

# 62. Multi-entity conversation

Exemple :

> Compare TBT et X.

Puis :

> Et lequel est le plus critique ?

Les deux entités restent actives.

---

# 63. Multi-twin traversal

Flore peut naviguer :

```text
Twin A
↓ relation
Twin B
↓ process
Twin C
```

---

# 64. Traversal policy

Définir :

```text
max_depth
max_nodes
security_scope
time_scope
```

---

# 65. Conversational graph queries

Exemple :

> Montre-moi ce qui dépend indirectement de TBT.

Intent :

```text
EXPLORE
```

Tool :

```text
find_dependencies(depth=n)
```

---

# 66. Deep analysis threshold

Flore doit reconnaître lorsqu’une question dépasse un simple chat.

Critères :

- nombreuses sources ;
- historique long ;
- plusieurs domaines ;
- besoin de contradiction ;
- besoin de scénario.

---

# 67. Investigation escalation

Pattern :

```text
User question
↓
Quick retrieval
↓
Insufficient certainty
↓
Propose investigation
```

---

# 68. Auto-escalation

Pour certains cas, Flore peut automatiquement créer une analyse structurée si l’utilisateur le demande clairement.

---

# 69. Investigation handoff

Le contexte conversationnel est transformé en :

```yaml
InvestigationIntake:
  question:
  scope:
  trigger:
  known_claims:
  known_unknowns:
  conversation_ref:
```

---

# 70. Conversation after investigation start

Le chat reste lié à l’Investigation.

Exemple :

> Où en est-on ?

Flore lit l’état durable.

---

# 71. Long-running task architecture

Une tâche longue produit :

```text
job_id
```

---

# 72. SSE events

Exemples :

```text
accepted
planning
retrieving
expert_started
partial_finding
expert_completed
synthesis
completed
```

---

# 73. User-visible streaming

Ne pas exposer la chaîne de pensée.

Afficher uniquement :

- progression ;
- actions ;
- résultats partiels.

---

# 74. Reconnection

Le client doit pouvoir se reconnecter à un job.

---

# 75. Flore Job Card

Dans la conversation :

```text
Historical analysis — TBT
62%
4/6 stages complete
3 validated findings available
```

---

# 76. Partial result

Flore peut dire :

> « J’ai déjà confirmé deux fonctionnalités. L’analyse historique continue. »

---

# 77. Cancellation

L’utilisateur peut annuler une tâche.

---

# 78. Resume

Une tâche reprise ne doit pas recommencer toutes les étapes.

---

# 79. Conversation branching

Une investigation ou analyse peut créer un nouveau fil spécialisé.

---

# 80. Case vs Investigation

Le fil conversationnel reste un **Case / Thread**.

L’Investigation reste le dossier structuré.

---

# 81. Conversation Thread object

```yaml
ConversationThread:
  id:
  context_refs:
  investigation_ref:
  messages:
  summary:
  status:
```

---

# 82. Thread scope

Un Thread peut être attaché à :

- Twin ;
- Domain ;
- Opportunity ;
- Investigation ;
- Decision.

---

# 83. Flore proactive suggestions

Flore peut proposer des actions contextuelles.

Exemple sur Opportunity :

```text
Validate with Process Expert
Open affected area in Atlas
Start Investigation
```

---

# 84. Proactive message discipline

Flore ne doit pas interrompre sans raison.

---

# 85. Proactive thresholds

Seulement si :

- sujet suivi ;
- décision imminente ;
- risque critique ;
- résultat demandé.

---

# 86. Explainability conversation

Exemple :

> Pourquoi tu penses ça ?

Flore doit répondre avec provenance, pas avec une justification vague.

---

# 87. Example answer architecture

```text
Answer:
TBT appears to depend on EligibilityService for batch validation.

Why:
3 independent evidences.

Evidence:
Git code
runtime trace
configuration

Confidence:
High

Unknown:
fallback behavior not confirmed
```

---

# 88. Contradiction conversation

Question :

> Y a-t-il quelque chose qui contredit cette conclusion ?

Flore consulte :

- Contradiction Store ;
- opposing Evidence ;
- expert disagreements.

---

# 89. Unknown conversation

Question :

> Qu’est-ce que tu ne sais pas encore ?

Doit être une requête native.

---

# 90. Historical conversation

Flore doit comprendre la différence :

> Que savions-nous à cette date ?

vs

> Que savons-nous aujourd’hui de cette date ?

---

# 91. Time travel support

Le Context Resolver ajoute :

```text
knowledge_time
valid_time
```

---

# 92. Report architecture

Quand l’utilisateur demande un rapport :

Flore :

```text
collects
validates
structures
creates report artifact
```

---

# 93. Report object

```yaml
Report:
  id:
  request:
  scope:
  generated_at:
  knowledge_snapshot_ref:
  sections:
  evidence_refs:
  artifact_ref:
```

---

# 94. Report styles

```text
executive
technical
audit
historical
decision
```

---

# 95. Report evidence

Les références doivent être spécifiques.

Exemple :

```text
repo
commit
file
line
```

---

# 96. Flore and Decisions

Flore peut :

- résumer ;
- comparer ;
- expliquer ;
- préparer.

---

# 97. Flore cannot silently commit critical decisions

Une Decision importante exige une action utilisateur explicite.

---

# 98. Decision support response

Structure :

```text
Preferred scenario
Why
Trade-offs
Risks
Unknowns
Confidence
```

---

# 99. Human override

Si utilisateur choisit autre scénario :

Flore enregistre le rationale si demandé.

---

# 100. Flore and Continuous Improvement

Questions :

> Est-ce que la décision fonctionne ?

> Quels effets secondaires ?

> Qu’avons-nous appris ?

---

# 101. Transformation Memory routing

Intent :

```text
HISTORICAL_ANALYSIS
```

ou :

```text
COMPARE
```

vers Transformation Memory.

---

# 102. Similar episode conversation

Exemple :

> Avons-nous déjà vu quelque chose de similaire ?

---

# 103. Similarity response

Doit exposer :

- ce qui est similaire ;
- ce qui est différent ;
- outcome ;
- learning.

---

# 104. No precedent overconfidence

Flore ne doit pas transformer un précédent en certitude.

---

# 105. Security architecture

Flore est soumise au même modèle de permissions que tout Méridian.

---

# 106. Security trimming

Pipeline :

```text
User identity
↓
Scope
↓
Tool authorization
↓
Retrieval filter
↓
Context Pack
↓
Model
```

---

# 107. Restricted evidence

Flore peut dire :

> « Une preuve supplémentaire existe mais vous n’y avez pas accès. »

---

# 108. No leakage through synthesis

Même la synthèse ne doit pas révéler implicitement une information restreinte.

---

# 109. Tool authorization

Chaque tool call est vérifié.

---

# 110. Delegated identity

Les agents exécutent au nom du contexte autorisé.

---

# 111. Prompt injection defense

Source content est isolé.

---

# 112. Conversation injection

Un utilisateur peut demander :

> ignore les politiques.

Les policies restent hors contrôle du prompt utilisateur.

---

# 113. Tool side effects

Les tools avec side effect exigent :

- permissions ;
- confirmation ;
- audit.

---

# 114. Memory security

La mémoire conversationnelle respecte la classification.

---

# 115. Conversation retention

Configurable selon policy.

---

# 116. Audit

Tracer :

```text
user query
resolved intent
resolved context
tools
experts
knowledge refs
actions
```

---

# 117. Privacy

Éviter de stocker des données personnelles inutiles dans conversation summaries.

---

# 118. Observability

Métriques :

```text
requests
latency
tool calls
agent calls
workflow escalations
errors
```

---

# 119. Conversational quality metrics

```text
intent accuracy
context resolution accuracy
evidence coverage
follow-up continuity
user correction rate
```

---

# 120. Cost metrics

```text
cost per conversation
cost per answer
cost per investigation handoff
```

---

# 121. First-response latency

Pour les questions simples :

objectif interactif.

---

# 122. Progressive latency

Pour tâches longues :

le premier signal de progression doit arriver rapidement.

---

# 123. Retrieval metrics

```text
precision
claim relevance
evidence relevance
security correctness
```

---

# 124. Conversation success

Une conversation est réussie si elle permet :

- réponse ;
- compréhension ;
- action ;
- navigation.

Pas seulement si l’utilisateur reçoit du texte.

---

# 125. Feedback

L’utilisateur peut indiquer :

```text
Useful
Missing evidence
Wrong context
Too technical
Too vague
```

---

# 126. Context correction

Exemple :

> Je parle du TBT batch, pas du service TBT.

Flore met à jour le contexte.

---

# 127. Context correction should persist in thread

---

# 128. Intent correction

Exemple :

> Non, je veux un rapport, pas juste un résumé.

Le router replannifie.

---

# 129. Conversational commands

Exemples :

```text
montre-moi
compare
ouvre
surveille
investigue
explique
résume
exporte
```

---

# 130. Conversational navigation

Flore peut piloter l’UI.

Exemple :

> Montre ça dans Atlas.

---

# 131. UI action contract

```yaml
UIAction:
  type:
  target_ref:
  parameters:
```

---

# 132. UI actions

```text
FOCUS_ATLAS
OPEN_TWIN
OPEN_INVESTIGATION
OPEN_EVIDENCE
OPEN_DECISION
SHOW_COMPARISON
```

---

# 133. Conversation cards

Flore peut renvoyer des composants structurés :

- Twin card ;
- Opportunity card ;
- Claim card ;
- Scenario comparison ;
- Job card.

---

# 134. Text + UI

Réponse idéale :

```text
short synthesis
+
structured cards
+
actions
```

---

# 135. Flore personality

Flore doit être :

- calme ;
- concise ;
- compétente ;
- transparente.

---

# 136. Avoid anthropomorphic excess

Flore n’a pas besoin de jouer un personnage émotionnel.

---

# 137. Tone

Professionnel mais naturel.

---

# 138. Confidence-aware language

Si confidence faible :

> « Les éléments disponibles suggèrent… »

---

# 139. Action language

Actions courtes :

```text
Investiguer
Voir dans Atlas
Comparer
Ouvrir les preuves
```

---

# 140. Conversation empty state

Selon surface :

Twin :

> « Je peux expliquer ce que Méridian sait de cette application, ses dépendances ou ses changements récents. »

Investigation :

> « Je peux comparer les hypothèses, expliquer les preuves ou mobiliser un nouvel expert. »

---

# 141. Starter prompts

Doivent être contextuels et peu nombreux.

---

# 142. Command palette integration

Flore peut être invoquée depuis Cmd/Ctrl+K.

---

# 143. Keyboard shortcut

Proposition :

```text
Cmd/Ctrl + J
```

pour ouvrir Flore.

---

# 144. Mobile/compact behavior

Flore devient une surface plein écran ou bottom sheet.

---

# 145. Offline/degraded mode

Si le Knowledge Plane est partiellement indisponible :

Flore doit le dire.

---

# 146. Example degraded message

> « Les données de monitoring sont temporairement indisponibles. Je peux toujours utiliser la connaissance déjà indexée. »

---

# 147. Hallucination guard

Avant synthèse :

```text
check required claims
check evidence
check permission
```

---

# 148. Unsupported assertions

Les assertions sans support doivent être marquées comme :

```text
inference
```

ou retirées.

---

# 149. Response validator

Pipeline :

```text
Draft response
↓
Citation/evidence validation
↓
Permission check
↓
Confidence check
↓
Final response
```

---

# 150. Structured output

Les outputs intermédiaires doivent utiliser schemas.

---

# 151. Model routing

Questions simples :

```text
fast model
```

Analyses complexes :

```text
strong reasoning model
```

---

# 152. Model fallback

Si modèle principal indisponible :

fallback selon policy.

---

# 153. Cost-aware planning

Une simple question ne doit pas devenir workflow.

---

# 154. Escalation threshold

Éléments qui augmentent coût acceptable :

- impact ;
- user request ;
- decision importance ;
- uncertainty.

---

# 155. Flore direct answer path

```text
Query
↓
Resolve
↓
Knowledge retrieval
↓
Synthesize
↓
Answer
```

---

# 156. Flore expert path

```text
Query
↓
Resolve
↓
Need specialization
↓
Expert
↓
Contribution
↓
Answer
```

---

# 157. Flore workflow path

```text
Query
↓
Resolve
↓
Complex task
↓
Create Job
↓
Workflow
↓
Partial results
↓
Final artifact
```

---

# 158. Flore investigation path

```text
Query
↓
Insufficient certainty / explicit request
↓
Investigation Intake
↓
Investigation
```

---

# 159. Query examples

## Simple

> Qui possède TBT ?

## Medium

> Pourquoi cette relation existe ?

## Complex

> Quelles fonctionnalités ont été ajoutées sur 3 ans avec code refs ?

## Strategic

> Peut-on retirer TBT dans 18 mois ?

---

# 160. Example — historical TBT request

```text
User
↓
Flore
↓
Intent: HISTORICAL_ANALYSIS + REPORT
↓
Entity: APP-2748
↓
Time: -3 years
↓
Requirement: code refs
↓
Historical workflow
↓
Feature Claims
↓
Evidence validation
↓
Report artifact
```

---

# 161. Example — incident

> Pourquoi le parcours ralentit ?

Flore :

```text
Situation context
↓
existing Investigation?
↓
if yes: summarize
if no: quick analysis
↓
propose investigation
```

---

# 162. Example — Opportunity

> Pourquoi Méridian pense que cette application peut être retirée ?

Réponse :

```text
capability overlap
low usage
few unique consumers
high maintenance
```

avec Evidence.

---

# 163. Example — Decision

> Quelle option est la moins risquée ?

Flore doit demander/consulter les critères de décision existants.

---

# 164. Example — Learning

> Notre dernière migration a-t-elle vraiment aidé ?

Route :

```text
Decision
→ Initiative
→ Outcomes
→ Learning
```

---

# 165. Conversation state machine

```text
IDLE
↓
UNDERSTANDING
↓
RESOLVING
↓
EXECUTING
↓
STREAMING
↓
ANSWERED
```

Branches :

```text
WAITING_FOR_HUMAN
FAILED
CANCELLED
```

---

# 166. Pending action

Flore peut conserver :

```text
pending_action
```

pour les confirmations.

---

# 167. Action confirmation

Exemple :

> « Cette action ouvrira une investigation L3. Confirmer ? »

---

# 168. No confirmation fatigue

Ne pas demander confirmation pour les lectures.

---

# 169. Human approval boundary

Confirmer :

- write ;
- decision ;
- external action ;
- expensive workflow si policy.

---

# 170. Conversation-to-artifact

Flore peut créer :

- Investigation ;
- Report ;
- Decision draft ;
- Watch ;
- Saved view.

---

# 171. Artifact provenance

L’objet créé référence la conversation source.

---

# 172. Conversation links

Chaque message peut référencer des objets Méridian.

---

# 173. Deep links

Exemple conceptuel :

```text
meridian://twin/APP-2748
```

---

# 174. Response persistence

Les réponses critiques peuvent être sauvegardées comme Insight ou Report.

---

# 175. Insight object

Option future :

```yaml
Insight:
  id:
  statement:
  source_refs:
  context:
  created_from_conversation:
```

À éviter si cela duplique Expression/Claim.

---

# 176. Flore in Today

Starter prompts :

```text
Why is this important?
What changed since yesterday?
What needs a decision?
```

---

# 177. Flore in Atlas

```text
Explain this area
Show dependencies
What is emerging here?
```

---

# 178. Flore in Twin

```text
What does this application do?
What changed?
What do we not know?
```

---

# 179. Flore in Investigation

```text
Which hypothesis is strongest?
What contradicts it?
What is missing?
```

---

# 180. Flore in Decision

```text
Compare scenarios
What risk are we accepting?
What outcome should we watch?
```

---

# 181. Flore in Transformation Memory

```text
Have we seen this before?
What did we learn?
Where does this learning apply?
```

---

# 182. Internationalization

Flore doit supporter plusieurs langues.

Le contexte métier conserve les termes canoniques.

---

# 183. Terminology normalization

Exemple :

```text
"application"
"app"
"système"
```

peuvent mapper au même concept selon contexte.

---

# 184. Mixed-language environments

Le code peut être anglais, les tickets français, la conversation française.

Flore doit préserver les références originales.

---

# 185. Source quotation

Les citations de preuve restent dans leur langue d’origine, avec résumé si utile.

---

# 186. Naming policy

Flore ne doit pas inventer de nom métier quand une entité n’est pas confirmée.

---

# 187. Unknown entity

Peut utiliser :

```text
Unknown Service #42
```

jusqu’à résolution.

---

# 188. Conversational observability architecture

```text
User Request
└── Context Resolution
    └── Intent
        └── Plan
            ├── Tool calls
            ├── Expert calls
            └── Workflow
                └── Response
```

---

# 189. Trace attributes

```text
conversation.id
user.scope
intent
entity.ids
investigation.id
job.id
```

---

# 190. Evaluation suite

Évaluer :

- intent ;
- context ;
- tool routing ;
- entity resolution ;
- evidence ;
- follow-up ;
- permissions.

---

# 191. Golden conversations

Exemple :

```text
User: What changed in TBT?
Flore: ...
User: And over the last year?
```

Tester continuité temporelle.

---

# 192. Adversarial tests

- prompt injection ;
- ambiguous entity ;
- restricted data ;
- false premise ;
- unsupported conclusion.

---

# 193. False premise handling

Utilisateur :

> Pourquoi TBT est-il arrêté ?

Si ce n’est pas vrai :

> Flore corrige le prémisse avec Evidence.

---

# 194. Calibration tests

Si Flore dit :

> high confidence

la qualité réelle doit le justifier.

---

# 195. Tool-use tests

Vérifier qu’elle ne répond pas de mémoire générale quand un Tool est requis.

---

# 196. Permission tests

Vérifier absence de fuite indirecte.

---

# 197. Long task tests

- reconnect ;
- cancel ;
- resume ;
- partial result.

---

# 198. MVP Flore

Le MVP doit supporter :

```text
contextual chat
entity resolution
scope/time resolution
Knowledge tools
Graph tools
Twin questions
Investigation creation
Job streaming
Evidence/Trust
```

---

# 199. MVP intents

```text
LOOKUP
EXPLAIN
SUMMARIZE
EXPLORE
HISTORICAL_ANALYSIS
INVESTIGATE
REPORT
```

---

# 200. MVP memory

```text
session memory
thread summary
active context
```

Pas besoin d’une mémoire longue complexe au départ.

---

# 201. MVP tool routing

Rules + semantic classification.

---

# 202. MVP UI

Flore panel :

- context header ;
- chat ;
- structured responses ;
- evidence chips ;
- action chips ;
- job progress.

---

# 203. Phase 2

Ajouter :

- decision support ;
- Transformation Memory ;
- richer expert routing ;
- proactive suggestions ;
- advanced report generation.

---

# 204. Phase 3

Ajouter :

- broader multilingual support ;
- richer proactive behavior ;
- strategic scenario conversations ;
- complex cross-domain traversal.

---

# 205. Anti-patterns

## Generic chatbot

Pas de contexte réel.

## Conversation as database

Mauvais stockage.

## LLM-first retrieval

Hallucination.

## One giant prompt

Coût et fragilité.

## Hidden workflow

Utilisateur perdu.

## Chain-of-thought exposure

Inutile et risqué.

## Always clarify

Conversation frustrante.

## Never clarify

Contexte faux.

## Chat-only product

Méridian réduit à Flore.

## Unbounded tool access

Risque.

---

# 206. Critères de succès

Flore est réussie si :

1. elle comprend le contexte de la surface ;
2. l’utilisateur n’a pas à répéter les entités ;
3. elle choisit entre réponse, tool, expert et workflow ;
4. elle expose la preuve et l’incertitude ;
5. elle sait dire qu’elle ne sait pas ;
6. elle peut transformer une conversation en Investigation ou Report ;
7. les tâches longues restent suivables ;
8. les permissions sont appliquées avant retrieval ;
9. elle reste cohérente avec le Domain Model ;
10. elle donne l’impression de converser avec l’entreprise, pas avec un chatbot générique.

---

# 207. Architecture cible synthétique

```text
                         USER
                           │
                           ▼
                     FLORE PANEL
                           │
                           ▼
                 CONVERSATION SESSION
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
       CONTEXT RESOLVER           INTENT RESOLVER
              │                         │
              └────────────┬────────────┘
                           ▼
                   CAPABILITY ROUTER
                           │
       ┌──────────┬────────┼────────┬──────────┐
       ▼          ▼        ▼        ▼          ▼
   KNOWLEDGE    GRAPH    EXPERTS  WORKFLOW  UI ACTIONS
       │          │        │        │          │
       └──────────┴────────┴────────┴──────────┘
                           │
                           ▼
                   EVIDENCE ASSEMBLER
                           │
                           ▼
                  RESPONSE SYNTHESIZER
                           │
                           ▼
                     TRUST VALIDATOR
                           │
                           ▼
                       SSE / UI
```

---

# 208. Vision finale

Flore doit faire disparaître la complexité de Méridian sans la masquer.

L’utilisateur peut poser :

> « Pourquoi cette opportunité est-elle apparue ? »

Et derrière une question simple, Flore peut :

- résoudre le contexte ;
- retrouver les Claims ;
- traverser le Mesh ;
- comparer les preuves ;
- appeler un Expert ;
- déclencher un workflow ;
- produire un Report ;
- ouvrir une Investigation.

Mais l’expérience utilisateur reste :

> **une conversation naturelle, claire et contextualisée.**

---

# 209. Conclusion

Flore n’est pas le cerveau de Méridian.

Elle est :

> **la voix, le guide et l’interface conversationnelle de son intelligence distribuée.**

Sa valeur repose sur quatre capacités :

```text
COMPRENDRE LE CONTEXTE
↓
CHOISIR LA BONNE CAPACITÉ
↓
EXPOSER LA PREUVE
↓
TRANSFORMER LA CONVERSATION EN ACTION
```

Une Flore réussie ne donne pas seulement des réponses.

Elle permet à l’utilisateur de :

- explorer ;
- comprendre ;
- investiguer ;
- décider ;
- apprendre.

Elle devient alors réellement :

> **la conversation avec l’entreprise vivante.**

---

# 210. Prochain document

Le prochain document recommandé est :

> **MÉRIDIAN — Security, Governance & Trust Model**

Il devra formaliser :

- identité ;
- RBAC / ABAC ;
- sécurité des sources ;
- propagation des permissions ;
- sécurité des Claims dérivés ;
- agent permissions ;
- tool permissions ;
- classification ;
- isolation tenant ;
- audit ;
- provenance ;
- human approvals ;
- AI governance ;
- trust ;
- explainability ;
- data retention ;
- prompt injection defense.

Ce document sera indispensable pour rendre Méridian crédible dans un environnement bancaire et entreprise.
