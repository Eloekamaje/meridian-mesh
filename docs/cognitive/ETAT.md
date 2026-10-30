# État d'avancement cognitif

**Date :** 2026-10-30  
**Branche :** `jumeau-p4-confort`

**Documents directeurs :** [PRD-001](../prd/PRD-001-enterprise-intelligence-mesh.md), [ADR-0001](../adr/0001-identite-typed-twin-discovery.md), [ADR-0002](../adr/0002-orchestrateur-general.md), [ADR-0003](../adr/0003-mesh-transversal-intelligence.md), [ADR-0004](../adr/0004-capability-first-harness.md), [ADR-0005](../adr/0005-enterprise-object-model.md), [ADR-0007](../adr/0007-polyglot-postgres-graph.md)

> **État vs cible.** Les trois outils de l'orchestrateur sont une amorce. La cible est le harness capacitaire d'ADR-0004, le modèle d'entreprise d'ADR-0005 et l'architecture polyglotte d'ADR-0007 (Postgres pour la connaissance, graph store pour le Mesh). Les écarts sont des chantiers, pas des exceptions.

## Lots livrés

### Lot 1 — identité et résolution (commit `1961729`)

- `backend/jumeau/identite.py` : résolution typée `SourceArtifact → Twin → Application candidate`.
- Aucun nom de dépôt n'est un alias d'application.
- Twin provisoire utilisable ; préambule de nomination ; absence non concluante ; ambiguïté explicite.
- `backend/server.py` : routage réel par `identite.resoudre`, trace `resolution` dans la réponse et dans la conversation.
- `backend/jumeau/interfaces.py` : contrats, opérations, bindings, assertions `declared/observed/inferred`, parseurs OpenAPI/configuration.
- `docs/adr/0001-identite-typed-twin-discovery.md` et `docs/cognitive/PROGRAMME.md`.

Preuve live sur « régénère le flux du gsf-mockup » : `repo:gsf-mockup → twin:nouveau-jumeau (provisoire) → application candidate`, consultation du twin, 1 schéma, 16 preuves.

### Lot 2 — persistance, impact, connecteurs, jeu d'or

- `backend/jumeau/interfaces_depot.py` + tables `interface_*` : persistance Postgres multi-tenant, idempotente, avec preuve et mode ; refus des URLs porteuses de secrets.
- `backend/jumeau/decouverte.py` : diff contrats/opérations/bindings/assertions et impacts sur les consommateurs.
- `backend/jumeau/connecteur_interfaces.py` : connecteur fichiers OpenAPI/config, parcours borné, locators relatifs, aucun réseau.
- `backend/jumeau/interfaces.py` : `depuis_claims` — les claims `EXPOSE` du code deviennent des opérations déclarées.
- `backend/jumeau/tests/fixtures/mobilisation_golden.json` + test : 18 cas de résolution.
- Tests du lot : **59** ciblés, **891** tests jumeau avec base avant l'ajout du bridge claims ; **893** après.

### Lot 3 — DiscoveryRun et découverte au gardien

- `backend/jumeau/decouverte_interfaces.py` : `executer()` collecte, persiste, compare, calcule les impacts et journalise un `DiscoveryRun`.
- `backend/jumeau/schema.sql` : table `discovery_run` (statut, compteurs, changements, impacts, erreur).
- `interfaces_depot.lire_graph()` : relit le graphe typé.
- `interfaces.depuis_claims()` : les `EXPOSE` du code deviennent des opérations déclarées ; un dépôt sans OpenAPI statique n'est plus vide.
- `gardien.veiller()` : après une ingestion, lance la découverte d'interfaces en best-effort et journalise le run.
- API : `GET /jumeaux/{jid}/interfaces` (graphe + runs) et `POST /jumeaux/{jid}/interfaces/decouvrir` (run manuel), protégés par le périmètre.
- Remplacement de périmètre : un run remplace les opérations/assertions de sa source et de son format ; les autres sources restent intactes. Un second run identique ne produit plus de faux changements.
- WSDL/SOAP : `parse_wsdl` + détection `.wsdl`/`.xml` par contenu, adresses assainies, opérations `SOAP`.
- Atlas : bouton/panneau « Interfaces » alimenté par `GET /mesh/interfaces` (opérations, arêtes, impacts, runs) et « voir sur la carte ».
- Runtime en ombre : `POST /jumeaux/{jid}/interfaces/observer` ingère un export APM/gateway normalisé (`CONSOMME`/`EXPOSE`, `mode=observed`, source, trace) sans écraser le déclaré.
- Arêtes d'interfaces : couche Atlas optionnelle, arêtes React Flow déclaré/observé/inféré, dérivation cible productrice prouvée par EXPOSE.
- OTLP : parsing des traces `resourceSpans` (CLIENT/SERVER, HTTP/gRPC, statut, trace) vers observations `observed`.
- Situations : une découverte avec impact `breaking`/`warning` publie une situation d'interface dans le fil, sans bloquer la passe du Gardien.
- Tirage OTLP authentifié : HTTPS + allowlist `JUMEAU_OTLP_HOTES`, secret Vault/env, pas de redirection, taille bornée ; endpoint `POST /jumeaux/{jid}/interfaces/observer/pull`.
- Notifications d'impact : persona par équipe (fallback gouvernance), upsert idempotent, SSE `notification.creee`, lien Atlas.
- Connecteur OTLP de bout en bout : catalogue UI, configuration URL/secret/fréquence, déclaration `source OTLP`, test sans réseau, tirage authentifié, source publique avec dernier tirage/erreur, bouton manuel, tirage d'arrière-plan avec fréquence et backoff.
- Orchestrateur général : un seul modèle, une politique, outils `resoudre_application`, `mobiliser_jumeaux`, `concevoir_architecture` ; aucun routeur d'intention hardcodé dans le chemin principal.
- Conception greenfield : proposition structurée `mode="proposition"`, hypothèses, aucun jumeau/preuve ; live dating → outil `concevoir_architecture` seul, 12 composants, aucun participant.
- App existante : live Conduit → `resoudre_application` puis `mobiliser_jumeaux`, participant Conduit.
- Tests : **1058 tests jumeau** (3 skip), **148 tests frontend**, build OK. Exécution réelle sur `gsf-mockup` : 3 opérations `GET /`, `GET /status`, `POST /status` ; premier run 7 changements, second run 0.
- Promotion gouvernée : `POST /jumeaux/{jid}/promouvoir` + table `identity_decision`, formulaire dans la revue, audit acteur/avant/après, id inchangé.
- Revue d'un jumeau réel : section « Interfaces et impacts » avec contrats, opérations, assertions et dernier DiscoveryRun.

### P0 — socle d'entreprise, Claim et harness

- `objet_entreprise` : table canonique générique (8 familles, 5 modes, temporalité, version) + `entreprise_depot` avec isolation tenant.
- `claim` : `mode`, `version`, `remplace_id` ; trigger `claim_accepte_exige_preuve` : un Claim `ACCEPTED` exige une preuve `SUPPORT` en plus de la revue.
- `harness` : registre capacitaire branché dans l'orchestrateur, catalogue filtré, audit en mémoire, `rechercher_outil`/`decrire_outil`, timeout des outils asynchrones.
- `GrapheNeo4j` : adaptateur Cypher paramétré du port `GraphStore`, testé par session factice.
- Produit : `/` et `/aujourdhui` ouvrent Aujourd'hui ; Atlas reste l'exploration.
- Boucle P1 canonique : Situation → Investigation → Décision → Initiative → Outcome → Learning, persistée dans `objet_entreprise` (`boucle.py`), avec transitions et liens validés.
- Audit harness persistant : table `outil_audit` append-only, expurgation, sink optionnel dans `harness.py` ; chargeur de manifestes JSON.
- Synchronisation graphe : mapping identité/relations legacy vers `NoeudTwin`/`Arete`, dry-run, réconciliation, sans accès direct aux stores.
- API canonique : `/api/boucle/objets`, `/api/boucle/objets/{id}`, `/api/boucle/synthese`, lecture tenant-scopée, filtres et chaîne/historique.
- UI : page `/boucle` avec six familles, filtres, détail, chaîne et liens Travail/Atlas ; entrée de navigation.
- Migration legacy en dry-run : 13 situations, 10 initiatives, 45 relations lues, 0 erreur ; aucune écriture massive tant que le graph store de production n'est pas branché.
- Tenant : `tenant.py` (demo local, production sans fallback, slug, absence « non observé »), branché dans Boucle.
- Audit : `outil_audit` persistant best-effort après tour ; live dating = 1 ligne `concevoir_architecture · concevoir · ok · local`.
- Catalogue : `GET /api/outils` expose les manifestes intégrés + `JUMEAU_MANIFESTES`, sans exécution.
- Graphe : `graph_store.py` choisit Neo4j si configuré, sinon mémoire ; `graphe_sync` prêt.
- OpenAPI : génération de manifestes read-only/écriture depuis les opérations, enregistrables dans le registre.
- Backfill réel sur Neo4j local (tenant `demo`) : **23 objets canoniques** (13 situations, 10 initiatives), **42 Twins**, **45 relations**, 0 erreur. `scripts/dev-neo4j.sh` génère un mot de passe local hors dépôt ; l'API Boucle expose le tenant `demo` avec `X-Tenant: demo` (le tenant `local` reste vide).
- Identités canoniques : backfill `jumeaux` Mongo → Postgres (`migration_identites.py`), **42 identités** en tenant `demo`, sans écrasement ni secret ; les tables canoniques sont passées en `demo`.
- Parité Mongo/canonique : **0 écart** sur 42 identités, 13 situations, 10 initiatives et 45 relations ; `parite_mongo.py` rend les écarts sans migrer ni supprimer.
- Graphe continu : le Gardien synchronise l'identité Postgres et les relations Mongo vers le `GraphStore` à chaque passe (`_synchroniser_graphe`), avec confiance en pourcentage normalisée.
- API graphe : `/api/boucle/graphe/resume`, `/graphe/{twin}/voisins`, `/graphe/{twin}/impact`, `/graphe/chemins` ; lecture tenant-scopée, profondeur bornée.
- Tenant authentifié : proxy (`AUTH_TENANT_HEADER`, défaut `X-Auth-Request-Tenant`) et OIDC (`AUTH_TENANT_CLAIM`, défaut `tenant`) posent `request.state.tenant` ; l'absence de tenant et un `X-Tenant` divergent sont refusés.
- Outils multi-protocoles : `interface_outils.py` compile toute opération connue (REST, SOAP/WSDL, gRPC) en manifeste ; `protocoles_outils.py` couvre GraphQL, gRPC et AsyncAPI ; OpenAPI et MCP restent des adaptateurs parmi d'autres. Chargement par `JUMEAU_OPENAPI`, `JUMEAU_MCP_OUTILS`, `JUMEAU_INTERFACES`, `JUMEAU_PROTOCOLES`, CLI et lecture des `interface_operation` Postgres dans `/api/outils`. Aucun `tools/call` exécuté.
- Atlas : le panneau d'un twin lit `/api/boucle/graphe/{id}/impact` quand un tenant est fourni (`localStorage.meridian.tenant` ou `?tenant=`) et affiche les impacts amont/aval canoniques, en plus des voisins Mongo.
- RLS : `jumeau/rls.py` fournit les policies tenant, le contexte `set_config(..., true)` et une activation explicite ; le mode est opt-in (`JUMEAU_RLS=1`) et n'est pas activé sur la base locale.
- Tests : **1272 tests jumeau** (2 skip), **8 auth**, **12 routes Boucle**, **166 frontend**, build non-CI OK (le build CI reste bloqué par des avertissements ESLint préexistants). Live : 42 Twins, 45 relations, 23 objets et 5 opérations d'interface en `demo`.

## Constat du connecteur sur gsf-mockup

Le dépôt `gsf-mockup` ne contient pas de spec OpenAPI statique. Le connecteur fichiers rend donc 0 contrat. Le bridge `depuis_claims` lit les 3 claims `EXPOSE` (`GET /`, `GET /status`, `POST /status`) et produit 3 opérations déclarées, persistables. Les échanges externes réels restent à observer par gateway/APM ou par une source de configuration dédiée.

## Limites actuelles

- Neo4j/Neptune de **production** n'est pas branché : le graphe live tourne sur Neo4j local Docker ; l'API et le Gardien fonctionnent, pas encore la haute disponibilité ni le backfill de production.
- Le tenant est extrait du proxy/OIDC et vérifié dans l'API ; les policies RLS sont fournies mais **pas encore activées** sur les bases, et les chemins legacy restent filtrés par code.
- Mongo reste lu par les **cases**, le fil Aujourd'hui et l'Atlas ; la parité des identités, situations, initiatives et relations est à zéro, mais la migration des cases n'est pas faite.
- Les adaptateurs de protocoles sont volontaires (CLI, variables d'environnement ou opérations d'interface déjà découvertes) ; la découverte automatique depuis la gateway/le CMDB reste à brancher.
- L'Atlas rend l'impact canonique quand un tenant est sélectionné ; les relations Mongo restent la source principale de la carte et des voisins.
- Dans le modèle **1 twin ↔ 1 application**, `application_id = twin_id = id réel de l'application` ; la promotion ne change pas cet id. Le multi-twins par application n'est pas retenu.
- L'Atlas affiche les interfaces/impacts et les situations sont publiées ; la propagation fine des changements au fil « Aujourd'hui » reste à renforcer.
- Le connecteur lit OpenAPI, configuration, claims `EXPOSE`, WSDL et OTLP tiré depuis une source APM/gateway authentifiée. Un export propriétaire non OTLP (Datadog/Kong/Apigee natif) reste un adaptateur optionnel.
- Les arêtes d'interface sont dessinées en rendu graphe ; un `CONSOMME` vers une URL externe sans production résolue ne crée toujours pas d'arête (aucune cible inventée).
- Le tirage authentifié accepte un endpoint OTLP/APM/gateway compatible OTLP ; un connecteur propriétaire (Datadog, Kong, Apigee) reste optionnel si l'export n'est pas OTLP.
- Les notifications persona/SSE sont branchées pour les impacts breaking/warning.
- La promotion est gouvernée et auditée ; le modèle 1 twin ↔ 1 application est définitif.

## Prochain lot

1. Déployer Neo4j/Neptune en production, rejouer le backfill multi-tenant et vérifier l'idempotence à l'échelle.
2. Activer RLS en production (rôle applicatif non-superuser, `meridian.tenant_id` posé par transaction) et vérifier les chemins legacy.
3. Brancher la découverte automatique gateway/CMDB/OTLP sur les adaptateurs de protocoles (OpenAPI, WSDL, GraphQL, gRPC, AsyncAPI).
4. Migrer les `cases` (forme de travail) puis retirer les lectures Mongo restantes après parité.
5. Enrichir le jeu d'or de l'orchestrateur et mesurer les choix d'outils multi-protocoles.

## Commandes d'exploitation

```bash
# identités legacy → Postgres (dry-run, puis réel)
python -m jumeau.migration_identites --tenant demo --dry-run
python -m jumeau.migration_identites --tenant demo

# parité Mongo / identités + objets + graphe
python -m jumeau.parite_mongo --tenant demo

# ingestion explicite d'outils
python -m jumeau.ingestion_outils --openapi comptes=/chemin/openapi.json
python -m jumeau.ingestion_outils --interface ventes=/chemin/ventes.wsdl
python -m jumeau.ingestion_outils --graphql comptes=/chemin/schema.graphql
python -m jumeau.ingestion_outils --grpc paiements=/chemin/service.proto
python -m jumeau.ingestion_outils --asyncapi ventes=/chemin/asyncapi.yaml
JUMEAU_OPENAPI='[{"application":"comptes","path":"/chemin/openapi.json","tenant":"demo"}]' \
JUMEAU_INTERFACES='[{"application":"ventes","path":"/chemin/ventes.wsdl","tenant":"demo"}]' \
JUMEAU_PROTOCOLES='[{"application":"comptes","path":"/chemin/schema.graphql","type":"graphql","tenant":"demo"}]' \
  uvicorn server:app --host 127.0.0.1 --port 8001

# RLS : activation explicite par un rôle de déploiement, puis JUMEAU_RLS=1
python -m jumeau.rls --activer   # si le CLI est ajouté au déploiement

# lectures graphe tenant-scopées
curl -H 'X-Tenant: demo' http://127.0.0.1:8001/api/boucle/graphe/resume
curl -H 'X-Tenant: demo' http://127.0.0.1:8001/api/boucle/graphe/paiements/impact
```

Le mot de passe Neo4j local n'est jamais versionné : `scripts/dev-neo4j.sh` le génère dans
`/tmp/meridian-neo4j.env`. En production, fournir `GRAPH_STORE=neo4j`, `NEO4J_URI`, `NEO4J_USER`,
`NEO4J_PASSWORD` et `NEO4J_DATABASE` par le gestionnaire de secrets.
