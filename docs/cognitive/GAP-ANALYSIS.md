# GAP ANALYSIS — Méridian vs PRD-001 et ADR-0002/0003/0004/0005

**Date :** 2026-10-30  
**Périmètre :** code du dépôt `meridian-mesh`, docs `docs/prd/PRD-001-enterprise-intelligence-mesh.md`, ADR-0002 à ADR-0005, `docs/cognitive/ETAT.md`.  
**Règle :** une exigence n'est `conforme` que si le code la satisfait de bout en bout. Une fonctionnalité présente seulement dans les données de démonstration, un prompt ou un test mocké est `partiel` ou `absent`. Les statuts sont volontairement sévères : `ETAT.md` décrit une amorce, pas la cible.

**Note de bas de page :** le working tree contient deux modules non suivis : `backend/jumeau/modele_entreprise.py` (types purs des 8 familles) et `backend/jumeau/capacites.py` (registre capacitaire en mémoire). Ils ne sont importés ni par `backend/server.py`, ni par `backend/jumeau/orchestrateur.py`, ni par `schema.sql` ; ils sont donc signalés comme socle « pur » non branché, et un module pur ne suffit pas à rendre une exigence conforme.

---

## 1. Résumé exécutif

1. **Le noyau reste app-first.** `jumeau` n'a ni `type`, ni périmètre, ni version (`backend/jumeau/schema.sql:jumeau`), `identite.resoudre` pose `application_id = twin_id` (`backend/jumeau/identite.py:resoudre`), et l'accueil de l'UI est l'Atlas des applications (`frontend/src/App.js:Routes`).
2. **Le modèle d'entreprise à 8 familles n'est pas branché.** Un module pur définit les types (`backend/jumeau/modele_entreprise.py:ObjetEntreprise/Twin/Situation/Decision/Outcome`), mais le schéma ne contient que 19 tables, aucune pour Domain, Capability, Process, Journey, Situation, Investigation, Decision, Initiative, Outcome ou Learning (`backend/jumeau/schema.sql`). Les situations, investigations, décisions et initiatives sont des documents Mongo (démo seedée ou publication du gardien), pas des objets canoniques (`backend/seed_data.py:SITUATIONS/CASES/INITIATIVES`, `backend/server.py:seed_database`, `backend/jumeau/gardien.py:publier`).
3. **Le harness capacitaire d'ADR-0004 n'est pas branché.** Un registre pur existe (`backend/jumeau/capacites.py:RegistreCapacites`, avec `lister/chercher/decrire`), mais `orchestrateur.outils` retourne encore exactement trois outils codés en dur (`resoudre_application`, `mobiliser_jumeaux`, `concevoir_architecture`) ; aucun exécuteur avec permissions, audit, timeout ou chargement MCP n'est utilisé. `manifestes.py` ne lit que les dépendances `pyproject.toml`/`package.json` (`backend/jumeau/manifestes.py:lister`).
4. **Le contrat Claim est incomplet.** Les cinq modes `DECLARED/OBSERVED/INFERRED/PROPOSED/CONFIRMED` n'existent pas dans la table `claim` ; seules les assertions d'interface en connaissent trois (`backend/jumeau/interfaces_depot.py:MODES`). Un Claim peut être `ACCEPTED` sans preuve : le trigger n'exige qu'une revue (`backend/jumeau/schema.sql:claim_accepte_exige_revue`).
5. **La boucle de valeur s'arrête avant Outcome/Learning.** Décision et initiative existent comme documents/champs Mongo, et les classes `Outcome`/`Learning` existent dans le module pur, mais aucun outcome n'est mesuré ni relié à une initiative et aucun learning n'est réutilisé ; les preuves de situation/initiative ne sont pas des références à des Claims (chaînes de démonstration, situations du gardien sans preuve structurée) (`backend/seed_data.py:SITUATIONS/INITIATIVES`, `backend/jumeau/gardien.py:situation`, `backend/jumeau/modele_entreprise.py:Outcome/Learning`).

---

## 2. Tableau de conformité par exigence et ADR

Légende : `conforme` = satisfait par le code ; `partiel` = mécanisme réel mais incomplet ou non canonique ; `absent` = non implémenté. `P2` sur une ligne conforme signifie « à préserver », pas « à refaire ». Les exigences proches sont regroupées sur une ligne lorsque le même mécanisme les couvre ; chaque ID est cité.

| ID | Exigence courte | Statut | Preuve code | Écart | Prio |
|---|---|---|---|---|---|
| **FR-001** | Modéliser les 8 familles et leurs agrégats | partiel | `backend/jumeau/modele_entreprise.py` (types purs) ; `backend/jumeau/schema.sql` (19 tables) | Les dataclasses existent, mais aucune persistance/API : pas de table Domain, Capability, Process, Journey, Team, Situation, Investigation, Decision, Initiative, Outcome, Learning ; Domain/Team ne sont que des chaînes (`jumeau.domaine`, `jumeau.equipe`) | P0 |
| **FR-002** | Claim : sujet, prédicat, objet, mode, statut, maturité, confiance, preuves, sources, validité | partiel | `schema.sql:claim`, `claim_preuve`, `claim_source` ; `depot.enregistrer` | Mode absent ; sources et preuves présentes ; validité par `valide_depuis/valide_jusqua` ; pas de lien de remplacement | P0 |
| **FR-003** | Distinguer les 5 modes de connaissance | partiel | `modele_entreprise.Claim/MODES` (purs) ; `schema.sql:claim` ; `interfaces_depot.MODES` | Le type pur porte les 5 modes, mais `claim` n'a pas de colonne `mode` ; les assertions d'interface n'ont que `declared/observed/inferred` ; `conception.repondre` expose un booléen `proposition`, pas un mode de Claim | P0 |
| **FR-004** | Historique des versions et remplacements | partiel | `modele_entreprise.Claim` (pur, `version` et `remplace_id`) ; `depot.enregistrer` (upsert), `depot.reviser` | Le modèle pur porte les champs, mais aucune table d'historique/API : `valide_jusqua` clôt sans chaîne de succession et une réobservation réutilise la même ligne | P1 |
| **FR-005** | Contradictions et inconnues explicites | partiel | `schema.sql:contradiction` ; `backend/jumeau/croisement.py` ; `backend/jumeau/routes.py:trancher` | Contradictions oui, avec preuves A/B, verdict et immuabilité ; aucune entité `Unknown` ni registre des inconnues | P1 |
| **FR-006** | Aucun Claim promu sans preuve et sans règle | partiel | `modele_entreprise.Claim` (pur, `CONFIRMED` exige une preuve) ; `schema.sql:claim_accepte_exige_revue` ; `depot.reviser` | L'invariant existe dans le modèle pur, mais le trigger n'exige qu'une ligne `revue` ACCEPTED, pas une preuve `SUPPORT` ; un Claim M1 sans preuve peut devenir ACCEPTED en base | P0 |
| **FR-010/011/013** | Sources hétérogènes, provenance/fraîcheur, source partielle | partiel | `schema.sql:source` ; `backend/jumeau/interfaces.py:parse_openapi/parse_config/depuis_claims` ; `decouverte_interfaces.executer` | GIT, DOCUMENTATION, CONFLUENCE, JIRA, SERVICENOW, DATADOG, OTLP oui ; pas de Observation/Evidence générique ; fraîcheur non uniforme ; `partial` seulement sur le graphe d'interfaces | P1 |
| **FR-012** | Une source n'est ni une application, ni un Claim, ni le Mesh | conforme | `identite.resoudre` ; `Resolution.preambule` | Respecté par le résolveur typé `source → twin → application` ; à étendre aux Twins non applicatifs | P2 |
| **FR-014/NFR-008** | Ajouter une source, un outil ou un type de Twin sans réécrire le noyau | partiel | `capacites.py:RegistreCapacites` (pur) ; `schema.sql:source_type_check` ; imports de `backend/server.py` et `backend/jumeau/gardien.py` ; `orchestrateur.outils` | Le registre pur couvre les outils, mais il n'est pas branché ; ajouter un type de source exige un `ALTER TABLE` et des imports, et ajouter un outil exige encore de modifier `orchestrateur.outils` | P0 |
| **FR-020** | Twin : identité stable, type, périmètre, propriétaire, version | partiel | `modele_entreprise.Twin` (pur) ; `schema.sql:jumeau` ; `depot.jumeau_par_id` ; `identite.resoudre` | Le type pur existe, mais le stockage n'a ni `type`, ni `scope`, ni `version` ; `application_id = twin_id` fige le Twin comme application | P0 |
| **FR-021/022/023** | Fiche vivante, Claims, preuves, relations, inconnues, non-autorité du Twin | partiel | `gardien.fiche_courante` ; `carte.carte` ; `poignee.py` ; `schema.sql:contradiction` | Fiche et Claims oui ; relations stockées en Mongo, non typées ; `Unknown` absent ; le Twin applicatif reste l'unité de réponse | P1 |
| **FR-030/032** | Relations typées, contradictions, dépendances, capacités partagées, processus, domaines émergents | partiel | `modele_entreprise.Relation/Domain` (purs) ; `server.get_mesh` (collection `relations`) ; `recoupement.verifier` ; `poignee.serrer` | Le runtime stocke les relations en Mongo, sans type ni période de validité ; capacités = Claims `REALISE_CAPACITE` ; aucun Twin Process/Domain/Capability persisté | P0 |
| **FR-031/033** | Confronter les Claims entre sources et Twins ; topologie temporelle | partiel | `recoupement.verifier` ; `croisement.py` ; `connaissance` (validité) ; `frontend/src/pages/Atlas.jsx:Atlas` | Confrontation surtout intra-Twin/sources ; le mode historique de l'Atlas ne s'appuie pas sur une topologie Mesh versionnée ; pas d'API « à une date » | P1 |
| **FR-034/ADR-0003 C1** | Ne pas présenter le Mesh comme source, outil de vérification ou catalogue | partiel | `orchestrateur.PROMPT` ; `server.get_mesh` ; `frontend/src/App.js:Routes` | Le prompt est corrigé ; `/api/mesh` retourne des `jumeaux` et l'accueil redirige vers `/atlas` | P1 |
| **FR-040/041** | Signaux → situations candidates, avec seuils et attributs | partiel | `modele_entreprise.Situation` (pur) ; `gardien.signaux`, `gardien.situation` ; `pulls_runtime.tirer_et_publier` | Règles fixes `REGLES/SCORES` ; confiance `90` codée dans `gardien.situation` ; situations Mongo non canoniques ; pas de seuil de maturité | P1 |
| **FR-042/043** | Exprimer, ignorer, investiguer, décider ; distinguer fait/hypothèse/interprétation | partiel | `modele_entreprise.Situation` (pur) ; `server.agir_situation`, `server.decider_situation` ; `seed_data.SITUATIONS` | Mise à jour de statut et texte libre ; pas d'objet `Expression` typé ; hypothèses et interprétations en JSON de démonstration | P1 |
| **FR-050/051** | Investigation multi-Twins/experts/sources ; décision avec options, critères, incertitudes, acteur, date | partiel | `modele_entreprise.Investigation/Decision` (purs) ; `backend/cases_routes.py:ouvrir_investigation_case`, `decider_case` ; `mobilisation.Mobilisation` | Le modèle pur prévoit hypothèses, experts, options et critères ; le runtime utilise `cases` Mongo, une décision texte et aucun `Expert`/`ExpertContribution` persistant | P1 |
| **FR-052** | Initiative reliée à une décision et à un outcome attendu | partiel | `modele_entreprise.Initiative` (pur, avec `outcome_attendu_ids`) ; `backend/initiatives_routes.py:travail_de_initiative`, `repondre` ; `seed_data.INITIATIVES` | Le type pur prévoit le lien, mais l'initiative Mongo est seulement liée à un travail ; aucun outcome attendu persisté ni lien de preuve | P1 |
| **FR-053/054** | Outcome mesuré et relié ; Learning réutilisable | absent | `modele_entreprise.Outcome/Learning` (classes pures, non branchées) ; aucune table/API/mesure | Les types existent dans le module pur, mais aucune mesure, aucun lien à une initiative, aucune réutilisation ; la boucle décision → initiative → outcome → apprentissage est absente du runtime | P1 |
| **FR-060/061** | Flore agent situé, distinguant existant/conception/comparaison/investigation/décision | partiel | `orchestrateur.executer`, `orchestrateur.PROMPT` ; `server.generer_reponse_flore` | Un seul agent et une politique, mais trois outils applicatifs ; la distinction est confiée au modèle, sans capacités typées ni jeu d'or | P0 |
| **FR-062/AC-001** | Greenfield sans jumeau, sans Atlas, proposition étiquetée | conforme | `conception.repondre` ; `backend/jumeau/tests/test_conception.py` | Aucun jumeau, aucune preuve, `proposition=True`, schéma `mode="proposition"` | P2 |
| **FR-063/064** | Application existante : identité, sources, preuves ; absence non concluante | partiel | `identite.resoudre` ; `mobilisation.preuves_verifiees` ; `Resolution.preambule` | Preuves vérifiées par citation ; la règle « non observé dans tel périmètre, à telle date » n'est centralisée que pour l'identité | P1 |
| **FR-065** | Clarification si l'ambiguïté change la réponse | partiel | `identite.Resolution` (`statut="ambigu"`, `requires_confirmation`) ; `orchestrateur.PROMPT` | L'ambiguïté d'identité est déterministe ; l'ambiguïté générale dépend du modèle et n'est pas testée | P1 |
| **FR-066** | Trace d'orchestration : capacités et outils utilisés | conforme | `orchestrateur.Contexte.outils` ; `orchestrateur.executer:enrichir` | Trace en mémoire, non append-only ; suffisante pour la réponse | P2 |
| **FR-070/071/072** | Manifeste d'outil, registre filtré tenant/persona/périmètre/risque, découverte à la demande | partiel | `backend/jumeau/capacites.py:RegistreCapacites` (pur) ; `orchestrateur.outils` ; `manifestes.py:lister` | Le registre pur sait valider, lister, chercher et décrire un manifeste, mais il n'est pas branché : `orchestrateur.outils` reste une liste de trois outils, sans exécuteur, sans filtre de risque appliqué, sans audit | P0 |
| **FR-073/074** | Lecture seule par défaut ; approbation humaine des actions sensibles | partiel | `orchestrateur.outils` ; `routes.reviser` ; `server.promouvoir_jumeau` | Les trois outils sont read-only, mais sans métadonnées d'effet ; revue de Claim et promotion humaine existent, pas d'approbation générique d'outil | P1 |
| **FR-075** | Ajouter un outil read-only par manifeste/MCP sans modifier le noyau | absent | `orchestrateur.outils` | Aucun chargement de manifeste ou de serveur MCP ; aucun exécuteur | P0 |
| **FR-076** | Aucun modèle n'installe ou n'auto-autorise un outil | conforme | Absence de tout chemin d'installation dans `orchestrateur` | Conforme par construction ; à préserver lors de l'ajout du registre | P2 |
| **FR-080** | Projections par rôle : architecture, business, client, employé, opérations, risque, finance, data, transformation | absent | `seed_data.PERSONAS` (4 personas) ; `server.projete_jumeau` | Quatre personas seulement ; projection centrée sur les champs du jumeau applicatif ; pas de projection des situations, décisions, outcomes | P1 |
| **FR-081** | Chaque projection applique droits et tenant | partiel | `server.resoudre_perimetre`, `server.autorisations` ; `server.get_mesh_interfaces` | Filtrage par espace/persona et refus multi-tenant sur les interfaces ; pas de tenant de requête pour les autres projections | P1 |
| **FR-082/083** | Audit des actions sensibles ; secrets hors prompt/log/preuve/réponse | partiel | `server.journaler` ; `schema.sql:revue`, `identity_decision` ; `interfaces._assainir_url` ; `pulls_runtime._source_publique` | Audit partiel ; appels d'outils seulement en mémoire (`Contexte.outils`) ; pas de redaction globale ni de journal append-only des outils | P1 |
| **NFR-001/002/005** | Preuve, temporalité, explicabilité de chaque affirmation | partiel | `schema.sql:preuve/claim` ; `interfaces.Assertion` ; `frontend/src/components/MessageFlore.jsx:MessageFlore` | Preuves solides sur Claims et interfaces ; situations, décisions et initiatives ne portent pas de références de preuve normées ; modes absents | P0 |
| **NFR-003** | Multi-tenant sur objets, cache, prompt, outil, log | partiel | `tenant_id` dans `schema.sql` ; `server.get_mesh_interfaces` ; `backend/jumeau/naissance.py:naitre` | Stockage tenant-scoped ; aucune identité de tenant dans la requête HTTP ; naissance avec `tenant_id="local"` ; pas de RLS | P0 |
| **NFR-004/009** | Sécurité, moindre privilège, résilience aux pannes | partiel | `pulls_runtime.tirer_et_publier` ; `orchestrateur.executer` ; `server.generer_reponse_flore` | Sources en panne isolées ; pas de timeout/retry par outil ; pas de politique de privilège centrale ; un échec d'orchestrateur produit un signal, pas une absence | P1 |
| **NFR-006** | p95 de latence défini par produit | partiel | `backend/jumeau/latence.py:main` (`REFERENCES`, `OBJECTIFS`, p50/p95) ; `mesure.Chrono` | Banc manuel avec objectifs 2 s/5 s ; p95 calculé mais non comparé à un SLO de production ; aucune mesure continue | P2 |
| **NFR-007** | Coût et usage par tour | partiel | `mesure.usage` ; `conception._usage` ; `frontend/src/components/MessageFlore.jsx:MessageFlore` | Coût exposé en conception et dans l'UI ; l'orchestrateur n'agrège pas systématiquement l'usage des outils | P2 |
| **NFR-010** | Évaluer outils, Claims et décisions par un jeu d'or | partiel | `backend/jumeau/evaluation.py:passe` ; `backend/jumeau/tests/test_orchestrateur.py` | L'évaluation couvre les Q&A du jumeau ; les tests d'orchestrateur mockent l'agent et ne mesurent pas le choix d'outil ; pas de jeu d'or Claims/décisions | P1 |
| **AC-002/003** | Réponse existante avec Claims/preuves/fraîcheur/contradictions ; situation transverse multi-Twins et domaine | partiel | `mobilisation.preuves_verifiees` ; `server.filtre_situation` | Preuves citées possibles ; fraîcheur et contradictions non garanties ; situations multi-jumeaux mais sans Twin Domain/Capability | P1 |
| **AC-004** | Twin PROCESS/CAPABILITY/JOURNEY créable sans modifier le noyau | partiel | `modele_entreprise.Twin` (pur) ; `schema.sql:jumeau` ; `identite.resoudre` | Le type existe dans le module pur, mais `jumeau` n'a pas de champ `type`, `application_id` est l'identité du Twin et la création/lecture n'est pas supportée | P0 |
| **AC-005** | Outil read-only ajouté par manifeste/MCP, filtré et audité | partiel | `capacites.py:RegistreCapacites` (pur) ; `orchestrateur.outils` | Le registre existe, mais aucun outil n'est ajouté à chaud, filtré par politique ou audité de bout en bout | P0 |
| **AC-006** | Décision reliée à initiative, outcome et apprentissage | absent | `modele_entreprise.Decision/Initiative/Outcome/Learning` (purs) ; `cases_routes.decider_case` ; `initiatives_routes` | Les classes pures existent, mais aucune chaîne persistée/API : décision et initiative en Mongo, aucun outcome mesuré ni learning réutilisé | P1 |
| **AC-007/008** | Absence formulée « non observé » ; proposition distinguée d'observation | partiel | `identite.Resolution.preambule` ; `conception.repondre` ; `MessageFlore` | Absence non concluante limitée à l'identité ; proposition UI/API correcte, mais pas de mode Claim `PROPOSED` vs `OBSERVED` | P1 |
| **ADR-0002** | Orchestrateur général, un modèle, trois outils, sélection bornée | partiel | `orchestrateur.executer` ; `server.intention_selection` | Un modèle et trois outils ; le chemin de sélection explicite réintroduit une classification par expressions (`intention_selection`) | P1 |
| **ADR-0003** | Mesh transversal, Flore située, 5 modes, UI non app-first, test d'architecture | partiel | `orchestrateur.PROMPT` ; `conception.repondre` ; `schema.sql:claim` ; tests | C1/C2 conformes ; C3–C7 absents ou partiels ; aucun test d'architecture n'interdit `Twin == application` ou `Mesh == source` | P0 |
| **ADR-0004** | Harness capacitaire : manifeste, registre, découverte, exécuteur, politique, audit | partiel | `capacites.py:RegistreCapacites` (pur) ; `orchestrateur.outils` ; `manifestes.py` | Le registre et le manifeste sont posés en mémoire, mais l'exécuteur, le chargement, la politique appliquée et l'audit append-only manquent ; les trois outils restent le noyau de fait | P0 |
| **ADR-0005** | 8 familles, 7 types de Twin, agrégats, temporalité | partiel | `modele_entreprise.py` (types purs) ; `schema.sql` ; `registre.document` ; `identite.resoudre` | Les types purs existent, mais le stockage et les API restent app-only ; agrégats absents ; la temporalité de connaissance n'existe que sur `claim` et `interface_assertion`, pas sur les relations ni les situations | P0 |

---

## 3. Écarts d'architecture

### 3.1 Mesh encore réduit à un outil/source ou app-first

Le discours est corrigé : `orchestrateur.PROMPT` dit que le Mesh n'est « ni une source, ni un outil de vérification » et `identite.resoudre` distingue dépôt, Twin et application. Mais le produit reste app-first par ses points d'entrée : `frontend/src/App.js` redirige `/` vers `/atlas` ; `Atlas.jsx` est un `ReactFlow` de nœuds `twin` ; `server.get_mesh` retourne `jumeaux` et `relations`. La policy est donc en avance sur le modèle et l'UI.

### 3.2 Noyau = trois outils vs registre capacitaire

`orchestrateur.outils` construit une liste fermée de trois fonctions et `executer` la passe directement à `Agent(tools=tour)`. Un registre pur existe (`backend/jumeau/capacites.py:RegistreCapacites`) et sait valider, lister, chercher et décrire un manifeste, mais il n'est importé ni par `orchestrateur.py` ni par `server.py` : aucun exécuteur avec timeout, permission, coût, audit ou chargement MCP n'est branché. `manifestes.py` reste un lecteur de dépendances de paquets. C'est l'alternative 1 rejetée par ADR-0004, à laquelle s'ajoute un début de registre non intégré.

### 3.3 Modèle Twin app-only vs 8 familles / 7 types

La table `jumeau` ne porte pas de `type` ; `identite.resoudre` fixe `application_id = twin_id` ; les tables `interface_*` utilisent `application_id` ; `registre.document` projette toujours une « Application ». Le module pur `backend/jumeau/modele_entreprise.py:Twin` définit bien les 7 types, mais il n'est ni persisté ni exposé. Les types `PROCESS`, `CAPABILITY`, `JOURNEY`, `ORGANIZATION`, `PRODUCT`, `DATA_DOMAIN` d'ADR-0005 n'ont donc ni stockage, ni API, ni UI. Les capacités sont des Claims `REALISE_CAPACITE` (`carte.carte`), pas des entités.

### 3.4 Absence de Situation/Investigation/Decision/Initiative/Outcome/Learning comme objets canoniques

Le module pur `modele_entreprise.py` définit `Situation`, `Investigation`, `Decision`, `Initiative`, `Outcome` et `Learning`, mais le schéma ne contient aucune de ces tables et les classes ne sont branchées à aucune API. Les situations, cas et initiatives sont stockés dans Mongo : seed de démonstration (`server.seed_database`) et publications réelles du gardien ou du tirage OTLP (`gardien.publier`, `pulls_runtime._publier_situation`). `cases_routes.py` et `initiatives_routes.py` les mettent à jour, mais les décisions sont des textes dans `case.decisions` (`cases_routes.decider_case`) et les preuves sont des listes de chaînes dans la démo (`seed_data.SITUATIONS`). Aucun `Outcome` ni `Learning` n'est mesuré ou relié. La boucle PRD §2 s'arrête à l'initiative et ne mesure rien.

### 3.5 Absence de manifests/permissions/découverte dynamique

Le registre pur `capacites.py:RegistreCapacites` fournit `lister`, `chercher` et `decrire`, mais il n'est pas la source du tour : `orchestrateur.outils` reste la seule autorité. Les permissions sont des autorisations d'espace sur les jumeaux (`server.autorisations`), pas des permissions d'outil par tenant, persona, périmètre et risque. Aucun audit append-only des appels d'outils : `Contexte.outils` est une liste en mémoire, renvoyée dans `orchestration` (`orchestrateur.executer:enrichir`). Aucun chargement de manifeste/MCP et aucune découverte appliquée au tour.

### 3.6 Projections/UI app-first

Les projections sont des vues de jumeaux filtrées par persona et espace (`server.projete_jumeau`, `server.autorisations`). Les 9 rôles de FR-080 ne sont pas représentés : `seed_data.PERSONAS` n'en contient que 4. Les situations sont visibles dans l'Atlas (`Atlas.jsx:situationsJumeaux`) et dans `Actualites`, mais l'accueil reste la carte des applications. Les écrans `InterfacesJumeau.jsx` et `SchemaSvg.jsx` sont utilement centrés sur les preuves et les états, mais restent des vues d'application ou de schéma, pas des projections d'entreprise.

### 3.7 Tests et évaluation insuffisants pour la cible

Les tests sont nombreux et sérieux sur l'identité, les interfaces et la conception (`backend/jumeau/tests/`), et deux suites testent les modules purs (`test_modele_entreprise.py`, `test_capacites.py`). Mais il n'existe pas de test d'architecture qui échoue si un outil est ajouté dans `orchestrateur.outils`, si `Twin == application`, ou si le Mesh est présenté comme une source. `test_orchestrateur.py` mocke l'agent et vérifie la présence des trois outils ; il ne mesure pas la sélection réelle. `evaluation.py:passe` évalue des Q&A de jumeau (exactitude, ancrage), pas les choix d'outils, les modes de Claim ni les décisions. Aucun test d'isolation multi-tenant de bout en bout.

---

## 4. Ce qui est déjà bon et à conserver

- **Résolution d'identité typée et absence non concluante** : `identite.Resolution` porte mentions, chemin, candidats, confiance, ambiguïté et préambule ; `Resolution.preambule` dit explicitement qu'une absence n'est pas une preuve. C'est un bon socle pour AC-007 et FR-012.
- **Claims, preuves, maturité et revue humaine** : `schema.sql:claim/preuve/revue` avec preuves immuables, revue obligatoire avant `ACCEPTED`, maturité recalculée par trigger (`recalculer_maturite`) et contradictions avec verdict. C'est la partie la plus solide du produit.
- **Graphe d'interfaces** : `interfaces.py` et `interfaces_depot.py` séparent `declared`, `observed`, `inferred`, calculent des identifiants stables, assainissent les URLs, refusent les secrets et persistent par tenant. `decouverte_interfaces.executer` journalise un `DiscoveryRun` avec changements et impacts.
- **Runtime en ombre et résilience des sources** : `connecteurs_runtime` produit des assertions `observed` ; `pulls_runtime.tirer_et_publier` isole les pannes par source, masque URL et secret (`_source_publique`) et publie une situation seulement sur impact prouvé (`impacts_situations.situation_depuis_run`).
- **Conception greenfield propre** : `conception.repondre` ne mobilise aucun jumeau, ne produit aucune preuve et expose `proposition=True` avec un schéma `mode="proposition"` ; les tests `test_conception.py` verrouillent cette séparation.
- **Traçabilité de l'orchestration** : `Contexte.outils` et `orchestrateur.executer:enrichir` exposent les outils et arguments utilisés ; le budget `_Budget` évite les boucles d'outils.
- **UI de preuve** : `MessageFlore` affiche l'origine, la relecture et le badge « Proposition » ; `SchemaSvg` distingue les états de flèche (`code`, `valide`, `recoupe`, `propose`, `conteste`). Ces affordances doivent survivre à la refonte.
- **Sécurité des secrets sur les interfaces** : `_assainir_url`, `_url_porte_un_secret` et `_source_publique` sont des garde-fous concrets à généraliser, pas à réécrire.
- **Socle de types purs à brancher, pas à réécrire** : `backend/jumeau/modele_entreprise.py` pose les 8 familles, les 7 types de Twin, les 5 modes et les classes de la boucle ; `backend/jumeau/capacites.py` pose le manifeste et le registre. Ces modules sont testés isolément mais non branchés ; ils constituent un bon point de départ pour P0-A/P0-C.
- **Décision 1 Twin ↔ 1 application** : cohérente avec `ETAT.md` et le PRD §10 ; à conserver, mais en ajoutant un `type` et en créant des Twins distincts pour les processus/capacités.

---

## 5. Plan P0/P1/P2 avec dépendances, fichiers, critères et tests

### P0 — Socle de vérité et d'extensibilité

**P0-A — Modèle d'entreprise minimal et types de Twin.**  
Contenu : ajouter `type`, `scope`, `version` à `jumeau` (APPLICATION par défaut, puis PROCESS, CAPABILITY, JOURNEY, ORGANIZATION, PRODUCT, DATA_DOMAIN) ; créer les tables canoniques `domain`, `relationship`, `situation`, `investigation`, `decision`, `initiative` (squelettes, cycle de vie en P1-A) ; permettre à un Claim de cibler autre chose qu'une application.  
Fichiers : `backend/jumeau/modele_entreprise.py` (brancher les types purs), `backend/jumeau/schema.sql`, `backend/jumeau/depot.py`, `backend/jumeau/registre.py`, `backend/jumeau/identite.py`, `backend/server.py`, `frontend/src/pages/Jumeaux.jsx`, `frontend/src/pages/Atlas.jsx`.  
Dépendances : aucune.  
Critères : AC-004 ; un Twin PROCESS/CAPABILITY/JOURNEY est créé et lu sans modifier le noyau ; un Claim peut porter sur un PROCESS ; les données de démonstration sont séparées des objets canoniques.  
Tests : migration idempotente ; création/lecture des 3 types ; test d'architecture qui échoue si `application_id` est utilisé comme type universel dans le noyau.

**P0-B — Contrat Claim complet.**  
Contenu : aligner le schéma sur le modèle pur (`mode` avec les 5 valeurs, `version`, `remplace_id`) ; exiger au moins une preuve `SUPPORT` pour passer à `ACCEPTED` (le trigger doit vérifier `claim_preuve`, pas seulement `revue`) ; exposer les modes dans l'API et l'UI.  
Fichiers : `backend/jumeau/schema.sql`, `backend/jumeau/depot.py`, `backend/jumeau/connaissance.py`, `backend/jumeau/routes.py`, `frontend/src/components/MessageFlore.jsx`.  
Dépendances : P0-A pour le typage des sujets.  
Critères : FR-002/003/004/006 ; un Claim sans preuve reste `PROPOSED/INFERRED` et ne peut pas être `ACCEPTED` ; l'historique d'un remplacement est lisible ; les 5 modes sont visibles.  
Tests : `test_claim_modes.py`, `test_promotion_preuve.py`, test de migration des Claims existants (backfill `DECLARED`), test API/UI.

**P0-C — Harness capacitaire v0.**  
Contenu : définir le manifeste d'outil (nom, capacité, objets lus/écrits, schéma, portée, permissions, coût, timeout, mode de preuve) ; créer registre + politique + exécuteur + audit append-only ; exposer `search_tools`/`describe_tool` ; convertir les trois outils actuels en adaptateurs, pas en noyau.  
Fichiers : `backend/jumeau/capacites.py` (brancher le registre pur), nouveaux `backend/jumeau/harness/politique.py`, `executeur.py`, `chargeur.py` ; `backend/jumeau/schema.sql` (`tool_manifest`, `tool_call_audit`) ; `backend/jumeau/orchestrateur.py` ; `backend/server.py`.  
Dépendances : P0-A et P0-B (types d'objets et modes de preuve).  
Critères : AC-005 ; un outil read-only ajouté par manifeste est découvert et appelé sans modifier le code du noyau ; un outil sans permission explicite n'est pas exposé ; le catalogue est filtré par tenant/persona/périmètre/risque ; une action sensible est bloquée sans approbation ; chaque appel est audité.  
Tests : `test_harness_manifeste.py` (ajout à chaud), `test_harness_politique.py` (filtrage et refus), `test_harness_audit.py`, test de non-régression des trois outils.

**P0-D — Frontière tenant et règle d'absence.**  
Contenu : porter le tenant dans le contexte de requête (auth/middleware), supprimer `tenant_id="local"` de `naissance.naitre`, appliquer le tenant à toutes les lectures/écritures, formaliser « non observé dans tel périmètre, à telle date ».  
Fichiers : `backend/auth.py`, `backend/server.py`, `backend/jumeau/depot.py`, `backend/jumeau/naissance.py`, `backend/jumeau/routes.py`.  
Dépendances : P0-B.  
Critères : NFR-003 ; deux tenants ne peuvent ni se lire ni se citer ; AC-007 ; aucune réponse hors tenant.  
Tests : isolation croisée API, test de naissance avec tenant explicite, test de la formulation d'absence.

### P1 — Boucle d'exploitation et projections

**P1-A — Boucle Situation → Investigation → Decision → Initiative canonique.**  
Contenu : relier les objets P0-A aux Claims et preuves ; structurer une décision (options, critères, incertitudes, acteur, date, preuves) ; relier une initiative à une décision et à un outcome attendu ; projeter les `cases`/`initiatives` Mongo vers ces objets sans casser les routes existantes.  
Fichiers : `backend/jumeau/schema.sql`, nouveau `backend/jumeau/boucle.py`, `backend/cases_routes.py`, `backend/initiatives_routes.py`, `backend/server.py`.  
Dépendances : P0-A, P0-C.  
Critères : AC-003/AC-006 partiels ; une situation relie plusieurs Twins et un domaine ; une décision est reliée à une investigation, une initiative et des preuves ; les routes UI existantes continuent de fonctionner.  
Tests : `test_boucle.py`, test de projection Mongo → canonique, test API décision/initiative.

**P1-B — Outcome et Learning.**  
Contenu : créer `outcome` (mesure, période, cible, preuve, initiative) et `learning` (énoncé, conditions de réutilisation, situation source) ; exposer la mesure et la réutilisation dans l'UI.  
Fichiers : `backend/jumeau/schema.sql`, nouveau `backend/outcomes_routes.py`, `backend/initiatives_routes.py`, `frontend/src/pages/TravailDetail.jsx`.  
Dépendances : P1-A.  
Critères : FR-053/054 ; une décision peut être reliée à une initiative, un outcome mesuré et un apprentissage réutilisable ; AC-006.  
Tests : test de chaîne complète décision → initiative → outcome → learning → nouvelle situation.

**P1-C — Projections par rôle et UI situation-first.**  
Contenu : définir les 9 projections de FR-080 ; appliquer droits + tenant ; faire de « Aujourd'hui »/situations l'entrée principale et de l'Atlas une exploration secondaire ; ajouter les vues métier.  
Fichiers : `backend/server.py`, `backend/mesh_vue_routes.py`, `frontend/src/App.js`, `frontend/src/pages/Atlas.jsx`, nouveau `frontend/src/pages/Projections.jsx`.  
Dépendances : P0-A, P1-A.  
Critères : FR-080/081 ; neuf rôles ; aucune projection ne fuit un tenant ou un jumeau hors périmètre ; l'Atlas n'est plus l'accueil unique.  
Tests : test API des 9 projections, test d'isolation, test de navigation UI.

**P1-D — Tests d'architecture et évaluation de la cible.**  
Contenu : tests qui échouent si un outil est ajouté hors manifeste, si `Twin == application`, si le Mesh est présenté comme source ; jeu d'or pour la sélection d'outils, les modes de Claim et les décisions.  
Fichiers : `backend/jumeau/tests/test_architecture.py`, `backend/jumeau/evaluation.py`, `backend/jumeau/tests/test_orchestrateur.py`, `backend/jumeau/tests/test_conception.py`.  
Dépendances : P0-C, P1-A.  
Critères : NFR-010 ; les régressions d'architecture échouent en CI ; les choix d'outils sont mesurés sur des cas réels.  
Tests : `test_architecture.py`, `test_evaluation_outils.py`, `test_evaluation_claims.py`.

### P2 — Échelle et exploitation

**P2-A — Mesh temporel et fraîcheur.**  
Contenu : période de validité sur `relationship`, API « topologie à une date », propagation de la fraîcheur des preuves aux projections.  
Fichiers : `backend/jumeau/schema.sql`, `backend/server.py`, `backend/mesh_vue_routes.py`, `frontend/src/pages/Atlas.jsx`.  
Dépendances : P0-A, P1-A.  
Critères : FR-033/NFR-002 ; une relation et une situation sont lisibles à une date ; une preuve périmée est signalée.  
Tests : test de snapshot daté, test de fraîcheur.

**P2-B — Coût, latence et robustesse du harness.**  
Contenu : budget par outil, timeout, retry, circuit breaker, quotas, télémétrie coût/latence.  
Fichiers : `backend/jumeau/harness/executeur.py`, `backend/jumeau/mesure.py`, `backend/jumeau/orchestrateur.py`.  
Dépendances : P0-C.  
Critères : NFR-006/007/009 ; un outil lent ou en panne ne bloque pas le tour ; chaque tour expose son coût.  
Tests : test de timeout/retry, test de budget, test de panne isolée.

**P2-C — Séparation démonstration / canonique.**  
Contenu : sortir les situations, cas et initiatives de démonstration des requêtes canoniques ; les isoler dans un espace `demo_*` ou les migrer vers le modèle P0-A.  
Fichiers : `backend/server.py:seed_database`, `backend/seed_data.py`, `backend/cases_routes.py`, `backend/initiatives_routes.py`, frontend.  
Dépendances : P0-A, P1-A.  
Critères : aucune situation/décision de démonstration n'est présentée comme un objet d'entreprise ; les tests et la démo restent reproductibles.  
Tests : test de séparation des collections, test de navigation démo.

---

## 6. Risques de régression et décisions à prendre

### Risques

- **Migration du schéma Claim** : `schema.sql` est rejoué à chaque initialisation (`depot.appliquer_schema`), et `depot.enregistrer` fait un upsert sur `(jumeau_id, prédicat, objet)`. Ajouter `mode/version` sans backfill casse les Claims existants et les tests. Mitigation : migration expand/contract, backfill `DECLARED`, double lecture temporaire.
- **Double stockage Postgres/Mongo** : les Claims sont en Postgres, les situations/cas/initiatives/relations en Mongo (`server.seed_database`, `poignee.py`). Créer les objets canoniques sans supprimer les collections crée deux vérités. Mitigation : décider la source de vérité (D1) et projeter l'autre store.
- **Harness dynamique** : un registre d'outils augmente la surface d'attaque (manifeste piégé, outil qui ment, sélection erronée). Mitigation : manifeste signé/allowlist, lecture seule par défaut, exécuteur avec timeout et audit (ADR-0004).
- **Refonte UI** : `App.js` redirige `/` vers `/atlas` et de nombreux écrans dépendent des routes `cases`/`initiatives`. Changer l'accueil casse les liens profonds. Mitigation : feature flag, conservation des routes, redirection transitoire.
- **Multi-tenant** : `auth.py` accepte `X-Persona` en mode demo et `server.resoudre_perimetre` s'appuie sur des espaces statiques (`seed_data.ESPACES`). Introduire un tenant de requête peut casser la démo. Mitigation : mode demo avec tenant explicite `demo`, tests d'isolation.
- **Exigence de preuve** : durcir `ACCEPTED` peut supprimer les hypothèses M1 utiles. Mitigation : distinguer hypothèse (`PROPOSED/INFERRED/M1`) et connaissance promue (`ACCEPTED` avec preuve), sans interdire les hypothèses.

### Décisions à prendre

1. **D1 — Source de vérité canonique** : Postgres pour les objets d'entreprise et les Claims, Mongo limité aux projections/UI de démonstration. Sinon le double stockage restera une dette.
2. **D2 — Modèle Twin** : conserver 1 Twin ↔ 1 entité et ajouter `type`, ou créer des Twins distincts pour Process/Capability. Le PRD §10 exclut le multi-Twin par application ; la première option est la plus cohérente.
3. **D3 — Standard du harness** : manifeste interne d'abord, adaptateur MCP ensuite, OpenAPI en option. ADR-0004 rejette MCP comme voie unique.
4. **D4 — Tenant** : tenant par déploiement ou tenant par requête avec RLS. NFR-003 et `server.get_mesh_interfaces` poussent vers le tenant par requête.
5. **D5 — Entrée produit** : « Aujourd'hui »/situations comme accueil, Atlas comme exploration. FR-034 et ADR-0003 C1/C6 l'exigent ; `App.js` fait l'inverse aujourd'hui.
6. **D6 — Données de démonstration** : les garder dans un namespace `demo` ou les migrer vers le modèle canonique. En l'état, `seed_data.SITUATIONS` et `seed_data.INITIATIVES` contaminent la lecture produit.

---

## 7. Questions ouvertes (max 6)

1. **Premier Twin non applicatif** : `PROCESS` ou `CAPABILITY` ? Le PRD §13 pose la question ; ADR-0005 plan d'implémentation propose `PROCESS` puis `CAPABILITY`.
2. **Standard de découverte d'outils** : manifeste interne, MCP, OpenAPI ou plusieurs ? ADR-0004 accepte les trois, mais le premier choix conditionne le registre.
3. **Stockage de la boucle** : unifier Situation/Investigation/Decision/Initiative/Outcome/Learning en Postgres, ou conserver Mongo pour la boucle et Postgres pour les Claims ? Aucun ADR ne tranche.
4. **Modèle de tenant** : un tenant par déploiement ou multi-tenant par requête avec RLS ? NFR-003 l'exige, `auth.py` et `naissance.py` ne le permettent pas encore.
5. **Seuils signal → situation** : quelles données historiques et quels seuils de maturité pour éviter les faux positifs ? FR-040 le demande, `gardien.signaux` ne fixe que des règles structurelles.
6. **Rétention et gouvernance** : quelle durée pour les preuves, observations, outcomes et contradictions non tranchées ? Le PRD §13 questions 5 et 6 restent ouvertes ; `schema.sql:contradiction` et `preuve` sont immuables mais sans politique de rétention.
