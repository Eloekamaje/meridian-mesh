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
- Tests : **1172 backend jumeau** (3 skip), **153 frontend**, build OK. Live dating : `concevoir_architecture` seul, 0 participant, 12 composants, audit 1 appel, schéma proposition.

## Constat du connecteur sur gsf-mockup

Le dépôt `gsf-mockup` ne contient pas de spec OpenAPI statique. Le connecteur fichiers rend donc 0 contrat. Le bridge `depuis_claims` lit les 3 claims `EXPOSE` (`GET /`, `GET /status`, `POST /status`) et produit 3 opérations déclarées, persistables. Les échanges externes réels restent à observer par gateway/APM ou par une source de configuration dédiée.

## Limites actuelles

- Dans le modèle **1 twin ↔ 1 application**, `application_id = twin_id = id réel de l'application` ; la promotion ne change pas cet id. Le multi-twins par application n'est pas retenu.
- L'Atlas affiche les interfaces/impacts et les situations sont publiées ; la propagation fine des changements au fil « Aujourd'hui » reste à renforcer.
- Le connecteur lit OpenAPI, configuration, claims `EXPOSE`, WSDL et OTLP tiré depuis une source APM/gateway authentifiée. Un export propriétaire non OTLP (Datadog/Kong/Apigee natif) reste un adaptateur optionnel.
- Les arêtes d'interface sont dessinées en rendu graphe ; un `CONSOMME` vers une URL externe sans production résolue ne crée toujours pas d'arête (aucune cible inventée).
- Le tirage authentifié accepte un endpoint OTLP/APM/gateway compatible OTLP ; un connecteur propriétaire (Datadog, Kong, Apigee) reste optionnel si l'export n'est pas OTLP.
- Les notifications persona/SSE sont branchées pour les impacts breaking/warning.
- La promotion est gouvernée et auditée ; le modèle 1 twin ↔ 1 application est définitif.

## Prochain lot

1. Brancher `objet_entreprise`/`boucle` dans les API/UI et migrer les collections Mongo canoniques.
2. Brancher l'audit persistant et le chargeur de manifestes dans le serveur ; compléter MCP/OpenAPI.
3. Brancher `graphe_sync` + `GrapheNeo4j`/Neptune dans l'ingestion, puis migrer les relations Mongo.
4. Porter le tenant de requête et la règle d'absence dans tous les chemins.
5. Enrichir le jeu d'or de l'orchestrateur et mesurer les choix d'outils.
