# ADR-0011: Runtime durable adossé à PostgreSQL

**Date**: 2026-10-31
**Status**: accepted
**Deciders**: Panel architecture (Principal Architect, Runtime, IA, Staff) + utilisateur

## Context

Les réponses longues de Flore sont aujourd'hui générées dans des tâches `asyncio`, streamées en SSE et suivies
en mémoire (`TOURS`) avec un relais Redis et un reaper. Ce prototype fonctionne, mais il ne survit pas
proprement à un redémarrage de worker, ne rejoue pas un journal durable, ne persiste pas les approbations et
n'expose pas une sémantique unique de commande, de deadline ou d'annulation.

Le runtime doit rester cohérent localement, sans AWS, tout en pouvant utiliser SQS, EventBridge ou Step
Functions comme adapters demain.

## Decision

Adopter **PostgreSQL comme source de vérité du runtime** :

- toute **query** est synchrone, en lecture seule, bornée et sans effet de bord ;
- toute **commande** est persistée et asynchrone par défaut ; l'API retourne `202 + run_id` ;
- une commande courte peut attendre son état terminal, mais emprunte le même chemin ;
- un **run** est une machine à états persistée, rejouable et annulable ;
- le streaming SSE lit un **journal append-only** de run, pas la mémoire du processus ;
- les deadlines, approbations, reprises et annulations sont persistées.

Machine à états initiale :

```text
QUEUED → RUNNING → SUCCEEDED
          ↘ WAITING_RETRY → RUNNING
          ↘ FAILED | CANCELLED | EXPIRED
```

Règles :

1. Le client ne reçoit jamais un long appel HTTP bloquant pour une commande.
2. Une requête de lecture peut rester synchrone ; elle indique sa fraîcheur.
3. Un run possède `deadline_at`, `cancel_requested_at`, `attempt`, `lease_until` et `fencing_token`.
4. Un événement de run possède une séquence monotone et un `event_id`.
5. Redis ne porte que le fan-out et le réveil des lecteurs SSE ; il n'est pas la source de vérité.
6. Step Functions peut être un adaptateur pour des workflows longs, jamais la source de vérité locale.

## Alternatives Considered

### Alternative 1: Conserver les tâches asyncio en mémoire
- **Pros**: aucun schéma, aucun worker.
- **Cons**: perte au redémarrage, annulation non fiable, reprise impossible, multi-worker fragile.
- **Why not**: le runtime actuel est déjà le principal risque de cohérence.

### Alternative 2: Step Functions comme source de vérité
- **Pros**: orchestration managée, reprise, timers.
- **Cons**: couplage AWS, pas de parité locale, migration prématurée.
- **Why not**: la cible doit rester portable et démontrable sans AWS.

### Alternative 3: Temporal ou moteur de workflow complet
- **Pros**: durabilité, sagas, timers.
- **Cons**: infrastructure, courbe d'exploitation, sur-ingénierie pour le pilote.
- **Why not**: une machine à états Postgres minimale couvre le besoin actuel.

### Alternative 4: Tout synchrone
- **Pros**: simplicité apparente.
- **Cons**: timeouts HTTP, perte de contrôle, mauvaise expérience sur les runs longs.
- **Why not**: incompatible avec les agents, les connecteurs et les approbations.

## Consequences

### Positive
- Un redémarrage de worker ne perd ni run ni événement.
- Le même chemin sert au local, à AWS et aux tests.
- L'annulation, la reprise et la deadline deviennent observables.
- Le frontend peut se reconnecter avec `Last-Event-ID`.

### Negative
- Nouveau schéma et nouveau worker.
- Le streaming dépend de Postgres et d'un journal.
- Les tests doivent couvrir les pannes, pas seulement le happy path.

### Risks
- Construire un mini-moteur de workflow trop général.
- Saturer Postgres si le débit d'événements explose.
- Oublier les timers durables et les effets externes idempotents.

## Acceptance Criteria

1. `POST /runs` retourne `202` avec un `run_id` pour une commande longue.
2. Un run survit à l'arrêt et au redémarrage du worker.
3. Un client peut reprendre un SSE avec `Last-Event-ID`.
4. Une annulation met le run à `CANCELLED` et produit un événement terminal.
5. Une query de lecture ne crée ni run ni événement.
6. Les tests couvrent : kill worker, double commande, timeout, annulation, reprise.
7. Aucun état de run durable ne vit uniquement dans Redis ou en mémoire.

## References

- [ADR-0010](0010-monolithe-modulaire-hexagonal.md), [ADR-0012](0012-outbox-idempotence.md)
- `backend/jumeau/flux.py`, `backend/jumeau/tours_redis.py`, `backend/cognitif_routes.py`
- `backend/jumeau/schema.sql`
