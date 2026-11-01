# ADR-0014: Adapters AWS sans lock-in

**Date**: 2026-10-31
**Status**: accepted
**Deciders**: Panel architecture (Principal Architect, Runtime, IA, Staff) + utilisateur

## Context

Méridian doit pouvoir tourner sur AWS sans que le domaine, les cas d'usage ou les tests dépendent d'AWS.
Le pilote actuel est local (Docker Compose) et ne possède pas de credentials AWS. La cible doit donc être
crédible sur AWS, mais rester exécutable et testable hors AWS.

## Decision

AWS est un **jeu d'adapters optionnels** derrière les ports de l'ADR-0010.

| Port | Local | AWS possible |
|---|---|---|
| API / worker | Uvicorn, processus | ECS/Fargate, ALB |
| ExecutionStore | Postgres Docker | RDS Postgres Multi-AZ |
| KnowledgeStore | Postgres | RDS Postgres |
| GraphStore | Neo4j Docker | Neo4j Aura ou Neptune |
| WorkStore | Mongo ou Postgres | DocumentDB ou Postgres |
| StreamPublisher | Redis / Postgres | ElastiCache, SQS, EventBridge |
| Scheduler | table `timer` | EventBridge Scheduler |
| AgentRuntime | Strands local | Bedrock |
| SecretStore | Vault local | Secrets Manager |
| Artefacts | disque/S3 local | S3 |
| Observabilité | logs/OTel | CloudWatch + OTel |

Règles :

1. Aucun import SDK AWS dans `domain/` ni dans `application/`.
2. Les adapters AWS sont derrière les mêmes contrats que les adapters locaux.
3. Les tests de conformité s'exécutent contre les adapters locaux et, en option, AWS.
4. Step Functions peut orchestrer des workflows longs, mais ne devient pas la source de vérité.
5. Lambda n'est pas utilisé pour les runs agents longs ; les workers tournent sur Fargate.
6. Le tenant et RLS sont des frontières d'application et de base, pas des options AWS.

## Alternatives Considered

### Alternative 1: Lambda-first
- **Pros**: coût à la demande, ops réduites.
- **Cons**: timeouts, streaming, connexions Postgres, agents longs, cold starts.
- **Why not**: le run agent est un workload long et stateful.

### Alternative 2: SDK AWS dans le domaine
- **Pros**: développement rapide.
- **Cons**: lock-in, tests locaux impossibles, couplage.
- **Why not**: incompatible avec la portabilité demandée.

### Alternative 3: Step Functions comme cœur
- **Pros**: orchestration managée.
- **Cons**: pas de parité locale, logique métier dans le cloud.
- **Why not**: la machine à états Postgres reste la référence.

### Alternative 4: Cloud-agnostique total dès maintenant
- **Pros**: liberté maximale.
- **Cons**: sur-abstraction, aucun déploiement réel.
- **Why not**: les adapters AWS sont ajoutés après parité locale.

## Consequences

### Positive
- Le même produit tourne en Docker et sur AWS.
- Les services AWS sont remplaçables.
- Les tests locaux restent la référence.
- Le coût d'entrée AWS est progressif.

### Negative
- Certains adapters AWS ne seront pas exercés avant le déploiement.
- Duplication de configuration local/AWS.
- Les tests de conformité demandent de la discipline.

### Risks
- Fuite d'un import AWS dans le cœur.
- Divergence de comportement local/AWS.
- Utiliser Step Functions pour compenser un runtime mal conçu.
- Sous-estimer RLS et la latence réseau.

## Acceptance Criteria

1. `domain/` et `application/` n'importent aucun SDK AWS.
2. Chaque port possède un contrat et un test de conformité.
3. Le produit démarre en Docker sans AWS.
4. Un adapter AWS peut être remplacé par le local sans changer le cas d'usage.
5. Les runs longs ne sont pas exécutés dans Lambda.
6. Step Functions, si utilisé, est un adapter, pas la source de vérité.
7. Tenant/RLS sont testés indépendamment du cloud.

## References

- [ADR-0010](0010-monolithe-modulaire-hexagonal.md), [ADR-0011](0011-runtime-durable-postgres.md)
- [ADR-0013](0013-projection-graphe.md)
- `docker-compose.yml`, `docker-compose.prod.yml`, `backend/server.py`
