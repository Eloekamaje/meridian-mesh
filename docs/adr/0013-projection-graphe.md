# ADR-0013: Projection graphe et cohérence éventuelle

**Date**: 2026-10-31
**Status**: accepted
**Deciders**: Panel architecture (Principal Architect, Runtime, IA, Staff) + utilisateur

## Context

Postgres porte les identités, Claims, preuves et objets canoniques ; Neo4j porte la topologie et les impacts.
Aujourd'hui, certaines écritures alimentent les deux stores dans le même flux applicatif, sans outbox ni
version de graphe. Un crash ou une panne Neo4j peut donc produire un graphe en avance, en retard ou
irréconciliable.

Le graphe doit rester reconstructible et ne jamais devenir la vérité première.

## Decision

Le graphe est une **projection événementielle idempotente** de Postgres.

- L'écriture canonique et l'événement sont dans l'outbox Postgres.
- Un **projector** consomme l'outbox et applique les upserts Neo4j par `tenant`, `twin_id` et `version`.
- Chaque lecture graphe expose `graph_version` et `stale_since`.
- Le projector est rejouable et reconstructible depuis zéro.
- Aucune écriture applicative directe vers Neo4j.
- Une panne Neo4j ne bloque pas les écritures canoniques ; l'outbox retarde et reprend.
- Les requêtes d'impact indiquent explicitement la fraîcheur du graphe.

### Mise en œuvre

`JUMEAU_GRAPH_PROJECTION` choisit le chemin : `direct` (défaut, compatibilité avec le pilote) fait
l'upsert immédiat puis planifie l'outbox ; `outbox` n'écrit pas dans le graphe et n'enfile que
`graph.synchroniser`, consommé par `python -m jumeau.execution.outbox_worker`. Une valeur inconnue est
refusée sans écriture. Runbook : [projection-graphe.md](../architecture/projection-graphe.md).

## Alternatives Considered

### Alternative 1: Double écriture directe
- **Pros**: latence minimale.
- **Cons**: incohérence, pas de rejeu, couplage applicatif au graphe.
- **Why not**: incompatible avec la source de vérité unique.

### Alternative 2: Transaction distribuée Postgres/Neo4j
- **Pros**: cohérence forte.
- **Cons**: complexité, disponibilité, couplage, support limité.
- **Why not**: surdimensionné et fragile.

### Alternative 3: Pas de graphe, tout en Postgres
- **Pros**: un seul store.
- **Cons**: perte des requêtes de parcours et d'impact.
- **Why not**: le graphe est un besoin produit réel.

### Alternative 4: CDC externe (Debezium)
- **Pros**: découplage maximal.
- **Cons**: infrastructure, exploitation, pas nécessaire aujourd'hui.
- **Why not**: l'outbox applicatif suffit et reste testable.

## Consequences

### Positive
- Le graphe est reconstructible et auditable.
- Les écritures canoniques ne dépendent pas de Neo4j.
- La fraîcheur est visible dans l'API et l'UI.
- Le projector peut être scalé indépendamment.

### Negative
- Cohérence éventuelle entre Postgres et Neo4j.
- Un décalage peut apparaître en cas de panne ou de backlog.
- Les tests doivent couvrir le rejeu et la parité.

### Risks
- Un projector non idempotent qui duplique des arêtes.
- Une UI qui présente le graphe comme temps réel.
- Un schéma d'événement instable.
- Oublier la suppression/archivage dans la projection.

## Acceptance Criteria

1. Aucune route n'écrit directement dans Neo4j.
2. Le projector est idempotent : un événement rejoué ne change pas le résultat.
3. Le graphe peut être reconstruit depuis Postgres sans perte.
4. Les lectures exposent `graph_version` et `stale_since`.
5. Une panne Neo4j n'empêche pas une écriture canonique.
6. Les tests couvrent rejeu, backlog, suppression, parité.
7. Les impacts affichent la fraîcheur.

## References

- [ADR-0007](0007-polyglot-postgres-graph.md), [ADR-0012](0012-outbox-idempotence.md)
- `backend/jumeau/graphe_sync.py`, `backend/jumeau/graphe_neo4j.py`, `backend/jumeau/graph_store.py`
- `backend/jumeau/migration_canonique.py`, `backend/jumeau/parite_mongo.py`
