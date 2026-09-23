# MÉRIDIAN — Design System & UI Component Specification
## Tokens, composants, interactions, motion, Atlas, Flore, Trust, Investigation et Decision UI

**Statut :** Design system de référence  
**Version :** 1.0  
**Produit :** MÉRIDIAN  
**Tagline :** **DÉCOUVRIR · COMPRENDRE · DÉCIDER**

---

# 0. Objet du document

Ce document transforme la vision UX de Méridian en un système de design concret, cohérent et implémentable.

Il répond à la question :

> **Quels sont les éléments visuels, comportementaux et interactifs qui permettent à Méridian de garder une identité futuriste, crédible et homogène à travers toutes ses surfaces ?**

Il définit :

- les design tokens ;
- la palette ;
- la typographie ;
- les règles d’espacement ;
- la grille ;
- les élévations ;
- les surfaces ;
- les composants ;
- les états ;
- les patterns d’interaction ;
- les composants Atlas ;
- les composants Flore ;
- les composants de confiance ;
- les composants Investigation / Decision ;
- le système de motion ;
- les règles responsive ;
- les exigences d’accessibilité.

Le principe central est :

> **Méridian ne doit pas seulement être cohérent graphiquement.  
> Il doit être cohérent cognitivement.**

Un même concept doit avoir :

- la même apparence ;
- la même logique ;
- les mêmes états ;
- le même langage d’interaction ;
- quel que soit l’endroit où il apparaît.

---

# 1. Principes du Design System

## 1.1 Cohérence avant originalité locale

Une Opportunity doit être reconnaissable :

- dans Aujourd’hui ;
- dans Atlas ;
- dans Flore ;
- dans une Investigation ;
- dans Transformation Memory.

---

## 1.2 Le visuel encode du sens

La couleur, la forme et la motion ne sont pas décoratives.

Elles doivent communiquer :

- type ;
- maturité ;
- confiance ;
- criticité ;
- statut ;
- fraîcheur.

---

## 1.3 La profondeur est progressive

Le composant doit supporter :

```text
summary
peek
detail
deep evidence
```

---

## 1.4 Futuriste ≠ spectaculaire

Le futurisme vient principalement de :

- fluidité ;
- profondeur ;
- spatialité ;
- intelligence contextuelle ;
- précision.

Pas d’effets gratuits.

---

## 1.5 Enterprise-grade

Chaque composant doit pouvoir fonctionner dans :

- usage quotidien ;
- environnement bancaire ;
- contexte critique ;
- grands volumes ;
- audit.

---

# 2. Architecture du Design System

```text
FOUNDATIONS
├── Color
├── Typography
├── Spacing
├── Radius
├── Elevation
├── Motion
├── Grid
└── Iconography

PRIMITIVES
├── Button
├── Input
├── Badge
├── Tooltip
├── Chip
├── Card
├── Panel
├── Drawer
├── Popover
└── Table

DOMAIN COMPONENTS
├── Twin Node
├── Domain Membrane
├── Opportunity Card
├── Risk Card
├── Claim Card
├── Evidence Card
├── Hypothesis Card
├── Expert Card
├── Scenario Card
├── Decision Card
├── Outcome Card
└── Learning Card

COMPOSITES
├── Trust Panel
├── Investigation Board
├── Decision Board
├── Atlas Inspector
├── Flore Panel
└── Transformation Episode
```

---

# 3. Theme strategy

Recommandation :

> **Dark theme comme thème principal.**

Light theme optionnel ultérieurement.

---

# 4. Dark background architecture

La profondeur repose sur plusieurs niveaux.

```text
Background 0 — #070B12
Background 1 — #0B111B
Surface 1    — #111926
Surface 2    — #172131
Surface 3    — #1D2A3C
```

Les valeurs exactes pourront être ajustées après tests WCAG.

---

# 5. Accent palette

Palette conceptuelle :

```text
Cyan Core       — #36D8FF
Cyan Deep       — #1594C7
Violet Core     — #8B6CFF
Amber Core      — #EFB44C
Green Core      — #4FD49B
Rose Risk       — #F25B7D
Red Critical    — #FF4D57
```

---

# 6. Neutral palette

```text
Text Primary     — #F4F7FB
Text Secondary   — #AEB9C8
Text Muted       — #77859A
Border Default   — rgba(255,255,255,0.10)
Border Strong    — rgba(255,255,255,0.18)
```

---

# 7. Semantic colors

## Knowledge

```text
cyan
```

## AI / Reasoning

```text
violet
```

## Maturity / Emerging

```text
amber
```

## Validated / Positive

```text
green
```

## Risk

```text
rose / red
```

## Unknown

```text
slate / amber outline
```

---

# 8. Color usage policy

La couleur doit répondre à une question.

Exemple :

> Pourquoi cette carte est-elle ambre ?

Réponse :

> Elle est encore en maturation.

Pas :

> Parce que c’est plus joli.

---

# 9. Surface opacity

Les cartes peuvent utiliser :

```text
opaque surface
semi-transparent surface
glass surface
```

Le glass est réservé aux zones où l’arrière-plan spatial doit rester perceptible :

- Atlas rail ;
- floating toolbar ;
- Flore panel.

---

# 10. Glass surface token

Concept :

```css
background: rgba(15, 23, 34, 0.82);
backdrop-filter: blur(18px);
border: 1px solid rgba(255,255,255,0.10);
```

---

# 11. Typography

Typographie recommandée :

```text
Primary UI: Inter / Geist / equivalent enterprise sans
Display: même famille ou variante légèrement plus expressive
Monospace: JetBrains Mono / equivalent
```

---

# 12. Type scale

```text
Display XL   40 / 48
Display L    32 / 40
Heading 1    28 / 36
Heading 2    22 / 30
Heading 3    18 / 26
Body L       16 / 24
Body M       14 / 22
Body S       13 / 20
Caption      12 / 18
Micro        11 / 16
```

---

# 13. Typography hierarchy

Utiliser le contraste de taille plus que le contraste de couleur.

---

# 14. Numeric style

Pour :

- confidence ;
- maturity ;
- KPI ;
- outcome.

Utiliser chiffres tabulaires lorsque pertinent.

---

# 15. Monospace usage

Réservé à :

- IDs ;
- code ;
- technical locators ;
- timestamps détaillés ;
- Claim predicates si vue technique.

---

# 16. Spacing system

Base :

```text
4 px
```

Tokens :

```text
space-1  = 4
space-2  = 8
space-3  = 12
space-4  = 16
space-5  = 20
space-6  = 24
space-8  = 32
space-10 = 40
space-12 = 48
space-16 = 64
```

---

# 17. Border radius

```text
xs = 6
sm = 10
md = 14
lg = 18
xl = 24
full = 999
```

---

# 18. Radius usage

## Small

inputs / chips.

## Medium

cards.

## Large

panels / Flore.

## Organic

Atlas domains, non-tokenized geometry.

---

# 19. Borders

Borders fins.

```text
1px
```

Éviter les cartes trop encadrées.

La hiérarchie doit venir aussi de :

- espace ;
- profondeur ;
- contraste.

---

# 20. Elevation

Dark UI :

les ombres classiques ont peu d’effet.

Utiliser :

- léger shadow ;
- border ;
- luminosité ;
- blur ;
- profondeur.

---

# 21. Elevation tokens

```text
E0 flat
E1 card
E2 floating panel
E3 drawer
E4 command / modal
```

---

# 22. Grid

Desktop principal :

```text
12 columns
24px gutter
32px page margin
```

---

# 23. Width breakpoints

Conceptuels :

```text
< 768        compact
768–1199     medium
1200–1599    desktop
1600+        large canvas
```

---

# 24. Large canvas

Sur grand écran :

- Atlas gagne en surface ;
- rails plus riches ;
- investigation en 3 colonnes possible.

---

# 25. Iconography

Style :

```text
outline
1.5–2 px
rounded
consistent geometry
```

---

# 26. Domain icons

Créer une famille spécifique :

```text
Twin
Domain
Claim
Evidence
Opportunity
Risk
Investigation
Decision
Outcome
Learning
```

---

# 27. Twin icon

Doit suggérer :

> intelligence + système.

Éviter robot humanoïde cartoon.

Préférer :

- noyau ;
- module ;
- petit glyph intelligent.

---

# 28. Domain icon

Forme territoriale / membrane.

---

# 29. Motion system

Durées recommandées :

```text
instant   80–120 ms
fast      160–220 ms
normal    240–320 ms
slow      420–600 ms
cinematic 700–1200 ms
```

---

# 30. Motion easing

```text
standard
decelerate
accelerate
spring-soft
```

---

# 31. Motion rule

Les transitions structurelles utilisent `normal`.

Atlas navigation peut utiliser `slow/cinematic`.

---

# 32. Reduced motion

Obligatoire.

Toutes les animations non essentielles doivent pouvoir être réduites.

---

# 33. Button

Variants :

```text
primary
secondary
ghost
danger
success
```

---

# 34. Button primary

Utiliser parcimonieusement.

Une page ne doit pas contenir 8 actions primaires.

---

# 35. Button sizes

```text
sm
md
lg
```

---

# 36. Icon button

Très important pour Atlas.

Doit toujours avoir :

- tooltip ;
- aria-label ;
- hit area suffisante.

---

# 37. Chip

Types :

```text
filter
status
scope
metadata
action
```

---

# 38. Semantic chip examples

```text
MATURE
HIGH CONFIDENCE
WATCHING
RESTRICTED
NEW
```

---

# 39. Badge

Utilisé pour :

- count ;
- importance ;
- state.

---

# 40. Status system

États génériques :

```text
neutral
active
positive
warning
risk
critical
inactive
```

---

# 41. Input

Inputs doivent rester très sobres.

---

# 42. Search input

Recherche globale :

- large ;
- keyboard shortcut ;
- autocomplete ;
- entity icons ;
- context grouping.

---

# 43. Command palette

Recommandation forte.

Shortcut :

```text
Cmd/Ctrl + K
```

Actions :

```text
Go to Twin
Open Investigation
Ask Flore
Search Claim
Create Investigation
Change Scope
```

---

# 44. Card primitive

Structure :

```text
header
body
metadata
actions
```

---

# 45. Card interaction states

```text
default
hover
selected
focused
disabled
loading
stale
```

---

# 46. Selected card

Accent léger + border.

Pas de gros fond saturé.

---

# 47. Loading card

Skeleton subtil.

---

# 48. Stale card

Affiche clairement :

```text
May be outdated
```

avec un indicateur de fraîcheur.

---

# 49. Panel

Les panneaux structurent :

- rail ;
- workspace ;
- detail view.

---

# 50. Drawer

Pour :

- Evidence ;
- context details ;
- secondary information.

---

# 51. Modal

Réservé aux actions bloquantes courtes.

---

# 52. Tooltip

Doit expliquer :

- icône ;
- score ;
- état.

Ne doit pas contenir un article.

---

# 53. Popover

Pour prévisualisations courtes.

---

# 54. Peek component

Pattern clé.

Peut contenir :

```text
title
short summary
confidence
main relation
quick action
```

---

# 55. Trust Panel

## 55.1 Rôle

Composant transversal majeur.

Il répond :

> **Pourquoi puis-je faire confiance à cette information ?**

---

# 56. Trust Panel structure

```text
Confidence
Maturity
Freshness
Evidence
Sources
Contradictions
Unknowns
```

---

# 57. Confidence component

Ne pas montrer seulement :

```text
87%
```

Montrer :

```text
87% · High
```

avec explication au hover/click.

---

# 58. Maturity component

Peut être représenté sous forme :

- step bar ;
- segmented rail ;
- textual stage.

---

# 59. Freshness component

Exemples :

```text
Updated 12 min ago
Data current to 14:32
Some sources stale
```

---

# 60. Evidence count

Exemple :

```text
7 evidences · 3 independent sources
```

---

# 61. Contradiction indicator

Un triangle rouge n’est pas toujours nécessaire.

Utiliser un indicateur analytique.

---

# 62. Unknown indicator

Exemple :

```text
2 critical unknowns
```

---

# 63. Claim Card

Structure :

```text
Statement
Predicate summary
Status
Confidence
Maturity
Scope
Evidence
History
```

---

# 64. Claim variants

```text
compact
standard
technical
```

---

# 65. Claim compact

Pour Flore / summary.

---

# 66. Claim technical

Expose :

```text
subject
predicate
object
qualifiers
version
```

---

# 67. Evidence Card

Structure :

```text
Source
Type
Excerpt
Locator
Supports / Contradicts
Freshness
```

---

# 68. Evidence source badge

Exemples :

```text
GitHub
Jira
Datadog
CMDB
Human
```

---

# 69. Evidence Preview

Ne jamais afficher trop de contenu.

Extrait court + lien approfondir.

---

# 70. Evidence Drawer

Sections :

```text
Evidence
Source metadata
Artifact version
Related Claims
Security
Timeline
```

---

# 71. Unknown Card

Visuel :

- sobre ;
- ambre/slate ;
- actionnable.

---

# 72. Unknown actions

```text
Investigate
Ask owner
Connect source
Ignore
```

---

# 73. Contradiction Card

Structure :

```text
Claim A
vs
Claim B
Why conflict
Scope
Time
Resolution status
```

---

# 74. Opportunity Card

Structure :

```text
Type
Title
Why now
Potential value
Confidence
Maturity
Affected scope
CTA
```

---

# 75. Opportunity visual coding

Accent :

```text
cyan + amber
```

selon maturité.

---

# 76. Risk Card

Structure similaire, mais :

- impact ;
- exposure ;
- time horizon ;
- propagation.

---

# 77. Risk visual coding

Rose / rouge seulement pour informations réellement importantes.

---

# 78. Situation Card

Doit être plus neutre qu’une Opportunity.

Une Situation n’est pas encore une conclusion définitive.

---

# 79. Situation maturity bar

Visible directement.

---

# 80. Investigation Card

Pour listes :

```text
Question
Status
Progress
Owner
Experts
Confidence
Next milestone
```

---

# 81. Investigation Progress Component

Stages :

```text
Scope
Evidence
Analysis
Contradiction
Synthesis
Scenarios
Decision
```

---

# 82. Progress style

Segmented rail horizontal ou vertical.

---

# 83. Hypothesis Card

Structure :

```text
Statement
Status
Confidence
Support
Against
Owner
```

---

# 84. Hypothesis color

Ne pas donner une couleur « vérité ».

Utiliser status + strength.

---

# 85. Expert Card

Structure :

```text
Expert
Mission
Status
Key findings
Evidence count
Confidence
```

---

# 86. Expert visual identity

Chaque famille peut avoir un glyph spécifique, mais pas une couleur totalement différente.

---

# 87. Expert Run state

```text
queued
running
partial
complete
failed
blocked
```

---

# 88. Scenario Card

Structure :

```text
Name
Approach
Value
Risk
Cost
Time
Reversibility
Confidence
```

---

# 89. Scenario Comparison Matrix

Colonnes :

```text
Scenario A
Scenario B
Scenario C
```

Lignes :

```text
Value
Cost
Risk
Time
Customer
Employee
Architecture
Reversibility
Confidence
```

---

# 90. Comparison highlight

L’UI peut mettre en évidence :

- best score ;
- trade-offs ;
- critical weakness.

Ne pas faire de classement opaque.

---

# 91. Recommendation Banner

Affiche :

```text
Méridian recommendation
```

distinctement de :

```text
Human decision
```

---

# 92. Decision Card

Structure :

```text
Selected scenario
Rationale
Approvers
Date
Accepted risk
Expected outcomes
Review date
```

---

# 93. Decision visual status

```text
draft
pending approval
decided
superseded
review due
```

---

# 94. Outcome Card

Structure :

```text
Metric
Expected
Observed
Delta
Attribution
Confidence
Trend
```

---

# 95. Outcome delta

Doit être visuellement évident.

---

# 96. Unexpected Effect Card

Accent spécifique.

Doit signaler :

> un effet non prévu est apparu.

---

# 97. Learning Card

Structure :

```text
What we learned
Conditions
Confidence
Related outcomes
Applicability
Reuse count
```

---

# 98. Transformation Episode Card

Structure :

```text
Trigger
Investigation
Decision
Outcome
Learning
Timeline
```

---

# 99. Transformation Timeline

Événements :

```text
Situation
Investigation
Decision
Deployment
Outcome
Learning
```

---

# 100. Atlas Design System

Atlas nécessite un sous-système spécifique.

---

# 101. Atlas Canvas

Fond :

- sombre ;
- léger grid/noise optionnel ;
- zéro distraction.

---

# 102. Atlas Node primitive

Un nœud possède :

```text
shape
icon
label
state
halo
badges
ports
```

---

# 103. Twin Node

Taille par défaut compacte.

States :

```text
normal
hover
selected
related
muted
risk
opportunity
unknown
```

---

# 104. Twin Node hover

Montre :

```text
name
role
confidence
key signal
```

---

# 105. Twin Node selected

Le nœud devient plus net.

Ses voisins sont mis en avant.

Le reste s’atténue.

---

# 106. Node badges

Maximum 2 badges visibles.

Exemples :

```text
risk
opportunity
unknown
```

---

# 107. Domain Membrane

Surface organique semi-transparente.

Props :

```text
type
confidence
declared/observed
selected
activity
```

---

# 108. Domain Membrane declared

Contour régulier.

---

# 109. Domain Membrane observed

Contour légèrement plus organique.

---

# 110. Domain Membrane proposed

Contour pointillé / pulsation légère.

---

# 111. Edge primitive

Props :

```text
type
strength
confidence
direction
activity
selected
```

---

# 112. Edge styles

```text
solid = confirmed
dashed = inferred
dotted = proposed
```

---

# 113. Edge animation

Uniquement pour activité / propagation.

---

# 114. Atlas Halo

Utilisé pour :

- situation ;
- opportunity ;
- risk ;
- maturity.

---

# 115. Halo rule

Pas plus de 2 halos concurrents au même endroit.

---

# 116. Atlas Layer Switcher

Composant flottant.

Layers :

```text
Domains
Twins
Processes
Signals
Risks
Opportunities
Investigations
```

---

# 117. Atlas Temporal Scrubber

Composant stratégique.

```text
Now
Past date
Before/After
Replay
```

---

# 118. Atlas Lasso Tool

Actions après sélection :

```text
Investigate
Compare
Ask Flore
Save view
```

---

# 119. Atlas Mini Inspector

Au hover/click léger :

```text
entity
summary
main relationship
status
```

---

# 120. Atlas Context Rail

Rail droit :

```text
Summary
Signals
Opportunities
Risks
Investigations
Claims
```

---

# 121. Atlas Map Controls

```text
zoom
fit
center
layers
time
lasso
reset
```

---

# 122. Atlas Zoom behavior

Zoom doit préserver la stabilité spatiale.

Les nœuds ne doivent pas sauter aléatoirement.

---

# 123. Atlas labels

À faible zoom :

- peu de labels.

À fort zoom :

- davantage de détails.

---

# 124. Atlas density management

Techniques :

```text
clustering
LOD
semantic zoom
label collision
edge bundling
```

---

# 125. Semantic zoom

La nature de ce qu’on affiche change avec le niveau.

---

# 126. Flore Design System

Flore possède un langage distinct mais intégré.

---

# 127. Flore Entry

Dans top bar :

- icône ;
- nom ;
- petit état contextuel.

Exemple :

```text
Flore · Context: TBT
```

---

# 128. Flore Panel

Largeur desktop :

```text
380–520 px
```

adaptative.

---

# 129. Flore Panel anatomy

```text
Context header
Conversation
Structured answer
Evidence / trust
Action chips
Composer
```

---

# 130. Flore Context Header

Affiche :

```text
Current context
Scope
Time
```

---

# 131. Flore Answer block

Ne doit pas ressembler à du texte de chatbot brut.

Peut inclure :

- title ;
- concise answer ;
- findings ;
- evidence chips ;
- actions.

---

# 132. Flore Trust expansion

Chaque réponse importante a :

```text
Why this answer?
```

---

# 133. Flore streaming

Le streaming doit afficher des **étapes utiles**, pas le raisonnement interne.

Exemple :

```text
Searching relevant claims…
Comparing recent changes…
2 supporting sources found…
```

---

# 134. Flore action chips

```text
Show in Atlas
Open Evidence
Create Investigation
Compare History
Watch
```

---

# 135. Investigation Workspace System

Le workspace nécessite une composition robuste.

---

# 136. Investigation Desktop Layout

```text
Header
Progress
Main column ~ 60%
Right rail ~ 30–35%
```

---

# 137. Investigation Right Rail

```text
Status
Experts
Unknowns
Trust
Quick actions
```

---

# 138. Investigation tabs

Éviter trop de tabs.

Préférer sections scroll + sticky mini-nav.

---

# 139. Sticky Investigation Nav

```text
Summary
Hypotheses
Evidence
Experts
Scenarios
Decision
```

---

# 140. Investigation Evidence Board

Vue optionnelle :

```text
FOR
AGAINST
UNKNOWN
```

---

# 141. Decision Board System

Design plus solennel et clair.

---

# 142. Decision Hero

Affiche :

```text
Question
Readiness
Recommendation
Decision status
```

---

# 143. Decision Comparison Zone

Composant central.

---

# 144. Decision Evidence Zone

Doit permettre de descendre rapidement vers les preuves.

---

# 145. Decision Approval Component

Affiche :

```text
approver
role
status
time
```

---

# 146. Transformation Memory System

Surface plus narrative.

---

# 147. Episode Timeline

Peut être horizontale sur desktop.

---

# 148. Pattern Cluster Card

Affiche :

```text
Pattern
Occurrences
Confidence
Common conditions
Typical side effects
```

---

# 149. Today Design System

Cards plus éditoriales.

---

# 150. Today section components

```text
Hero strip
Critical card
Opportunity card
Investigation-ready card
Outcome card
Learning card
```

---

# 151. Today Hero Strip

Doit rester extrêmement compact.

---

# 152. Today grouping

Groupes possibles :

```text
Needs attention
Emerging
Ready to decide
Learning
```

---

# 153. Empty state Today

Exemple :

> Rien ne demande une action immédiate dans ce scope.

---

# 154. Table system

Certaines surfaces ont besoin de tables.

Exemples :

- Sources ;
- Claims ;
- Decisions ;
- Expert Registry.

---

# 155. Table design

Dense mais lisible.

Support :

- sticky header ;
- filters ;
- sorting ;
- column visibility ;
- row expansion.

---

# 156. Timeline component

Props :

```text
events
importance
time scale
grouping
```

---

# 157. Before/After component

Deux modes :

```text
split
overlay
```

---

# 158. Diff component

Pour :

- Claims ;
- graph relations ;
- configuration ;
- decision versions.

---

# 159. Notification component

Notifications catégorisées.

---

# 160. Notification severity

```text
info
attention
decision
risk
critical
```

---

# 161. Toasts

Réservés aux confirmations brèves.

---

# 162. Error states

Doivent être utiles.

Exemple :

> Datadog source temporarily unavailable. Existing knowledge remains accessible.

---

# 163. Degraded state

Composant distinct.

Indique :

```text
what is unavailable
what remains usable
```

---

# 164. Permission state

Exemple :

> Some evidence is restricted.

---

# 165. Data freshness warning

Exemple :

> Jira data is 18 hours old.

---

# 166. Skeletons

Chaque surface majeure possède son skeleton.

---

# 167. Long-running Job component

Structure :

```text
Job title
Stage
Progress
Completed steps
Partial findings
Cancel
```

---

# 168. Long Job visual principle

L’utilisateur doit voir que le système **travaille intelligemment**.

---

# 169. Long Job stages

Exemple :

```text
Collecting
Resolving
Analyzing
Contradicting
Synthesizing
```

---

# 170. Progressive result component

Permet de publier un finding avant la fin.

---

# 171. Responsive — compact desktop

Sur <1200 px :

- right rail devient drawer ;
- navigation gauche icon-only ;
- Atlas controls regroupés.

---

# 172. Tablet

- Atlas utilisable ;
- investigation sections stacked ;
- scenario comparison swipe/stack.

---

# 173. Mobile

Usage secondaire.

Priorités :

- Today ;
- Flore ;
- notifications ;
- decision review.

Atlas complet peut être limité.

---

# 174. Accessibility — contrast

Tous les tokens doivent être validés contre WCAG.

---

# 175. Accessibility — color independence

Un état ne doit jamais être communiqué uniquement par couleur.

---

# 176. Accessibility — keyboard

Tous les composants interactifs doivent être accessibles clavier.

---

# 177. Atlas keyboard navigation

Navigation :

```text
Tab
Arrow keys
Enter
Escape
```

avec inspector alternatif.

---

# 178. Accessibility — screen readers

Les graphes doivent avoir une représentation sémantique alternative.

---

# 179. Accessibility — motion

Respect `prefers-reduced-motion`.

---

# 180. Focus states

Focus ring visible.

---

# 181. Content design

Le Design System doit inclure une logique de rédaction.

---

# 182. Labels

Courts.

Exemple :

```text
Why now
Evidence
Unknowns
Decision
```

---

# 183. Status language

Préférer verbes/états compréhensibles.

---

# 184. AI language

Éviter :

```text
AI thinks
```

Préférer :

```text
Méridian suggests
Evidence currently supports
```

---

# 185. Uncertainty language

Toujours calibrée.

---

# 186. Number formatting

Localisé.

---

# 187. Date formatting

Afficher :

- relatif dans l’UI ;
- absolu au détail.

Exemple :

```text
12 min ago
Sep 9, 2026 · 14:32
```

---

# 188. Design tokens structure

Exemple :

```json
{
  "color": {
    "bg": {
      "base": "#070B12",
      "surface": "#111926"
    },
    "accent": {
      "knowledge": "#36D8FF",
      "reasoning": "#8B6CFF",
      "maturity": "#EFB44C"
    }
  }
}
```

---

# 189. CSS variable strategy

Exemple :

```css
--mdn-bg-base
--mdn-surface-1
--mdn-text-primary
--mdn-accent-knowledge
--mdn-accent-risk
```

---

# 190. Component naming

Préfixe recommandé :

```text
Mdn
```

Exemple :

```text
MdnTrustPanel
MdnTwinNode
MdnOpportunityCard
```

---

# 191. React architecture

Composants découplés du backend.

Le composant consomme un ViewModel.

---

# 192. ViewModel principle

Exemple :

```ts
type OpportunityCardVM = {
  id: string
  title: string
  whyNow: string
  confidence: number
  maturity: string
}
```

---

# 193. Domain object != UI component props

Ne jamais exposer directement les entités backend complexes au composant.

---

# 194. Storybook

Recommandation forte.

Chaque composant doit avoir :

- story ;
- states ;
- accessibility tests ;
- visual regression.

---

# 195. Component quality gates

```text
TypeScript strict
unit tests
a11y
visual regression
responsive
dark theme
loading/error states
```

---

# 196. Design-to-code workflow

```text
Design tokens
↓
Figma variables
↓
Code tokens
↓
Storybook
↓
Application
```

---

# 197. Figma organization

```text
Foundations
Primitives
Domain Components
Atlas
Flore
Investigation
Decision
Patterns
Templates
```

---

# 198. Design component maturity

```text
Draft
Pilot
Stable
Deprecated
```

---

# 199. Versioning

Design System version :

```text
1.x
2.x
```

Breaking changes documentés.

---

# 200. Visual regression

Particulièrement important pour Atlas et surfaces riches.

---

# 201. Performance

Les effets visuels doivent respecter la performance.

---

# 202. Blur cost

Utiliser backdrop blur avec modération.

---

# 203. Atlas rendering performance

Pour grands graphes :

- WebGL/canvas selon besoin ;
- LOD ;
- clustering ;
- offscreen culling.

---

# 204. Motion performance

Privilégier transform/opacity.

---

# 205. Component telemetry

Certaines interactions peuvent être mesurées :

```text
trust panel opened
evidence opened
scenario compared
investigation started
```

---

# 206. Telemetry ethics

Ne pas transformer le Design System en outil de surveillance individuelle.

---

# 207. Dark theme image treatment

Images et mini visualisations doivent être adaptées pour ne pas casser la cohérence.

---

# 208. Chart palette

Les charts utilisent la même palette sémantique.

---

# 209. Chart rules

Éviter :

- 12 couleurs ;
- légendes complexes ;
- gradients inutiles.

---

# 210. Sparkline

Très utile pour Outcome / Signal.

---

# 211. Confidence visualization

Éviter le gauge automobile.

Préférer :

- label ;
- petite barre ;
- trust detail.

---

# 212. Maturity visualization

Segmented progress.

---

# 213. Risk visualization

Doit montrer :

```text
impact
likelihood
exposure
```

pas seulement une couleur.

---

# 214. Opportunity visualization

Doit montrer :

```text
potential value
confidence
maturity
```

---

# 215. Interaction sound

Pas nécessaire en première version.

---

# 216. Futuristic details permitted

Avec retenue :

- fine glow ;
- animated edge pulse ;
- soft ambient gradient ;
- semantic halos ;
- spatial transitions.

---

# 217. Futuristic details prohibited

Éviter :

- hologrammes kitsch ;
- néons partout ;
- 3D gratuite ;
- glitch ;
- cyberpunk overload.

---

# 218. Product visual signature

La signature doit être :

> **Dark spatial intelligence + soft luminous semantics + extremely clean information hierarchy.**

---

# 219. Signature components

Les composants qui feront reconnaître Méridian immédiatement :

1. Atlas Domain Membrane
2. Twin Node
3. Trust Panel
4. Flore contextual panel
5. Investigation Progress Rail
6. Scenario Comparison
7. Transformation Episode Timeline

---

# 220. MVP Component Set

Priorité P0 :

```text
App Shell
Navigation
Top Bar
Search
Flore Panel
Card primitives
Trust Panel
Twin Node
Domain Membrane
Atlas Controls
Opportunity Card
Investigation Card
Hypothesis Card
Evidence Card
Scenario Card
Decision Card
Progress Job
```

---

# 221. P1 components

```text
Outcome Card
Learning Card
Transformation Episode
Before/After
Pattern Cluster
Advanced Atlas layers
```

---

# 222. Design System delivery order

```text
1. Foundations
2. App Shell
3. Card primitives
4. Trust components
5. Atlas primitives
6. Flore
7. Investigation
8. Decision
9. Outcome / Learning
10. Responsive / accessibility hardening
```

---

# 223. UX consistency checks

Avant release :

1. le même status est-il présenté pareil partout ?
2. confidence a-t-elle la même logique ?
3. maturity a-t-elle la même logique ?
4. Evidence est-elle toujours accessible ?
5. Unknown est-il visible ?
6. la décision humaine est-elle distinguée de la recommandation ?
7. les couleurs gardent-elles leur sens ?

---

# 224. Design QA checklist

```text
spacing
alignment
states
contrast
keyboard
loading
empty
error
responsive
motion
copy
```

---

# 225. Anti-patterns

## Component drift

Chaque équipe invente sa carte.

## Color drift

Le rouge signifie dix choses.

## Atlas visual chaos

Nœuds et edges non maîtrisés.

## AI purple everywhere

Tout l’IA en violet.

## Glass everywhere

Lisibilité dégradée.

## Huge cards

Densité faible artificielle.

## Tiny text

Dashboard illisible.

## Hidden focus

Mauvaise accessibilité.

## Motion without purpose

Décoration.

## Design tokens ignored

Dette UI rapide.

---

# 226. Critères de succès

Le Design System est réussi si :

1. Méridian est reconnaissable immédiatement ;
2. une Opportunity est cohérente partout ;
3. les concepts de confiance, maturité, preuve et inconnue sont visuellement stables ;
4. Atlas reste lisible malgré la complexité ;
5. Flore semble intégrée au produit et non ajoutée ;
6. Investigation et Decision utilisent les mêmes briques cognitives ;
7. le futurisme reste professionnel ;
8. les composants sont accessibles ;
9. les équipes front peuvent livrer rapidement sans réinventer le langage ;
10. le système peut évoluer sans perdre son identité.

---

# 227. Architecture finale du Design System

```text
                        MERIDIAN DESIGN SYSTEM
                                │
          ┌─────────────────────┼─────────────────────┐
          ▼                     ▼                     ▼
      FOUNDATIONS            PRIMITIVES          DOMAIN COMPONENTS
          │                     │                     │
   Color / Type           Buttons / Cards      Claim / Evidence
   Spacing / Motion       Panels / Inputs      Opportunity / Risk
   Grid / Radius          Drawers / Chips      Decision / Learning
          │                     │                     │
          └─────────────────────┼─────────────────────┘
                                ▼
                           COMPOSITES
                 ┌──────────────┼──────────────┐
                 ▼              ▼              ▼
               ATLAS          FLORE       INVESTIGATION
                 │              │              │
                 └──────────────┼──────────────┘
                                ▼
                         PRODUCT SURFACES
                Today · Decision · Memory · Sources
```

---

# 228. Vision finale

Le Design System de Méridian doit permettre de construire un produit qui paraît :

> **plus proche d’un système d’intelligence vivant que d’une application enterprise traditionnelle.**

Cette sensation ne vient pas d’un effet visuel isolé.

Elle vient de la cohérence entre :

- espace ;
- information ;
- temps ;
- mouvement ;
- confiance ;
- contexte.

Le produit doit rester spectaculaire lorsqu’on le découvre, mais calme lorsqu’on l’utilise chaque jour.

---

# 229. Conclusion

Le Design System concrétise la promesse visuelle de Méridian.

La direction cible est :

> **dark, spatiale, premium, lumineuse avec retenue, structurée par la preuve et l’incertitude.**

Les composants centraux sont :

- Atlas ;
- Trust Panel ;
- Flore ;
- Opportunity ;
- Investigation ;
- Scenario ;
- Decision ;
- Outcome ;
- Learning.

La priorité n’est pas simplement d’avoir une belle interface.

La priorité est d’obtenir :

> **un langage visuel capable de représenter une entreprise vivante, ses connaissances, ses incertitudes, ses décisions et son expérience.**

---

# 230. Prochain document

Le prochain document recommandé est :

> **MÉRIDIAN — Flore Conversational Architecture**

Il devra détailler :

- intents ;
- context resolution ;
- conversation state ;
- memory ;
- tool routing ;
- multi-twin queries ;
- investigation escalation ;
- trust/evidence exposure ;
- streaming ;
- conversational actions ;
- report generation ;
- contextual behavior by surface.

Ce sera le document qui fera de Flore non pas un chatbot, mais **l’interface conversationnelle de l’entreprise vivante**.
