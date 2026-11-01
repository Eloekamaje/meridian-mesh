# ADR-0012: Outbox, inbox, idempotence et concurrence

**Date**: 2026-10-31
**Status**: accepted
**Deciders**: Panel architecture (Principal Architect, Runtime, IA, Staff) + utilisateur

## Context

Les écritures métier et les effets de bord se répartissent entre Postgres, Neo4j, Mongo, Redis, les connecteurs
et le LLM. Sans protocole commun, un crash entre deux écritures produit des états incohérents : Claim écrit
sans événement, graphe en avance, notification envoyée deux fois, run bloqué.

Le runtime doit garantir des effets **au moins une fois** avec des consommateurs **idempotents**, sans imposer
Kafka ni une transaction distribuée.

## Decision

Appliquer le trio **outbox transactionnel + inbox + idempotence** à toute frontière durable.

### Enveloppe de commande

```text
command_id · run_id · tenant_id · idempotency_key
correlation_id · causation_id · deadline_at · priority
aggregate_id · expected_version · payload · schema_version
```

### Règles

1. L'écriture métier et la ligne d'outbox sont dans **la même transaction Postgres**.
2. Un dispatcher publie l'outbox avec `FOR UPDATE SKIP LOCKED` ; Redis/SQS/EventBridge ne sont que transport.
3. Chaque consommateur possède une **inbox** et déduplique sur `(consumer, event_id)`.
4. Chaque effet externe possède une clé d'idempotence `(run, step, cible, opération)`.
5. Un worker détient un **bail** (`lease_until`) et un **fencing token** ; seul le détenteur peut committer.
6. Le reaper expire les baux ; il n'exécute jamais le travail.
7. Les retries sont réservés aux erreurs transitoires, avec backoff + jitter, `max_attempts` et DLQ persistée.
8. Les timers sont des lignes `due_at` en base ; pas de `asyncio.sleep` durable, pas de TTL Redis comme timer.
9. La concurrence est sérialisée par agrégat (`expected_version` ou verrou) et plafonnée par tenant, twin et
   connecteur.
10. Aucune double écriture Postgres → Neo4j/Mongo : le projector consomme l'outbox.

### Garanties

| Élément | Garantie |
|---|---|
| Livraison | at-least-once |
| Effet métier | idempotent, au plus une application visible |
| Ordre | par agrégat via `version`, pas global |
| Échec | retry borné, DLQ, compensation si nécessaire |
| Crash | reprise par bail, aucun doublon de commit |
| Timer | durable, rejouable |

## Alternatives Considered

### Alternative 1: Double écriture directe Postgres + Neo4j
- **Pros**: simple localement.
- **Cons**: incohérence au crash, pas de rejeu, pas de reconstruction.
- **Why not**: incompatible avec une source de vérité unique.

### Alternative 2: File Redis comme source de vérité
- **Pros**: rapide, déjà présente.
- **Cons**: perte de messages, pas de transaction, pas d'audit durable.
- **Why not**: Redis reste un accélérateur, pas un journal.

### Alternative 3: Kafka
- **Pros**: log distribué, replay.
- **Cons**: exploitation, coût, compétences, surdimensionné pour 5k applications.
- **Why not**: l'outbox Postgres couvre le volume et préserve la portabilité.

### Alternative 4: Exactly-once de bout en bout
- **Pros**: promesse théorique rassurante.
- **Cons**: impossible avec la plupart des effets externes.
- **Why not**: at-least-once + idempotence est la garantie réaliste et vérifiable.

## Consequences

### Positive
- Aucune perte silencieuse entre deux stores.
- Les reprises et doublons sont testables.
- Les adapters SQS/EventBridge restent interchangeables.
- La DLQ et les timers sont observables.

### Negative
- Tables et workers supplémentaires.
- Les effets externes doivent exposer des clés d'idempotence.
- Le débogage demande de suivre `correlation_id`, `causation_id` et `run_id`.

### Risks
- Oublier l'inbox sur un consommateur.
- Utiliser Redis comme source de vérité par facilité.
- Ne pas versionner les événements.
- Confondre bail et transaction distribuée.

## Acceptance Criteria

1. Toute commande possède une `idempotency_key` unique par tenant.
2. Une commande rejouée ne crée ni deuxième run ni deuxième effet.
3. Un consommateur rejoué ne produit aucun doublon visible.
4. Un crash après écriture métier mais avant publication est rejoué par l'outbox.
5. Un timer survit à un redémarrage.
6. Deux workers ne peuvent pas committer le même run.
7. Les tests couvrent doublon, crash, retry, DLQ, bail expiré.
8. Aucun chemin d'écriture ne fait Postgres puis Neo4j/Mongo sans outbox.

## References

- [ADR-0011](0011-runtime-durable-postgres.md), [ADR-0013](0013-projection-graphe.md)
- `backend/jumeau/schema.sql`, `backend/jumeau/gardien.py`, `backend/jumeau/graphe_sync.py`
