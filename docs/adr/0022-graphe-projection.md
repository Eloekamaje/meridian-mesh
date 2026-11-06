# ADR-0022 — Le graphe est une projection Postgres

**Date :** 2026-11-03  
**Statut :** proposed — remplace la propriété contradictoire d'ADR-0007  
**Décideurs :** Architecture, Données, Runtime

## Décision

Le graphe Neo4j/Neptune est une **projection idempotente et reconstructible** de la topologie
canonique Postgres. Il n'est pas une seconde vérité.

- Postgres possède les relations canoniques, les Claims, les preuves et les décisions.
- Le projector consomme l'outbox et applique les upserts.
- Chaque lecture expose `graph_version` et `stale_since`.
- Mongo n'est plus une source du chemin RAG.
- Le graphe peut être reconstruit depuis zéro.

ADR-0007 reste l'historique du choix polyglotte ; sa clause « le graphe n'est pas une projection »
est remplacée par la présente décision.

## Conséquences

- Une panne Neo4j ne bloque pas les écritures.
- Les tests de parité et de rejeu deviennent obligatoires.
- Les communautés et les rapports sont des index dérivés versionnés.
