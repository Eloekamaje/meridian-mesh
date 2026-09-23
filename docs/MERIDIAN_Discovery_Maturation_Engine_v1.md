# MÉRIDIAN — Discovery & Maturation Engine
## Détection, corrélation, maturation, émergence et priorisation des phénomènes significatifs

**Statut :** Architecture fonctionnelle et technique de référence  
**Version :** 1.0  
**Produit :** MÉRIDIAN  
**Tagline :** **DÉCOUVRIR · COMPRENDRE · DÉCIDER**

---

# 0. Objet du document

Ce document définit le moteur qui permet à Méridian de passer :

```text
Observation
↓
Signal
↓
Situation candidate
↓
Maturation
↓
Expression
↓
Opportunity / Risk / Investigation
```

Il répond à la question :

> **Comment Méridian distingue-t-il ce qui se passe de ce qui compte réellement ?**

Ce moteur est central.

Sans lui, Méridian devient :

- une plateforme de monitoring ;
- un moteur d’alertes ;
- une collection de règles ;
- une accumulation de signaux sans hiérarchie.

Avec lui, Méridian peut :

- observer ;
- corréler ;
- accumuler des preuves ;
- détecter des patterns ;
- faire mûrir une compréhension ;
- retarder volontairement une conclusion ;
- exprimer une opportunité ou un risque au bon moment.

Le moteur doit être construit pour :

- minimiser le bruit ;
- rendre la maturation explicable ;
- intégrer la temporalité ;
- distinguer nouveauté et répétition ;
- gérer l’incertitude ;
- combiner règles, statistiques, graphes et agents ;
- rester contrôlable par l’humain.

---

# 1. Principe fondamental

Méridian ne doit jamais faire :

```text
Observation
→ Alert
```

par défaut.

Le pipeline cible est :

```text
Observation
↓
Signal
↓
Candidate Situation
↓
Correlation
↓
Maturation
↓
Interpretation
↓
Expression
```

Le système doit toujours se demander :

> **Est-ce nouveau ?**
>
> **Est-ce significatif ?**
>
> **Est-ce durable ?**
>
> **Est-ce corroboré ?**
>
> **Est-ce explicable ?**
>
> **Est-ce actionnable ?**

---

# 2. Le rôle du moteur

Le Discovery & Maturation Engine a six responsabilités.

## 2.1 Détecter

Identifier des changements potentiellement significatifs.

## 2.2 Regrouper

Éviter que plusieurs signaux proches deviennent plusieurs alertes.

## 2.3 Corréler

Relier les faits par temps, topologie, processus ou contexte.

## 2.4 Maturer

Accumuler des preuves sans conclure trop tôt.

## 2.5 Interpréter

Donner du sens à la situation.

## 2.6 Prioriser

Déterminer si l’humain doit être sollicité.

---

# 3. Architecture conceptuelle

```text
SOURCES / TWINS / MESH
         │
         ▼
   OBSERVATION BUS
         │
         ▼
   SIGNAL DETECTORS
         │
         ▼
 SIGNAL NORMALIZATION
         │
         ▼
  DEDUP / FINGERPRINT
         │
         ▼
 SITUATION CORRELATOR
         │
         ▼
   MATURITY ENGINE
         │
         ├── Evidence
         ├── History
         ├── Topology
         ├── Claims
         ├── Contradictions
         └── Expert checks
         │
         ▼
 INTERPRETATION ENGINE
         │
         ▼
   EXPRESSION ENGINE
         │
    ┌────┼─────┬──────────┐
    ▼    ▼     ▼          ▼
Opportunity  Risk   Investigation  Observe
```

---

# 4. Observation

Une Observation est un fait.

Exemples :

```text
latency p95 increased
commit merged
new dependency detected
manual action count increased
ticket volume increased
business rule changed
customer abandonment increased
```

Une Observation n’a pas nécessairement d’importance.

---

# 5. Signal

Un Signal est une Observation évaluée comme potentiellement significative.

Exemple :

```yaml
Signal:
  id:
  type:
  entity_refs:
  metric:
  baseline:
  current_value:
  deviation:
  confidence:
  first_seen:
  last_seen:
  source_refs:
  fingerprint:
  severity_hint:
```

---

# 6. Catégories de Signals

## 6.1 Technique

```text
performance
error
availability
dependency
capacity
security
configuration
deployment
```

## 6.2 Structurel

```text
new relation
missing relation
domain drift
ownership drift
architecture drift
```

## 6.3 Métier

```text
volume change
process delay
rule change
exception increase
drop-off
conversion change
```

## 6.4 Organisationnel

```text
manual work increase
rework
team dependency
handoff increase
```

## 6.5 Client

```text
abandonment
wait time
complaint pattern
journey degradation
```

---

# 7. Détecteurs

Un détecteur doit être spécialisé.

Types :

```text
Threshold Detector
Baseline Deviation Detector
Trend Detector
Change Detector
Graph Change Detector
Pattern Detector
Business Rule Detector
Human Report Detector
LLM-assisted Detector
```

---

# 8. Détection déterministe

À privilégier lorsque possible.

Exemples :

```text
error rate > threshold
new edge in graph
claim invalidated
deployment after incident
```

Avantages :

- explicable ;
- reproductible ;
- rapide ;
- peu coûteux.

---

# 9. Détection statistique

Utilisée pour :

- dérives ;
- ruptures ;
- saisonnalité ;
- anomalies multivariées ;
- tendances faibles.

Exemples :

```text
rolling z-score
EWMA
change point
seasonal baseline
trend regression
```

---

# 10. Détection agentique

Le LLM intervient lorsqu’il faut interpréter des combinaisons complexes.

Exemple :

```text
new Jira theme
+ repeated support issue
+ code change
```

Le LLM peut proposer :

> « ces éléments pourraient appartenir à la même évolution fonctionnelle »

mais cela reste une hypothèse.

---

# 11. Signal Normalization

Tous les signaux doivent être transformés dans un format commun.

```yaml
NormalizedSignal:
  type:
  subject_ref:
  temporal_window:
  magnitude:
  direction:
  source:
  evidence_refs:
  confidence:
  semantic_tags:
```

---

# 12. Fingerprint

Le Fingerprint sert à dédupliquer.

Exemple :

```text
hash(
  signal_type
  entity
  metric
  time_bucket
  semantic_context
)
```

---

# 13. Dédoublonnage

Le moteur doit éviter :

```text
1 incident
→ 75 signaux
→ 75 cartes
```

Il regroupe les signaux proches selon :

- même entité ;
- même cause probable ;
- même fenêtre temporelle ;
- même pattern ;
- même graphe d’impact.

---

# 14. Situation Candidate

Une Situation Candidate est un ensemble de signaux qui pourraient appartenir au même phénomène.

```yaml
SituationCandidate:
  id:
  title:
  signal_refs:
  entity_refs:
  temporal_window:
  graph_scope:
  similarity_score:
  correlation_score:
  status:
```

---

# 15. Corrélation temporelle

Exemple :

```text
14:01 deployment
14:06 latency increase
14:10 retries increase
14:14 support tickets
```

La proximité temporelle est un indice, pas une preuve de causalité.

---

# 16. Corrélation topologique

Utiliser le Mesh.

Exemple :

```text
A → B → C
```

Si A change et C dégrade, B peut être une piste.

---

# 17. Corrélation processus

Plus importante encore dans la vision complète de Méridian.

Exemple :

```text
step 1
→ service A
→ manual validation
→ service B
→ customer result
```

Plusieurs signaux peuvent être corrélés car ils appartiennent au même processus.

---

# 18. Corrélation par changement commun

Exemple :

```text
Commit X
affects A
affects B
affects C
```

Les signaux A/B/C peuvent être regroupés.

---

# 19. Corrélation sémantique

Utiliser embeddings ou LLM pour détecter :

```text
tickets parlant de "validation lente"
+
documents parlant de "nouvelle validation"
```

---

# 20. Correlation Score

Score conceptuel :

```text
temporal proximity
+ topology proximity
+ shared change
+ semantic similarity
+ same process
+ same population
```

---

# 21. Situation lifecycle

```text
CANDIDATE
↓
QUALIFYING
↓
MATURING
↓
MATURE
```

Branches :

```text
DISMISSED
MERGED
SPLIT
ARCHIVED
```

---

# 22. Qualification

La qualification répond :

> Est-ce suffisamment cohérent pour continuer ?

Critères :

- plusieurs signaux ;
- importance minimale ;
- relation plausible ;
- pas de bruit connu ;
- scope identifiable.

---

# 23. Situation Split

Une Situation peut être divisée.

Exemple :

```text
Situation candidate:
payment errors + customer calls
```

Puis découverte :

```text
payment errors → incident A
customer calls → unrelated campaign
```

La Situation est scindée.

---

# 24. Situation Merge

Deux Situations peuvent être fusionnées si un lien fort apparaît.

---

# 25. Maturation

La maturation consiste à laisser une Situation accumuler suffisamment de connaissance.

Elle ne signifie pas seulement :

> attendre.

Elle signifie :

- collecter ;
- confronter ;
- recalculer ;
- chercher ;
- mesurer ;
- tester.

---

# 26. Inputs de maturation

```text
Signals
Claims
Evidence
Relationships
Historical cases
Changes
Unknowns
Contradictions
Expert Contributions
Human Feedback
```

---

# 27. Maturity Dimensions

La maturité doit être multi-dimensionnelle.

## 27.1 Evidence maturity

Avons-nous suffisamment de preuves ?

## 27.2 Structural maturity

Le périmètre est-il compris ?

## 27.3 Temporal maturity

Le phénomène est-il durable ou éphémère ?

## 27.4 Causal maturity

Avons-nous des hypothèses cohérentes ?

## 27.5 Impact maturity

Savons-nous qui ou quoi est affecté ?

## 27.6 Actionability maturity

Peut-on faire quelque chose ?

---

# 28. Maturity Vector

Exemple :

```yaml
Maturity:
  evidence: 0.82
  structure: 0.91
  temporal: 0.72
  causal: 0.46
  impact: 0.79
  actionability: 0.51
```

Éviter un seul score cachant ces dimensions.

---

# 29. Composite Maturity

Pour certaines règles internes, un score composite peut exister.

Mais l’UI doit pouvoir expliquer ses composantes.

---

# 30. Confidence vs Maturity

Rappel :

```text
maturity
≠
confidence
```

Une Situation peut être très mature mais rester incertaine.

---

# 31. Maturity Gate

Une Situation ne devient pas Expression tant qu’elle n’atteint pas un seuil minimal.

Exemple :

```text
evidence >= 0.6
structure >= 0.7
impact >= 0.5
```

Les seuils dépendent du type.

---

# 32. Type-specific maturation

Exemple :

## Incident

Le temps est critique.

Seuils plus rapides.

## Opportunity

Peut mûrir plus lentement.

## Risk critique

Peut être exprimé tôt malgré faible maturité si l’impact potentiel est élevé.

---

# 33. Early Warning

Pattern :

```text
Low maturity
High potential impact
→ Early Warning
```

Le produit doit alors dire :

> « Signal encore incertain mais potentiellement important. »

---

# 34. Evidence Accumulation

Le moteur doit pouvoir attendre de nouvelles preuves.

Exemple :

```text
latency increase
↓
wait 15 min
↓
runtime confirmation
↓
support tickets
↓
confidence increase
```

---

# 35. Active Maturation

Méridian peut activement chercher des preuves.

```text
Situation
↓
Missing evidence
↓
Acquisition Planner
↓
Query source
↓
Expert quick check
↓
Human request
```

---

# 36. Passive Maturation

Le système attend les événements naturels.

Pertinent pour :

- tendances ;
- adoption ;
- outcome ;
- long-term drift.

---

# 37. Hybrid Maturation

La plupart des situations combinent passif et actif.

---

# 38. Unknowns

Les Unknowns influencent la maturation.

Exemple :

> nous ignorons quel segment client est touché.

Cela peut empêcher une Opportunity d’être qualifiée.

---

# 39. Critical Unknown

Un Unknown est critique lorsqu’il bloque :

- l’interprétation ;
- la décision ;
- la mesure de risque.

---

# 40. Contradictions

Une contradiction peut :

- réduire confidence ;
- ralentir maturation ;
- déclencher un expert ;
- provoquer split de Situation.

---

# 41. Maturation Rules Engine

Le moteur doit supporter des règles configurables.

```yaml
MaturationRule:
  situation_type:
  minimum_signals:
  minimum_source_diversity:
  max_staleness:
  contradiction_tolerance:
  required_evidence_types:
  required_experts:
```

---

# 42. Rule examples

## Opportunity Rationalization

```text
requires:
- capability overlap
- low usage
- cost evidence
- consumer evidence
```

## Customer Friction

```text
requires:
- journey or process evidence
- customer impact signal
- time correlation
```

---

# 43. Statistical Persistence

Une anomalie unique peut être ignorée.

Exemple :

```text
duration < 2 min
→ transient
```

Mais une tendance sur plusieurs heures peut mûrir.

---

# 44. Novelty Detection

Le système doit distinguer :

```text
new phenomenon
vs
known recurring phenomenon
```

---

# 45. Historical Similarity

Comparer la Situation avec des cas passés.

Exemple :

```text
current pattern ≈ incident March 2025
```

Cela augmente l’information disponible.

---

# 46. Historical Similarity must not force conclusion

Un cas similaire n’est pas une preuve que la cause est identique.

---

# 47. Recurrence

Un phénomène récurrent peut être plus important qu’une anomalie forte mais isolée.

---

# 48. Drift

Types :

```text
technical drift
process drift
domain drift
behavior drift
customer drift
organizational drift
```

---

# 49. Slow-burn phenomena

Méridian doit détecter des phénomènes lents.

Exemples :

- augmentation progressive du travail manuel ;
- dépendance croissante à une application ;
- fragmentation d’un domaine ;
- réduction lente d’usage ;
- dette opérationnelle.

---

# 50. Opportunity Discovery

Une opportunité ne vient pas seulement d’un incident.

Patterns :

```text
duplication
idle capability
high manual work
high cost / low value
repeated workaround
capability overlap
process bottleneck
unused data
organizational mismatch
```

---

# 51. Opportunity Candidate

Une Opportunity Candidate reste dans le moteur tant que la valeur potentielle n’est pas suffisamment établie.

---

# 52. Value Estimation

Peut combiner :

```text
time saved
cost avoided
risk reduced
customer impact
employee impact
strategic alignment
```

---

# 53. Opportunity Score

Exemple conceptuel :

```text
potential_value
× confidence
× feasibility
× strategic_relevance
÷ estimated_cost
```

À utiliser comme aide, pas comme décision automatique.

---

# 54. Risk Discovery

Patterns :

```text
single point of failure
unowned dependency
capacity saturation
stale critical knowledge
unsupported system
regulatory gap
security drift
```

---

# 55. Risk Priority

Peut combiner :

```text
probability
× impact
× exposure
× propagation
```

---

# 56. Expression

Une Expression est la première formulation destinée à l’humain.

Elle doit être :

- concise ;
- prudente ;
- explicable ;
- orientée impact.

---

# 57. Expression Structure

```yaml
Expression:
  title:
  summary:
  type:
  why_now:
  affected_scope:
  confidence:
  maturity:
  evidence_refs:
  contradiction_refs:
  unknown_refs:
  recommended_next_step:
```

---

# 58. Why Now

Champ essentiel.

Exemple :

> « Le phénomène devient significatif parce que trois sources indépendantes convergent depuis 48 h. »

---

# 59. Expression Types

```text
OPPORTUNITY
RISK
ANOMALY
DRIFT
CHANGE
CONTRADICTION
EMERGING_PATTERN
KNOWLEDGE_GAP
```

---

# 60. Expression Tone

Éviter :

> « Méridian a découvert la cause. »

Préférer :

> « Les éléments disponibles suggèrent actuellement que… »

selon confidence.

---

# 61. Expression Calibration

Mapping possible :

```text
0.90+ → highly supported
0.75–0.90 → strongly suggested
0.55–0.75 → plausible
<0.55 → emerging / uncertain
```

---

# 62. Attention Engine

Toutes les Expressions ne sont pas affichées.

Le moteur d’attention détermine :

> mérite-t-elle une place dans Aujourd’hui ?

---

# 63. Attention Score

Dimensions :

```text
impact
urgency
novelty
confidence
maturity
user relevance
actionability
strategic relevance
```

---

# 64. User Relevance

Le même phénomène n’a pas la même priorité pour :

- architecte ;
- directeur métier ;
- responsable applicatif ;
- risque.

---

# 65. Personalization without hiding critical issues

Le moteur peut personnaliser.

Mais un risque critique doit rester visible aux bonnes personnes même s’il n’est pas dans leur historique de consultation.

---

# 66. Attention Budget

Principe clé :

> chaque utilisateur dispose d’un budget d’attention limité.

Méridian doit donc limiter le nombre d’éléments.

---

# 67. Daily Attention Limit

Exemple :

```text
Top 3 critical
Top 5 relevant
rest → available in feed
```

---

# 68. Noise Suppression

Techniques :

- dedup ;
- merge ;
- cooldown ;
- recurring suppression ;
- baseline learning ;
- relevance filter ;
- confidence gate.

---

# 69. Cooldown

Un phénomène déjà montré ne doit pas revenir toutes les heures sans changement significatif.

---

# 70. Significant Change

Une Expression réapparaît si :

- confidence change ;
- impact change ;
- new contradiction ;
- new evidence ;
- status change.

---

# 71. Reopen

Une Situation archivée peut être réouverte si un nouveau signal pertinent apparaît.

---

# 72. Maturation Scheduler

Différents rythmes.

```text
incident: seconds/minutes
risk: minutes/hours
opportunity: hours/days
strategic drift: days/weeks
```

---

# 73. Cost-aware maturation

Les analyses coûteuses sont déclenchées seulement si l’information attendue le justifie.

---

# 74. Quick Check

Avant un Expert complet :

```text
lightweight model
+ targeted tools
```

pour déterminer si cela mérite investigation.

---

# 75. Escalation Levels

```text
L0 Observe
L1 Lightweight validation
L2 Focused analysis
L3 Multi-expert investigation
L4 Strategic investigation
```

---

# 76. Human Gate

Certains phénomènes peuvent demander confirmation avant investigation lourde.

Exemple :

> « Voulez-vous approfondir cette opportunité ? »

---

# 77. Auto-investigation

À réserver à :

- incident critique ;
- risque élevé ;
- politique explicite.

---

# 78. Discovery Policies

Chaque domaine peut configurer :

```text
signal types
thresholds
maturity gates
attention rules
auto-investigation rules
```

---

# 79. Policy Versioning

Les règles doivent être versionnées.

Une Expression doit pouvoir dire :

> générée avec policy v3.

---

# 80. Policy Simulation

Avant activation :

```text
replay historical data
↓
measure alerts/opportunities
↓
estimate noise
```

---

# 81. False Positive Tracking

Mesurer :

```text
expressions dismissed
/
expressions shown
```

---

# 82. False Negative Review

Plus difficile.

Utiliser les incidents/opportunités historiques pour vérifier :

> Méridian aurait-il dû détecter cela plus tôt ?

---

# 83. Detection Evaluation

Dimensions :

```text
precision
recall
time-to-detection
time-to-expression
noise
cost
```

---

# 84. Time to Meaning

Métrique intéressante :

```text
first raw signal
→ first meaningful expression
```

---

# 85. Time to Decision Readiness

```text
expression
→ investigation ready for decision
```

---

# 86. Discovery Quality

La qualité ne se mesure pas au nombre de signaux.

Elle se mesure au nombre de phénomènes utiles.

---

# 87. Signal-to-Expression Ratio

Un ratio faible peut être bon.

Exemple :

```text
10 000 signals
→ 12 expressions
```

si les 12 sont pertinentes.

---

# 88. Situation Compression Ratio

Mesure la capacité à regrouper.

---

# 89. Human Feedback

L’utilisateur peut :

```text
Useful
Not relevant
Already known
Wrong correlation
Too early
Too late
```

---

# 90. Feedback Learning

Le feedback peut ajuster :

- attention ;
- thresholds ;
- ranking.

Mais les règles critiques ne doivent pas s’auto-modifier sans gouvernance.

---

# 91. Discovery Explainability

Une Situation doit pouvoir montrer :

```text
Why grouped?
Why matured?
Why shown?
```

---

# 92. Explain Correlation

Exemple :

```text
Grouped because:
- same process
- 12 min temporal proximity
- same deployment
- graph distance = 1
```

---

# 93. Explain Maturity

```text
Maturity increased because:
+ second independent source
+ persisted for 4 hours
+ expert confirmation
```

---

# 94. Explain Attention

```text
Shown because:
high customer impact
high user relevance
new phenomenon
```

---

# 95. Discovery Event Model

```text
SignalDetected
SignalDeduplicated
SituationCreated
SituationMerged
SituationSplit
MaturityChanged
ExpressionCreated
ExpressionUpdated
AttentionRaised
OpportunityCreated
RiskCreated
```

---

# 96. Event Example

```yaml
event_type: MaturityChanged
situation_id: SIT-92
old_value: 0.51
new_value: 0.74
reasons:
  - NEW_RUNTIME_EVIDENCE
  - CROSS_TWIN_CONFIRMATION
```

---

# 97. Discovery Storage

Autoritatif :

```text
PostgreSQL / domain store
```

Analytics :

```text
OpenSearch / time-series / graph
```

---

# 98. Signal Store

Doit supporter volume élevé.

Tous les signaux ne nécessitent pas la même rétention.

---

# 99. Situation Store

Faible volume, forte valeur.

Rétention longue pour les situations significatives.

---

# 100. State Machine

```text
CANDIDATE
↓
QUALIFYING
↓
MATURING
↓
EXPRESSED
↓
QUALIFIED
```

Branches :

```text
DISMISSED
MERGED
SPLIT
ARCHIVED
```

---

# 101. Example — Performance incident

```text
Datadog latency signal
↓
error rate signal
↓
recent deployment
↓
same topology
↓
Situation
↓
Quick Architecture Expert
↓
Expression:
"Possible regression after deployment"
```

---

# 102. Example — Customer friction

```text
abandon rate +5%
manual validation +12%
process duration +17%
↓
Situation
↓
maturation 48h
↓
journey expert
↓
Expression:
"Friction progressive in renewal journey"
```

---

# 103. Example — Rationalization Opportunity

```text
low usage
+ high cost
+ capability overlap
+ few consumers
↓
Situation
↓
Architecture + Finance quick validation
↓
Opportunity
```

---

# 104. Example — Domain Drift

```text
new graph community
+ repeated cross-domain calls
+ shared capability claims
↓
Situation
↓
Domain Architect Expert
↓
Expression:
"Observed structure differs from declared domain"
```

---

# 105. Example — Employee friction

```text
manual rework rising
+ repeated tickets
+ tool switching
↓
Situation
↓
Process Expert
↓
Expression:
"Operational burden appears to be increasing"
```

---

# 106. Example — Slow modernization opportunity

```text
legacy app usage declining
+ new platform usage rising
+ overlap increasing
↓
months of maturation
↓
Opportunity
```

---

# 107. Investigation trigger

Une Expression peut déclencher une Investigation si :

```text
impact high
AND uncertainty non-trivial
AND decision required
```

---

# 108. No-investigation cases

Certaines Expressions peuvent être directement :

- informatives ;
- auto-résolues ;
- faibles ;
- déjà connues.

---

# 109. Opportunity trigger

Une Situation devient Opportunity si :

```text
potential improvement exists
AND benefit plausible
AND affected scope known
```

---

# 110. Risk trigger

Une Situation devient Risk si :

```text
negative outcome plausible
AND exposure exists
```

---

# 111. Knowledge Gap Expression

Méridian peut aussi exprimer :

> « Nous manquons de connaissance sur cette zone critique. »

C’est une Expression valide.

---

# 112. Knowledge Gap Opportunity

Exemple :

> connecter ServiceNow pour réduire l’incertitude sur les incidents.

---

# 113. Proactive discovery

La découverte proactive doit être contrôlée par budget.

Modes :

```text
PASSIVE
STANDARD
ACTIVE
AGGRESSIVE
```

---

# 114. Passive mode

Observe uniquement.

---

# 115. Standard mode

Corrélation + maturation normale.

---

# 116. Active mode

Recherche ciblée de preuves.

---

# 117. Aggressive mode

Investigation proactive plus large.

À réserver aux zones critiques.

---

# 118. Discovery Scope

Le moteur doit pouvoir opérer :

```text
Twin
Team
Domain
Process
Journey
Enterprise
```

---

# 119. Local Discovery

Un Twin peut détecter un phénomène local.

---

# 120. Mesh Discovery

Le Mesh peut détecter un pattern transverse.

---

# 121. Local-to-Mesh promotion

```text
local signal
↓
cross-twin relevance
↓
Mesh situation
```

---

# 122. Mesh-to-Local feedback

Une Situation globale peut enrichir les Twins concernés.

---

# 123. Discovery in Atlas

Atlas doit afficher :

- zones émergentes ;
- intensité ;
- propagation ;
- maturité.

---

# 124. Atlas layers

```text
Signals
Situations
Risks
Opportunities
Drift
```

---

# 125. Discovery in Today

La page Aujourd’hui n’affiche que les éléments ayant franchi le seuil d’attention.

---

# 126. Discovery in Feed

Le Feed peut montrer des changements plus faibles.

---

# 127. Flore interaction

Questions :

> Pourquoi ceci est-il apparu ?

> Qu’est-ce qui manque encore ?

> Depuis quand cela mûrit-il ?

> Quelles preuves ont changé ton niveau de confiance ?

---

# 128. Flore action

Actions possibles :

```text
explain
dismiss
watch
investigate
ask expert
expand scope
```

---

# 129. Watch

L’utilisateur peut choisir :

> surveiller cette Situation.

Le système augmente alors sa pertinence pour cet utilisateur.

---

# 130. Dismiss

Un dismiss doit conserver la raison.

```text
not relevant
known issue
false correlation
low value
```

---

# 131. Dismiss != delete

La Situation reste dans l’historique.

---

# 132. Governance

Le moteur doit être gouverné par :

- Product ;
- Domain owners ;
- Risk ;
- Architecture ;
- AI governance.

---

# 133. Critical Discovery Policy

Exemple :

```text
Security high-risk
→ bypass attention suppression
```

---

# 134. User-specific suppression

Ne doit jamais masquer une obligation réglementaire.

---

# 135. Discovery Audit

Pour toute Expression, conserver :

```text
signals
rules
models
experts
policy versions
timestamps
scores
```

---

# 136. Reproducibility

Un audit doit pouvoir reconstruire :

> pourquoi cette Expression a été créée à cette date.

---

# 137. Agent Role in Maturation

Les agents interviennent comme :

- interpreters ;
- validators ;
- contradictors ;
- gap finders.

Ils ne sont pas le moteur unique.

---

# 138. Deterministic Core

Le moteur doit avoir un noyau déterministe :

```text
dedup
time windows
graph distance
thresholds
policy
state transitions
```

---

# 139. Statistical Core

Pour :

```text
anomaly
trend
change point
similarity
```

---

# 140. Agentic Layer

Pour :

```text
semantic correlation
business interpretation
opportunity framing
hypothesis generation
```

---

# 141. Three-layer model

```text
DETERMINISTIC
+
STATISTICAL
+
AGENTIC
```

C’est la combinaison qui donne la robustesse.

---

# 142. Cost Model

Le plus grand volume doit être traité sans LLM.

Exemple :

```text
100k observations
↓ rules/stats
5k signals
↓ correlation
120 situations
↓ lightweight AI
12 expressions
↓ deeper expert analysis
2 investigations
```

---

# 143. Funnel Architecture

Le système fonctionne comme un entonnoir.

```text
OBSERVATIONS      100%
SIGNALS             5%
SITUATIONS        0.1%
EXPRESSIONS      0.01%
INVESTIGATIONS  0.001%
```

Valeurs illustratives uniquement.

---

# 144. Information Density

Plus on monte dans le funnel :

- moins d’objets ;
- plus de contexte ;
- plus de coût ;
- plus de valeur.

---

# 145. Backpressure

Si trop de Situations sont créées :

- augmenter gates ;
- réduire active maturation ;
- prioriser ;
- mettre en queue.

---

# 146. Situation Queue

Priorisation :

```text
critical risk
customer impact
business value
user request
recurrence
background
```

---

# 147. SLA classes

```text
REALTIME
NEAR_REALTIME
DAILY
WEEKLY
STRATEGIC
```

---

# 148. Data freshness

Chaque Situation hérite des contraintes de fraîcheur de ses données.

---

# 149. Stale Situation

Si les preuves deviennent trop anciennes :

```text
maturity may remain
confidence decreases
```

---

# 150. Situation Decay

Un phénomène non confirmé peut perdre en priorité.

---

# 151. Evidence Decay

Certaines preuves vieillissent.

Exemple :

```text
runtime data
```

plus vite que :

```text
code structure
```

---

# 152. Decay Policy

Par type de Claim / Signal.

---

# 153. Outcome feedback

Si une Opportunity conduit à une initiative puis un Outcome :

```text
Outcome
↓
feedback into detection policy
```

---

# 154. Example

Si Méridian détecte souvent à tort une opportunité sur un pattern particulier, le système peut proposer d’ajuster la règle.

Pas d’auto-modification silencieuse.

---

# 155. Maturation Learning

Les politiques peuvent apprendre via :

- feedback ;
- historical replay ;
- Outcomes.

---

# 156. Human Calibration

Les experts humains peuvent qualifier des Expressions historiques.

---

# 157. Evaluation Dataset

Construire un dataset :

```text
true incidents
true opportunities
false positives
slow-burn cases
domain drift cases
```

---

# 158. Replay Engine

Rejouer l’historique.

Mesurer :

```text
would detect?
when?
with what maturity?
with how much noise?
```

---

# 159. Scenario — TBT

Exemple complet.

## Observation 1

```text
new outgoing dependency
```

## Observation 2

```text
new Jira feature
```

## Observation 3

```text
runtime traffic increased
```

## Signal

```text
architecture change
```

## Situation

```text
TBT introducing new capability dependency
```

## Maturation

```text
code + Jira + trace
```

## Expression

> « TBT semble intégrer une nouvelle dépendance fonctionnelle vers EligibilityService. »

---

# 160. Scenario — Opportunity

## Observations

```text
manual validations rising
journey duration rising
abandonment rising
```

## Situation

```text
renewal friction
```

## Maturation

```text
process + customer + runtime
```

## Opportunity

> « Réduction potentielle d’une validation manuelle redondante. »

---

# 161. Scenario — Organizational drift

## Observations

```text
Team B changes app X frequently
declared owner is Team A
tickets assigned to Team B
```

## Expression

> « Le modèle d’ownership déclaré semble diverger du fonctionnement observé. »

---

# 162. UI — Situation card

```text
Title

Type
Maturity
Confidence

Why now
Impact
Affected area

Evidence
Unknowns
Contradictions

[Explain] [Watch] [Investigate]
```

---

# 163. UI — Maturity timeline

```text
12:05 candidate
13:20 second source
14:10 cross-twin confirmation
14:25 expert check
14:30 expressed
```

---

# 164. UI — Why this matters

Une carte doit expliquer :

```text
business impact
technical impact
customer impact
employee impact
```

selon disponibilité.

---

# 165. UI — Hidden details

Les détails techniques ne doivent pas surcharger la carte principale.

Ils sont accessibles via drill-down.

---

# 166. API — Signals

```text
GET /signals
GET /signals/{id}
POST /signals/{id}/dismiss
```

---

# 167. API — Situations

```text
GET /situations
GET /situations/{id}
POST /situations/{id}/watch
POST /situations/{id}/investigate
POST /situations/{id}/dismiss
```

---

# 168. API — Maturity

```text
GET /situations/{id}/maturity
GET /situations/{id}/history
```

---

# 169. API — Explain

```text
GET /situations/{id}/explain
```

Retour :

```text
correlation reasons
maturity reasons
attention reasons
evidence
unknowns
```

---

# 170. Technical components

```text
Signal Detector Service
Signal Normalizer
Fingerprint/Dedup Service
Situation Correlator
Maturity Engine
Interpretation Engine
Attention Engine
Discovery Policy Service
Replay/Evaluation Engine
```

---

# 171. Event Backbone

Les composants communiquent via événements.

---

# 172. State Store

PostgreSQL/Aurora pour :

- Situation ;
- lifecycle ;
- policy ;
- audit.

---

# 173. Time-Series / Search

Pour :

- observations ;
- signals ;
- history.

---

# 174. Graph

Pour :

- topology ;
- process relation ;
- impact scope.

---

# 175. Cache

Pour :

- repeated correlation ;
- baselines ;
- recent fingerprints.

---

# 176. Model usage

LLM principalement pour :

- semantic correlation ;
- interpretation ;
- opportunity wording ;
- unknown identification.

---

# 177. Avoid LLM for

```text
dedup
threshold
trend math
time window
graph distance
policy
```

---

# 178. Failure handling

Si l’Interpretation Agent échoue :

```text
Situation stays MATURING
```

Pas de perte.

---

# 179. Degraded mode

Si agents indisponibles :

- rules/stats continue ;
- situations continue ;
- expressions agentiques retardées.

---

# 180. Observability

Mesures :

```text
observations/sec
signals/sec
dedup ratio
situations/hour
maturity changes
expressions/day
false positive feedback
time to meaning
LLM cost
```

---

# 181. Cost observability

```text
cost per expression
cost per opportunity
cost per investigation triggered
```

---

# 182. Discovery health

Dashboard global :

```text
signal backlog
situation backlog
maturation backlog
stale situations
critical unknowns
policy errors
```

---

# 183. Security

Les Signals héritent des permissions de leurs sources.

Une Situation combinant plusieurs scopes doit appliquer l’intersection/union selon politique.

---

# 184. Security-safe Expression

Une Expression peut être générée de façon agrégée sans exposer les preuves sensibles.

---

# 185. Tenant Isolation

Tous les signaux et situations portent `tenant_id`.

---

# 186. MVP

Le MVP Discovery & Maturation doit supporter :

```text
Signal
Situation
Correlation
Maturity
Expression
Opportunity
Risk
Human dismiss/watch
Explainability
```

---

# 187. MVP detectors

Commencer avec :

```text
metric anomaly
code/deployment change
graph relation change
claim change
manual human signal
```

---

# 188. MVP correlation

```text
time
entity
graph proximity
shared change
```

---

# 189. MVP maturity

Dimensions simples :

```text
evidence
persistence
source diversity
impact
```

---

# 190. MVP attention

```text
impact
confidence
user relevance
novelty
```

---

# 191. MVP expert usage

Un seul Quick Expert Check avant Expression complexe.

---

# 192. MVP use cases

## Use case 1

Incident après changement.

## Use case 2

Opportunité de rationalisation.

## Use case 3

Friction processus.

## Use case 4

Domain drift.

---

# 193. Phase 2

Ajouter :

- historical similarity ;
- recurrence ;
- active maturation ;
- domain-specific policies ;
- richer opportunity patterns.

---

# 194. Phase 3

Ajouter :

- causal models ;
- multi-modal signals ;
- predictive opportunity maturation ;
- strategic drift ;
- richer business/client/employee detection.

---

# 195. Anti-patterns

## Alert Everything

Tout afficher.

## LLM Detects Everything

Coût + bruit.

## One Maturity Score

Opaque.

## No Dedup

Explosion de cartes.

## No History

Impossible de distinguer nouveauté et récurrence.

## Correlation = Causation

Erreur majeure.

## Auto-investigate Everything

Coût énorme.

## No Attention Budget

Fatigue utilisateur.

## Hide Uncertainty

Fausse confiance.

## No Human Feedback

Pas de calibration.

---

# 196. Critères de succès

Le moteur est réussi si :

1. la majorité des Observations ne deviennent jamais des Expressions ;
2. les Signals similaires sont correctement regroupés ;
3. les Situations expliquent pourquoi elles existent ;
4. maturity et confidence sont distincts ;
5. les utilisateurs voient peu mais voient utile ;
6. les phénomènes lents peuvent émerger ;
7. une Opportunity peut naître sans incident ;
8. l’incertitude reste visible ;
9. l’investigation n’est déclenchée que lorsque justifiée ;
10. les politiques sont rejouables et évaluables.

---

# 197. Architecture cible synthétique

```text
                OBSERVATIONS
                     │
                     ▼
                DETECTORS
                     │
                     ▼
                  SIGNALS
                     │
                     ▼
             NORMALIZE / DEDUP
                     │
                     ▼
              CORRELATION
                     │
                     ▼
               SITUATIONS
                     │
                     ▼
               MATURATION
       ┌─────────────┼─────────────┐
       ▼             ▼             ▼
   EVIDENCE        HISTORY       EXPERTS
       │             │             │
       └─────────────┴─────────────┘
                     │
                     ▼
              INTERPRETATION
                     │
                     ▼
                EXPRESSION
             ┌───────┼────────┐
             ▼       ▼        ▼
       OPPORTUNITY   RISK   INVESTIGATION
                     │
                     ▼
               ATTENTION
                     │
                     ▼
                 HUMAIN
```

---

# 198. Conclusion

Le Discovery & Maturation Engine est le mécanisme qui empêche Méridian de devenir un système bavard.

Il applique une discipline :

> **tout ce qui est observé n’est pas important.  
> tout ce qui est important n’est pas encore compris.  
> tout ce qui est compris ne mérite pas une action immédiate.**

La vraie intelligence de Méridian consiste à savoir :

- quoi ignorer ;
- quoi surveiller ;
- quoi faire mûrir ;
- quoi exprimer ;
- quoi investiguer.

Le moteur doit donc être conçu comme un **entonnoir cognitif**.

À la base :

```text
beaucoup de faits
```

Au sommet :

```text
très peu de sujets à forte valeur
```

C’est cette capacité qui permet à Méridian de devenir un produit d’exploitation continue plutôt qu’un système d’alertes sophistiqué.

---

# 199. Prochain document

Le prochain document recommandé est :

> **MÉRIDIAN — Investigation & Decision Engine**

Il devra formaliser le cycle :

```text
Expression / Opportunity / Risk
↓
Investigation
↓
Hypotheses
↓
Experts
↓
Contradiction
↓
Scenarios
↓
Decision
```

et surtout expliquer comment Méridian passe :

> **d’un phénomène suffisamment mature**

à :

> **une décision humaine éclairée, comparable et traçable.**
