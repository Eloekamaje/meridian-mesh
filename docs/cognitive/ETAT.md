# État d'avancement cognitif

**Date :** 2026-10-30  
**Branche :** `jumeau-p4-confort`

**Documents directeurs :** [PRD-001](../prd/PRD-001-enterprise-intelligence-mesh.md), [ADR-0001](../adr/0001-identite-typed-twin-discovery.md), [ADR-0002](../adr/0002-orchestrateur-general.md), [ADR-0003](../adr/0003-mesh-transversal-intelligence.md), [ADR-0004](../adr/0004-capability-first-harness.md), [ADR-0005](../adr/0005-enterprise-object-model.md), [ADR-0007](../adr/0007-polyglot-postgres-graph.md), [ADR-0008](../adr/0008-travail-work-store.md)

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
- Outils multi-protocoles : `interface_outils.py` compile toute opération connue (REST, SOAP/WSDL, gRPC, GraphQL, AsyncAPI) en manifeste ; `protocoles_outils.py` fournit les extracteurs GraphQL/gRPC/AsyncAPI ; `interfaces_protocoles.py` les ramène au graphe d'interface commun. `connecteur_interfaces.py` découvre désormais ces fichiers dans les dépôts, donc le Gardien les persiste et `/api/outils` les expose sans spec OpenAPI. OpenAPI/MCP restent des adaptateurs parmi d'autres ; aucun `tools/call` exécuté.
- Découverte : Git/claims `EXPOSE`/OTLP et fichiers GraphQL, gRPC, AsyncAPI, OpenAPI et WSDL alimentent `interface_operation` ; le catalogue Postgres est lu par `/api/outils` avec le contexte tenant.
- Atlas : le panneau d'un twin lit `/api/boucle/graphe/{id}/impact` quand un tenant est fourni (`localStorage.meridian.tenant` ou `?tenant=`) et affiche les impacts amont/aval canoniques, en plus des voisins Mongo.
- RLS : `jumeau/rls.py` fournit les policies tenant, le contexte `set_config(..., true)` et une activation explicite ; le mode est opt-in (`JUMEAU_RLS=1`) et n'est pas activé sur la base locale.
- Cognition exécutable : `executeur.py` (politique, approbation, allowlist, timeout, audit), `twins_types.py` (PROCESS/CAPABILITY/JOURNEY/etc. + Claims), `outcomes.py` (Outcome mesuré → Learning réutilisable), `memoire_org.py` (mémoire ANNOTATION), `attention.py` (score/dédup à l'échelle), `temporalite.py` (validité, fraîcheur, topologie datée), `evaluation_outils.py` (jeu d'or).
- API cognitive : `/api/boucle/twins`, `/twins/{id}/claims`, `/outcomes`, `/learnings`, `/memoire`, `/attention`, `/topologie`, `/evaluation` ; aucune exécution d'outil externe sans politique.
- Spécialistes cognitifs : noyau `specialistes.py` (contrat, autorité proposition, orchestration parallèle, timeout, déduplication) et trois spécialistes — `decouverte`, `preuve`, `impact`/`outcome`. Ils lisent un contexte borné et produisent des artefacts ; aucun n'écrit, ne promeut ni ne décide. **Domain packs volontairement différés.**
- API : `POST /api/boucle/specialistes/analyser` exécute les spécialistes en parallèle, avec une connexion tenant-scopée par spécialiste pour éviter tout partage non thread-safe.
- Profils composés : `profils.py` résout explicite/identité/inférence/défaut, avec autorité jamais supérieure à la lecture pour un profil inconnu ; `methodes_cognitives.py` et `competences_cognitives.py` sont des catalogues versionnés ; `composition.py` produit un plan borné (méthodes, compétences, spécialistes, budget, autorité).
- Réponses situées : `reponse_cognitive.py` conserve un **socle de faits unique** et change seulement la lecture, le vocabulaire, les actions et les prochaines étapes. Un dev, un PO et un profil inconnu reçoivent les mêmes faits ; l'inconnu reste en lecture seule.
- API : `/api/boucle/profils`, `/composition`, `/analyser` ; `POST /analyser` exécute un socle de preuves indépendant du profil et applique la lentille du profil.
- Value Ledger : `valeur` (Postgres, ADR-0009), types/statuts/attribution, baseline → cible → observe → écart, preuves et confiance ; `/api/boucle/valeurs` et `/valeurs/resume`. Les devises et unités ne sont jamais additionnées, et une valeur sans baseline reste une mesure.
- Pilote : `plugin/meridian/evals/` contient un runner à quatre bras (`skill+mcp`, `checklist+mcp`, `data-only`, `human`), deux scénarios pilotes, deux variantes adverses, des data packs gelés, des clés de correction, un schéma de revue humaine et un seed de valeur idempotent. Pilote incident 5 runs : skill **5/5** (113 s, 0,77 USD), checklist **0/5** (173 s, 1,31 USD), data-only **0/5** (84 s, 0,55 USD). R-118 5 runs : skill **5/5** à budget 2,00 USD (143 s, 0,95 USD), checklist **1/5**, data-only **1/5**. Panel de 8 reviewers agents : 13/16 approbations, 3 rejets skill corrigés depuis. **Décision : no-go production, go conditionnel** pour une seconde itération avec revue humaine et outcome réel.
- Plugin portable : `plugin/meridian/` fournit **4 skills** (incident-ops, architecture-impact, benefits-okr, enterprise-portfolio), **3 subagents** (vérificateur, impact, découverte), un **serveur MCP read-only** (profils, composition, analyse globale ou applicative, portefeuille, impacts, Claims, learnings, attention), une policy d'autorité et un contrat de réponse. Les profils pilotes sont **ops, architecte, product_owner** ; les skills ont des `references/`, des `evals/` et passent le validateur Agent Skills. Les tools MCP portent les annotations read-only et le serveur a un jeu d'évaluation de 10 questions. Les domain packs restent vides.
- Tests : **1506 tests jumeau** (3 skip), **47 tests plugin**, **8 auth**, **12 routes Boucle**, **166 frontend**, build non-CI OK (le build CI reste bloqué par des avertissements ESLint préexistants). Live : 12 profils, 14 méthodes, 14 compétences ; dev/PO reçoivent **6 faits identiques** avec des lectures différentes, profil inconnu en lecture seule. Portefeuille Paiement : **10 situations, 3 hautes, 6 initiatives**, Value Ledger séparé par devise/unité ; `/analyser` sans application bascule en lecture portefeuille/entreprise.

## Constat du connecteur sur gsf-mockup

Le dépôt `gsf-mockup` ne contient pas de spec OpenAPI statique. Le connecteur fichiers rend donc 0 contrat. Le bridge `depuis_claims` lit les 3 claims `EXPOSE` (`GET /`, `GET /status`, `POST /status`) et produit 3 opérations déclarées, persistables. Les échanges externes réels restent à observer par gateway/APM ou par une source de configuration dédiée.

## Limites actuelles

- Neo4j de production dispose désormais d'un service `docker-compose.prod.yml` (volume, auth, healthcheck, mémoire) et des variables `NEO4J_*` ; le branchement à un Neptune managé et la haute disponibilité cloud restent à faire.
- Context Pack et trace de raisonnement : `contexte.py` borne faits/preuves/entités et produit une empreinte stable ; `raisonnement.py` expose plan, spécialistes, preuves, alternatives, contradictions, abstention et limites. `POST /boucle/analyser` renvoie `contexte` et `raisonnement`.
- PRD-002 et l'index des fiches produit relient mémoire, contexte, raisonnement, apprentissage et valeur. La mémoire durable utilisateur, la rétention/consentement et la calibration restent des chantiers.
- DecisionSupport est exposé dans chaque réponse (`options`, `recommandation` nulle sans proposition explicite, `abstention`, `conditions_de_retournement`).
- Autorité : un client ne peut plus demander `decision`/`approbation` via le body ; le profil est une lentille, l'autorité agent est plafonnée à `proposition`. Hors demo, le profil du body est ignoré au profit de l'identité authentifiée.
- Le tenant est extrait du proxy/OIDC et vérifié dans l'API ; les policies RLS sont fournies et appliquées au contexte de la Boucle et du catalogue d'outils, mais **pas encore activées** ni généralisées à tous les chemins legacy.
- Mongo canonique est migré (parité zéro sur identités, relations, situations, initiatives). Les **cases** restent un store de travail distinct par ADR-0008 ; le fil Aujourd'hui et la carte Atlas lisent encore leurs collections legacy.
- La découverte est automatique pour les dépôts (OpenAPI/WSDL/GraphQL/gRPC/AsyncAPI), les claims `EXPOSE` et OTLP ; les exports propriétaires de gateway/CMDB restent à brancher.
- L'Atlas rend l'impact canonique quand un tenant est sélectionné ; les relations Mongo restent la source principale de la carte et des voisins. Les formulaires de création Outcome/Twin/mémoire ne sont pas encore dans l'UI.
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
3. Brancher les exports propriétaires gateway/CMDB sur le même graphe d'interface (les formats standards sont déjà couverts).
4. Spécifier le store **Travail** (ADR-0008) puis retirer les lectures Mongo du fil Aujourd'hui/Atlas après parité.
5. Brancher les adaptateurs externes sur `Executeur`, ajouter les domain packs (Paiements, Risque), puis installer le plugin dans les harness et mesurer deux workflows réels.

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
`/tmp/meridian-neo4j.env`. En production, `docker-compose.prod.yml` fournit Neo4j avec `NEO4J_PASSWORD` ;
renseigner aussi `GRAPH_STORE=neo4j`, `NEO4J_URI`, `NEO4J_USER` et `NEO4J_DATABASE` dans `.env.prod`.
