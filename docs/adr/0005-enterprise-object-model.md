# ADR-0005 — Modèle d'entreprise : huit familles d'objets et Twins non applicatifs

**Date :** 2026-10-30  
**Statut :** Accepté  
**Décideurs :** Produit, architecture d'entreprise, données, sécurité  
**Complète :** ADR-0003  
**Remplace :** la réduction implicite « Twin = application » et « Mesh = relations entre applications ».

## Contexte

L'implémentation initiale est centrée sur des jumeaux **applicatifs** : code, sources, Claims, relations, Atlas. C'est un bon point d'amorçage, mais ce n'est pas le modèle d'entreprise complet.

Le domaine Méridian définit huit familles d'objets et plusieurs types de Twin. Si le code et les agents ne connaissent que l'application :

- les processus, capacités, parcours, organisations, produits et domaines de données sont invisibles ;
- les situations transverses sont difficiles à exprimer ;
- les investigations et décisions n'ont pas d'objets de premier ordre ;
- le Mesh devient un graphe d'applications, pas une intelligence d'entreprise ;
- les outils et les agents restent app-first.

## Décision

Méridian adopte le **modèle d'entreprise en huit familles** et les **types de Twin** du Domain Model.

### Familles

1. **Identité & structure** : Twin, Domain, Capability, Application, Process, Journey, Team.
2. **Sources & preuves** : Source, Artifact, Observation, Evidence.
3. **Connaissance** : Claim, Relationship, Unknown, Contradiction.
4. **Émergence** : Signal, Situation, Expression, Opportunity, Risk.
5. **Investigation** : Investigation, Hypothesis, Expert, ExpertContribution.
6. **Décision** : Scenario, Decision, Initiative.
7. **Résultat & apprentissage** : Outcome, Learning.
8. **Interaction & gouvernance** : UserContext, Scope, Permission, Annotation, Subscription.

### Agrégats

`Twin`, `Claim`, `Situation`, `Opportunity`, `Risk`, `Investigation`, `Decision`, `Initiative`, `Learning`, `Source`, `Domain`.

### Types de Twin

`APPLICATION`, `PROCESS`, `CAPABILITY`, `JOURNEY`, `ORGANIZATION`, `PRODUCT`, `DATA_DOMAIN`.

L'application est le **premier type implémenté**, pas le type universel.

### Modes

`DECLARED`, `OBSERVED`, `INFERRED`, `PROPOSED`, `CONFIRMED`.

### Temporalité

Tout objet important porte : date d'observation, date d'apprentissage, période de validité, version, preuve, confiance, maturité, contradiction éventuelle.

### Cycle

> **Source → Observation → Claim → Mesh → Signal → Expression → Opportunité → Investigation → Décision → Initiative → Outcome → Apprentissage**

### Règle d'or

**Le Twin comprend localement ; le Mesh comprend transversalement.** Aucun Twin ne doit être présenté comme la vérité de l'entreprise.

## Alternatives considérées

### Alternative 1 — Twin = application uniquement
- **Avantages** : simplicité, alignement avec le code et l'Atlas.
- **Inconvénients** : ignore les processus, capacités, parcours, organisations, produits et données.
- **Pourquoi rejetée** : le modèle de domaine dit explicitement que le Twin n'est pas limité à l'application.

### Alternative 2 — Modèle CMDB classique
- **Avantages** : référentiel connu, relations déclarées.
- **Inconvénients** : statique, pauvre en Claims, preuves, temporalité et émergence.
- **Pourquoi rejetée** : Méridian n'est pas un CMDB.

### Alternative 3 — Claims uniquement
- **Avantages** : souple.
- **Inconvénients** : pas d'objets de décision, d'investigation, d'outcome ou d'apprentissage.
- **Pourquoi rejetée** : la valeur produit est dans la boucle complète, pas dans le seul stock de connaissances.

### Alternative 4 — Modèle applicatif étendu par des tags
- **Avantages** : peu de changements.
- **Inconvénients** : les processus et capacités restent des attributs, pas des entités ; les relations et décisions restent faibles.
- **Pourquoi rejetée** : les objets majeurs doivent être explicites, identifiables et traçables.

## Conséquences

### Positives

- Le Mesh peut relier applications, processus, capacités et parcours.
- Les situations et décisions deviennent des objets de premier ordre.
- Les outils peuvent être organisés par capacité et type d'objet.
- La conception et la transformation peuvent être situées dans le modèle d'entreprise.
- Les projections par rôle deviennent possibles.

### Négatives / coûts

- Schéma et APIs plus riches.
- Discovery plus complexe : il faut savoir reconnaître un processus ou une capacité.
- UI à adapter : l'Atlas ne doit pas être le seul point d'entrée.
- Migration progressive nécessaire : l'application reste le premier type.

### Risques

- **Sur-modélisation** : créer des objets sans usage. Mitigation : chaque objet doit avoir un cas d'usage, une API et une projection.
- **Confusion de types** : processus vs capacité vs parcours. Mitigation : définitions du Domain Model, revue de modèle.
- **Données incomplètes** : un Twin de processus peut être partiel. Mitigation : modes, inconnues, fraîcheur.

## Plan d'implémentation

1. Garder `APPLICATION` comme premier type opérationnel.
2. Ajouter le schéma des huit familles et les agrégats sans casser les Twins existants.
3. Ajouter `PROCESS` et `CAPABILITY` en lecture, puis `JOURNEY`.
4. Relier les Claims et relations aux nouveaux types.
5. Exposer les situations, investigations, décisions, initiatives, outcomes et apprentissages.
6. Adapter les projections et les outils par capacité.
7. Ajouter les tests d'architecture : aucun outil ne doit supposer que Twin = application.

## Critères d'acceptation

1. Un Twin `PROCESS`, `CAPABILITY` ou `JOURNEY` peut être créé et lu sans modifier le noyau.
2. Un Claim peut porter sur une application, un processus, une capacité ou un parcours.
3. Une situation peut relier plusieurs types de Twin.
4. Une décision peut être reliée à une investigation, une initiative, un outcome et un apprentissage.
5. Les modes et la temporalité sont présents sur les objets importants.
6. L'UI ne présente pas le Twin applicatif comme le seul objet du produit.
7. Un test d'architecture interdit `Twin == application` dans le noyau.

## Références

- `docs/MERIDIAN_Domain_Model_Information_Architecture_v1.md`
- `docs/MERIDIAN_Functional_Architecture_v1.md`
- `docs/MERIDIAN_Knowledge_Claims_Architecture_v1.md`
- [PRD-001](../prd/PRD-001-enterprise-intelligence-mesh.md)
- [ADR-0003](0003-mesh-transversal-intelligence.md)
- [ADR-0004](0004-capability-first-harness.md)
