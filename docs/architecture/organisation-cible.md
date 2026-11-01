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
| `jumeau/analyse_service.py` | `meridian/application/analyse_service.py` | déplacé, exception de ports documentée |
| `jumeau/backfill_graphe.py` | `meridian/adapters/outbound/neo4j/backfill_graphe.py` | déplacé, shim |
| `jumeau/flux.py` | `meridian/adapters/inbound/http/flux.py` | déplacé, shim |
| `jumeau/execution/**` | `meridian/application/execution/**` + `adapters/outbound/{postgres,neo4j}/**` + `adapters/inbound/{http/runs,worker/execution_worker}` | déplacé, shims |
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

### Lot `jumeau` top-level du 2026-11-01

Tous les modules top-level restants ont été déplacés par lots, avec shim `sys.modules` (et
`runpy`/entrée `main` pour les CLI) :

- Domaine : `schemas`, `origine`, `recettes`.
- Application : `decouverte`, `impacts_situations`, `mesure`, `protocole`, `protocoles_outils`,
  `openapi_outils`, `mcp_outils`, `interface_outils`, `interfaces_protocoles`, `ingestion_outils`,
  `evaluation_gold`, `methodes`, `executeur`.
- Postgres : `depot` (avec `schema.sql`), `temps`, `connaissance`, `recoupement`, `carte`,
  `comprendre`, `examen`, `croisement`, `twins_types`, `decouverte_interfaces`, `ingestion_runtime`,
  `pulls_runtime`, `application_memoire`, `audit_harness`, `portefeuille`, `valeur`,
  `retrieval_memoire`, `memoire_org`, `outcomes`, `boucle`, `specialiste_impact`,
  `specialiste_decouverte`, `decision_cognitive`, `migration_canonique`.
- Mongo : `registre`, `travail`, `migration_identites`, `parite_mongo`.
- Redis : `partage`, `evenements`, `tours_redis`, `notifications_impacts`.
- LLM : `juge`, `harness`, `conception`, `orchestrateur`, `contradicteur`, `poignee`, `mobilisation`,
  `agent`, `flore`, `gardien`, `evaluation`, `latence`.
- Connecteurs : `source_git`, `lecteurs`, `adaptateur`, `appels`, `manifestes`,
  `chargeur_manifestes`, `connecteur_interfaces`, `cbm`, `index_store`, `systemes`, `github`,
  `atlassian`, `confluence`, `jira`, `servicenow`, `datadog`, `connecteurs`, `connecteurs_runtime`,
  `connecteurs_runtime_pull`, `auth_source`, `naissance`, `ingerer`, `reindexer`, `essai_source`,
  `http_adapter`.

Les données de ces modules suivent : `schema.sql` (Postgres), `methodes/` (application),
`charte_flore.md` et `references/` (LLM).

Il ne reste en `jumeau` que `analyse_service` (couplé à `jumeau.execution`, à `auth`/`boucle_routes`
et à psycopg), `flux` (FastAPI/SSE, dont le propriétaire est `adapters/inbound/http`) et
`backfill_graphe` (hors périmètre de ce lot). Les autres dépendances legacy assumées sont
`postgres/rls.py → jumeau.tenant`, `llm/flore.py` et `llm/mobilisation.py → jumeau.flux`, et
`llm/gardien.py → jumeau.execution.outbox` (migration en cours par un autre lot).

## État de `jumeau`

À ce stade, `backend/jumeau/` est un **namespace de compatibilité** : chaque module est un shim
`sys.modules` vers `meridian`. Les seuls fichiers non-shims sont `__init__.py` et
`execution/__init__.py` (ré-exports). `analyse_service.py` vit dans `application/` mais reste une
exception de dépendance tant qu'il n'a pas reçu ses ports (`auth`, `boucle_routes`, `psycopg`).

## Prochaines extractions

1. Extraire `analyse_service` derrière des ports, puis le déplacer sous `meridian/application/`.
2. Déplacer `flux` sous `meridian/adapters/inbound/http/` avec l'accord du propriétaire de l'inbound.
3. Extraire des ports étroits (`KnowledgeStore`, `EntrepriseStore`, `GraphStore`, `EventPublisher`)
   pour sortir les services DB-couplés aujourd'hui placés sous `adapters/outbound/postgres/`.
4. Supprimer les shims après migration de tous les appelants et tests.

## Tests de garde

`backend/jumeau/tests/test_architecture.py` vérifie que le domaine reste pur, que l'application ne dépend
ni des adapters ni des SDK, que les ports ne dépendent pas des couches externes, que les adapters
sortants ne dépendent pas de l'inbound, et que boto3 reste un import paresseux.
