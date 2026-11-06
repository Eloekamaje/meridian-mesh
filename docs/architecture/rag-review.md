# Revue RAG / GraphRAG — contre-expertise et décisions

**Date :** 2026-11-03  
**Portée :** architecture cible de retrieval documentaire et GraphRAG  
**Documents relus :** PRD-001, PRD-002, PRD-004, ADR-0007, `rag-bedrock.md`  
**Statut :** revue appliquée ; ADR-0021 à ADR-0025 proposés

## Verdict de la revue

Le retrieval est une capacité interne au service de la preuve, pas la proposition de valeur.
La cible doit rester :

```text
documents → candidats → preuve → ContextePack → raisonnement → décision
```

Un chunk ou une communauté ne devient jamais une vérité canonique.

## Contradictions relevées

- **ADR-0007 vs ADR-0013** : le graphe est déclaré tantôt propriétaire de la topologie, tantôt
  projection reconstructible. Le code doit trancher avant une exploitation multi-store.
- **Deux chemins de retrieval** : `/analyser` passe par le Context Resolver et le Context Pack ;
  le chat injecte directement documents et communautés. Les exigences CTX-003/006/008 ne sont
  pas tenues de la même façon.
- **ACL live** : les documents lus en direct pouvaient contourner l'ACL avant le prompt.
- **Tenant** : le chat utilisait `JUMEAU_TENANT` au lieu du tenant de requête.
- **Score** : la fraîcheur seule pouvait faire entrer un chunk sans pertinence.
- **RLS** : les stores documentaires n'ouvraient pas le contexte tenant.
- **Index** : chargement des 400 chunks récents en Python, pas d'index vectoriel.
- **Dimensions** : un changement de modèle pouvait annuler silencieusement le signal sémantique.
- **Prompt injection** : documents et web étaient transmis comme du texte brut.

## Corrections appliquées

- ACL appliquée aux documents live avant le prompt ;
- tenant de requête utilisé pour le RAG ;
- contexte tenant posé dans les stores `document_chunk`, `graph_community`, sources ;
- score de pertinence nul si lexical/sémantique/graphe sont nuls ;
- embeddings partiels refusés plutôt que tronqués ;
- documents délimités comme données dans le prompt ;
- communautés hiérarchiques et rapports précompilés ;
- verrou Redis par Travail ;
- images analysées par Vision avec opt-in externe ;
- panneau UI « Contexte retrouvé ».

## Décisions à formaliser

1. **ADR-0021 — Retrieval unifié** : un seul service de retrieval, produisant des preuves
   documentaires candidates et un ContextePack unique.
2. **ADR-0022 — Propriété du graphe** : trancher ADR-0007/ADR-0013 et versionner la topologie.
3. **ADR-0023 — ACL de retrieval** : ACL par document, pas seulement par source ; fail-closed.
4. **ADR-0024 — Cycle de vie des embeddings** : modèle, dimension, migration et ré-embedding.

## Limites assumées

- Les ACL natives Confluence/SharePoint ne sont pas encore synchronisées.
- L'index vectoriel reste un scan borné en Python ; pgvector/ANN n'est pas activé.
- Les rapports de communautés ne sont pas filtrés par ACL documentaire.
- Le backfill et le calcul des communautés sont des scripts, pas encore des workers planifiés.
