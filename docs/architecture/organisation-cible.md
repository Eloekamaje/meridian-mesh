# Organisation cible du code

Cible : **monolithe modulaire hexagonal** (ADR-0010).

```text
meridian/domain/          types et invariants purs
meridian/application/     cas d'usage, commandes, requêtes, politiques
meridian/ports/           contrats étroits (inbound/outbound)
meridian/adapters/
  inbound/http/           FastAPI, SSE, MCP, webhook
  inbound/worker/         workers d'ingestion, outbox, exécution
  outbound/postgres/      dépôts, transactions, RLS
  outbound/mongo/         registre, travail
  outbound/neo4j/         GraphStore et projections
  outbound/aws/           Secrets Manager, SQS/EventBridge, Scheduler
  outbound/llm/           Strands/Bedrock
meridian/composition.py   racine de composition
server.py                 point d'entrée ASGI mince
```

## Règles de dépendance

1. `domain` n'importe ni `application`, ni `ports`, ni `adapters`, ni FastAPI/Postgres/Mongo/Neo4j/Strands/boto3.
2. `application` dépend de `domain` et de `ports` ; jamais d'un adapter concret ni d'un SDK.
3. `ports` ne dépend que de `domain` (ou de types standard).
4. `adapters` peuvent dépendre de `application`, `ports`, `domain` et de leur SDK.
5. Seule la racine de composition (`server.py`/`meridian/composition.py`) assemble les adapters.
6. Les anciens chemins (`backend/jumeau/...`, `backend/*_routes.py`, `backend/server.py`) sont des **shims de compatibilité** ; ils ne doivent plus recevoir de nouvelle logique.

## Migration réalisée

| Ancien | Cible | État |
|---|---|---|
| `jumeau/modele_entreprise.py` | `meridian/domain/modele_entreprise.py` | déplacé, shim |
| `jumeau/rls.py` | `meridian/adapters/outbound/postgres/rls.py` | déplacé, shim |
| `jumeau/graph_store.py` | `meridian/adapters/outbound/neo4j/graph_store.py` | déplacé, shim |
| `jumeau/aws_adapters.py` | `meridian/adapters/outbound/aws/adapters.py` | déplacé, shim |
| `server.py` | `meridian/adapters/inbound/http/legacy.py` | déplacé ; `server.py` remplace son module en `sys.modules` |
| `jumeau/import_identite.py` | `meridian/domain/import_identite.py` | déplacé, shim |
| `jumeau/source_routes.py` | `meridian/adapters/inbound/http/sources.py` | déplacé, shim |
| `jumeau/source_worker.py` | `meridian/adapters/inbound/worker/source_worker.py` | déplacé, shim |
| `jumeau/execution/outbox_worker.py` | `meridian/adapters/inbound/worker/outbox_worker.py` | déplacé, shim |
| `jumeau/routes.py` | `meridian/adapters/inbound/http/interfaces.py` | déplacé, shim |
| — | `meridian/application/commandes.py`, `meridian/ports/commandes.py`, `meridian/adapters/outbound/mongo/commandes_depot.py` | première tranche application/port/adapter |
| `*_routes.py` | `meridian/adapters/inbound/http/*.py` | déplacés, shims `sys.modules` |

### Lot domain/application/adapters du 2026-11-01

- Domaine : `profils`, `methodes_cognitives`, `competences_cognitives`, `packs_domaines`,
  `raisonnement`, `attention`, `contexte`, `specialistes`, `temporalite`, `contrefactuel`,
  `capacites`, `tenant`, `graphe`, `interfaces`, `identite` → `meridian/domain/`.
- Application : `composition`, `reponse_cognitive`, `evaluation_cognitive`, `resolveur_contexte`,
  `specialiste_preuve`, `evaluation_outils`, `graphe_sync`, `consolidation_memoire`,
  `evaluation_profils` → `meridian/application/`.
- Adapters outbound : `graphe_neo4j` → `meridian/adapters/outbound/neo4j/` ; `calibration`,
  `entreprise_depot`, `valeur_depot`, `memoire_durable`, `interfaces_depot`, `retention`,
  `pg_recherche`, `session_memoire`, `identite_depot` → `meridian/adapters/outbound/postgres/`.

Chaque ancien chemin `jumeau/*.py` reste un shim `sys.modules` sans logique. Restent dans
`jumeau` les cas d'usage encore couplés à un dépôt concret ou à HTTP (`boucle`, `outcomes`,
`memoire_org`, `portefeuille`, `retrieval_memoire`, `analyse_service`, `specialiste_impact`,
`specialiste_decouverte`), `depot` (porte `schema.sql`), `registre` (Postgres + Mongo) et les
connecteurs (`github`, `source_git`, `systemes`, `cbm`, `connecteurs*`) encore liés à
`naissance`/`ingerer`. Leur extraction exige d'abord des ports étroits.

## Prochaines extractions

1. Sortir de `legacy.py` les cas d'usage `commandes` (création/lancement), `sources` et `analyser` vers `meridian/application/` ; la lecture/aperçu d'import est déjà extraite.
2. Définir les ports `CommandesStore`, `KnowledgeStore`, `GraphStore`, `SecretStore`, `EventPublisher`.
3. Déplacer les dépôts Postgres/Mongo/Neo4j sous `meridian/adapters/outbound/`.
4. Déplacer les workers sous `meridian/adapters/inbound/worker/` et les exposer par des scripts minces.
5. Supprimer les shims après migration de tous les appelants et tests.

## Tests de garde

`backend/jumeau/tests/test_architecture.py` vérifie que le domaine reste pur, que l'application ne dépend
ni des adapters ni des SDK, et que boto3 reste un import paresseux.
