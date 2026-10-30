# ADR-0006 — Postgres unique, sans projection ni read model séparé

**Date :** 2026-10-30  
**Statut :** Remplacé par ADR-0007 — décision rejetée  
**Décideurs :** Produit, architecture, données, sécurité  
**Complète :** ADR-0003, ADR-0005  
**Remplacé par :** [ADR-0007](0007-polyglot-postgres-graph.md)

> **Correction du 2026-10-30.** Cette ADR a surcorrigé « pas de projection » en « un seul Postgres ». La décision courante est l'architecture polyglotte d'ADR-0007 : Postgres pour la connaissance et la preuve, graph store natif pour la topologie du Mesh. Le corps ci-dessous reste l'historique du raisonnement ; il ne doit pas être appliqué.

## Contexte

Le parc cible dépasse **5 000 applications**, avec plusieurs millions de Claims, relations, interfaces et observations possibles. Une première recommandation proposait :

- Postgres comme source canonique ;
- Neptune/Neo4j comme projection graphe ;
- OpenSearch comme projection recherche ;
- Mongo comme projection ou démo.

Le produit refuse les projections : elles créent un second modèle de vérité, des dérives de cohérence, une reconstruction à maintenir et une surface d'exploitation supplémentaire. La contrainte est donc :

> **Un seul Postgres canonique et servant. Aucune projection externe, aucun read model séparé, aucune double écriture.**

## Décision

Méridian utilise **Postgres comme unique système de vérité et comme moteur de lecture** pour les objets d'entreprise, les Claims, les preuves, les relations, les situations, les décisions et les apprentissages.

- **Graphe** : table canonique `relation` + requêtes récursives (`WITH RECURSIVE`) bornées, avec indexes `(tenant_id, source)` et `(tenant_id, target)`.
- **Recherche** : index GIN Postgres sur `to_tsvector('french', ...)` ; repli `ILIKE` pour les requêtes partielles ; `pg_trgm`/`pgvector` peuvent compléter **dans Postgres** si nécessaire.
- **Objets** : `jumeau.type` (7 types), `claim.mode` (5 modes), JSONB pour les attributs flexibles, colonnes typées pour les filtres.
- **Temporalité** : `valid_from`, `valid_to`, dates d'observation et de création dans Postgres.
- **Échelle** : partitionnement par tenant/domaine, indexes, read replicas **du même schéma**, pool de connexions. Si nécessaire, Citus ou un Postgres distribué — jamais une autre base de vérité.
- **Aucune projection** : pas de Neptune, pas d'OpenSearch, pas de Mongo canonique, pas de matérialisation externe. Les DTO/API en mémoire ne sont pas des stores.
- **Mongo** : les collections existantes sont un **legacy de démonstration** à migrer vers Postgres ; elles ne doivent pas recevoir de nouvelles écritures canoniques.

### Règles de requête

- Toute lecture filtrée par `tenant_id`.
- Parcours de graphe borné (`MAX_PROFONDEUR = 8`) et sans cycle.
- Recherche top-k bornée (`MAX_RESULTATS = 50`), jamais un scan complet exposé à l'UI.
- Une requête lente est un problème d'index/partitionnement, pas une raison d'ajouter une projection.
- Les relations fermées (`valid_to`) sont exclues des parcours courants.

## Alternatives considérées

### Alternative 1 — Projections graphe/recherche
- **Avantages** : performances de traversée et de recherche à très grande échelle.
- **Inconvénients** : double vérité, cohérence, reconstruction, coût, sécurité, dérive.
- **Pourquoi rejetée** : refus produit explicite ; 5 000 applications restent dans l'ordre de grandeur de Postgres.

### Alternative 2 — Mongo comme source canonique
- **Avantages** : flexibilité de documents.
- **Inconvénients** : transactions, temporalité, RLS, joins, audit et requêtes de graphe plus faibles.
- **Pourquoi rejetée** : la vérité d'entreprise exige un noyau transactionnel et temporel.

### Alternative 3 — Neptune/OpenSearch
- **Avantages** : graphe et recherche managés.
- **Inconvénients** : deux systèmes à synchroniser, deux modèles, deux sécurité, deux coûts.
- **Pourquoi rejetée** : projection déguisée.

### Alternative 4 — Materialized views
- **Avantages** : accélération interne.
- **Inconvénients** : duplication, refresh, fraîcheur, dérive.
- **Pourquoi rejetée** : le produit refuse les projections ; on préfère indexes/partitions/requêtes bornées.

## Conséquences

### Positives

- Une seule vérité, une seule sauvegarde, un seul modèle d'audit et de sécurité.
- Les Claims, relations, situations et décisions sont transactionnels et temporels.
- Moins de composants à exploiter.
- La recherche et le graphe restent dans le même tenant et le même périmètre.
- Aucune reconstruction de projection à maintenir.

### Négatives / coûts

- La performance dépend fortement des index, du partitionnement et de la discipline de requête.
- Les parcours très profonds ou les recherches très larges doivent être bornés.
- Un `tsvector` français ne remplace pas un moteur de recherche spécialisé ; il faut accepter cette limite ou ajouter des extensions Postgres.
- Les collections Mongo existantes doivent être migrées ; jusque-là, elles restent une dette de démonstration.
- Les read replicas ne servent que la lecture et doivent rester sur le même schéma.

### Risques

- **Requête de graphe coûteuse** : borner profondeur, indexes, plans EXPLAIN, tests de charge.
- **Recherche insuffisante** : GIN/tsvector + trigram, puis pgvector dans Postgres.
- **Croissance > Postgres** : partitionnement, Citus/read replicas ; dernière option : revoir l'ADR, pas ajouter une projection silencieuse.
- **Migration Mongo** : double lecture temporaire, backfill, tests d'isolation, puis fermeture des écritures Mongo canoniques.

## Critères d'acceptation

1. Aucun chemin canonique n'écrit ou ne lit une projection externe.
2. `relation` et les parcours sont dans Postgres, filtrés par tenant et bornés.
3. La recherche de Twins/Claims utilise les index Postgres, sans OpenSearch.
4. `jumeau.type` et `claim.mode` sont présents et contraints.
5. Les tests couvrent voisins, chemins, cycles, tenant, recherche et absence de fuite.
6. Une requête de parcours à 5 000 nœuds reste sous le budget p95 défini par produit.
7. Aucun nouveau store externe n'est ajouté sans nouvel ADR.

## Références

- [PRD-001](../prd/PRD-001-enterprise-intelligence-mesh.md)
- [ADR-0003](0003-mesh-transversal-intelligence.md)
- [ADR-0005](0005-enterprise-object-model.md)
- `backend/jumeau/pg_graphe.py`, `backend/jumeau/pg_recherche.py`, `backend/jumeau/schema.sql`
