# Méridian — état actuel et reste à faire

> **Photographie :** 6 novembre 2026, commit `d2d9f9b`.
> Ce document décrit ce qui existe réellement dans le dépôt ; il ne décrit pas la cible.
> Les documents de vision et les PRD restent la cible ; ce fichier est la carte de l’état
> courant et la matrice de traçabilité vers le code et les tests. Les écarts produit détaillés
> sont dans [ecarts-vision.md](ecarts-vision.md).

## 0. Comment lire ce document

Chaque capacité est lue avec trois statuts :

- **Implémenté** : présent dans le code, couvert par des tests, utilisable ;
- **Partiel** : code présent, mais intégration, couverture ou exploitation incomplète ;
- **Cible** : décrit dans la vision ou l’ADR, pas encore dans le code.

Une phrase sans code derrière reste une cible, même si elle est déjà dans un diagramme.

---

## 1. Résumé exécutif

Méridian est un **système d’intelligence vivante de l’entreprise**. Sa cible est la boucle
**Découvrir → Maturer → Exprimer → Investiguer → Décider → Agir → Mesurer → Apprendre**,
mécanique opérationnelle du triptyque **Découvrir · Comprendre · Décider**. **Méridian n’est
pas un Twin** : les Twins sont des représentations d’entités de l’entreprise, pas la
plateforme elle-même (voir 3.10).

Dans le code actuel, elle s’appuie sur quatre couches qui étaient souvent séparées :

1. **un modèle d’entreprise canonique** (Twins, situations, décisions, initiatives, outcomes,
   learnings, claims, preuves) ;
2. **une découverte de liens entre composants** à partir du code, des contrats, de la
   configuration, des manifestes et des traces ;
3. **une mémoire d’agent multi-niveaux**, avec provenance, portée, rétention et revue ;
4. **un harness agentique borné**, qui enquête, propose et s’arrête, sans jamais confirmer seul.

Le principe reste : **le déterministe prouve, l’agent propose, l’humain confirme**.

---

## 1 bis. Diagramme d’architecture

![Architecture actuelle de Méridian](../diagrammes/architecture-etat-actuel.png)

[Ouvrir le diagramme en grand (HTML)](../diagrammes/architecture-etat-actuel.html) ·
[SVG](../diagrammes/architecture-etat-actuel.svg)

Le schéma distingue les surfaces, l’API, le harness, le moteur de liens, la connaissance,
la mémoire, les sources, Postgres canonique et les stores spécialisés. Le moteur de liens est
le point focal ; la revue humaine reste la seule voie de confirmation.

### Composants du diagramme

| Composant | Responsabilité | Fichiers principaux |
|---|---|---|
| **Surfaces** | Atlas, Travail, Boucle, revue, preuves | `frontend/src/pages`, `frontend/src/components/map`, `frontend/src/components/case` |
| **API FastAPI** | auth, RBAC, REST, SSE, limites | `backend/meridian/adapters/inbound/http/*.py`, `auth.py`, `limites.py` |
| **Harness** | exploration, enquête, planification, budgets, arrêt | `application/exploration_agent.py`, `investigation_runtime.py`, `boucle_investigation.py`, `adapters/outbound/llm/planificateur_liens.py` |
| **Moteur de liens** | extraction, identité, matching, contradictions | `application/moteur_liens.py`, `connectors/cbm_liens.py`, `connectors/extraction_*.py`, `domain/chemins.py` |
| **Connaissance** | claims, preuves, maturité, calibration | `domain/modele_entreprise.py`, `postgres/connaissance.py`, `postgres/entreprise_depot.py`, `postgres/calibration_croyances.py` |
| **Mémoire** | travail, épisodique, sémantique, procédurale, réflexive, prospective, organisationnelle, documentaire | `postgres/memoire_durable.py`, `memoire_org.py`, `memoire_prospective.py`, `session_memoire.py`, `retrieval_memoire.py`, `chunk_store.py` |
| **Sources** | Git, Confluence, SharePoint, ServiceNow, Datadog, OTLP, CBM, Graphify, legacy | `adapters/outbound/connectors/*`, `adapters/outbound/postgres/ingestion_runtime.py` |
| **Stores spécialisés** | Travail Mongo, graphe Neo4j, temps réel Redis, artefacts S3/MinIO | `adapters/outbound/mongo/*`, `neo4j/*`, `redis/*`, `connectors/index_store.py` |
| **Postgres canonique** | identités, liens, mémoire, exécution, planification | `adapters/outbound/postgres/schema.sql`, `depot.py`, `code_index_store.py` |

---

## 2. Architecture d’exécution

### 2.1 Couches

```text
frontend/                       React 19, Atlas, Travail, revue, boucle
        │
        ▼
backend/meridian/adapters/inbound/http
        │  FastAPI, auth, RBAC, SSE
        ▼
backend/meridian/application    cas d’usage, moteurs, harness, mémoire
        │
        ▼
backend/meridian/domain         modèles purs, invariants, décisions
        │
        ▼
backend/meridian/ports          contrats
        │
        ▼
backend/meridian/adapters/outbound
        ├── postgres            modèle canonique, mémoire, exécution, planification
        ├── mongo               Travail, cas, pièces, legacy
        ├── neo4j               projection graphe
        ├── redis               SSE, état des tours, rate limiting
        ├── connectors          Git, Confluence, SharePoint, ServiceNow, Datadog, OTLP, CBM…
        ├── llm                 DeepSeek, Bedrock, planificateurs, exploration
        ├── aws                 SQS/EventBridge/S3/Secrets Manager optionnels
        └── stockage            artefacts d’index locaux ou S3/MinIO
```

### 2.2 Stockages et source de vérité

| Stockage | Rôle | Contenu |
|---|---|---|
| **Postgres** | **source canonique** | identités, claims, preuves, objets d’entreprise, décisions, mémoire durable, mémoire prospective, exécution, planification, chunks, communautés |
| **MongoDB** | Travail et legacy | cas, conversations, pièces, situations historiques, collections de démonstration, journal |
| **Neo4j** | projection graphe | nœuds Twin, relations, parcours, situations, impacts, communautés |
| **Redis** | temps réel | bus SSE, état des tours, verrous, rate limiting |
| **Local / S3 / MinIO** | artefacts | copies Git au SHA, index reconstructibles, preuves de code |
| **Graphify** | contexte d’architecture | documentation, communautés, carte large |
| **CBM** | graphe de code | routes, appels HTTP, variables, tables, ressources |

Règle : **Postgres porte le canonique**. Mongo ne doit pas devenir une seconde vérité pour les
objets d’entreprise. La double écriture Travail est un pont temporaire, pas une cible.

### 2.3 Workers

| Worker | Rôle |
|---|---|
| `source_worker` | ingestion pull-first des sources Git et exécution des runs |
| `outbox_worker` | publication des événements durables (outbox) |
| `travail_worker` | synchronisation du read model Travail Mongo → Postgres |
| `planification_worker` | synchronisation capacité/charge/prévision |
| `reconciliation_worker` | réconciliation périodique des liens |
| `execution_worker` | exécution des runs et des outils |

Scripts de développement : `scripts/dev-source-worker.sh`, `dev-outbox-worker.sh`,
`dev-travail-worker.sh`, `dev-planification-worker.sh`.

---

## 3. Flux fonctionnels

### 3.1 Naissance et ingestion d’un Twin

```text
source (Git, Confluence, SharePoint, ServiceNow, Datadog, OTLP)
  → run d’ingestion
  → extraction déterministe
  → observations + couverture
  → claims + preuves
  → manifeste de naissance
  → twin.born
  → découverte locale des liens
  → propositions / cas de résolution
```

Points d’entrée :

- `backend/meridian/adapters/outbound/connectors/ingerer.py` : ingestion Git ;
- `backend/meridian/adapters/outbound/connectors/naissance.py` : naissance et sources ;
- `backend/meridian/adapters/outbound/postgres/relations_naissance.py` : manifeste et
  propositions historiques ;
- `backend/meridian/adapters/outbound/postgres/decouverte_naissance.py` : `twin.born`,
  `reconcilier_twin`, réconciliation globale.

### 3.2 Connaissance et preuves

- Les **Claims** portent un sujet, un prédicat, un objet, une preuve et une maturité.
- Les **preuves** sont localisées (fichier, ligne, SHA, source) et versionnées.
- Les **contradictions** sont conservées ; elles ne sont jamais écrasées silencieusement.
- La **maturité** distingue hypothèse, corroboration, validation.
- La **calibration** compare confiance annoncée et outcome observé.

Modules clés :

- `domain/modele_entreprise.py` ;
- `adapters/outbound/postgres/connaissance.py` ;
- `adapters/outbound/postgres/entreprise_depot.py` ;
- `application/evaluation_raisonnement.py`, `application/evaluation_cognitive.py` ;
- `adapters/outbound/postgres/calibration_croyances.py`.

### 3.3 Découverte des liens entre composants

Le moteur relie producteurs, consommateurs, déploiements et preuves.

```text
code / contrats / configuration / manifestes / traces
  → observations normalisées
  → interfaces, appels, déploiements, configurations
  → résolution d’identité (service, hôte, route, file, propriété, JNDI)
  → appariement + score de chemin
  → lien proposé, question ou contradiction
  → revue humaine
```

Sources d’extraction :

| Élément | Source |
|---|---|
| code multi-langages | CBM (`cbm_observations.py`, `cbm_liens.py`) |
| code local de repli | `extraction_code.py` |
| contrats | `extraction_contrats.py` + `domain/interfaces.py` |
| configuration / K8s / Helm / ingress | `extraction_config.py` |
| traces | `extraction_traces.py` |
| chemins | `domain/chemins.py` |
| secrets | `domain/secrets.py` |

Points forts actuels :

- CBM est la source principale ; les parseurs locaux ne relisent pas un fichier couvert.
- Namespace Kubernetes et `chemin_backend` des ingress statiques sont modélisés.
- JNDI est extrait depuis `@Resource`/`@EJB` et relié aux listeners JMS/KAFKA par binding.
- Les routes JAX-RS, servlets, Spring, FastAPI/Flask, ASP.NET et les clients HTTP sont couverts.
- Les liens restent `suggere` ; la revue humaine les confirme, les rejette ou les conteste.
- Les contradictions et les portées `UNKNOWN` restent visibles.

Limites :

- les rewrites d’ingress paramétrés (`/$1`) ne sont pas devinés ;
- la couverture réelle de CBM sur Go/PHP/Ruby/batch reste à mesurer ;
- les bindings WebSphere/JNDI spécifiques demandent une matrice de cas réels ;
- il n’y a pas de store dédié aux liens : propositions et cas utilisent les objets d’entreprise.

### 3.4 Mémoire de l’agent

Méridian couvre les types de mémoire utiles à un agent, avec des responsabilités séparées.

| Type | Rôle | Modules |
|---|---|---|
| **Travail / court terme** | contexte du tour, session, résumé borné | `session_memoire.py`, `memoire_dialogue.py`, `retrieval_memoire.py` |
| **Épisodique** | sessions, dossiers, décisions, outcomes | `memoire_durable.py` (scopes `session`, `situation`), `dossiers_raisonnement.py`, `outcomes.py` |
| **Sémantique** | faits, claims, connaissances, documents | `connaissance.py`, `memoire_org.py`, `chunk_store.py` |
| **Procédurale** | compétences, méthodes, recettes, learnings | `competences_cognitives.py`, `methodes_cognitives.py`, `recettes.py`, `legacy_packs.py` |
| **Relationnelle** | Twins, liens, topologie, communautés | `domain/graphe.py`, `neo4j/graphe_neo4j.py`, `community_store.py`, `moteur_liens.py` |
| **Réflexive** | croyances, calibration, consolidation, leçons | `domain/epistemie.py`, `calibration_croyances.py`, `consolidation_memoire.py`, `examen.py` |
| **Prospective** | intentions, échéances, rappels | `domain/memoire_prospective.py`, `postgres/memoire_prospective.py` |
| **Organisationnelle** | mémoire d’équipe / tenant | `memoire_org.py`, `entreprise_depot.py`, RLS/tenant |
| **Documentaire / externe** | RAG, chunks, embeddings, communautés | `documentation.py`, `chunk_store.py`, `embeddings.py`, `retrieval_hybride.py` |

Cycle de vie :

- **encodage** : `memoire_durable.creer`, `memoire_org.memoriser`, `chunk_store.indexer`, Claims ;
- **récupération** : `retrieval_memoire.recuperer`, `memoire_dialogue.recuperer`,
  `retrieval_hybride` ;
- **consolidation** : `consolidation_memoire` propose fusions et conflits,
  `application_memoire` applique après approbation ;
- **oubli** : `memoire_durable.purger`, `supprimer`, `exporter`, `retention.py`.

Hiérarchie d’autorité dans le retrieval : `claim` > `learning` > `intention` >
`annotation` > `durable`.

![Mémoire de l’agent Méridian](../diagrammes/memoire-agent.png)

[Ouvrir le diagramme mémoire en grand (HTML)](../diagrammes/memoire-agent.html) ·
[SVG](../diagrammes/memoire-agent.svg)

Mémoire prospective :

- `Intention` porte objet, échéance avec fuseau, scope, source, priorité, statut et preuves ;
- un cas de résolution ouvert avec `next_check` crée une intention à 7 jours ;
- sa résolution la clôt ; un abandon l’annule ;
- une réévaluation rouvre une intention à 1 jour ;
- les échéances dues sont candidates au retrieval ;
- API : `/boucle/intentions`, clôture et report.

Réutilisation mesurée des Learnings :

- `outcomes.marquer_reutilise` enregistre `succes`, `echec` ou `inconnu`, l’outcome et les preuves ;
- `outcomes.metriques_reutilisation` calcule les taux par Learning et au total ;
- `retrieval_memoire` expose les compteurs dans le candidat ;
- API : `/boucle/learnings/{id}/reutilisations`, `/boucle/learnings/metriques`.

Ce qui n’existe pas :

- pas de mémoire **paramétrique** (pas de fine-tuning ni de poids propres) ;
- pas de mémoire **sensorielle/perceptive** (images, audio, vidéo) ;
- pas encore de notification proactive des intentions dues : l’API et le retrieval les exposent,
  mais le worker de rappel n’est pas branché.

### 3.5 Harness agentique

```text
question / cas
  → planificateur (règles ou LLM borné)
  → outils read-only
  → observation
  → budget (étapes, outils, temps, candidats)
  → arrêt explicite
  → candidats / hypothèses
  → revue humaine
```

Modules :

- `application/exploration_agent.py` : harness d’exploration de dépôt ;
- `application/investigation_runtime.py` : investigation applicative structurée ;
- `application/boucle_investigation.py` : boucle bornée d’un `ResolutionCase` ;
- `application/planification` et `application/investigation_planning.py` : réexamens ;
- `adapters/outbound/llm/planificateur_liens.py` : planificateur LLM borné, repli déterministe ;
- `adapters/outbound/postgres/outils_investigation.py` : bindings, manifestes, code, CMDB,
  gateway, source vide.

Principes :

- aucun agent ne confirme un lien ;
- un outil inconnu, réutilisé ou en panne arrête la boucle avec une raison ;
- le contenu des sources est une donnée, jamais une instruction ;
- les budgets sont explicites et tracés.

### 3.6 Boucle décision / outcome

```text
Situation → Investigation → Décision → Initiative → Outcome → Learning
```

Modules :

- `domain/modele_entreprise.py` : Situation, Investigation, Decision, Initiative, Outcome,
  Learning ;
- `adapters/outbound/postgres/boucle.py` : persistance et transitions ;
- `adapters/outbound/postgres/outcomes.py` : mesure et capitalisation ;
- `adapters/outbound/postgres/calibration.py` et `calibration_croyances.py` : confiance vs
  outcome ;
- `application/planification/*` : capacité, charge, prévision, budget ;
- frontend `pages/Boucle.jsx` et `pages/Travail.jsx`.

**Lecture importante.** Le live Travail/Actualités continue d'écrire dans MongoDB `cases`,
`situations` et `initiatives`, mais le pont C2 enfile désormais les actions et décisions vers
l'outbox canonique ; le worker C1 crée ou met à jour Situation, Investigation, Decision,
Initiative, puis `GET /cases/{id}` expose la trace `boucle` au front. Le lot C3 enfile aussi
`initiative.maj` après une réponse d'initiative : l'Initiative canonique parente des Outcomes
existe donc sans insertion manuelle. Le lot D mesure les observations et crée des `Outcome`
canoniques (le `Learning` reste une validation humaine). L'UI Boucle expose les transitions
canoniques, la création d'une Situation racine via `POST /boucle/situations` (C4a) et, depuis
C4b, la création et la comparaison de Scénarios via `/boucle/scenarios`.
Le backfill `migration_canonique` et `/boucle/objets` restent disponibles. La chaîne est donc
branchée et opérable depuis l'UI, mais l'activation des workers, la migration tenant rétroactive
et le parcours end-to-end supervisé restent à faire. Le détail est dans
[pont-travail-c2.md](pont-travail-c2.md) et [mesure-auto.md](mesure-auto.md).

### 3.7 Architecture cognitive

![Architecture cognitive de Méridian](../diagrammes/architecture-cognitive.png)

[Ouvrir le diagramme cognitif en grand (HTML)](../diagrammes/architecture-cognitive.html) ·
[SVG](../diagrammes/architecture-cognitive.svg)

Le noyau ne traite pas une question comme un prompt : il construit un **dossier de
raisonnement** vérifiable. Le pipeline réel est :

```text
entrée
  → qualification & cadrage
  → contexte & mémoire
  → croyances & présupposés
  → composition bornée
  → dossier de raisonnement
  → critique & gates
  → décision & réponse
  → outcome & Learning
  ↺ retour vers le contexte
```

Modules et responsabilités :

| Étape | Modules |
|---|---|
| Entrée | `adapters/inbound/http/*`, `Travail`, `Atlas`, `cases` |
| Qualification & cadrage | `application/noyau_raisonnement.py` (`qualifier`, `cadrer`) |
| Contexte & mémoire | `application/resolveur_contexte.py`, `postgres/retrieval_memoire.py`, `memoire_*` |
| Épistémique | `domain/epistemie.py`, `application/epistemie.py` (`QuestionFrame`, `Belief`, `SourcePlan`) |
| Composition | `application/composition.py`, `domain/profils.py`, `methodes_cognitives.py`, `competences_cognitives.py` |
| Dossier | `domain/dossier_raisonnement.py` (`Demande`, `Cadre`, `PlanRaisonnement`, `ContexteRaisonnement`, `Constat`, `Option`, `Critique`, `Decision`, `Validation`, `Gate`) |
| Critique & gates | `application/noyau_raisonnement.critiquer_reponse`, `application/gates_tour.py`, `application/contrat_*` |
| Décision & réponse | `application/reponse_cognitive.py`, `application/decision_tour.py`, `decision_cognitive.py` |
| Outcome & Learning | `application/evaluation_raisonnement.py`, `apprentissage_raisonnement.py`, `postgres/outcomes.py`, `calibration_croyances.py` |

Principes :

- le **dossier** est la trace commune : demande, cadre, plan, croyances, constats, options,
  critiques, décision, validation, gates et réponse ;
- la **critique** est structurelle et indépendante du modèle ; elle ne réécrit pas le livrable ;
- les **gates** peuvent bloquer ou exiger une clarification avant toute réponse ;
- la **composition** borne les méthodes, compétences, spécialistes, budgets et niveaux
  d’autorité ;
- les **spécialistes** lisent un contexte borné et produisent des artefacts ; ils n’écrivent
  ni ne décident ;
- la **réponse** est une conséquence du dossier, pas l’inverse ;
- un **Learning** est proposé, pas auto-promu ; la réutilisation et l’outcome restent traçables.

Limites actuelles :

- le chemin `/boucle/analyser` persiste le dossier ; le chemin legacy `/aurora` utilise le
  même noyau mais sa persistance dépend du Travail ;
- la boucle d’apprentissage est branchée sur les outcomes et la calibration, mais la promotion
  d’un Learning reste humaine ;
- il n’y a pas encore de révision automatique des croyances à partir d’un outcome : la
  révision est proposée, pas appliquée.

### 3.8 Le Twin : identité, naissance, vie

![Cycle de vie d’un Twin](../diagrammes/cycle-vie-twin.png)

[Ouvrir le cycle de vie en grand (HTML)](../diagrammes/cycle-vie-twin.html) ·
[SVG](../diagrammes/cycle-vie-twin.svg)

Un Twin est une **représentation vivante** d’une entité de l’entreprise, pas seulement
d’une application. Son identité est stable ; ses connaissances, ses liens et ses sources
évoluent autour d’elle. **Méridian n’est pas un Twin** : c’est la plateforme qui maintient
ces représentations. Le cas du `meridian` de test/backfill est traité en 3.10.

**Identité**

- `jumeau.id` : identifiant interne stable, jamais remplacé par un nom de dépôt ;
- `tenant_id` : isolation stricte ;
- `type` : `APPLICATION`, `PROCESS`, `CAPABILITY`, `JOURNEY`, `ORGANIZATION`, `PRODUCT`,
  `DATA_DOMAIN`, `RESOURCE`, `SUPPLIER`, `TEAM`, `ECOSYSTEM` ;
- `application_id` : identité applicative **optionnelle**, jamais générée artificiellement ;
- propriétaire, périmètre, domaine, mission, alias, identifiants ;
- statut de naissance : `PROVISIONAL` ou `CONFIRMED`, dérivé du registre et non décidé par
  l’ingestion. Le vocabulaire reste double avec `Twin.statut` (`PROVISOIRE`, `ACTIF`, etc.) ;
  son unification est une dette de cohérence.

**Naissance**

1. **Commande** : tenant, type, mission, acteur, visibilité.
2. **Préalables** : `verifier_prealables_naissance` exige commande, identité, propriétaire
   et périmètre ; un Twin sans périmètre ne reçoit pas `twin.born`.
3. **Sources** : Git, Confluence, SharePoint, ServiceNow, Jira, Datadog, OTLP, documentation.
4. **Claims & preuves** : l’ingestion produit des claims localisés ; une preuve `SUPPORT`
   est exigée pour un claim accepté.
5. **Manifeste** : `manifeste_depuis_claims` transforme les claims `EXPOSE`/`CONSOMME` en
   expositions, consommations, ressources et inconnues.
6. **`twin.born`** : événement durable, idempotent, consommé par la découverte locale.
7. **Découverte locale** : liens, propositions, cas de résolution, frontières inconnues.
8. **Revue humaine** : confirmer, rejeter, contester, compléter, promouvoir.
9. **Veille** : réingestion, réévaluation, mémoire, réconciliation périodique.

**Ce que le Twin ne fait pas**

- il ne se confirme pas lui-même ;
- il ne transforme pas un nom de dépôt en identité applicative ;
- il ne déduit pas une portée `SERVICE`/`PARTNER`/`PUBLIC` sans ingress, contrat, trace ou
  déclaration ;
- il ne fusionne pas deux identités sans décision humaine.

**Projection**

| Couche | Rôle |
|---|---|
| Postgres | identité canonique (`jumeau`), sources, claims, preuves, interfaces, décisions |
| Mongo | registre projeté, Travail, cas, conversations, pièces |
| Neo4j | topologie : nœuds Twin, relations, parcours, communautés |
| Frontend | Atlas, fiche de revue, panneau de liens, Travail |
| `identity_decision` | audit des promotions et créations |

**Twin antérieur** : `legacy.born` / `backfill_manifestes` reconstruisent un manifeste
historique. Ils valent `twin.born` pour le résolveur, jamais une confirmation automatique.

### 3.9 Les autres objets d’entreprise

| Objet | Rôle | Cycle / statuts | Stockage / accès |
|---|---|---|---|
| **Claim** | fait sujet-prédicat-objet, avec mode, maturité et preuves | `DECLARED`, `OBSERVED`, `INFERRED`, `PROPOSED`, `CONFIRMED`, `SUPPORTED`, `STRENGTHENED`, `MATURE`, `CONTESTED`, `INVALIDATED`, `HISTORICAL` | Postgres `claim`, `preuve`, `claim_preuve` ; `/api/boucle/twins/{id}/claims` |
| **Relation** | lien entre deux objets, distinct d’un claim | `supposee`, `observee`, `validation`, `confirmee`, `contestee`, `obsolete` | Postgres / Neo4j ; Atlas et revue |
| **Situation** | phénomène émergent reliant Twins, signaux, claims ou impacts | `CANDIDATE`, puis qualification | `objet_entreprise` + backfill ; création via `POST /api/boucle/situations` et bouton « Nouvelle situation » dans Boucle ; le live lit/écrit encore Mongo `situations` |
| **Opportunity / Risk** | possibilité ou risque attaché à une situation | `DETECTED`, puis qualification | Classes de domaine testées ; aucune instanciation live identifiée ; sous-document `opportunite` legacy pour Opportunity, pas d’équivalent Risk |
| **Investigation** | espace structuré de compréhension : question, hypothèses, preuves | `OPEN`, puis clôture | Créée par le pont C2 ou par `POST /api/boucle/situations/{id}/investigations` (UI) ; lecture `/api/boucle/objets` |
| **Decision** | décision humaine reliée à une investigation, avec options et rationale | `PROPOSED`, puis tranchée | Créée par le pont C2 ou par `POST /api/boucle/investigations/{id}/decisions` (UI) ; lecture `/api/boucle/objets` |
| **Scenario** | option d’action comparable, rattachée à une Investigation et/ou une Decision | `DRAFT`, `PROPOSED`, `EVALUATED`, `SELECTED`, `REJECTED`, `ARCHIVED` | `objet_entreprise` + liens inverses `scenario_ids` (liste) / `scenario_id` (premier scénario historique, promu au premier restant s’il est retiré, sinon `None`) ; `POST/GET /api/boucle/scenarios`, `POST /api/boucle/scenarios/comparer` et UI Boucle ; filtre de liste direct, formulaire aux champs principaux, comparaison plafonnée à 50 |
| **Initiative** | traduction d’une décision en action suivie | `PLANNED`, puis exécution | Créée par C3 après une réponse d’initiative ou par `POST /api/boucle/decisions/{id}/initiatives` (UI) ; `objet_entreprise` + backfill, lecture `/api/boucle/objets` |
| **Outcome** | mesure observée après une initiative | `OBSERVED` | `objet_entreprise`, `POST /api/boucle/outcomes` ou worker D ; exige une Initiative canonique |
| **Learning** | connaissance généralisable issue d’un outcome ou d’une investigation | `PROPOSED`, promotion humaine | `objet_entreprise`, `/api/boucle/outcomes`, `/raisonnement/apprentissage` |
| **Source** | système externe fournissant observations et artefacts | type, curseur, fraîcheur, secret_ref | Postgres `source`, workers d’ingestion |
| **Domain** | domaine métier ou de données | stable | `objet_entreprise` / graphe |
| **Annotation** | mémoire organisationnelle déclarée | déclarée | `memoire_org`, `objet_entreprise` |

Objets de la vision qui ne sont pas encore des objets d’entreprise canoniques :
**Signal**, **Expression**, **Hypothesis**, **Expert**, **ExpertContribution**.
Le dossier de raisonnement porte des hypothèses et des options, mais ce ne sont pas les objets
durables décrits par le Domain Model. Voir [ecarts-vision.md](ecarts-vision.md).

Règles transverses :

- chaque objet porte `tenant_id`, une famille, un type, un mode, une temporalité, une
  confiance et des preuves ;
- une écriture canonique passe par `entreprise_depot` et ses invariants ;
- une promotion ou une confirmation est une décision humaine auditée ;
- les contradictions ne sont jamais écrasées ;
- un objet sans preuve reste `PROPOSED`/`suggere`, jamais `CONFIRMED`.

### 3.10 Méridian n’est pas un Twin

**Méridian est un système d’intelligence vivante de l’entreprise**, pas un Twin. La vision le
définit comme un **système d’exploitation cognitif** : il observe, comprend, fait émerger,
investigue, décide, agit, mesure et apprend. Le Mesh, les Twins, les Claims, les sources, les
relations et l’Atlas sont sa **fondation cognitive** ; ils ne sont pas le produit visible.

```text
Découvrir → Maturer → Exprimer → Investiguer → Décider → Agir → Mesurer → Apprendre
```

Un Twin représente une **entité de l’entreprise** (application, processus, capacité, parcours,
organisation, produit, domaine de données, ressource, fournisseur, équipe ou écosystème).
Flore est l’interface conversationnelle d’exploitation ; **Flore n’est ni Méridian ni un
Twin**. Atlas est la géographie du Mesh ; il n’est pas le produit.

Le `meridian` qui apparaît dans la fixture de `test_flore.py` ou dans un backfill local
historique (`docs/cognitive/ETAT.md`) est une **donnée de test ou de déploiement**. Ce n’est
ni un concept produit, ni une identité définie par la vision.

**Ce que Méridian n’est pas** : un Knowledge Graph, une CMDB augmentée, un outil
d’observabilité, un outil de documentation, un assistant conversationnel, un outil de process
mining, un moteur de recherche, un outil d’architecture, une plateforme multi-agents ou un
simple Digital Twin. Il peut incorporer certaines de ces capacités ; la différence est la
boucle complète d’observation, de maturation, d’investigation, de décision, de mesure et
d’apprentissage.

---

## 4. Modules clés

| Domaine | Fichiers |
|---|---|
| Modèle d’entreprise | `domain/modele_entreprise.py`, `domain/decouverte_liens.py`, `domain/liens_composants.py`, `domain/naissance_relationnelle.py` |
| Liens | `application/moteur_liens.py`, `adapters/outbound/connectors/cbm_liens.py`, `extraction_*` |
| Connaissance | `adapters/outbound/postgres/connaissance.py`, `entreprise_depot.py`, `calibration_croyances.py` |
| Mémoire | `memoire_durable.py`, `memoire_org.py`, `memoire_prospective.py`, `session_memoire.py`, `retrieval_memoire.py`, `chunk_store.py` |
| Harness | `exploration_agent.py`, `investigation_runtime.py`, `boucle_investigation.py`, `planificateur_liens.py` |
| Ingestion | `ingerer.py`, `source_worker.py`, `connecteurs*.py`, `legacy_index.py` |
| Graphe | `domain/graphe.py`, `neo4j/graphe_neo4j.py`, `community_store.py` |
| API | `adapters/inbound/http/*.py` |
| Frontend | `frontend/src/pages`, `components/map`, `components/case` |

---

## 5. API et interfaces

Les routeurs sont montés sous `/api` :

- `/api/mesh`, `/api/jumeaux`, `/api/relations`, `/api/situations` : Atlas et registre ;
- `/api/cases/*` : Travail, messages, pièces jointes, fusion, canvas ;
- `/api/boucle/*` : sources, relations, résolutions, enquête, mémoire, intentions,
  learnings, métriques ;
- `/api/jumeaux/{id}/...` : code index, interfaces, exploration ;
- `/api/runs/*`, `/api/planification/*`, `/api/raisonnement/*` ;
- `/api/health`, `/api/moi`, `/api/preferences`.

La surface exacte est celle d’OpenAPI (`/docs` en développement). Les routes de revue
principales :

| Endpoint | Rôle |
|---|---|
| `GET /api/boucle/relations` | propositions de relation |
| `POST /api/boucle/relations/{id}/revue` | confirmer / rejeter / contester |
| `GET /api/boucle/resolutions` | cas non résolus |
| `POST /api/boucle/resolutions/{id}/revue` | revue d’un candidat |
| `POST /api/boucle/resolutions/{id}/enqueter` | enquête bornée |
| `GET/POST /api/boucle/intentions` | mémoire prospective |
| `GET /api/boucle/learnings/metriques` | réutilisation mesurée |

### 5.1 Cycle d’une requête

**Analyse cognitive (`POST /api/boucle/analyser`)**

```text
cognitif.analyser_cognitif
  → analyse_service.executer
      → resolveur_contexte.resoudre
      → composition.planifier (profil, méthodes, compétences, spécialistes)
      → spécialistes (découverte, preuve, impact, outcome selon le plan)
      → retrieval_memoire.recuperer + enrichir_pack
      → epistemie.faits_depuis_recherche
      → noyau_raisonnement.preparer_dossier
      → reponse_cognitive.composer
      → noyau_raisonnement.completer_dossier
      → evaluation_raisonnement.evaluer
  → dossiers_raisonnement.enregistrer_dsn
```

**Travail / Aurora (`POST /api/aurora/demander`)**

```text
legacy.aurora_demander
  → generer_tour
  → generer_reponse_flore
  → noyau_raisonnement.preparer_dossier / completer_dossier
  → réponse située, citations et artefacts
```

**Ingestion d’une source Git**

```text
source_worker / POST /boucle/sources/{id}/ingest
  → ingerer.ingerer
      → cbm.indexer / cbm.interroger
      → legacy_index.indexer_legacy
      → code_index_store.remplacer_source
      → decouverte_naissance.reconcilier_twin
```

**Naissance et liens**

```text
relations_naissance.celebrer_naissance
  → manifeste_depuis_claims
  → emettre_twin_born
  → decouverte_naissance.traiter_twin_born
      → extractions_depuis_manifests + cbm_liens.extraire_observations
      → moteur_liens.moteur_liens
      → propositions / ResolutionCase
      → revue humaine
```

### 5.2 Où regarder pour modifier quoi

| Objectif | Point d’entrée |
|---|---|
| Ajouter/modifier une route HTTP | `backend/meridian/adapters/inbound/http/*.py` |
| Changer la naissance ou le manifeste | `application/relations_naissance.py`, `postgres/relations_naissance.py` |
| Changer l’appariement des liens | `application/moteur_liens.py`, `domain/chemins.py` |
| Ajouter une source d’extraction | `adapters/outbound/connectors/*` puis mapper dans `decouverte_composants.py` |
| Ajouter une mémoire | domaine + store Postgres + `retrieval_memoire.py` + tests |
| Changer le pipeline cognitif | `application/noyau_raisonnement.py`, `domain/dossier_raisonnement.py` |
| Changer l’ingestion | `connectors/ingerer.py`, `legacy_index.py`, `code_index_store.py` |
| Changer l’Atlas ou la revue | `frontend/src/pages`, `frontend/src/components/map` |
| Ajouter un worker | `adapters/inbound/worker/` + script `scripts/` + unité systemd |

---

## 6. Configuration et exploitation

### Démarrage local

```bash
# 1. moteurs
export JUMEAU_PG_PASSWORD="motdepasse"
docker compose up -d mongodb redis postgres

# 2. backend
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt
export JUMEAU_PG_DSN="postgresql://meridian:motdepasse@127.0.0.1:5434/meridian"
export MONGO_URL="mongodb://127.0.0.1:27017"
export DB_NAME="meridian_db"
.venv/bin/uvicorn server:app --host 0.0.0.0 --port 8001 --reload

# 3. frontend
cd ../frontend
yarn install
yarn start
```

Neo4j est optionnel : `scripts/dev-neo4j-light.sh up` ou
`docker compose -f docker-compose.neo4j.yml up -d` avec `NEO4J_PASSWORD`.

Le schéma Postgres est idempotent et appliqué par les workers et les scripts de maintenance
(`depot.appliquer_schema`). Pour une base neuve, lancer une fois un worker ou un script qui
appelle `appliquer_schema` avant la première écriture.

### Variables structurantes

| Variable | Rôle |
|---|---|
| `JUMEAU_PG_DSN` | Postgres canonique |
| `MONGO_URL`, `DB_NAME` | Travail et legacy |
| `REDIS_URL` | SSE, tours, rate limiting, multi-worker |
| `NEO4J_URI`, `GRAPH_STORE=neo4j` | projection graphe |
| `AUTH_MODE` | `demo`, `proxy` ou `oidc` |
| `JUMEAU_MODELE` | `deepseek`, `bedrock`, etc. |
| `CBM_BIN` | binaire codebase-memory-mcp |
| `JUMEAU_INDEX_STORE` | `local`, `s3`, `none` |
| `JUMEAU_RLS` | activation RLS, explicite |
| `JUMEAU_TRAVAIL_STORE` | `mongo` ou `postgres` |

### Scripts utiles

```bash
scripts/dev-source-worker.sh
scripts/dev-outbox-worker.sh
scripts/dev-travail-worker.sh
scripts/dev-planification-worker.sh
scripts/reconcilier-liens.py --help
scripts/worker-reconciliation.py --help
scripts/evaluer-liens.py --help
scripts/decouvrir-liens-composants.py --help
```

---

## 7. Tests et qualité

Au 6 novembre 2026 :

- **2 977 tests passés, 4 ignorés** sur la suite complète, hors 4 tests dépendants de
  l’environnement (timing heartbeat, quota LLM simulé, données `demo`, périmètre de naissance) ;
- **`pyflakes` propre** sur les fichiers modifiés récents ;
- suites dédiées : liens, CBM, chemins, secrets, lecture de fichiers, JNDI, mémoire
  prospective, outcomes, retrieval, naissance, réconciliation.

Commandes :

```bash
cd backend
JUMEAU_PG_DSN='postgresql://...' .venv/bin/python -m pytest meridian/tests -q
cd ../frontend
CI=true npm test -- --watchAll=false
npm run build
```

Les tests historiques de `backend/tests/` visent un backend externe et ne font pas partie de
la suite locale.

---

## 8. État par capacité

| Capacité | État | Commentaire |
|---|---|---|
| Registre Twins | **solide** | Postgres + projection Mongo/Neo4j |
| Situations / boucle canonique | **partielle** | Modèle/store, UI de lecture et transitions (création d’une Situation racine → Investigation → Decision → Initiative → Outcome → Learning) ; pont C2 Travail → canonique (Situation/Decision/Initiative), C3 Initiative canonique après réponse, mesure D → Outcome ; Learning humain ; workers et migration tenant à activer |
| Scénarios canoniques | **opérationnelle, périmètre UI borné** | Création depuis Investigation/Decision, liste filtrée directement par parent, comparaison déterministe avec écarts et référence ; UI Boucle ; `scenario_ids` pluriel et `scenario_id` = premier scénario historique (promu au premier restant s’il est retiré, sinon `None`) ; formulaire limité aux métriques principales ; comparaison plafonnée à 50 ; reste à relier les scénarios de capacité et la sélection dans la décision |
| Signal, Expression, Hypothesis, Expert | **absents comme objets canoniques** | Noms de famille, dossier de raisonnement ou profils ; voir [ecarts-vision.md](ecarts-vision.md) |
| Claims, preuves, maturité | **solide** | contradictions et revue conservées |
| Ingestion Git + CBM | **solide** | CBM à installer dans l’environnement cible |
| Liens HTTP/JMS/SOAP | **solide** | revue humaine, contradictions |
| Namespace + ingress statique | **solide** | rewrite paramétré non deviné |
| JNDI code → binding → listener | **solide** | matrice WebSphere réelle à valider |
| Mémoire durable / org / retrieval | **solide** | hiérarchie d’autorité explicite |
| Mémoire prospective | **solide** | API + retrieval ; worker de rappel à brancher |
| Réutilisation des Learnings | **solide** | mesure manuelle/API ; enregistrement automatique à brancher |
| Harness agentique | **opérationnel** | planificateur LLM live à valider |
| Planification capacité/prévision | **opérationnel** | connecteurs réels à valider |
| RLS multi-tenant | **disponible, non activé par défaut** | activation explicite et workers à vérifier |
| Auth proxy/OIDC | **disponible** | `demo` interdit en production |
| UI revue P0/P1 | **solide** | extension P2/P3 à faire |
| Corpus de production | **absent** | précision/rappel non mesurés à l’échelle |

## 8 bis. Traçabilité doc → code → test

Cette matrice vérifie qu’une affirmation de cette documentation a bien un support dans le
dépôt. Une ligne sans test est explicitement une cible ou une couverture partielle.

| Affirmation | Code | Tests | Statut |
|---|---|---|---|
| Twin typé, identité stable, 11 types | `domain/modele_entreprise.py`, `postgres/schema.sql` | `test_twins_types.py`, `test_tenant_twins.py` | **Implémenté** |
| Préalables de naissance et manifeste | `application/relations_naissance.py`, `postgres/relations_naissance.py` | `test_commandes_naissance.py`, `test_relations_naissance.py` | **Implémenté** |
| `twin.born` durable et idempotent | `relations_naissance.emettre_twin_born`, `execution_outbox` | `test_decouverte_naissance.py` | **Implémenté** |
| Découverte locale et réconciliation | `postgres/decouverte_naissance.py`, `application/moteur_liens.py` | `test_decouverte_naissance.py`, `test_moteur_liens.py` | **Implémenté** |
| Extraction CBM et liens | `connectors/cbm_liens.py`, `cbm_observations.py`, `moteur_liens.py` | `test_cbm_liens.py`, `test_moteur_liens.py` | **Implémenté**, binaire CBM requis |
| Namespace, ingress statique, JNDI | `connectors/extraction_config.py`, `extraction_commune.py`, `cbm_liens.py` | `test_extraction_config.py`, `test_jndi_liens.py` | **Implémenté**, matrice WebSphere partielle |
| Mémoire durable, org, session | `postgres/memoire_durable.py`, `memoire_org.py`, `session_memoire.py` | `test_memoire_durable.py`, `test_memoire_org.py`, `test_session_memoire.py` | **Implémenté** |
| Mémoire prospective | `domain/memoire_prospective.py`, `postgres/memoire_prospective.py`, `schema.sql` | `test_memoire_prospective.py`, `test_decouverte_naissance.py` | **Implémenté**, worker de rappel absent |
| Retrieval unifié | `postgres/retrieval_memoire.py` | `test_retrieval_memoire.py` | **Implémenté** |
| Réutilisation mesurée des Learnings | `postgres/outcomes.py`, `retrieval_memoire.py`, `cognitif.py` | `test_outcomes.py`, `test_retrieval_memoire.py` | **Partiel**, enregistrement automatique absent |
| Dossier et noyau de raisonnement | `application/noyau_raisonnement.py`, `domain/dossier_raisonnement.py`, `analyse_service.py` | `test_noyau_raisonnement.py`, `test_raisonnement.py`, `test_critique_raisonnement.py` | **Implémenté** |
| Persistance cognitive unifiée | `cognitif.py`, `postgres/dossiers_raisonnement.py`, `cases.py` | `test_cognitif_routes.py` | **Partiel**, `/aurora` dépend du Travail |
| Auth, RBAC, tenant, RLS | `auth.py`, `postgres/rls.py`, `schema.sql` | `test_tenant.py`, `test_rls.py`, `test_worker_rls.py` ; `backend/tests/test_auth.py` | **Partiel**, RLS opt-in |
| Workers source/outbox/travail/planification | `adapters/inbound/worker/*` | `test_worker_rls.py`, `test_index_versionne.py` | **Partiel**, déploiement à superviser |
| Projection Neo4j | `adapters/outbound/neo4j/*`, `graphe_sync.py` | `test_graphe_neo4j.py`, `test_graphe_sync.py` | **Implémenté**, activable |
| Planification capacité/prévision | `application/planification/*`, connecteurs | `test_planification_*` | **Implémenté**, connecteurs live partiels |
| Couverture CBM Go/PHP/Ruby/batch | CBM externe | aucun test de couverture réelle | **Cible** |
| Corpus de production / shadow mode | absent | aucun | **Cible** |
| Mémoire paramétrique / sensorielle | absente | aucun | **Cible / non retenu** |
| UI revue P2/P3 | absente | tests P0/P1 seulement | **Cible** |

---

## 9. Reste à faire

### P0 — avant pilote réel

| Dette | Pourquoi | Critère d’acceptation |
|---|---|---|
| Unification live/canonique | le pont C2 relie Travail au canonique, mais les workers et la migration tenant ne sont pas encore activés en production | un parcours Situation → Decision → Outcome piloté depuis Travail, trace canonique visible, worker supervisé ; Learning reste une validation humaine |
| Corpus de production labellisé + shadow mode | les mesures actuelles portent sur un corpus de test | précision/rappel/fausses certitudes sur un jeu réel, revue aveugle |
| Activation RLS + workers multi-tenant | RLS existe mais `JUMEAU_RLS=0` par défaut | policies actives, tests d’isolation, workers en contexte ou bypass explicite |
| Déploiement supervisé des workers | les runs restent `QUEUED` sans worker | source/outbox/travail/reconciliation supervisés, redémarrage testé |
| Validation des connecteurs live | ServiceNow, Datadog, gateway, portail ne sont pas testés en conditions réelles | un cas par connecteur, preuves et limitation documentées |
| CBM dans l’environnement cible | le binaire est absent de certains environnements | ingestion et couverture vérifiées au déploiement |

### P1 — qualité et couverture

| Dette | Pourquoi | Critère d’acceptation |
|---|---|---|
| Enregistrement automatique des réutilisations | aujourd’hui l’API mesure, mais l’usage réel n’est pas toujours tracé | un Learning utilisé dans un Context Pack produit une trace, sans gonfler les compteurs |
| UI intentions + métriques de réutilisation | l’API existe, pas l’écran | liste des échéances, clôture/report, taux de succès |
| Rewrites d’ingress paramétrés | `/$1` n’est pas interprété | corpus d’ingress réel, matching backend correct |
| Matrice JNDI/WebSphere | l’extraction générique est faite, pas les cas WebSphere | cas `java:comp/env`, `java:global`, files/topics |
| Rafraîchissement incrémental à l’échelle | `reconcilier_twin` est branché, mais la passe reste globale | mesure du coût, filtre multi-Twins si nécessaire |
| Unification des chargeurs | règles partagées, parcours distincts | une matrice de tests puis un chargeur unique |
| Store dédié des liens | décision actuelle : objets d’entreprise | décision réévaluée avec le volume et les requêtes |
| Autres forges | GitHub est branché | GitLab/Azure DevOps avec tests |
| Couverture CBM Go/PHP/Ruby/batch | non mesurée | corpus réel + taux de couverture |
| Persistance cognitive unifiée | `/boucle/analyser` persiste le dossier ; `/aurora` dépend du Travail | un seul chemin de persistance et de reprise, tests de rejeu |
| Révision automatique des croyances | la révision est proposée, pas appliquée | révision traçable sur outcome, seuil et revue humaine |
| Vocabulaire de statut Twin | `PROVISOIRE`/`PROVISIONAL` et `ACTIF`/`CONFIRMED` coexistent | un seul vocabulaire, migration et tests de compatibilité |

### P2 — industrialisation

- connecteurs live portail API et gateway externe ;
- verrou multi-instance du worker de réconciliation ;
- observabilité (métriques, traces, coûts, files) ;
- migration/versionnement formel du schéma Postgres ;
- réduction de la double écriture Mongo/Postgres ;
- performance grands graphes et retrieval à grande échelle.

---

## 10. Limites et risques

- **Pas de corpus de production** : les chiffres de qualité restent locaux.
- **CBM** est un prérequis d’ingestion ; son absence dégrade la couverture sans bloquer l’API.
- **RLS** n’est pas actif par défaut ; un déploiement multi-tenant doit l’activer et vérifier
  les workers.
- **Mongo/Postgres** : la double écriture Travail est un pont ; toute nouvelle donnée
  canonique doit aller dans Postgres.
- **Auth** : `demo` est interdit en production ; utiliser `proxy` ou `oidc`.
- **Mémoire paramétrique/sensorielle** : hors périmètre actuel ; Méridian ne fine-tune pas de
  modèle et n’ingère pas d’audio/image.
- **Agentique** : les tests utilisent des décideurs injectés ; le planificateur LLM live reste
  à valider.
- **Secrets** : les preuves et exports sont expurgés, mais aucun système ne doit dépendre d’un
  secret stocké en clair dans un fichier de configuration.

---

## 11. Conventions de contribution

- branche de base : `dev` ;
- commits et PR : `type(scope): résumé` (`feat`, `fix`, `docs`, `chore`, `refactor`, `test`) ;
- pas de confirmation automatique d’un lien ;
- toute nouvelle capacité d’extraction doit enrichir une source canonique, pas ajouter un
  parseur isolé ;
- tests avant commit : `pytest` ciblé puis suite complète ;
- les documents de vision restent la cible ; ce fichier décrit l’état.

---

## 12. Références

- [Écarts avec la vision](ecarts-vision.md)
- [Architecture maître](../MERIDIAN_Architecture_Master_v1.md)
- [Diagramme d’architecture actuelle](../diagrammes/architecture-etat-actuel.html)
- [Diagramme des mémoires](../diagrammes/memoire-agent.html)
- [Diagramme cognitif](../diagrammes/architecture-cognitive.html)
- [Cycle de vie d’un Twin](../diagrammes/cycle-vie-twin.html)
- [Photographie historique de l’architecture](architecture-actuelle.html)
- [Découverte des liens et boucle agentique](decouverte-liens-agentique.md)
- [ADR 0033 — liens composants](../adr/0033-liens-composants.md)
- [Dépendances runtime](dependances.md)
- [RLS](rls.md)
- [RAG Bedrock](rag-bedrock.md)
- [Graphify vs CBM](graphify-vs-cbm.md)
- [Ingestion continue](ingestion-continue.md)
- [Projection graphe](projection-graphe.md)
