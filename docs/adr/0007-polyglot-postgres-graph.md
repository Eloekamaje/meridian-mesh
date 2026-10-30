# ADR-0007 — Architecture polyglotte : Postgres pour la connaissance, graph store pour le Mesh

**Date :** 2026-10-30  
**Statut :** Accepté  
**Décideurs :** Produit, architecture, données, sécurité  
**Remplace :** ADR-0006 (Postgres unique, rejeté)  
**Complète :** ADR-0003, ADR-0005

## Contexte

L'ADR-0006 a interprété « pas de projection » comme « un seul Postgres ». C'est une erreur : un **graph store natif** n'est pas une projection s'il possède réellement la topologie du Mesh et qu'aucun objet n'est dupliqué.

Le parc cible dépasse **5 000 applications**. Les requêtes critiques sont :

- impact aval/amont sur plusieurs sauts ;
- dépendances et propagation ;
- domaines, capacités, processus, parcours ;
- chemins, cycles, centralité, clustering ;
- situations transverses et contradictions.

Postgres reste excellent pour les Claims, preuves, temporalité, transactions, audit et décisions. Il est moins adapté aux parcours de graphe profonds, aux traversées multi-relations et aux requêtes de voisinage à grande échelle.

## Décision

Méridian adopte une **architecture polyglotte à propriété claire** :

| Store | Objets possédés | Rôle |
|---|---|---|
| **Postgres** | Identité canonique du Twin (id, type, propriétaire, tenant, cycle de vie), Source, Artifact, Observation, Evidence, Claim, IdentityDecision, Decision, Initiative, Outcome, Learning, audit, temporalité | Vérité transactionnelle, preuve, gouvernance, recherche plein texte |
| **Graph store** (Neo4j ou Neptune) | Topologie : nœud Twin référençant l'identité Postgres, Relation, Domain, Capability, Process, Journey, Team, Situation, Opportunity, Risk, impacts | Vérité du Mesh : relations, émergence, parcours |
| **Mongo** | Aucun objet canonique | Legacy de démonstration, à migrer puis retirer |

### Règle de propriété

- **Un aspect d'objet a un seul store propriétaire.** L'identité du Twin est Postgres ; sa topologie est graphe. Aucun objet n'est copié intégralement dans l'autre store.
- Les références croisées sont des **IDs** : un Claim Postgres référence `twin_id` ; une relation du graphe référence des `claim_id`/`evidence_id` Postgres. Le nœud Twin du graphe ne porte que l'ID et les propriétés utiles au parcours, pas une copie de la fiche.
- Le graphe **n'est pas une projection** : il est écrit par la découverte et les décisions de topologie, pas reconstruit depuis Postgres.
- Postgres **n'est pas une projection** du graphe : les Claims et preuves y naissent.
- La coordination inter-stores passe par des **événements/IDs** et des opérations idempotentes ; pas de double écriture du même objet, pas de read model dupliqué.

### Choix du graph store

- **AWS** : Neptune (managé, HA, serverless) ;
- **On-prem / cloud-agnostique** : Neo4j (Community/Enterprise) ;
- Une **interface `GraphStore`** isole le produit du vendeur : `upsert_twin`, `upsert_relation`, `voisins`, `chemins`, `impact`, `situations`.
- Le choix est un déploiement, pas une réécriture métier.

### Recherche

- **Postgres** : `tsvector`/GIN pour Claims, preuves, décisions, documents ; `pg_trgm`/`pgvector` dans Postgres si nécessaire.
- **Graph store** : index de nœuds/relations pour la topologie.
- **Pas d'OpenSearch** ni de moteur de recherche séparé.

### Ce que l'on ne fait pas

- Pas de Neptune/Neo4j comme **projection** reconstruite depuis Postgres.
- Pas de Postgres comme copie du graphe.
- Pas de Mongo canonique.
- Pas de double écriture du même objet.
- Pas de « graph store » qui ne porte que des IDs sans relations : il doit posséder la topologie.

## Alternatives considérées

### Alternative 1 — Postgres unique (ADR-0006)
- **Avantages** : une seule base, transactions, simplicité.
- **Inconvénients** : parcours profonds, impact multi-sauts, clustering et voisinage à 5 000+ apps ; requêtes récursives coûteuses et difficiles à optimiser.
- **Pourquoi rejetée** : le graphe est le cœur du Mesh, pas un détail de stockage.

### Alternative 2 — Graph store comme projection
- **Avantages** : Postgres reste seule vérité ; graphe performant.
- **Inconvénients** : duplication, reconstruction, cohérence, double sécurité.
- **Pourquoi rejetée** : c'est exactement la projection refusée.

### Alternative 3 — Mongo canonique
- **Avantages** : flexibilité.
- **Inconvénients** : transactions, temporalité, RLS, audit, graphe faibles.
- **Pourquoi rejetée** : la vérité d'entreprise exige un noyau transactionnel.

### Alternative 4 — OpenSearch + graphe + Postgres
- **Avantages** : recherche très performante.
- **Inconvénients** : trois stores, trois cohérences, trois coûts.
- **Pourquoi rejetée** : Postgres FTS suffit pour le corpus initial ; OpenSearch n'est pas nécessaire.

## Conséquences

### Positives

- Parcours de graphe natifs et performants à 5 000+ applications.
- Postgres reste le noyau de preuve, de temporalité et de décision.
- Chaque objet a un propriétaire clair ; pas de double vérité.
- Neptune/Neo4j peuvent évoluer sans changer le modèle métier.
- Le Mesh peut être interrogé par impact, voisinage, domaine, capacité, processus et parcours.

### Négatives / coûts

- Deux stores à exploiter, sauvegarder, sécuriser et surveiller.
- Pas de transaction distribuée native : sagas/événements/idempotence.
- Les références croisées ne sont pas des FK.
- Il faut définir et tester la cohérence de propriété.
- Migration Mongo → Postgres/graphe nécessaire.

### Risques

- **Double écriture** : un objet écrit dans les deux stores. Mitigation : propriété exclusive, tests d'architecture.
- **Références orphelines** : IDs sans cible. Mitigation : validation, réconciliation, events.
- **Divergence de permissions** : appliquer le tenant et le périmètre aux deux stores.
- **Lock-in** : interface `GraphStore`, pas de Cypher dans le domaine métier.
- **Coût** : dimensionner Neptune/Neo4j ; 5 000 nœuds restent modestes, les relations/claims sont le vrai volume.

## Critères d'acceptation

1. Un Twin et ses relations vivent dans le graph store ; un Claim vit dans Postgres ; aucun des deux n'est une copie complète de l'autre.
2. Les parcours de voisinage/impact/chemins sont exécutés par le graph store, pas par une CTE Postgres de production.
3. Postgres conserve les Claims, preuves, temporalité, décisions, outcomes et l'audit.
4. Aucun objet canonique n'est écrit dans Mongo.
5. Une interface `GraphStore` permet de changer Neo4j/Neptune sans toucher au domaine.
6. Les tests couvrent : propriété unique, références croisées, tenant, impact, absence de projection.
7. Aucun nouveau store sans ADR.

## Références

- [PRD-001](../prd/PRD-001-enterprise-intelligence-mesh.md)
- [ADR-0003](0003-mesh-transversal-intelligence.md)
- [ADR-0005](0005-enterprise-object-model.md)
- [ADR-0006](0006-postgres-unique-sans-projection.md) — remplacé
