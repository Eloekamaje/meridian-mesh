# ADR-0024 — Cycle de vie des embeddings et recherche vectorielle

**Date :** 2026-11-03  
**Statut :** proposed  
**Décideurs :** Architecture, Données, SRE

## Décision

- Les embeddings sont stockés dans Postgres avec `embedding_model` et `embedding_dim`.
- Un changement de modèle ou de dimension déclenche un ré-embedding ; aucun mélange silencieux.
- La recherche à l'échelle utilise pgvector/ANN ou un index GIN/tsvector ; le scan Python de
  400 chunks est un mode dégradé explicitement signalé.
- Le backfill et la réindexation sont des workers idempotents, pas des effets de bord du chat.
- Une réponse sans provider réel est lexicale + graphe, jamais un faux vecteur.

## Conséquences

- Migration versionnée de `document_chunk`.
- Job de ré-embedding et métrique `embeddings_stale`.
- Refus des vecteurs de dimensions différentes au classement.
