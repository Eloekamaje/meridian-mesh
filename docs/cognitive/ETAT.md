# État d'avancement cognitif

**Date :** 2026-10-30  
**Branche :** `jumeau-p4-confort`

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
- Tests : 7 nouveaux, **900 tests jumeau** (3 skip), exécution réelle sur `gsf-mockup` : 3 opérations `GET /`, `GET /status`, `POST /status`.

## Constat du connecteur sur gsf-mockup

Le dépôt `gsf-mockup` ne contient pas de spec OpenAPI statique. Le connecteur fichiers rend donc 0 contrat. Le bridge `depuis_claims` lit les 3 claims `EXPOSE` (`GET /`, `GET /status`, `POST /status`) et produit 3 opérations déclarées, persistables. Les échanges externes réels restent à observer par gateway/APM ou par une source de configuration dédiée.

## Limites actuelles

- L'`application_id` de la candidate est encore l'id du twin : la séparation physique Application/Twin reste à faire en base.
- La persistance des interfaces n'est pas encore branchée à l'ingestion du Gardien ni à l'Atlas.
- Le change/impact engine est pur : pas encore d'événements `DiscoveryRun`, de webhook ni de propagation UI.
- Le connecteur ne lit ni WSDL, ni APM, ni gateway ; ce sont les prochains capteurs.
- La persistance des interfaces n'est pas encore exposée par l'API ni affichée dans l'Atlas.
- La promotion d'un twin provisoire est demandée dans la réponse mais n'a pas encore d'action serveur dédiée.

## Prochain lot

1. Exposer les interfaces/impacts dans l'API et l'Atlas.
2. Ajouter la promotion applicative avec décision humaine et audit.
3. WSDL, gateway/APM en mode ombre, puis tests d'isolation multi-tenant de bout en bout.
4. Brancher les changements du DiscoveryRun sur les notifications et le fil « Aujourd'hui ».
