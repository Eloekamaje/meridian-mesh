# MÉRIDIAN — Continuous Improvement & Learning Model
## De la décision aux résultats, des résultats aux apprentissages, des apprentissages à la transformation continue

**Statut :** Architecture fonctionnelle et produit de référence  
**Version :** 1.0  
**Produit :** MÉRIDIAN  
**Tagline :** **DÉCOUVRIR · COMPRENDRE · DÉCIDER**

---

# 0. Objet du document

Ce document définit la boucle d’amélioration continue de Méridian.

Il répond à la question :

> **Comment Méridian apprend-il réellement des conséquences des décisions de l’entreprise ?**

Les documents précédents permettent à Méridian de :

- découvrir ;
- faire mûrir ;
- investiguer ;
- comparer des scénarios ;
- accompagner une décision.

Mais sans retour sur les résultats, Méridian resterait un système d’analyse.

Ce document ajoute la dernière dimension :

> **l’expérience.**

La boucle complète devient :

```text
Discovery
↓
Maturation
↓
Expression
↓
Investigation
↓
Decision
↓
Initiative
↓
Observation
↓
Outcome
↓
Learning
↓
New Knowledge
↓
New Discovery
```

Le principe fondamental est :

> **Une décision n’est pas la fin d’un raisonnement.  
> C’est le début d’une nouvelle période d’observation.**

---

# 1. Pourquoi cette boucle est essentielle

Une organisation peut prendre une décision raisonnable à partir des informations disponibles et obtenir pourtant un résultat différent de celui attendu.

Exemple :

Avant :

> Réduire cette validation devrait diminuer le temps de traitement de 15 %.

Après :

```text
temps de traitement    -11 %
erreurs                -7 %
abandon client          -5 %
travail manuel          +4 %
```

Le résultat est globalement positif.

Mais un effet secondaire apparaît.

Sans mémoire structurée, l’entreprise retient souvent seulement :

> « le projet a réussi. »

Méridian doit retenir :

> **ce qui a réellement changé, dans quelles conditions, et avec quelles conséquences directes et indirectes.**

---

# 2. Position dans l’architecture globale

```text
INVESTIGATION & DECISION ENGINE
            │
            ▼
         DECISION
            │
            ▼
         INITIATIVE
            │
            ▼
     OBSERVATION PLAN
            │
            ▼
      RESULT MONITORING
            │
            ▼
         OUTCOMES
            │
            ▼
   EXPECTED vs OBSERVED
            │
            ▼
       LEARNING ENGINE
            │
   ┌────────┼─────────┐
   ▼        ▼         ▼
Claims   Signals   Patterns
   │        │         │
   └────────┴─────────┘
            │
            ▼
      FUTURE DISCOVERY
```

---

# 3. Principe de boucle fermée

Une initiative Méridian devrait idéalement toujours posséder :

1. une décision source ;
2. des hypothèses ;
3. des résultats attendus ;
4. un plan d’observation ;
5. une période de mesure ;
6. des critères de succès ;
7. une surveillance des effets secondaires.

Sans ces éléments, Méridian ne peut pas apprendre correctement.

---

# 4. De Decision à Initiative

La Decision exprime :

> ce qui a été choisi.

L’Initiative exprime :

> ce qui va réellement être fait.

Ces deux objets doivent rester distincts.

---

# 5. Decision Handoff

Lorsqu’une décision est enregistrée, le système doit produire un handoff structuré.

```yaml
DecisionHandoff:
  decision_ref:
  selected_scenario_ref:
  assumptions:
  expected_outcomes:
  risks_to_watch:
  unknowns_to_watch:
  affected_entities:
  review_date:
```

---

# 6. Initiative

## 6.1 Définition

Une Initiative représente l’exécution gouvernée d’une décision.

---

## 6.2 Structure

```yaml
Initiative:
  id:
  decision_ref:
  title:
  description:
  status:
  owner_ref:
  sponsor_ref:
  scope:
  affected_entity_refs:
  start_at:
  target_end_at:
  milestones:
  observation_plan_ref:
  expected_outcome_refs:
  actual_outcome_refs:
```

---

# 7. Initiative lifecycle

```text
PLANNED
↓
READY
↓
IN_PROGRESS
↓
DEPLOYED / IMPLEMENTED
↓
OBSERVING
↓
MEASURED
↓
LEARNED
↓
CLOSED
```

Branches :

```text
PAUSED
CANCELLED
FAILED
SUPERSEDED
```

---

# 8. Initiative ≠ Project Management replacement

Méridian ne doit pas devenir Jira ou un outil de portefeuille complet.

Il maintient uniquement les informations nécessaires pour :

- relier décision et action ;
- observer les effets ;
- produire de l’apprentissage.

Le suivi détaillé peut rester dans les outils existants.

---

# 9. External Initiative Reference

Exemple :

```yaml
ExternalInitiativeRef:
  system: Jira
  project: POLARIS
  epic: POL-122
```

ou :

```text
ServiceNow Change
Azure DevOps Epic
Portfolio item
```

---

# 10. Observation Plan

## 10.1 Définition

Le plan d’observation décrit :

> **comment Méridian saura si la décision produit le résultat attendu.**

---

# 11. Observation Plan Structure

```yaml
ObservationPlan:
  id:
  initiative_ref:
  baseline_period:
  observation_start:
  observation_end:
  metric_definitions:
  expected_outcomes:
  side_effect_indicators:
  risk_indicators:
  segmentation:
  confidence_requirements:
  evaluation_schedule:
```

---

# 12. Baseline

Une baseline est obligatoire pour toute comparaison significative.

Exemple :

```text
30 jours avant changement
vs
30 jours après changement
```

Mais le modèle doit également considérer :

- saisonnalité ;
- tendance préexistante ;
- changements concurrents ;
- population comparable.

---

# 13. Baseline Types

```text
HISTORICAL
CONTROL_GROUP
ROLLING
TARGET
BENCHMARK
NONE
```

---

# 14. Expected Outcome

Un Expected Outcome représente le résultat anticipé.

```yaml
ExpectedOutcome:
  id:
  initiative_ref:
  metric:
  direction:
  target:
  tolerance:
  time_horizon:
  rationale:
  source_hypothesis_refs:
```

---

# 15. Exemple

```yaml
metric: PROCESS_DURATION
direction: DECREASE
target: 15%
tolerance: +/- 4%
time_horizon: 30 days
```

---

# 16. Outcome

## 16.1 Définition

Un Outcome est ce qui a réellement été observé.

```yaml
Outcome:
  id:
  initiative_ref:
  expected_outcome_ref:
  metric:
  observed_value:
  baseline_value:
  delta:
  observed_at:
  observation_window:
  confidence:
  segmentation:
  evidence_refs:
```

---

# 17. Outcome types

```text
EXPECTED
BETTER_THAN_EXPECTED
WORSE_THAN_EXPECTED
NO_CHANGE
UNEXPECTED_POSITIVE
UNEXPECTED_NEGATIVE
INCONCLUSIVE
```

---

# 18. Expected vs Observed

Le produit doit rendre cette comparaison centrale.

```text
Dimension             Attendu      Observé

Délai                 -15 %        -11 %
Erreurs                -5 %         -7 %
Abandon client         -8 %         -5 %
Travail manuel          0 %          +4 %
```

La dernière ligne peut générer un nouveau Signal.

---

# 19. Outcome confidence

Le résultat observé possède lui aussi un niveau de confiance.

Pourquoi ?

Parce qu’un changement de métrique peut être corrélé mais pas nécessairement causé par l’initiative.

---

# 20. Attribution

Question clé :

> Ce résultat est-il réellement attribuable à la décision ?

Le système doit éviter :

```text
after = because of
```

---

# 21. Attribution dimensions

```text
temporal fit
population fit
control group
confounding changes
causal evidence
historical baseline
```

---

# 22. Attribution Status

```text
PLAUSIBLE
SUPPORTED
STRONGLY_SUPPORTED
UNCERTAIN
DISPUTED
```

---

# 23. Confounding Change

Exemple :

Pendant l’observation :

```text
new marketing campaign
+ infrastructure migration
+ policy change
```

Ces événements peuvent influencer le résultat.

---

# 24. Change Context

L’Outcome Evaluation doit consulter le Mesh pour détecter :

- changements voisins ;
- incidents ;
- autres initiatives ;
- variation de population ;
- saisonnalité.

---

# 25. Outcome Evaluator

Architecture conceptuelle :

```text
Expected Outcomes
+ Observed Metrics
+ Baseline
+ Change Context
+ Confounders
↓
Outcome Evaluator
↓
Result Classification
↓
Attribution Confidence
```

---

# 26. Side Effects

Méridian doit explicitement chercher :

> Qu’est-ce qui a changé ailleurs ?

---

# 27. Side Effect Detector

Observe :

```text
neighboring applications
downstream processes
employee work
customer journey
cost
risk
```

---

# 28. Positive Side Effect

Exemple :

Une modernisation prévue pour la résilience réduit également le temps de traitement.

---

# 29. Negative Side Effect

Exemple :

Une optimisation client augmente les reprises manuelles.

---

# 30. Displacement Effect

Très important.

Un problème peut être déplacé plutôt que résolu.

Exemple :

```text
less work in channel A
→ more work in operations B
```

Méridian doit détecter ce déplacement.

---

# 31. Local Optimization Trap

Le produit doit se méfier des optimisations locales.

Exemple :

```text
Application A faster
but
End-to-end process slower
```

Le succès doit être évalué au bon niveau.

---

# 32. Evaluation Scopes

```text
COMPONENT
APPLICATION
PROCESS
JOURNEY
DOMAIN
ENTERPRISE
```

---

# 33. Outcome Cascade

Une Initiative peut produire plusieurs Outcomes.

```text
Initiative
├── Technical Outcome
├── Process Outcome
├── Employee Outcome
├── Customer Outcome
└── Financial Outcome
```

---

# 34. Learning

## 34.1 Définition

Un Learning est une connaissance généralisable issue d’une expérience observée.

Ce n’est pas simplement :

> résultat = -11 %.

Un bon Learning exprime :

> ce que cette expérience nous apprend.

---

# 35. Learning Example

Outcome :

```text
manual work +4%
```

Learning :

> « La suppression de la validation X réduit le délai client, mais transfère une partie du contrôle vers les opérations lorsque l’automatisation Y n’est pas activée. »

---

# 36. Learning Structure

```yaml
Learning:
  id:
  source_initiative_ref:
  outcome_refs:
  statement:
  learning_type:
  scope:
  applicable_conditions:
  exceptions:
  confidence:
  evidence_refs:
  related_claim_refs:
  created_at:
```

---

# 37. Learning Types

```text
CAUSAL
OPERATIONAL
ARCHITECTURAL
PROCESS
CUSTOMER
EMPLOYEE
FINANCIAL
RISK
TRANSFORMATION
DECISION_PATTERN
```

---

# 38. Learning vs Claim

Un Learning représente une leçon issue d’une expérience.

Un Claim représente une affirmation sur l’entreprise.

Un Learning peut produire ou renforcer un Claim.

---

# 39. Learning Promotion

```text
Outcome
↓
Learning Candidate
↓
Evidence Validation
↓
Historical Comparison
↓
Learning
↓
Claim Proposal
```

---

# 40. Learning Candidate

Le système ne doit pas généraliser à partir d’un seul résultat faible.

---

# 41. Generalization Gate

Pour devenir Learning généralisable, considérer :

- attribution ;
- répétition ;
- conditions ;
- evidence strength ;
- similar historical cases.

---

# 42. Single-case Learning

Peut rester :

```text
CASE_SPECIFIC
```

---

# 43. Repeated Learning

Après plusieurs confirmations :

```text
REUSABLE
```

---

# 44. Institutional Learning

Un Learning très mature peut devenir une connaissance organisationnelle importante.

Exemple :

> « Les migrations de ce type échouent lorsqu’un consommateur batch historique n’est pas identifié avant le cutover. »

---

# 45. Learning Maturity

```text
L0 OBSERVED
L1 CASE_SPECIFIC
L2 REPEATED
L3 CROSS_VALIDATED
L4 INSTITUTIONAL
```

---

# 46. Learning confidence

Distincte de maturity.

---

# 47. Learning Scope

Un Learning n’est pas universel.

Exemple :

```text
valid for:
legacy batch applications
in mortgage domain
under high manual validation
```

---

# 48. Applicable Conditions

```yaml
ApplicableConditions:
  domain:
  architecture_pattern:
  process_pattern:
  scale:
  geography:
  customer_segment:
```

---

# 49. Exceptions

Les exceptions doivent être conservées.

---

# 50. Learning Store

Le Learning Store doit permettre :

- recherche sémantique ;
- recherche par pattern ;
- recherche par domaine ;
- temporalité ;
- provenance.

---

# 51. Transformation Memory

L’ensemble :

```text
Situation
Investigation
Decision
Initiative
Outcome
Learning
```

constitue la **mémoire de transformation** de Méridian.

---

# 52. Transformation Episode

Concept utile :

```yaml
TransformationEpisode:
  trigger_ref:
  investigation_ref:
  decision_ref:
  initiative_ref:
  outcome_refs:
  learning_refs:
```

---

# 53. Pourquoi un Episode

Permet de répondre :

> Qu’est-ce qui s’est passé de bout en bout ?

sans reconstruire manuellement dix objets.

---

# 54. Historical Pattern

Plusieurs Transformation Episodes similaires peuvent former un pattern.

---

# 55. Example Pattern

```text
legacy retirement
+
undocumented consumers
+
late migration issue
```

observé dans plusieurs transformations.

---

# 56. Pattern object

```yaml
TransformationPattern:
  id:
  episode_refs:
  pattern:
  conditions:
  common_risks:
  recurring_effects:
  confidence:
```

---

# 57. Decision Pattern

Exemple :

> Les décisions de consolidation rapides réduisent les coûts mais déplacent régulièrement la charge vers les opérations.

---

# 58. Pattern Discovery

Pipeline :

```text
Episodes
↓
Similarity
↓
Clustering
↓
Expert interpretation
↓
Pattern candidate
↓
Validation
```

---

# 59. Pattern must remain evidence-backed

Un clustering statistique n’est pas automatiquement un Learning.

---

# 60. Memory Retrieval

Lors d’une nouvelle Situation :

```text
Current Situation
↓
Transformation Memory Search
↓
Similar Episodes
↓
Relevant Learnings
↓
Investigation Context
```

---

# 61. Example

Flore peut dire :

> « Nous avons rencontré deux configurations similaires. Dans les deux cas, le consommateur batch a été identifié tardivement. »

---

# 62. Historical Reuse

Une ancienne décision peut être :

```text
RELEVANT
PARTIALLY_RELEVANT
NOT_APPLICABLE
```

---

# 63. No copy-paste decision

Méridian ne doit jamais conclure :

> cela a fonctionné avant, donc faisons la même chose.

Il doit comparer les conditions.

---

# 64. Counterfactual Learning

Question :

> Que se serait-il probablement passé si nous n’avions rien fait ?

Peut aider à évaluer la vraie valeur de la décision.

---

# 65. Counterfactual confidence

Toujours afficher une incertitude forte.

---

# 66. Learning Feedback into Claims

Exemple :

```text
Learning:
validation removal increases operations load
```

peut proposer :

```text
Claim:
Process X CREATES_MANUAL_WORK in Team Y under condition Z
```

---

# 67. Learning Feedback into Signals

Un Learning peut définir un nouveau pattern de détection.

Exemple :

> surveiller l’augmentation de reprises manuelles après ce type de changement.

---

# 68. Learning Feedback into Opportunity Discovery

Un Learning peut améliorer :

- pattern de rationalisation ;
- pattern d’automatisation ;
- pattern de friction.

---

# 69. Learning Feedback into Expert Selection

Exemple :

Les transformations de type X impliquent presque toujours l’Expert Processus.

Le selector peut utiliser cette expérience.

---

# 70. Learning Feedback into Scenario Generation

Les scénarios futurs peuvent inclure :

> cette option a historiquement créé un effet secondaire Y.

---

# 71. Learning Feedback into Risk

Un pattern historique peut augmenter le risque estimé.

---

# 72. Learning Feedback into Maturity

Une Situation ressemblant à un pattern historique peut mûrir plus rapidement.

Mais le Learning reste un prior, pas une preuve du cas courant.

---

# 73. Observe after action

Le moteur doit continuer d’observer après déploiement.

Fenêtres possibles :

```text
T+1h
T+1d
T+7d
T+30d
T+90d
```

selon l’initiative.

---

# 74. Multi-horizon Outcomes

Une décision peut être positive à court terme mais négative à long terme.

---

# 75. Example

```text
T+7 days:
performance +20%

T+90 days:
maintenance incidents +35%
```

---

# 76. Outcome Timeline

```text
Expected
↓
Early Result
↓
Stabilized Result
↓
Long-term Result
```

---

# 77. Outcome Stability

Statuts :

```text
EARLY
EMERGING
STABLE
REGRESSING
```

---

# 78. Review Date

Toute décision importante doit posséder une date de revue.

---

# 79. Automatic Review Trigger

La revue peut être déclenchée si :

- métrique hors tolérance ;
- risque augmente ;
- hypothèse devient fausse ;
- effet secondaire critique ;
- nouvelle contradiction.

---

# 80. Decision Review

Une revue peut conclure :

```text
KEEP
ADJUST
EXPAND
ROLLBACK
REINVESTIGATE
SUPERSEDE_DECISION
```

---

# 81. Closed-loop Decision

La boucle complète :

```text
Decision
↓
Observe
↓
Review
↓
Adjust
```

---

# 82. Initiative Adaptation

Une Initiative peut évoluer sans nouvelle décision stratégique si l’ajustement est dans le cadre autorisé.

---

# 83. Material Change

Un changement majeur exige une nouvelle Decision.

---

# 84. Outcome-driven Signal

Un résultat inattendu crée :

```text
Signal
```

et peut redémarrer le Discovery Engine.

---

# 85. Outcome-driven Opportunity

Exemple :

```text
manual rework +4%
```

→ nouvelle opportunité d’automatisation.

---

# 86. Outcome-driven Risk

Exemple :

```text
error rate improved
but fraud review decreased
```

→ nouveau Risk.

---

# 87. Improvement Loop

```text
Improvement A
↓
Outcome
↓
Side Effect
↓
Opportunity B
↓
Improvement B
```

C’est la nature vivante de Méridian.

---

# 88. Improvement Portfolio

Le produit peut montrer :

- initiatives en observation ;
- résultats positifs ;
- résultats négatifs ;
- apprentissages récents ;
- nouvelles opportunités issues des résultats.

---

# 89. Surface « En amélioration »

Dans Aujourd’hui :

```text
En amélioration

Initiative X
Expected -15%
Observed -11%
Status: positive, watch manual rework

Initiative Y
No measurable effect yet
```

---

# 90. Surface « Ce que nous avons appris »

Exemples :

> 3 apprentissages nouveaux cette semaine.

---

# 91. Initiative page

Sections :

```text
Decision
Plan
Affected area
Expected outcomes
Observed outcomes
Side effects
Learnings
Timeline
```

---

# 92. Outcome card

```text
Metric
Expected
Observed
Confidence
Trend
Attribution
```

---

# 93. Learning card

```text
What we learned
Where it applies
Confidence
Evidence
Related episodes
```

---

# 94. Flore interactions

Questions :

> Notre décision a-t-elle réellement amélioré la situation ?

> Quels effets inattendus sont apparus ?

> Avons-nous déjà vécu cela ?

> Qu’est-ce qui a fonctionné lors des transformations similaires ?

> Cette initiative produit-elle toujours de la valeur ?

---

# 95. Flore recommendation

Flore peut dire :

> « Le résultat principal est positif, mais un effet secondaire opérationnel mérite une nouvelle investigation. »

---

# 96. Flore and uncertainty

Exemple :

> « L’amélioration est visible, mais l’attribution à l’initiative reste moyenne car un autre changement a été déployé dans la même période. »

---

# 97. Outcome Explanation

Chaque Outcome doit pouvoir exposer :

```text
baseline
observed
comparison
confounders
evidence
confidence
```

---

# 98. Learning Explanation

Chaque Learning doit pouvoir exposer :

```text
episodes
outcomes
conditions
exceptions
evidence
```

---

# 99. Value Realization

Méridian doit pouvoir mesurer la valeur réalisée.

Pas seulement :

> valeur estimée.

---

# 100. Value dimensions

```text
financial
time
risk
customer
employee
resilience
quality
strategic
```

---

# 101. Financial Value

Exemples :

```text
cost avoided
infrastructure reduced
manual hours saved
revenue protected
```

---

# 102. Customer Value

```text
wait reduction
abandon reduction
conversion increase
complaint reduction
```

---

# 103. Employee Value

```text
manual steps reduced
rework reduced
tool switching reduced
```

---

# 104. Risk Value

```text
probability reduced
exposure reduced
recovery improved
```

---

# 105. Value Confidence

La valeur réalisée possède elle-même un niveau de confiance.

---

# 106. Cost of Initiative

Peut être importé depuis :

- portfolio ;
- finance ;
- effort ;
- cloud costs.

---

# 107. Realized ROI

Conceptuellement :

```text
realized value
/
actual cost
```

Mais éviter la fausse précision si les données sont faibles.

---

# 108. Strategic Value

Certaines initiatives produisent une valeur difficilement monétaire.

Exemples :

- réduction de dépendance legacy ;
- simplification ;
- augmentation de résilience ;
- amélioration de connaissance.

---

# 109. Improvement Scorecard

```text
Expected
Observed
Confidence
Value
Cost
Side Effects
Learning
```

---

# 110. Initiative Portfolio Intelligence

Méridian peut détecter :

- initiatives redondantes ;
- transformations concurrentes ;
- dépendances ;
- effets qui se neutralisent.

---

# 111. Cross-Initiative Effect

Deux initiatives peuvent affecter la même métrique.

---

# 112. Initiative Conflict

Exemple :

```text
Initiative A optimizes cost
Initiative B increases redundancy for resilience
```

Les objectifs peuvent être légitimement opposés.

---

# 113. Transformation Graph

Relations :

```text
Decision
INITIATES
Initiative

Initiative
AFFECTS
Twin / Process / Journey

Initiative
PRODUCES
Outcome

Outcome
SUPPORTS
Learning
```

---

# 114. Learning Graph

```text
Learning
APPLIES_TO
Domain

Learning
DERIVED_FROM
Episode

Learning
SUPPORTS
Future Scenario
```

---

# 115. Transformation Memory Graph

Permet des requêtes comme :

> Quelles transformations de legacy ont échoué pour des raisons de dépendances cachées ?

---

# 116. Historical Queries

```text
similar decisions
similar outcomes
repeated side effects
recurrent assumptions
```

---

# 117. Decision Outcome Correlation

À terme, Méridian peut apprendre :

> quels types de décisions fonctionnent mieux dans quelles conditions.

---

# 118. No autonomous policy optimization initially

Le système peut recommander :

> cette policy semble trop permissive.

Mais l’humain valide les changements.

---

# 119. Learning Governance

Certains Learnings peuvent avoir un impact stratégique.

Ils doivent pouvoir être :

```text
DRAFT
REVIEWED
APPROVED
INSTITUTIONAL
DEPRECATED
```

---

# 120. Learning Review

Experts humains ou domaine peuvent valider.

---

# 121. Conflicting Learnings

Deux Learnings peuvent être contradictoires.

Exemple :

```text
Case A:
centralization improved latency

Case B:
centralization reduced resilience
```

Méridian doit conserver les conditions.

---

# 122. Learning Reconciliation

Comparer :

- scope ;
- architecture ;
- scale ;
- context ;
- time.

---

# 123. Institutional Memory ≠ best practice catalog

Une Best Practice est générique.

La mémoire Méridian est issue de l’expérience réelle de l’entreprise.

---

# 124. Experience Capital

Concept produit :

> **Méridian transforme les transformations passées en capital d’expérience exploitable.**

---

# 125. Forgetting

Le système doit aussi savoir qu’un Learning peut devenir obsolète.

---

# 126. Learning Decay

Exemple :

Un Learning sur une architecture legacy peut perdre sa pertinence après migration.

---

# 127. Learning validity

```text
valid_from
valid_to
last_confirmed_at
```

---

# 128. Learning Challenge

Un nouvel Outcome peut contester un Learning ancien.

---

# 129. Transformation contradiction

Exemple :

> Une stratégie qui fonctionnait auparavant ne fonctionne plus.

Cela peut signaler un changement structurel de l’entreprise.

---

# 130. Improvement Event Model

```text
InitiativeStarted
InitiativeChanged
ObservationWindowOpened
OutcomeObserved
OutcomeStabilized
UnexpectedEffectDetected
LearningCandidateCreated
LearningCreated
LearningStrengthened
LearningContested
DecisionReviewRequested
```

---

# 131. Event Example

```yaml
event_type: UnexpectedEffectDetected
initiative_id: INI-44
metric: MANUAL_REWORK
expected: 0
observed: +4%
severity: MEDIUM
```

---

# 132. Technical Components

```text
Initiative Service
Observation Plan Service
Outcome Collector
Outcome Evaluator
Attribution Engine
Side Effect Detector
Learning Engine
Transformation Memory Service
Decision Review Service
Value Realization Service
```

---

# 133. Outcome Collector

Connecte les métriques et événements définis dans le plan d’observation.

---

# 134. Outcome Evaluator

Calcule :

- baseline ;
- delta ;
- confidence ;
- stability ;
- attribution.

---

# 135. Attribution Engine

Peut combiner :

```text
statistics
change timeline
graph context
control group
expert analysis
```

---

# 136. Side Effect Detector

Réutilise le Discovery Engine autour du scope impacté.

---

# 137. Learning Engine

Transforme :

```text
Outcome + Context + Decision + Hypotheses
```

en Learning Candidate.

---

# 138. Transformation Memory Service

Expose :

```text
find_similar_episodes
find_related_learnings
find_decision_history
find_repeated_side_effects
```

---

# 139. Decision Review Service

Gère :

```text
review dates
review triggers
review outcomes
```

---

# 140. Value Realization Service

Agrège :

- valeur attendue ;
- valeur observée ;
- coûts ;
- confiance.

---

# 141. Stores

Autoritatif :

```text
PostgreSQL / Aurora
```

Evidence :

```text
S3
```

Search :

```text
OpenSearch
```

Relationships :

```text
Graph
```

---

# 142. Time-series integration

Les Outcomes peuvent dépendre de :

- Datadog ;
- observability ;
- business KPIs ;
- process metrics ;
- CRM analytics.

---

# 143. Event-driven evaluation

Exemple :

```text
MetricChanged
↓
Outcome Collector
↓
Outcome Evaluator
```

---

# 144. Scheduled evaluation

Certaines métriques sont évaluées quotidiennement ou mensuellement.

---

# 145. Hybrid evaluation

La plupart des initiatives utilisent événementiel + périodique.

---

# 146. Observation windows

Éviter de conclure trop tôt.

Exemple :

```text
early window
stabilization window
long-term window
```

---

# 147. Statistical significance

À utiliser lorsqu’elle est pertinente.

Mais la décision ne doit pas dépendre d’une sophistication statistique inutile.

---

# 148. Practical significance

Un changement statistiquement significatif peut être insignifiant métier.

---

# 149. Business Threshold

Exemple :

```text
-0.2 sec
```

peut être statistiquement réel mais sans valeur business.

---

# 150. Outcome policy

Chaque type d’initiative peut définir :

- métriques ;
- fenêtres ;
- seuils ;
- required confidence.

---

# 151. Observation Policy Registry

```yaml
ObservationPolicy:
  initiative_type:
  default_metrics:
  evaluation_windows:
  required_side_effect_scopes:
  review_policy:
```

---

# 152. Policy versioning

Conserver la version appliquée.

---

# 153. Outcome Staleness

Un Outcome peut devenir ancien.

Mais reste historique.

---

# 154. Continuous Outcomes

Certaines initiatives continuent de produire des résultats.

Exemple :

- coût cloud ;
- latence ;
- satisfaction.

---

# 155. Persistent Monitoring

Après la phase officielle d’observation, certaines métriques peuvent rester surveillées à plus faible fréquence.

---

# 156. Regression Detection

Une amélioration peut régresser.

```text
Outcome positive
↓
3 months later
metric returns to baseline
```

Méridian doit le voir.

---

# 157. Improvement Durability

Nouvelle dimension :

> le bénéfice est-il durable ?

---

# 158. Durability Score

Peut considérer :

- durée ;
- stabilité ;
- régression ;
- dépendance à des actions manuelles.

---

# 159. Outcome portfolio

Méridian peut montrer :

```text
sustainable improvements
temporary improvements
regressions
unmeasured decisions
```

---

# 160. Unmeasured Decisions

Signal important :

> décision importante sans résultat mesuré.

---

# 161. Measurement Debt

Concept :

> **dette de mesure**.

Une organisation prend des décisions mais ne sait pas si elles fonctionnent.

Méridian peut la rendre visible.

---

# 162. Measurement Debt Metrics

```text
decisions without observation plan
initiatives without baseline
expected outcomes without observed outcome
```

---

# 163. Learning Debt

Même concept.

```text
completed initiatives
without learning review
```

---

# 164. Transformation Debt

Peut inclure :

- décisions non revues ;
- outcomes non mesurés ;
- Learnings non consolidés.

---

# 165. Product Opportunity

Cette dette peut elle-même devenir une Opportunity.

---

# 166. Decision Quality Feedback

Méridian peut progressivement mesurer :

- hypothèses souvent fausses ;
- risques sous-estimés ;
- scénarios surestimés.

---

# 167. No scoring of individual decision-makers

Le système évalue les décisions et patterns, pas les personnes.

---

# 168. Organizational Learning

L’objectif est :

> améliorer le système de décision.

Pas noter les individus.

---

# 169. Example — TBT retirement

## Decision

Décomposer TBT progressivement.

## Expected

```text
legacy dependency -40%
incident exposure -20%
migration risk medium
```

## Outcome

```text
legacy dependency -36%
incident exposure -18%
unknown batch consumers discovered
```

## Learning

> Les consommateurs batch historiques doivent être cartographiés avant la première phase de décomposition.

---

# 170. Example — Process optimization

## Decision

Supprimer une validation.

## Expected

```text
duration -15%
```

## Observed

```text
duration -11%
manual rework +4%
```

## Learning

> La validation peut être retirée seulement si l’étape d’automatisation Y est active.

---

# 171. Example — Cloud migration

## Expected

```text
availability +0.2%
cost -10%
```

## Observed

```text
availability +0.18%
cost +6%
```

## Learning

> La résilience s’est améliorée, mais le dimensionnement initial sur-provisionne la plateforme.

→ Opportunity FinOps.

---

# 172. Example — Customer journey

## Expected

```text
abandon -8%
```

## Observed

```text
abandon -5%
calls +12%
```

Learning :

> La simplification du parcours déplace les demandes explicatives vers le centre de contact.

---

# 173. Learning to new Opportunity

```text
call volume +12%
↓
Opportunity:
proactive explanation / automation
```

---

# 174. Improvement Chain

```text
Opportunity A
↓
Decision A
↓
Outcome A
↓
Learning A
↓
Opportunity B
↓
Decision B
```

---

# 175. Transformation Story

Méridian doit pouvoir raconter :

> D’où sommes-nous partis ?
>
> Qu’avons-nous compris ?
>
> Qu’avons-nous décidé ?
>
> Qu’avons-nous changé ?
>
> Qu’est-ce qui s’est réellement produit ?
>
> Qu’avons-nous appris ?

---

# 176. Transformation Story UI

Une timeline :

```text
Jan 12 — Situation
Jan 18 — Investigation
Jan 24 — Decision
Feb 10 — Deployment
Mar 10 — Outcome
Mar 15 — Learning
```

---

# 177. Executive View

Pour décideur :

```text
Decision
Value expected
Value realized
Unexpected effects
Learning
Next opportunity
```

---

# 178. Operational View

Pour équipes :

```text
metrics
signals
side effects
timeline
```

---

# 179. Architecture View

```text
affected twins
relations changed
dependency evolution
```

---

# 180. Learning View

```text
patterns
similar episodes
reuse
```

---

# 181. APIs — Initiative

```text
POST /initiatives
GET /initiatives/{id}
POST /initiatives/{id}/start-observation
```

---

# 182. APIs — Outcome

```text
GET /initiatives/{id}/outcomes
POST /initiatives/{id}/outcomes
GET /outcomes/{id}/explain
```

---

# 183. APIs — Learning

```text
GET /learnings
GET /learnings/{id}
POST /learnings/{id}/review
GET /learnings/similar
```

---

# 184. APIs — Transformation Memory

```text
GET /transformation-episodes
GET /transformation-episodes/{id}
POST /transformation-memory/search
```

---

# 185. APIs — Decision Review

```text
POST /decisions/{id}/review
GET /decisions/{id}/review-status
```

---

# 186. Security

Outcome et Learning héritent de la sensibilité des données utilisées.

---

# 187. Aggregated Learning

Un Learning peut parfois être partagé plus largement s’il ne révèle pas la donnée sensible sous-jacente.

---

# 188. Security review

La politique de dérivation doit valider cela.

---

# 189. Audit

Pour chaque Learning :

```text
decision
initiative
outcomes
evidence
author/agent
review
```

---

# 190. Reproducibility

Un Learning institutionnel doit être reconstruisible.

---

# 191. Observability

Métriques système :

```text
initiatives observing
outcomes collected
evaluation failures
side effects detected
learning candidates
learnings approved
```

---

# 192. Product metrics

```text
% decisions with observation plan
% initiatives with measurable outcomes
% outcomes producing learnings
% learnings reused
% unexpected effects detected
```

---

# 193. Time to Learning

Mesure :

```text
decision
→ validated learning
```

---

# 194. Learning Reuse Rate

Combien d’investigations futures utilisent des Learnings historiques.

---

# 195. Transformation Memory Coverage

Pourcentage des décisions importantes possédant :

```text
decision
+ outcome
+ learning
```

---

# 196. Realized Value Coverage

Combien de décisions ont une valeur réelle mesurée.

---

# 197. Improvement Velocity

Concept :

```text
Opportunity
→ Decision
→ Measured Improvement
```

---

# 198. Avoid vanity metrics

Ne pas mesurer :

- nombre de Learnings générés ;
- nombre d’Outcomes collectés ;

sans mesurer leur utilité.

---

# 199. Evaluation of Learning Engine

Golden cases :

- outcome positif avec side effect ;
- résultat non attribuable ;
- résultat contradictoire ;
- pattern récurrent.

---

# 200. Learning Precision

Un Learning proposé doit être réellement supporté.

---

# 201. Learning Overgeneralization Rate

Mesure critique.

Le système ne doit pas généraliser trop vite.

---

# 202. Historical Replay

Rejouer des transformations anciennes.

Question :

> Méridian aurait-il produit un Learning utile ?

---

# 203. MVP

Le MVP Continuous Improvement doit supporter :

```text
Decision
Initiative
Expected Outcome
Observation Plan
Outcome
Expected vs Observed
Learning
New Signal / Opportunity
```

---

# 204. MVP observation

Commencer avec des métriques simples :

- latency ;
- error ;
- cost ;
- process duration ;
- manual work.

---

# 205. MVP attribution

Simple :

```text
baseline
time window
known concurrent changes
expert interpretation
```

---

# 206. MVP side-effect detection

Autour du scope direct et des voisins du Mesh.

---

# 207. MVP Learning

Structure simple :

```text
what happened
why we think it happened
where it applies
confidence
```

---

# 208. MVP use case

Process optimization :

```text
expected duration -15%
observed -11%
manual work +4%
↓
Learning
↓
New Opportunity
```

Ce use case démontre toute la boucle.

---

# 209. Phase 2

Ajouter :

- Transformation Episodes ;
- similar case retrieval ;
- value realization ;
- review triggers ;
- richer side effects.

---

# 210. Phase 3

Ajouter :

- pattern discovery ;
- counterfactual analysis ;
- decision quality feedback ;
- predictive transformation memory.

---

# 211. Anti-patterns

## Decision ends the workflow

Pas d’apprentissage.

## Outcome without baseline

Comparaison faible.

## Metric equals value

Réduction abusive.

## Correlation equals attribution

Conclusion fausse.

## Ignore side effects

Optimisation locale.

## Learning as free text

Difficile à réutiliser.

## Generalize one case

Fausse règle.

## No conditions

Learning hors contexte.

## Person scoring

Mauvaise cible.

## Auto-modify governance

Risque.

---

# 212. Critères de succès

Le modèle est réussi si :

1. chaque décision importante peut définir ce qu’elle espère améliorer ;
2. Méridian continue d’observer après l’action ;
3. expected et observed sont distincts ;
4. les effets secondaires peuvent générer de nouveaux Signals ;
5. les optimisations locales sont comparées au système global ;
6. les Learnings conservent leur contexte ;
7. les expériences passées peuvent être retrouvées ;
8. les nouvelles investigations exploitent les Learnings sans les prendre pour vérité ;
9. les décisions sans mesure deviennent visibles ;
10. la boucle redémarre après chaque résultat significatif.

---

# 213. Architecture cible synthétique

```text
                     DECISION
                        │
                        ▼
                    INITIATIVE
                        │
                        ▼
                OBSERVATION PLAN
                        │
                        ▼
                 OUTCOME COLLECTOR
                        │
                        ▼
                 OUTCOME EVALUATOR
             ┌──────────┼──────────┐
             ▼          ▼          ▼
         BASELINE   CONFOUNDERS   SIDE EFFECTS
             │          │          │
             └──────────┴──────────┘
                        │
                        ▼
               EXPECTED vs OBSERVED
                        │
                        ▼
                 LEARNING ENGINE
                        │
             ┌──────────┼────────────┐
             ▼          ▼            ▼
          CLAIMS      SIGNALS      PATTERNS
             │          │            │
             └──────────┴────────────┘
                        │
                        ▼
             TRANSFORMATION MEMORY
                        │
                        ▼
                 FUTURE DISCOVERY
```

---

# 214. Vision cible

À terme, Méridian ne connaît pas seulement :

> **l’état de l’entreprise.**

Il connaît également :

> **son expérience.**

Il peut répondre :

> « Nous avons déjà rencontré cette configuration. »

> « Voici ce que nous avions décidé. »

> « Voici ce que nous pensions qu’il se passerait. »

> « Voici ce qui s’est réellement passé. »

> « Voici l’effet que personne n’avait anticipé. »

> « Voici ce que cette expérience nous a appris. »

> « Voici pourquoi cette expérience est — ou n’est pas — applicable aujourd’hui. »

Cette capacité constitue une différence majeure.

---

# 215. Conclusion

Le Continuous Improvement & Learning Model ferme la boucle de Méridian.

La logique complète devient :

```text
Découvrir
↓
Comprendre
↓
Exprimer
↓
Investiguer
↓
Décider
↓
Agir
↓
Mesurer
↓
Apprendre
↓
Redécouvrir
```

Le système n’est plus seulement capable de répondre :

> **Que devrions-nous faire ?**

Il devient capable de répondre :

> **Ce que nous avons fait a-t-il réellement fonctionné ?**

Puis :

> **Qu’est-ce que cette expérience doit changer dans notre manière de comprendre et de décider la prochaine fois ?**

C’est à ce moment que Méridian devient véritablement un système d’intelligence vivante de l’entreprise.

---

# 216. Prochain document

Le prochain document recommandé est :

> **MÉRIDIAN — UX & Interaction Design Specification**

Il devra transformer tout le modèle conceptuel en expérience utilisateur concrète :

- Aujourd’hui ;
- Atlas ;
- Flore ;
- Radar ;
- Opportunities ;
- Investigations ;
- Twin pages ;
- Decision Board ;
- Transformation Memory ;
- navigation ;
- drill-down ;
- evidence experience ;
- progressive results ;
- temporal navigation ;
- collaboration.

Ce sera le document qui rendra l’ensemble de la vision **visible et utilisable**.
