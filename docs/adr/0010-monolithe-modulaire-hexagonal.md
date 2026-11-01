# ADR-0010: Monolithe modulaire hexagonal, ports et adapters

**Date**: 2026-10-31
**Status**: accepted
**Deciders**: Panel architecture (Principal Architect, Runtime, IA, Staff) + utilisateur

## Context

Méridian est aujourd'hui un monolithe FastAPI modulaire. Les routes, les cas d'usage, l'accès aux stores et
certains détails d'infrastructure cohabitent dans `backend/server.py` et `backend/jumeau/*.py`. Le produit
fonctionne, les tests sont verts, mais les frontières ne sont pas explicites : un routeur peut appeler
directement Postgres, Neo4j, Redis, Vault, Strands ou un connecteur.

La cible doit rester simple à opérer, démontrable en Docker, migrable par étranglement et déployable sur AWS
sans que le domaine dépende d'AWS. Un découpage en microservices n'est pas justifié aujourd'hui.

## Decision

Adopter un **monolithe modulaire hexagonal** :

- le **domaine** ne dépend que du langage et de ses propres types ;
- l'**application** porte les commandes, requêtes, process managers, politiques et ports ;
- les **adapters inbound** (HTTP, SSE, MCP, CLI, webhook, scheduler) traduisent vers l'application ;
- les **adapters outbound** (Postgres, Neo4j, Mongo, Redis, Vault, LLM, connecteurs, AWS) implémentent les ports ;
- un **composition root** unique assemble les adapters au démarrage.

Un port n'est créé que s'il existe une vraie frontière : deuxième implémentation prévue, secret, effet externe,
isolation tenant ou besoin de test sans infrastructure. Le domaine n'importe ni FastAPI, ni Strands, ni Bedrock,
ni SDK AWS, ni client Neo4j.

Cible de dépendance :

```text
adapters/inbound ─┐
                  ├──> application ──> domain
adapters/outbound ┘         │
                            └──> ports
```

## Alternatives Considered

### Alternative 1: Microservices dès maintenant
- **Pros**: isolation de charge et de déploiement.
- **Cons**: réseau, transactions distribuées, exploitation et latence prématurés.
- **Why not**: le goulot actuel est la durabilité du runtime, pas le découpage réseau.

### Alternative 2: Réécriture hexagonale globale
- **Pros**: propreté immédiate.
- **Cons**: big-bang, régression fonctionnelle, perte du produit démontrable.
- **Why not**: migration par cas d'usage obligatoire ; les 1 702 tests doivent rester utiles.

### Alternative 3: Repository par table et couches cérémonielles
- **Pros**: séparation apparente.
- **Cons**: abstractions sans second implémenteur, dette de maintenance.
- **Why not**: l'hexagone est une règle de dépendance, pas un nombre de dossiers.

## Consequences

### Positive
- Le cœur est testable sans Postgres, Neo4j, LLM ni AWS.
- Les adapters AWS sont remplaçables sans toucher au domaine.
- La migration peut se faire route par route, cas d'usage par cas d'usage.
- Les frontières tenant, secrets, effets et streaming deviennent explicites.

### Negative
- Duplication temporaire pendant la strangulation.
- Coût de composition root et de tests de conformité des adapters.
- Risque d'abstraction prématurée si les ports sont multipliés.

### Risks
- Un monolithe distribué déguisé si l'on découpe trop tôt.
- Des ports trop génériques qui fuient les spécificités LLM/streaming.
- Une migration qui déplace les fichiers sans corriger le runtime.

## Acceptance Criteria

1. Le domaine ne contient aucun import FastAPI, Strands, Bedrock, AWS, Neo4j, Redis ou Vault.
2. Chaque port a une justification écrite et, à terme, au moins deux adapters ou une frontière de sûreté.
3. Une nouvelle route ne peut appeler un store qu'à travers un cas d'usage applicatif.
4. Le premier slice `/analyser` passe par l'application et un port de runtime.
5. Les tests de domaine tournent sans infrastructure.

## References

- [ADR-0003](0003-mesh-transversal-intelligence.md), [ADR-0007](0007-polyglot-postgres-graph.md)
- [ADR-0011](0011-runtime-durable-postgres.md), [ADR-0012](0012-outbox-idempotence.md)
- [ADR-0015](0015-frontiere-agent-workflow-outils.md)
- `backend/server.py`, `backend/cognitif_routes.py`, `backend/jumeau/`
