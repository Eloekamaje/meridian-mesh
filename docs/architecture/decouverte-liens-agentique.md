# Découverte des liens entre composants — boucle d'enquête, agentique et naissance

- **Statut :** draft de travail / brainstorm formalisé
- **Version :** 0.1
- **Date :** 2026-11-06
- **Portée :** découverte des producteurs et consommateurs, liens de composants, boucle agentique bornée, déclenchement à la naissance
- **Décisions liées :** ADR-0031 (naissance relationnelle), ADR-0032 (découverte des liens), ADR-0033 (liens entre composants)
- **Public :** produit, architecture, sécurité, propriétaires de domaine, exploitation

---

## 0. Objet

Ce document formalise la chaîne de découverte des liens entre composants et répond à quatre questions :

1. Comment Méridian découvre-t-il les producteurs et les consommateurs à partir du code, de la configuration, de Helm, des manifests de déploiement, des contrats et des traces ?
2. Quand la couche agentique intervient-elle, avec quels outils, quel budget et quelles garanties ?
3. Que déclenche exactement la naissance d'un Twin ? La naissance « engage-t-elle » une enquête ?
4. Quel est le timing de la boucle d'enquête, de la naissance à la revue humaine ?

Le document distingue volontairement :

- ce qui est **implémenté** aujourd'hui ;
- ce qui est **cible** ;
- ce qui reste **ouvert** au brainstorm.

---

## 1. Résumé exécutif

- La **naissance** (`twin.born`) déclenche une **découverte locale bornée**. Elle n'engage pas automatiquement une enquête agentique complète, ni une réconciliation globale du SI.
- L'**agentique** est un **enquêteur** sur le résidu : identité manquante, binding absent, source non structurée, contradiction. Il ne confirme jamais un lien.
- Le **déterministe** reste le squelette : extraction, résolution d'identité, appariement, contraintes, questions.
- L'**humain** confirme, rejette ou conteste ; il complète aussi les identités manquantes.
- L'engagement agentique est une **décision de politique** : `AUTO`, `ASSISTED` ou `MANUAL`, selon la criticité, les inconnues et le budget.
- Le timing cible est :
  - passe déterministe à la naissance : **< 5 min** ;
  - enquête rapide : **< 2 min** ;
  - enquête profonde : **< 15 min** ;
  - revue humaine : **4 h** (P0), **1 jour** (P1), **3 jours** (P2), batch (P3).
- Aucun lien n'est confirmé sans preuve. Aucun agent n'écrit un lien durable sans revalidation déterministe.

---

## 2. Problème et principes

### 2.1 Le problème

Une API exposée n'identifie pas son application :

```text
GET /accounts/{id}
  → route de passerelle
  → service comptes-api
  → application ?
```

Le nom du service n'est pas le propriétaire. La gateway n'est pas le producteur. Le dépôt n'est pas l'application. Le serveur d'application peut être inaccessible.

Il faut donc :

- découvrir les **producteurs** dans le code, la configuration, Helm, les manifests, les contrats ;
- découvrir les **consommateurs** dans leur code, leur configuration, les traces et la gateway ;
- résoudre les **identités** ;
- apparier les **opérations** ;
- produire des **soupçons prouvés** ;
- laisser l'humain combler ce qui manque.

### 2.2 Principes

1. **La preuve avant le lien.** Pas de lien sans source localisée.
2. **L'identité avant le matching.** `service → composant → application` avant de comparer des routes.
3. **Le déterministe d'abord.** L'agent intervient sur le résidu.
4. **L'inconnu est un résultat.** Une question ouverte vaut mieux qu'une attribution fausse.
5. **L'humain décide.** L'agent propose, le déterministe revalide, le propriétaire tranche.
6. **La contradiction est conservée.** Deux preuves incompatibles ne sont jamais fusionnées.
7. **Incrémental par défaut.** On revalide ce qui a changé, pas tout le SI.
8. **Couverture explicite.** On publie une matrice de ce qui est supporté, partiel ou absent.

---

## 3. Modèle

| Objet | Rôle |
|---|---|
| `Composant` | frontend, backend, worker, batch, gateway, ESB |
| `Interface` | route HTTP, opération SOAP, file JMS, topic Kafka |
| `Appel` | URL, propriété, service, file, topic |
| `Deploiement` | service, hôte, route de passerelle, environnement |
| `Ressource` | queue, topic, table, fichier |
| `Preuve` | source, localisation, date, mode, confiance |
| `LienPropose` | consommateur → fournisseur, avec vérifications et inconnues |
| `QuestionLien` | ce qui manque, avec la prochaine vérification |
| `ResolutionCase` | cas durable d'une question |
| `PropositionRelation` | proposition gouvernée pour le Mesh |

### 3.1 Invariants

- Même `application_id` ⇒ lien `interne`, pas une relation de Mesh.
- Applications distinctes ⇒ lien `mesh`, candidat à `PropositionRelation`.
- Hôte public non rattaché ⇒ `externe`, jamais un Twin interne.
- Seules les portées `SERVICE`, `PARTNER`, `PUBLIC` sont éligibles au Mesh.
- Un lien `UNKNOWN` reste visible, mais n'est pas éligible.
- Une contradiction produit `conteste`, jamais un écrasement.
- Un Twin `PROVISIONAL` ne peut pas confirmer une relation avant promotion.
- Aucun secret, identifiant ou URL avec credentials dans le modèle.

---

## 4. Pipeline cible

```text
SOURCES
  code · config · Helm · Kubernetes · contrats · gateway · traces · CMDB · portail API
        │
        ▼
OBSERVATIONS NORMALISÉES
  producteurs · consommateurs · déploiements · propriétés · contrats
        │
        ▼
RÉSOLUTION D'IDENTITÉ
  service → composant → application
  API → owner_twin_id / implementation_twin_id
        │
        ▼
GÉNÉRATION DE CANDIDATS
  opération ↔ opération · file ↔ listener · action SOAP ↔ interface
        │
        ▼
CONTRAINTES
  environnement · namespace · frontière · unicité · direction · temporalité
        │
        ├── liens proposés
        ├── questions ouvertes
        └── contradictions
        │
        ▼
REVUE HUMAINE + OBSERVATION
  accepter · rejeter · contester · compléter · observer
        │
        ▼
APPRENTISSAGE
  alias · mappings · contraintes négatives · revalidation
```

---

## 5. Couche déterministe

### 5.1 Extraction

| Source | Producteurs | Consommateurs |
|---|---|---|
| Java | routes Spring, JAX-RS, servlet, `@JmsListener`, Kafka | Feign, RestTemplate, WebClient, JMS |
| Python | FastAPI, Flask | requests, httpx |
| .NET / C# | ASP.NET `[Route]`, `[HttpGet]` | `HttpClient` |
| JavaScript/TypeScript | — | axios, fetch |
| OpenAPI / WSDL / GraphQL / gRPC / AsyncAPI | opérations exposées | — |
| Configuration | nom de service, contexte | URL, propriété, endpoint |
| Kubernetes | Deployment, Service, Ingress | variables d'environnement |
| Helm | image, service, ingress | variables d'environnement |
| Traces | — | appels observés |

#### 5.1.1 Parsing : AST d'abord, regex en repli

Le regex a été un bootstrap, pas une fin. Il est conservé pour :

- les langages sans parser disponible dans l'environnement ;
- les fichiers malformés ou générés ;
- les formats de déclaration simples.

Le chemin cible est l'AST :

| Langage | Parser | État |
|---|---|---|
| Python | `ast` (stdlib) | **branché**, repli regex sur syntaxe invalide |
| Java | tree-sitter / JavaParser | à brancher |
| C# | tree-sitter / Roslyn | à brancher |
| Go | tree-sitter | à brancher |

Un AST permet de résoudre les décorateurs, les constantes, les portées et les chaînes
de caractères sans confondre un commentaire avec un appel. Un fichier illisible ne
bloque pas : il redescend sur le texte avec un diagnostic.

#### 5.1.2 Une seule source de vérité par extraction

| Élément | Source canonique |
|---|---|
| Java : types, méthodes, annotations, routes Spring/JAX-RS, servlets | `java_source.py` |
| Contrats OpenAPI/WSDL/GraphQL/gRPC/AsyncAPI | `domain/interfaces.py`, `interfaces_protocoles.py` |
| Détection et mapping des contrats | `extraction_contrats.py` |
| Détection des fichiers de contrat | `connecteur_interfaces.py` |
| Preuves, chemins et appels HTTP partagés | `extraction_commune.py` |
| Lecture binaire/décodage partagée | `lecture_fichiers.py` |
| Refus des secrets dans les URL | `domain/secrets.py` |
| Traces d'appels | `extraction_traces.py` |
| Code local de repli (Java, Python, JS, ASP.NET) | `extraction_code.py` |
| Configuration, Kubernetes, Helm, ingress | `extraction_config.py` |
| Normalisation et matching de chemins | `domain/chemins.py` |
| Graphe de code multi-langages | CBM (`cbm_observations.py`, `cbm_liens.py`) |
| Fédération et couverture des observations | `code_index.py`, `code_index_orchestrator.py` |
| Architecture, documentation, communautés | Graphify (`graphify_semantics.py`) |
| Orchestration, lecture de fichiers, assemblage | `decouverte_composants.py` |
| Sources externes (ServiceNow, Datadog, Git, runtime, gateway) | `connectors/*` et `lecteurs.py` |

`decouverte_composants.py` est un **orchestrateur** : il lit les fichiers, choisit la
source de chaque famille et assemble un `ExtractionDepot`. Il ne doit pas reparser
Java, les contrats ou les connecteurs externes. Toute nouvelle capacité d'extraction
doit d'abord enrichir la source canonique, puis être mappée ici. Les contrats, les
traces, la configuration et le code local sont sortis dans `extraction_contrats.py`,
`extraction_traces.py`, `extraction_config.py` et `extraction_code.py`.

**CBM est la source principale** pour le code multi-langages : routes, appels HTTP,
variables d'environnement, tables et ressources. `cbm_liens.py` les mappe vers le
moteur. `decouverte_composants` ne garde ses parseurs locaux que comme **repli**
lorsque CBM n'est pas disponible. Graphify apporte l'architecture, les documents et
les communautés ; il ne remplace pas CBM pour les routes et les appels.

Deux précisions de déploiement :

- `Deploiement.namespace` conserve le namespace Kubernetes ; il ne modifie l'identité
  du déploiement que lorsqu'il est connu.
- `RoutePasserelle.chemin_backend` porte une réécriture d'ingress statique
  (`rewrite-target`). La résolution d'URL garde le chemin externe ; le matching des
  interfaces utilise le chemin backend. Un rewrite paramétré (`/$1`) n'est pas deviné.
- `@Resource`/`@EJB` avec `lookup` ou `mappedName` produit un `Appel` JNDI. Un binding
  `JNDI` traduit le nom vers une file ou un topic, puis le listener JMS/KAFKA fournit
  le composant producteur.

### 5.2 Résolution d'identité

Ordre de résolution :

```text
propriété ${accounts.base-url}
  → configuration de l'environnement
  → URL
  → hôte ou nom de service
  → route de passerelle la plus spécifique
  → service Kubernetes
  → composant
  → application
```

Un hôte d'ingress n'est **jamais** rattaché au composant gateway comme producteur. La route désigne un service ; le service désigne le producteur.

L'identité d'une API distingue :

- `owner_twin_id` : l'entité accountable ;
- `implementation_twin_id` : le composant qui répond ;
- `deployment_id` : où et dans quel environnement.

### 5.3 Appariement

- HTTP : suffixe de chemins avec templates, méthode, contexte, préfixe de gateway.
- JMS/Kafka : file ou topic exact.
- SOAP : action si connue ; sinon service identifié, avec ambiguïté si plusieurs opérations.
- DB/fichier : opération exacte, quand le transport sera supporté.

Un appariement doit contenir au moins un segment littéral commun. Sinon il est trop vague et devient une question.

### 5.4 Classification

| Nature | Condition |
|---|---|
| `interne` | même `application_id` |
| `mesh` | applications distinctes |
| `externe` | hôte public non rattaché |

### 5.5 Frontière

La portée est `SERVICE`, `PARTNER`, `PUBLIC`, `INTERNAL`, `ADMIN`, `HEALTH`, `DEMO`, `DEBUG` ou `UNKNOWN`.

Sans ingress, sans contrat public, sans portail API ou sans déclaration, la portée reste `UNKNOWN`. Le lien existe, mais il n'est pas éligible au Mesh.

### 5.6 Sorties

- `LienPropose` avec `implemente`, `configure`, `observe`.
- `QuestionLien` avec `missing_evidence` et `next_check`.
- `Contradiction` quand deux producteurs incompatibles sont prouvés.

---

## 6. Couche agentique

### 6.1 Rôle

L'agent est un **enquêteur borné**. Il ne remplace ni le moteur, ni la preuve, ni la décision.

Il intervient quand :

- une propriété de configuration manque ;
- un service n'est rattaché à aucun composant ;
- plusieurs producteurs sont candidats ;
- une route de gateway est ambiguë ;
- un owner d'API est introuvable ;
- une source non structurée peut contenir la réponse ;
- une contradiction doit être expliquée ;
- une question humaine mérite une prochaine vérification.

Il n'intervient pas pour :

- confirmer un lien ;
- écrire une relation durable ;
- remplacer un parseur déterministe ;
- accéder à un serveur ou à un secret ;
- tourner sans budget.

### 6.2 Outils

Outils read-only, allowlistés :

| Outil | Usage |
|---|---|
| `search_code` | chercher un symbole, une route, un client |
| `read_file` | lire un fichier borné, sans secret |
| `search_config` | chercher une propriété, un profil, un environnement |
| `read_contract` | lire OpenAPI/WSDL/AsyncAPI |
| `read_deployment` | lire Kubernetes/Helm/ingress |
| `read_gateway` | lire les routes et réécritures |
| `read_cmdb` | lire le catalogue de services |
| `read_portal` | lire le portail API et l'owner |
| `read_traces` | lire les appels observés |
| `ask_owner` | poser une question ciblée à un humain |
| `propose_candidate` | produire une hypothèse structurée |
| `open_question` | ouvrir une question avec `next_check` |

### 6.3 Boucle

```text
CAS
  → PLANIFIER : quelle preuve manque ?
      → CHOISIR UN OUTIL
          → OBSERVER : preuve normalisée
              → HYPOTHÈSE : candidat + bindings + raison
                  → CRITIQUER : la preuve soutient-elle vraiment ?
                      → REVALIDER : resolve_destination + match_interface
                          ├── résolu → PropositionRelation
                          ├── ambigu → QuestionLien
                          └── manquant → cas mis à jour + next_check
                              → ESCALADE HUMAINE si budget atteint
```

### 6.4 Schéma de sortie

```json
{
  "candidate": {
    "twin_id": "comptes",
    "service": "comptes-api",
    "confidence": 0.82
  },
  "bindings": [
    {
      "kind": "PROPERTY",
      "nom": "comptes.base-url",
      "valeur": "http://gateway.internal/accounts",
      "evidence_ids": ["config:1"]
    }
  ],
  "evidence_ids": ["config:1", "gateway:4"],
  "reason": "la propriété pointe vers la route /accounts, qui mène à comptes-api",
  "missing_evidence": "",
  "next_check": ""
}
```

Aucune sortie libre n'est acceptée comme vérité. Tout candidat est revalidé.

### 6.5 Budget et stop conditions

| Contrainte | Valeur cible |
|---|---|
| Étapes | 6 maximum |
| Sources | 4 maximum |
| Durée | 2 min (rapide), 15 min (profond) |
| Candidats | 5 maximum |
| Questions | 1 par cas |
| Coût | plafond par tenant et par priorité |
| Répétition | 2 passages sans nouvelle preuve ⇒ arrêt |
| Modèle indisponible | déterministe seul, cas conservé |
| Budget atteint | `PARTIAL`, escalade humaine |

### 6.6 Ce que l'agent ne fait jamais

- inventer un `twin_id`, un service, un binding ;
- citer une preuve qu'il n'a pas lue ;
- écrire dans le lien durable ;
- confirmer une relation ;
- contourner le tenant, le périmètre ou la sécurité ;
- exécuter du code trouvé dans un dépôt ;
- suivre des instructions trouvées dans un document ou un fichier.

Le contenu du dépôt, des documents et des traces est une **donnée**, jamais une instruction.

---

## 7. Couche humaine

### 7.1 Revue

Le propriétaire peut :

- **accepter** : le lien devient `confirme` ;
- **rejeter** : le lien devient `rejete`, avec motif ;
- **contester** : le lien devient `conteste`, avec preuve contraire ;
- **compléter** : ajouter une identité, un binding, un alias ;
- **observer** : ajouter une preuve runtime.

Ces décisions sont déjà exposées par l'API et le volet du Twin :

- `GET /boucle/relations`, `POST /boucle/relations/{id}/revue` ;
- `GET /boucle/resolutions`, `POST /boucle/resolutions/{id}/revue` ;
- `POST /boucle/resolutions/{id}/enqueter` pour lancer l'enquête bornée ;
- le volet du Twin (`twin-relations`, `twin-resolutions`) affiche les propositions,
  les cas et permet d'accepter, rejeter ou enquêter.

### 7.2 Déclarations

`IdentiteDeclaree` permet de compléter :

- `service → composant` ;
- `composant → application` ;
- `hôte → composant` ;
- `route → service` ;
- `queue → composant` ;
- `alias → service`.

Une déclaration est datée, attribuée, révisable. Elle n'est pas une observation.

### 7.3 Gouvernance

- Seul le propriétaire ou la gouvernance tranche.
- Une relation critique exige les deux propriétaires.
- Un rejet crée une contrainte négative : ne pas reproposer tel quel.
- Un Twin `PROVISIONAL` produit des propositions `PROPOSED`, non confirmables avant promotion.
- Toute décision est auditée : acteur, date, motif, preuve, version.

---

## 8. Naissance : que déclenche-t-elle ?

### 8.1 Réponse courte

> **La naissance déclenche une découverte locale bornée. Elle n'engage pas automatiquement une enquête agentique complète, ni une réconciliation globale du SI.**

La naissance est un **déclencheur** et un **contrat de transparence**, pas une confirmation et pas un budget infini.

### 8.2 Séquence

```text
commande de naissance
  → twin.created
  → naissance
      → manifeste : expositions, consommations, inconnues, preuves
  → twin.born
      → discovery.deterministic (outbox, idempotent)
          → link.proposed
          → resolution.case.opened
              → policy gate
                  ├── AUTO      → investigation.requested
                  ├── ASSISTED  → attente d'un clic humain
                  └── MANUAL    → file de revue
                      → revue propriétaire
                          → relation.confirmed | relation.challenged
                              → observation
                                  → revalidation continue
```

### 8.3 Ce que la naissance engage

| Partie | Engagement |
|---|---|
| Méridian | produire un rapport de liens déterministe dans un délai borné |
| Méridian | publier les questions, les inconnues et la couverture |
| Méridian | revalider sur changement et signaler l'obsolescence |
| Propriétaire | revoir les liens critiques dans le SLA |
| Propriétaire | confirmer ou contester, avec motif |
| Gouvernance | définir la politique d'engagement et le budget |
| Sécurité | approuver les sources et les modèles |

### 8.4 Ce que la naissance ne fait pas

- Elle ne confirme aucune relation.
- Elle ne lance pas un agent pour chaque Twin.
- Elle ne diffuse pas l'existence du Twin à tous les autres.
- Elle ne crée pas un budget illimité.
- Elle ne transforme pas une exposition `UNKNOWN` en `SERVICE`.
- Elle ne promeut pas un Twin `PROVISIONAL`.

### 8.5 Modes d'engagement

| Mode | Comportement | Cas d'usage |
|---|---|---|
| `AUTO` | l'agent démarre si la politique et le budget l'autorisent | P0 ; P1 après seuils ; sécurité, owner inconnu critique |
| `ASSISTED` | l'agent attend un clic « Investiguer » | P2, cas ambigu |
| `MANUAL` | la question reste dans la file, sans agent | P3, faible valeur, source restreinte |

### 8.6 Politique proposée

```json
{
  "discovery": {
    "mode": "ASSISTED",
    "priority": "P1",
    "budget": {
      "max_steps": 6,
      "max_sources": 4,
      "max_minutes": 2,
      "max_candidates": 5
    },
    "sources_allowed": ["code", "config", "helm", "contracts", "gateway", "traces"],
    "review_sla": "PT24H",
    "owner": "equipe-plateforme"
  }
}
```

Ce bloc est une **proposition** ; il n'est pas encore persisté dans le manifeste actuel.

### 8.7 Naissance partielle et Twin provisoire

- Une naissance partielle émet `twin.born` avec `partial=true` et des `unknowns`.
- Les liens restent `suggere`.
- Si un unknown est critique, l'agent peut être engagé en mode `AUTO` ou `ASSISTED`.
- Un Twin `PROVISIONAL` produit des propositions `PROPOSED` ; aucune confirmation avant promotion.
- Un échec de naissance n'émet pas `twin.born`.
- Un Twin antérieur reçoit `legacy.born` ; il vaut `twin.born` pour le résolveur, jamais confirmation de ses relations.
- `twin.born` est idempotent par `(tenant_id, twin_id, birth_run_id)` ; la passe déterministe l'est aussi.

---

## 9. Timing de la boucle d'enquête

### 9.1 Définitions

- **T0** : événement déclencheur (`twin.born`, changement, trace, question humaine).
- **Latence déterministe** : extraction + identité + matching + questions.
- **Latence agentique** : planification + outils + hypothèse + critique + revalidation.
- **SLA de revue** : délai cible de décision humaine.
- **Fraîcheur** : âge de la preuve.
- **Obsolescence** : lien non revalidé après un changement ou au-delà de `valid_until`.

### 9.2 Machine à états

```text
OUVERT
  → DETERMINISTE
      → QUALIFIE
          ├── RESOLU
          ├── AMBIGU
          └── MANQUANT
              → ENQUETE (optionnelle)
                  → EN_ATTENTE_REVUE
                      ├── CONFIRME
                      ├── CONTESTE
                      └── REJETE
                          → OBSERVE
                              → OBSOLETE
```

Horodatages :

```text
created_at
deterministic_started_at
deterministic_finished_at
agent_started_at
agent_finished_at
review_due_at
reviewed_at
last_observed_at
valid_until
```

### 9.3 Table de timing cible

| Déclencheur | Déterministe | Agent | Revue humaine | Revalidation |
|---|---:|---:|---:|---:|
| `twin.born` P0 | < 2 min | < 15 min | 4 h | sur changement + 7 j |
| `twin.born` P1 | < 5 min | < 5 min | 1 jour | sur changement + 14 j |
| `twin.born` P2 | < 15 min | assisté, < 2 min | 3 jours | sur changement + 30 j |
| `twin.born` P3 | batch quotidien | manuel | batch | 90 j |
| commit/config/déploiement | < 2 min | si contradiction | selon priorité | immédiate |
| trace/observation | < 1 min | si contradiction | selon priorité | continue |
| question humaine | immédiat | < 2 min | selon réponse | selon cas |
| revue périodique | diff quotidien | non | hebdomadaire | 7 j |

Ces valeurs sont des **cibles de conception**, pas des mesures actuelles.

### 9.4 Exemple de chronologie à la naissance

```text
T0        twin.born
T+30 s    extraction code/config/Helm/contrats
T+2 min   rapport déterministe : liens + questions
T+2 min   resolution.case.opened
T+3 min   policy gate
T+4 min   enquête rapide (si AUTO/ASSISTED)
T+15 min  enquête profonde (si P0)
T+4 h     revue humaine P0
T+1 j     revue humaine P1
T+7 j     revalidation
```

### 9.5 Backoff et escalade

- Aucune nouvelle preuve après 2 passages ⇒ arrêt, question mise à jour.
- Même question reposée 2 fois ⇒ escalade humaine.
- Modèle indisponible ⇒ déterministe seul, cas conservé, `next_check` planifié.
- Budget atteint ⇒ `PARTIAL`, escalade humaine.
- Contradiction non résolue ⇒ `CONTESTE`, pas de confirmation.
- Preuve trop ancienne ⇒ `confidence` baisse, `stale=true`.

### 9.6 SLA de revue

| Priorité | Définition | Revue cible |
|---|---|---|
| P0 | critique, sécurité, réglementaire, rupture | 4 h |
| P1 | transverse, fort impact, owner inconnu | 1 jour ouvré |
| P2 | normal, ambiguïté locale | 3 jours ouvrés |
| P3 | faible valeur, background | batch hebdomadaire |

---

## 10. Brainstorm et décisions d'engagement à la naissance

### Option A — La naissance lance toujours une enquête complète

**Pour :** couverture maximale, aucune décision humaine à prendre.  
**Contre :** coût, bruit, risque de fausse certitude, files d'attente, agent qui tourne pour des Twins sans enjeu.

### Option B — La naissance lance une découverte locale, l'agent est policy-gated

**Pour :** coût maîtrisé, preuve d'abord, agent sur le résidu, humain responsable.  
**Contre :** demande une politique et un budget ; certains cas attendent un clic.

### Option C — La naissance ne lance rien, tout est humain

**Pour :** contrôle maximal, zéro coût agent.  
**Contre :** lent, dépend de la disponibilité des propriétaires, rate des liens évidents.

### Recommandation soumise

**Option B**, avec graduation :

1. **Phase 1** : `ASSISTED` pour tous, `AUTO_START` uniquement pour P0 sécurité/owner inconnu.
2. **Phase 2** : `AUTO_START` pour P1 après 50 cas revus et précision ≥ 90 %.
3. **P2** reste `ASSISTED` jusqu'à une nouvelle décision fondée sur les métriques.
4. **Jamais** de `AUTO_CONFIRM`.

### Décisions retenues — 2026-11-06

| ID | Décision | Conséquence |
|---|---|---|
| **D-001** | La naissance déclenche une **découverte locale bornée** ; la réconciliation globale est périodique ou événementielle. | Pas de broadcast O(n²) ; `twin.born` ne bloque pas la naissance ; le nouveau Twin est relié à ses voisins directs. |
| **D-002** | Le **domaine paie** l'agentique ; chaque Twin a un **quota** ; la plateforme porte un **plafond global**. | Le déterministe reste toujours actif ; l'agentique est facturé et priorisé par domaine. |
| **D-003** | `AUTO_START` pour **P0 uniquement** au départ ; P1 après **50 cas revus** et **précision ≥ 90 %** ; `AUTO_CONFIRM` interdit. | L'agent peut démarrer seul sur le critique ; la confirmation reste humaine ; auto-revert si la précision chute. |
| **D-004** | Cross-tenant **interdit par défaut** ; relation `PARTNER` possible avec **double consentement**. | Pas de fuite d'existence ni de preuve brute ; relation partagée, preuves locales. |
| **D-005** | P3 revu par **échantillonnage architecture/ops**, sans confirmation automatique. | La revue passe à l'échelle sans réintroduire de fausse certitude. |
| **D-006** | Sources par défaut : **niveau 0** (code, config, contrats, Helm). Niveaux 1 et 2 en opt-in. Niveau 3 sur approbation nommée. | Le CLI et le manifeste peuvent porter une politique explicite ; aucune source inconnue n'est autorisée. |

### Backlog de brainstorm

| ID | Question ouverte | Owner proposé | Prochaine étape | Priorité |
|---|---|---|---|---|
| B-001 | Qui porte le `ResolutionCase` quand le Twin est `PROVISIONAL` ? | Produit + domaine | Définir un propriétaire temporaire (domaine ou acteur de naissance) et un transfert à la promotion. | P1 |
| B-002 | Qui revoit les P2 quand le propriétaire est indisponible ? | Domaine | Nommer un délégué dans le manifeste ; à défaut, file gouvernance. | P1 |
| B-003 | Quelles sources sont autorisées par défaut ? | Sécurité + architecture | Valider la matrice niveau 0/1/2/3 et le bloc `sources_allowed`. | P0 |
| B-004 | Comment traite-t-on un fournisseur externe sans contrat ? | Architecture + achats | Choisir entre dépendance `externe` seule ou `SUPPLIER` déclaré. | P2 |
| B-005 | Combien de temps conserve-t-on les preuves ? | Sécurité + juridique | Fixer décisions/audit, liens, traces, secrets. | P1 |
| B-006 | Que fait-on si le modèle est indisponible 24 h ? | Ops + IA | Déterministe seul, file d’attente, modèle de secours approuvé. | P1 |
| B-007 | Comment mesure-t-on le rappel sans labels ? | Data + architecture | Corpus labellisé + shadow mode + active learning. | P0 |
| B-008 | Comment traite-t-on les collisions de namespace/cluster ? | Architecture | Namespace ajouté à l’identité du déploiement ; une collision de service entre namespaces reste une ambiguïté visible. | résolu — D-007 |
| B-009 | Comment traite-t-on une API à plusieurs implémentations ? | Architecture | Owner unique, implémentations multiples, ambiguïté explicite. | P2 |
| B-010 | Comment facture-t-on le coût agentique ? | Produit + finance | Quota par Twin, rapport par domaine, plafond plateforme. | P2 |
| B-011 | Comment gère-t-on `legacy.born` ? | Architecture | Même passe déterministe, sans confirmation automatique. | P2 |
| B-012 | Quel est le SLA de revalidation après un changement ? | Ops | Mesurer le délai entre changement et invalidation. | P1 |

---

## 11. Métriques

| Métrique | Cible pilote |
|---|---|
| Précision des liens | ≥ 90 % |
| Rappel sur le jeu d'or | ≥ 80 % |
| Fausse certitude | 0 |
| Liens avec preuve complète | 100 % |
| Questions avec `next_check` | 100 % |
| Temps du déterministe à la naissance | < 5 min (P95) |
| Temps de résolution d'un cas | < 1 jour (P1) |
| Revue de 20 liens | < 30 min |
| Coût agentique par cas | plafonné |
| Claims non supportés acceptés | 0 |
| Liens stale après changement | 0 |
| Taux d'escalade humaine | mesuré |

---

## 12. Déploiement

### Phase 0 — Cadrage et corpus

- 5 à 8 applications, 3 à 5 technologies.
- Matrice de couverture.
- Jeu d'or labellisé.
- Métriques et seuils.

### Phase 1 — Déterministe + naissance

- `twin.born` → passe déterministe idempotente.
- Liens, questions, couverture.
- Intégration `PropositionRelation` / `ResolutionCase`.
- Revue humaine dans le volet du Twin.

### Phase 2 — Agentique assisté

- 10 cas réels.
- 3 outils read-only.
- Boucle bornée, critique, revalidation.
- Mesure du lift vs déterministe seul.

### Phase 3 — Agentique auto encadré

- `AUTO_START` pour P0 dès le pilote.
- `AUTO_START` pour P1 après 50 cas revus et précision ≥ 90 %.
- `AUTO_CONFIRM` interdit.
- Budget, audit, kill switch, auto-revert.
- Revalidation incrémentale.

### Phase 4 — Connecteurs et échelle

- GitHub/Nexus/artefacts.
- APM/traces, gateway, CMDB, portail API.
- Namespace/cluster, environnements.
- WebbSphere export seulement si la sécurité l'approuve.

---

## 13. Critères d'acceptation

1. `twin.born` déclenche une passe déterministe idempotente, sans bloquer la naissance.
2. Un lien de même application est `interne` et n'entre pas dans le Mesh.
3. Une gateway seule ne produit pas d'attribution abusive.
4. Une API tierce n'est pas un Twin interne.
5. Une contradiction n'est jamais écrasée.
6. Un lien sans preuve reste `suggere` avec une question.
7. Un agent ne peut pas écrire un lien durable sans revalidation.
8. Un Twin `PROVISIONAL` ne peut pas confirmer une relation.
9. Aucun secret n'apparaît dans un lien, une preuve ou un log.
10. Toute question possède `missing_evidence` et `next_check`.
11. Toute revue est auditée : acteur, date, motif, preuve.
12. Un changement invalide les liens affectés et déclenche une revalidation.

---

## 14. Ce que le document ne promet pas

- Tous les langages et protocoles.
- Tous les liens automatiquement.
- Zéro revue humaine.
- Un accès serveur ou un export WebSphere obligatoire.
- Une précision et un rappel parfaits.
- Un agent qui remplace le moteur déterministe.

« Global » signifie ici : **une matrice de couverture explicite, des adaptateurs derrière des contrats stables, et des métriques par source**. Pas un parseur unique qui prétend tout comprendre.

---

## 15. État actuel et prochaines étapes

### Implémenté

- Modèle `Composant`, `Interface`, `Appel`, `Deploiement`, `Preuve`, `LienPropose`, `QuestionLien`.
- Extraction Java/JS, contrats, configuration, Kubernetes, Helm, traces.
- Résolution de service, hôte, route, file.
- Appariement HTTP/JMS/SOAP.
- Contradictions, externes, internes.
- Revue `revoir_lien`.
- Conversion en `PropositionRelation` et `ResolutionCase`.
- Pont depuis les manifestes et bindings.
- Politique de sources `PolitiqueSources` (niveaux 0 à 3, approbation niveau 3).
- CLI multi-dépôts avec `--niveau-sources`, `--source` et `--approuve-par`.
- Harnais d'évaluation `evaluer_liens` : précision, rappel, f1, fausses certitudes,
  couverture des preuves, questions, externes, contradictions.
- Corpus labellisé `tests/fixtures/liens_corpus/corpus.json` : liens Mesh, interne,
  externe, politique de sources.
- CLI `scripts/evaluer-liens.py` avec mode `--strict`.
- Boucle d'enquête bornée `boucle_investigation.py` : planificateur, outils injectés,
  budget, arrêt, candidats validés.
- Outils persistés `OutilBindings`, `OutilManifestes`, `OutilCode`, `OutilCMDB`,
  `OutilGateway`, `OutilVide`.
- Planificateur LLM borné `planificateur_liens.py`, avec repli déterministe.
- Registre des Twins chargé comme CMDB minimale.
- Lecture des preuves de code au SHA via `source_git` ou `github.lire_fichier` ;
  copie Git locale en secours, sous `JUMEAU_ENQUETE_CODE=1` et racine autorisée.
- Service `enqueter_case`, route `POST /boucle/resolutions/{id}/enqueter`.
- Bouton « Enquêter » dans le volet du Twin, avec raison d'arrêt et nombre de candidats.
- Raccordement opt-in des lecteurs existants ServiceNow (`OutilServiceNow`) et Datadog
  (`OutilAPM`), avec repli sur le registre si aucune correspondance.
- `OutilRuntime` réutilise les assertions `observed` de `connecteurs_runtime`.
- `OutilPortail` lit owner/implémentation d'un extrait de portail API.
- Worker de réconciliation `reconciliation_worker.py` et script `worker-reconciliation.py`.
- Unité systemd `scripts/meridian-reconciliation-worker.service`.
- Extraction JAX-RS, servlet JEE, FastAPI/Flask (AST Python), ASP.NET et clients
  Python/.NET.
- Repli textuel tracé pour les fichiers Python invalides.
- Primitives de chemins partagées entre `code_links` et `moteur_liens`.
- Contrats extraits dans `extraction_contrats.py`, helpers dans `extraction_commune.py`.
- CBM mappé en interfaces, appels HTTP et configurations (`cbm_liens.py`).
- Les observations CBM persistées alimentent `twin.born` et `reconcilier` ;
  `extraire_depot` ne relit un fichier avec un parseur local que si CBM ne l'a pas couvert.
- Suites dédiées : extraction, mapping, chemins, secrets, lecture de fichiers, JNDI,
  naissance et réconciliation.

### `twin.born` — première intégration

- Handler outbox : `decouverte_naissance.traiter_twin_born`.
- Découverte **locale bornée** : seuls les liens et questions où le Twin naissant est impliqué sont persistés.
- Les observations CBM persistées (`cbm_route`, `cbm_relation_http_calls`, `cbm_env`,
  routes Java) sont relues par Twin et mappées en interfaces et appels. Le manifeste
  reste la **déclaration**, le code devient la **preuve**. L'environnement reste
  `inconnu` tant qu'aucun déploiement ne le rattache.
- Une interface de code sans environnement complète l'interface déclarée de même
  méthode et de même chemin : les preuves sont cumulées et le lien n'est pas dupliqué.
  L'environnement déclaré reste prioritaire ; sans déclaration, `inconnu` reste visible.
- La lecture des observations de liens est plafonnée à 20 000 lignes par passage ;
  un diagnostic explicite est ajouté si le plafond est atteint, pour que la découverte
  ne soit jamais présentée comme complète à tort.
- Le résolveur historique `proposer_relations` reste exécuté pour le matching exact
  et les ressources. Il est marqué **legacy** : les nouvelles heuristiques de chemin,
  de service et de configuration vont dans `moteur_liens`, pas ici.
- Les liens Mesh éligibles deviennent des `PropositionRelation`.
- Les questions et les frontières inconnues deviennent des `ResolutionCase`.
- Le handler est idempotent par les identifiants de proposition et de cas.
- `reconcilier_twin` réutilise ce handler après une réingestion de dépôt : le code
  change, les liens du Twin sont rafraîchis sans passe globale.
- Aucun agent n'est appelé dans ce handler.

### Réconciliation globale

- `reconcilier(conn, tenant, appliquer, limite)` réutilise le même moteur sur tous les
  manifestes, bindings et observations de code du tenant.
- Dry-run par défaut via `scripts/reconcilier-liens.py`.
- Les propositions et cas restent idempotents.
- Aucun lien n'est confirmé, aucun agent n'est appelé.
- Worker `scripts/worker-reconciliation.py` : une passe ou boucle à intervalle,
  SIGTERM/SIGINT, dry-run ou `--apply`.

### Boucle d'enquête bornée

- Deux boucles distinctes : `investigation_runtime` exécute une investigation
  applicative structurée (contrat de domaine, preuves, `BudgetInvestigation`) et ne
  connaît pas les liens ; `boucle_investigation` traite un `ResolutionCase` de lien,
  avec `BudgetEnquete` et des candidats, sans jamais confirmer.
- `boucle_investigation.py` : planificateur injecté, outils read-only injectés,
  budget `max_etapes` / `max_outils` / `max_candidats`.
- `PlanificateurRegles` : repli déterministe selon la preuve manquante.
- Un outil inconnu, réutilisé ou en panne arrête la boucle avec une raison explicite.
- Les candidats passent par `CandidatResolution` ; un candidat invalide est ignoré et tracé.
- Aucune écriture, aucune confirmation, aucun appel réseau.

### Enquête sur un cas

- `enqueter_case(conn, tenant, case_id)` charge le cas, les bindings et les manifestes.
- `POST /boucle/resolutions/{id}/enqueter` expose la boucle.
- Les outils résolvent une propriété par la chaîne de bindings, cherchent une exposition
  dans les manifestes, lisent un instantané de code, une CMDB ou des routes de gateway.
- Le cas est mis à jour avec les candidats ; aucune `PropositionRelation` n'est créée.
- `JUMEAU_ENQUETE_PLANIFICATEUR=llm` active `PlanificateurLLM` ; sans modèle ou en cas
  d'échec, `PlanificateurRegles` prend le relais.
- Le registre des Twins (`jumeau`) alimente `OutilCMDB`.
- `JUMEAU_ENQUETE_CODE=1` active la lecture des preuves de code au SHA via `source_git` ;
  `JUMEAU_ENQUETE_CODE_ROOT` borne les copies locales de secours.
- Les lecteurs ServiceNow et Datadog existent déjà ; ils sont branchés en opt-in :
  `JUMEAU_ENQUETE_CMDB=servicenow` et `JUMEAU_ENQUETE_APM=datadog`.
- `OutilServiceNow` propose un CI seulement s'il se rattache au registre ; sinon le CI
  reste une preuve. `OutilAPM` fait de même pour les dépendances observées.
- Le volet du Twin expose un bouton « Enquêter » et la raison d'arrêt.

### Mémoire prospective

- `domain/memoire_prospective.py` : `Intention` (objet, échéance, scope, source,
  priorité, statut), avec refus d'une échéance sans fuseau.
- `memoire_prospective.py` : création idempotente, lecture, échéances dues, clôture,
  report et purge à 90 jours, toujours bornés au tenant.
- Un cas de résolution ouvert avec `next_check` reçoit une échéance par défaut de 7 jours
  et crée une intention `case:<id>` ; sa résolution la clôt, son abandon l'annule.
- Une réévaluation de cas rouvre une intention à 1 jour.
- Les échéances dues sont candidates au retrieval avec `source=intention`.
- API : `POST/GET /boucle/intentions`, `POST /boucle/intentions/{id}/clore`,
  `POST /boucle/intentions/{id}/reporter`.

### Boucle Learning → réutilisation mesurée

- `outcomes.marquer_reutilise` accepte `resultat` (`succes`, `echec`, `inconnu`),
  `outcome_id` et `preuve_ids`.
- `outcomes.metriques_reutilisation` rend les compteurs par Learning et au total ;
  `taux_succes` ne porte que sur les réutilisations résolues.
- `retrieval_memoire` expose `reutilisation` dans les données du candidat Learning.
- API : `POST /boucle/learnings/{id}/reutilisations` et
  `GET /boucle/learnings/metriques`.

### Dettes restantes

**Bloquées par l'environnement**

- Corpus de production labellisé, shadow mode et rappel de production.
- Connecteurs live portail API et gateway externe ; les outils `OutilPortail` et
  `OutilRuntime` sont prêts, les sources restent à importer.
- Lecture d'autres forges que GitHub ; le dépôt GitHub au SHA est branché.
- Test live du planificateur LLM (les tests utilisent un décideur injecté).
- Déploiement effectif du worker (l'unité systemd existe) et verrou multi-instance.
- Couverture CBM des langages non testés localement (Go, PHP, Ruby, batch, fichiers) :
  elle est attendue de CBM, mais reste à mesurer sur un corpus réel. Sans CBM, ces
  langages n'ont pas de repli local.
- Test Postgres des cas de démonstration : il exige un tenant `demo` pré-rempli, absent
  de l'environnement de test local.

**Dettes fermées par décision**

- Namespace/cluster et réécritures d'ingress statiques : extraits et modélisés
  (`Deploiement.namespace`, `RoutePasserelle.chemin_backend`).
- JNDI : extrait depuis le code (`@Resource`/`@EJB`) et relié par binding aux listeners
  JMS/KAFKA.
- Les deux chargeurs de fichiers gardent des parcours distincts (filtres, diagnostics,
  limite de fichiers), mais partagent les règles binaires, le décodage et les dossiers
  techniques dans `lecture_fichiers.py`.
- Store dédié des liens : **non retenu** pour l'instant. Les propositions et cas
  utilisent les objets d'entreprise ; la décision sera réévaluée si le volume ou les
  besoins de requête le justifient.
- Rafraîchissement incrémental : `ingerer` appelle `reconcilier_twin` après avoir
  remplacé l'index d'un dépôt ; `twin.born` couvre la naissance. `reconcilier` reste la
  passe globale de contrôle.

### Prochain lot recommandé

1. Corpus de production labellisé + shadow mode.
2. Étendre la revue UI/API aux cas P2/P3 et à l'échantillonnage, une fois le corpus disponible.
3. Branchement de la boucle agentique sur un modèle réel et 3 outils read-only.
4. Déploiement supervisé du worker (systemd/Kubernetes).
5. Mesure du lift, puis `AUTO_START` P0, puis P1 après seuils.

---

## 16. Décisions retenues et points ouverts

### 16.1 Décisions retenues

| Sujet | Décision | Statut |
|---|---|---|
| Déclenchement naissance | découverte locale bornée + réconciliation globale périodique/événementielle | **retenu — D-001** |
| Budget agent | domaine + quota Twin + plafond plateforme | **retenu — D-002** |
| Auto-start | P0 d'abord ; P1 après 50 cas revus et précision ≥ 90 % ; jamais d'auto-confirm | **retenu — D-003** |
| Cross-tenant | interdit par défaut ; `PARTNER` avec double consentement | **retenu — D-004** |
| Revue P3 | échantillonnage architecture/ops, sans confirmation automatique | **retenu — D-005** |
| Sources par défaut | niveau 0 ; niveaux 1/2 en opt-in ; niveau 3 sur approbation nommée | **retenu — D-006** |
| Portée inconnue | visible, non éligible | acquis |
| Confirmation | humaine uniquement | acquis |
| Contradiction | conservée | acquis |
| Namespace / rewrite ingress | namespace et chemin backend extraits ; rewrite paramétré non deviné | **retenu — D-007** |
| JNDI | `@Resource`/`@EJB` extraits, binding JNDI → listener JMS/KAFKA | **retenu — D-008** |
| Store des liens | objets d'entreprise ; pas de store dédié tant que le volume le permet | **retenu — D-009** |
| Rafraîchissement | `reconcilier_twin` après réingestion, `twin.born` à la naissance ; `reconcilier` global périodique | **retenu — D-010** |
| Chargeurs de fichiers | règles de lecture partagées, parcours distincts | **retenu — D-011** |
| Mémoire prospective | intentions datées, cas et retrieval, clôture/report/purge | **retenu — D-012** |
| Réutilisation des Learnings | résultat mesuré, outcome et preuves, métriques | **retenu — D-013** |

### 16.2 Points encore ouverts

| Sujet | Recommandation | Statut |
|---|---|---|
| Mode par défaut hors P0 | `ASSISTED` | proposé |
| Budget technique agent | 6 étapes / 4 sources / 2 min (rapide), 15 min (profond) | proposé |
| Revue P0 | 4 h | proposé |
| Revue P1 | 1 jour | proposé |
| Revue P2 | 3 jours | proposé |
| Revalidation | sur changement + périodique | proposé |
| Fournisseur externe | dépendance `externe` ou `SUPPLIER` déclaré | proposé |
| Rétention des preuves | décisions 7 ans, liens 13 mois, traces 30–90 j, secrets jamais | proposé |
| Modèle indisponible | déterministe seul + file + modèle de secours approuvé | proposé |
| Rappel sans labels | corpus + shadow mode + active learning | proposé |
| Propriétaire d'un cas `PROVISIONAL` | domaine ou acteur de naissance, transfert à la promotion | proposé |
| Namespace/cluster | ajouter à l'identité de déploiement | proposé |

---

## 17. Conclusion

La naissance n'est pas un bouton « découvre tout ». C'est un **engagement de transparence** :

- Méridian doit produire rapidement ce qu'il sait, ce qu'il soupçonne et ce qu'il ignore ;
- l'agent doit enquêter uniquement là où la preuve manque ;
- le propriétaire doit pouvoir trancher ;
- le système doit revalider quand le monde change.

La bonne formule est :

```text
naissance
  → découverte locale bornée
      → soupçons + questions
          → agentique sur le résidu
              → revalidation
                  → revue humaine
                      → observation
                          → apprentissage
  → réconciliation globale périodique / événementielle
```

C'est cette discipline qui permet de dire :

> **« Voici ce que nous savons, voici ce que nous soupçonnons, voici ce qui manque, et voici qui doit trancher. »**
