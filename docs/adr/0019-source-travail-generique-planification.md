# ADR-0019: Capacité, charge, prévision et budget comme domaine générique, trackers comme adapters

**Date**: 2026-11-01
**Status**: accepted
**Deciders**: Utilisateur

## Context

Le pilotage d'une équipe — capacité, charge, planification, prévision, budget — ne doit pas être
construit dans l'adapter Jira. Jira n'est qu'un outil parmi Azure DevOps, Linear, GitHub Issues, Asana,
Monday, ClickUp, Trello, ServiceNow, etc. Les modèles de données diffèrent : story points ou heures,
sprints ou flux, équipes ou composants, worklogs ou absences, releases ou jalons.

Le code actuel contient déjà un lecteur Jira pour les preuves (`connectors/jira.py`) et une source de
trajectoire. Ce lecteur ne doit pas devenir le modèle de gestion du travail : cela figerait le produit sur
Jira, mélangerait preuve et planification, et rendrait les comparaisons multi-équipes fausses.

Le budget est encore un autre domaine : il vient de Finance, d'un ERP, de Tempo ou de Jira Align, et la
valeur vient du Value Ledger. Un story point n'est pas une unité monétaire.

## Decision

- Créer une capacité produit **Pilotage de la capacité, de la charge et de la prévision** avec un modèle
  canonique : équipe, compétence, disponibilité, élément de travail, estimation, cycle, release,
  dépendance, plan, prévision, budget, coût, valeur.
- Définir un port **`SourceTravail`** générique. Chaque outil de gestion du travail est un adapter qui
  déclare ses capacités (sprints, points, heures, worklogs, dépendances, releases, historique, équipes).
- Séparer les sources : `SourcePeople` (équipes, absences, compétences), `SourceFinance` (budget, taux),
  `SourceValeur` (Value Ledger), `SourceIncidents` (ITSM).
- Construire la prévision dans l'application, indépendamment de l'éditeur. Elle est probabiliste
  (P50/P85/P95), déterministe et reproductible ; le LLM ne fait pas l'arithmétique.
- Le budget et la valeur restent des objets financiers distincts ; aucun story point n'est converti en
  devise.
- Jira reste un adapter de preuve et de trajectoire **et** devient un adapter `SourceTravail`, sans que
  le domaine ou l'UI produit ne dépendent de son nom.

## Alternatives Considered

### Alternative 1: Construire la fonctionnalité dans l'adapter Jira
- **Pros** : rapide pour un premier client ; champs et API connus.
- **Cons** : lock-in, modèle contaminé par Jira, impossible de comparer plusieurs outils, dette de
  migration.
- **Why not** : le besoin est explicitement multi-outils.

### Alternative 2: Ne garder qu'un plus petit dénominateur commun
- **Pros** : modèle simple, adapters faciles.
- **Cons** : perte des sprints, de la vélocité, des dépendances et des releases ; prévisions pauvres.
- **Why not** : les capacités déclarées et la dégradation gracieuse couvrent mieux les différences.

### Alternative 3: Utiliser Jira Align ou Advanced Roadmaps comme moteur
- **Pros** : capacité et planification déjà outillées.
- **Cons** : dépendance à un éditeur, pas de sources non-Jira, pas de lien natif au graphe Méridian ni au
  Value Ledger, coût de licence.
- **Why not** : Méridian doit rester la couche transverse, pas un revendeur d'un plan Jira.

### Alternative 4: Construire une suite complète de gestion de projet
- **Pros** : contrôle total.
- **Cons** : duplication de Jira/ADO, périmètre immense, aucun avantage différenciant.
- **Why not** : Méridian agrège et éclaire ; il ne remplace pas le tracker.

## Consequences

### Positive
- La même fonctionnalité et la même prévision marchent avec plusieurs outils.
- Le modèle reste propre et testable ; les différences d'éditeur vivent dans les adapters.
- Le budget et la valeur ne sont pas contaminés par les story points.
- Le graphe, les incidents et le Value Ledger peuvent enrichir la planification.

### Negative
- Il faut écrire et maintenir plusieurs adapters.
- Certains outils ne fournissent pas l'historique ou les estimations : l'UI doit dégrader et s'abstenir.
- Le mapping équipe/compétence reste un travail de gouvernance.
- Le coût initial est plus élevé qu'un simple écran Jira.

### Risks
- **Fausse comparabilité** : ne jamais additionner les points entre équipes ; unité et équipe explicites.
- **Double comptage multi-sources** : source primaire par équipe/élément et déduplication.
- **Surveillance individuelle** : agrégation équipe et pas de classement de personnes.
- **Prévision trop confiante** : P50/P85/P95, calibration, abstention.
- **Budget improvisé** : source Finance obligatoire, Value Ledger pour la valeur.

## Acceptance Criteria

1. Le domaine et l'UI de capacité/charge/prévision ne contiennent aucun nom d'éditeur.
2. Deux adapters de travail différents produisent la même vue canonique.
3. Un adapter déclare ses capacités ; une donnée absente est `non observée`, jamais zéro.
4. Les story points ne sont jamais additionnés entre équipes.
5. La prévision s'abstient sans historique et produit P50/P85/P95 avec hypothèses.
6. Le budget vient d'une source Finance/Value Ledger et n'est jamais déduit des points.
7. Les tests couvrent deux adapters, l'absence de données, le multi-source et le budget séparé.

## References

- [PRD-003](../prd/PRD-003-capacite-charge-prevision-budget.md)
- [PRD-001](../prd/PRD-001-enterprise-intelligence-mesh.md)
- [PRD-002](../prd/PRD-002-memoire-contexte-raisonnement.md)
- [ADR-0009](0009-value-ledger.md)
