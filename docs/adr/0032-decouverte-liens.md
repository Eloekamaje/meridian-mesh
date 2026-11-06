# ADR-0032 — Découverte des liens : résolution de destination et cas non résolus

- **Statut :** proposed
- **Date :** 2026-11-06
- **Décideurs :** Produit, architecture, propriétaires de domaine, sécurité, exploitation
- **Portée :** découverte des échanges, résolution de destination, cas non résolus, boucle agentique bornée
- **Décisions liées :** ADR-0001 (identité typée), ADR-0003 (Mesh transversal), ADR-0004 (harness capacitaire), ADR-0007 (polyglotte), ADR-0012 (outbox/idempotence), ADR-0031 (naissance relationnelle)
- **Prérequis :** ADR-0031, portée `INTERNAL` / `SERVICE` / `UNKNOWN`, ressources intermédiaires

---

## 1. Contexte

### 1.1 Le problème

Le backfill local d'ADR-0031 a produit **8 manifestes** et **170 routes HTTP**. Après classification :

- **24 routes techniques** (`HEALTH`, `ADMIN`, `DEMO`) ;
- **146 routes `UNKNOWN`** ;
- **0 route `SERVICE` / `PARTNER` / `PUBLIC`** ;
- **0 consommation**.

Le résolveur ne peut donc produire **aucune relation de Mesh**. Ce n'est pas un défaut du résolveur : c'est l'absence de **frontière** et de **destination résolue**.

Une route dans le code ne dit pas :

- si elle est interne à l'application ;
- derrière quelle passerelle elle est publiée ;
- quel service la reçoit ;
- quel Twin la possède ;
- si elle est réellement utilisée.

Le code d'un client ne dit pas non plus :

- à quelle propriété de configuration correspond `${accounts.base-url}` ;
- vers quelle route de passerelle cette propriété pointe ;
- quel service se trouve derrière la passerelle ;
- si l'appel est observé en production.

### 1.2 Ce que le code fournit déjà

| Élément | État | Rôle |
|---|---|---|
| `domain/naissance_relationnelle.py` | implémenté | `Exposition`, `Consommation`, `Ressource`, `portee`, `PropositionRelation` |
| `application/relations_naissance.py` | implémenté | manifeste, matching direct et via ressource, propositions |
| `adapters/outbound/postgres/relations_naissance.py` | implémenté | manifestes, propositions, `twin.born`, backfill |
| `domain/decouverte_liens.py` | implémenté | `Binding`, `DestinationResolution`, `ResolutionCase` |
| `application/decouverte_liens.py` | implémenté | `resolve_destination`, ouverture de cas |
| `adapters/outbound/postgres/decouverte_liens.py` | implémenté | bindings et cas persistés |
| `GET /boucle/resolutions` | implémenté | lecture des cas ouverts |
| `POST /boucle/resolutions/{id}/resoudre` | implémenté | clôture avec preuves |
| `extract_exchanges` | manquant | extraction des échanges depuis le code/artefacts |
| `match_interface` | partiel | matching exact seulement |
| `observe_exchange` | manquant | traces/journaux |
| Boucle agentique | manquante | choix de la prochaine source |
| `ask_twin` / `ask_owner` | manquants | attestation et revue |

### 1.3 Forces en présence

- **Accessibilité.** WebSphere/WebLogic/JBoss ne sont pas toujours accessibles ; il faut partir des dépôts, artefacts, exports et traces.
- **Preuve.** Un binding déclaré n'est pas une observation ; une destination résolue n'est pas un usage.
- **Frontière.** Une route interne ne doit jamais devenir une relation inter-app.
- **Ambiguïté.** Deux services, deux routes ou deux Twins peuvent correspondre ; il faut garder le candidat.
- **Coût.** Une boucle agentique non bornée produit des appels, des questions et des tickets.
- **Gouvernance.** L'agent propose ; le propriétaire confirme ; l'observation renforce.

---

## 2. Décision

Méridian ajoute une **capacité** :

```text
discover_application_links(app_id, environment, mode=initial|change|on_demand)
```

composée de **sept outils déterministes** et d'une **boucle agentique bornée** :

| Outil | Rôle | Déterministe |
|---|---|---|
| `extract_exchanges` | routes, clients, événements, fichiers | oui |
| `resolve_destination` | propriété/URL/JNDI → cible ou candidats | oui |
| `match_interface` | opération ↔ contrat/route | oui |
| `observe_exchange` | traces/journaux, fenêtre et couverture | oui |
| `propose_link` | écrit une proposition avec preuves | oui |
| `ask_twin` | attestation ciblée d'un Twin | non, borné |
| `review_link` | confirmation/contestation propriétaire | humain |

Le premier lot implémenté est **`resolve_destination` + `ResolutionCase`**. Les autres outils sont des lots séparés.

### 2.1 Formule normative

> Le code et la configuration disent ce qui est **implémenté** et **configuré**.
> L'observation dit ce qui est **utilisé**.
> L'agent choisit la prochaine source quand une preuve manque.
> Le propriétaire confirme.
> Le Mesh conserve le lien, ses preuves, son environnement et son état.

---

## 3. Résolution de destination

### 3.1 Chaîne

```text
référence logique
  → propriété de configuration
  → URL
  → route de passerelle
  → nom de service
  → Twin
```

Ou, pour les services asynchrones :

```text
référence JNDI
  → file/topic
  → propriétaire de la ressource
  → Twin
```

### 3.2 Bindings

Un binding est un artefact déclaré :

```json
{
  "kind": "PROPERTY | GATEWAY_ROUTE | SERVICE | JNDI | QUEUE | TOPIC | DATABASE | FILE",
  "nom": "accounts.base-url",
  "valeur": "https://gateway.example/accounts",
  "environment": "prod",
  "source": "manifeste de déploiement",
  "evidence_ids": ["config:42"],
  "owner": "équipe plateforme"
}
```

Un binding n'est pas une vérité : il porte sa source, sa date, son environnement et son propriétaire.

### 3.3 Résultats

`resolve_destination` rend trois statuts :

| Statut | Signification |
|---|---|
| `resolved` | une cible unique a été trouvée |
| `ambiguous` | plusieurs cibles possibles ; aucune n'est choisie |
| `missing_evidence` | le maillon manque ; la question exacte est connue |

Un résultat `missing_evidence` contient :

- `missing_evidence` : ce qui manque ;
- `next_check` : la source à consulter ;
- `chain` : les étapes déjà établies ;
- `evidence_ids`.

### 3.4 Priorité des sources

1. configuration de déploiement (manifeste, Helm, Ansible, CI) ;
2. export de binding serveur (WebSphere, WebLogic, JBoss) ;
3. route de passerelle / ingress / service mesh ;
4. catalogue de services ;
5. déclaration humaine ;
6. traces/journaux.

Une source plus faible ne remplace jamais une source plus forte : elle la complète ou la conteste.

---

## 4. Cas non résolus

`ResolutionCase` est un objet durable de la famille `connaissance`, type `UNKNOWN` :

```json
{
  "id": "resolution-...",
  "tenant_id": "banque",
  "twin_id": "antifraude",
  "reference": "${accounts.base-url}",
  "environment": "prod",
  "status": "open | resolved | abandoned",
  "missing_evidence": "propriété absente du manifeste",
  "next_check": "consulter la configuration de déploiement",
  "owner": "équipe plateforme",
  "attempts": 0,
  "evidence_ids": [],
  "candidates": []
}
```

Règles :

- un cas est ouvert **uniquement** si la destination n'est pas résolue ;
- une résolution ultérieure le clôt avec ses preuves ;
- un cas n'est jamais une relation ;
- un cas sans réponse reste visible et interrogeable ;
- un cas ne traverse jamais un tenant.

---

## 5. Vérification triple

Une relation porte trois lectures indépendantes :

```json
{
  "verification": {
    "implemented": "confirmed | partial | missing",
    "routing": "configured | ambiguous | missing",
    "runtime_usage": "observed | unverified | absent"
  }
}
```

Exemple :

```text
Antifraude → Comptes · GET /accounts/{id}
  implemented: confirmed     (client dans le dépôt Antifraude, route dans Comptes)
  routing: configured        (propriété -> passerelle -> service comptes-api)
  runtime_usage: unverified  (aucune trace disponible)
```

Aucun des trois ne remplace les autres. Une relation `confirmed` sans observation doit afficher **« configuré, non observé »**.

---

## 6. Frontière et composants

La règle d'ADR-0031 s'applique :

- `SERVICE`, `PARTNER`, `PUBLIC` : éligible inter-app ;
- `INTERNAL`, `ADMIN`, `HEALTH`, `DEMO`, `DEBUG` : non éligible ;
- `UNKNOWN` : jamais matché ;
- `application_id` identique : lien de composant, pas relation de Mesh.

`discover_application_links` doit donc produire deux sorties distinctes :

1. **liens de composants** dans le Twin (frontend → backend, module → module) ;
2. **relations de Mesh** entre applications distinctes.

Un appel front-back n'est pas une dépendance entre applications.

---

## 7. Boucle agentique bornée

### 7.1 Déclencheurs

- analyse initiale d'un Twin ;
- changement de code, de configuration ou de contrat ;
- demande explicite de Flore avant une décision (décommissionnement, impact, migration) ;
- contradiction ou cas non résolu.

### 7.2 Boucle

```text
extraire
  → résoudre
      → résolu ? matcher
      → ambigu ? demander un candidat
      → manquant ? ouvrir un cas
  → observer
  → proposer
  → revue propriétaire
  → confirmer / contester / laisser ouvert
```

### 7.3 Budget

- maximum d'étapes ;
- maximum de sources consultées ;
- maximum de questions ;
- délai ;
- cache des résolutions ;
- interdiction de redemander la même preuve ;
- arrêt sur budget ou source épuisée.

### 7.4 Autorité

- `ask_twin` renvoie des **Claims et preuves**, jamais une confirmation ;
- `ask_owner` est une revue humaine ;
- `propose_link` écrit une proposition `supposee` ;
- `review_link` seul peut passer à `confirmee` ;
- aucun LLM ne produit `confirmee`.

---

## 8. WebSphere et serveurs inaccessibles

Le harness ne suppose pas l'accès à la console. Il accepte :

1. les descripteurs et bindings présents dans le dépôt ou l'artefact déployé ;
2. un export read-only ciblé fourni par l'équipe plateforme ;
3. les traces et journaux disponibles ;
4. un snapshot de binding horodaté, ingéré comme `SourceArtifact`.

`resolve_destination` peut alors rendre :

```text
Paiements publie via jms/PaymentEvents.
Binding de production à obtenir auprès de l'équipe plateforme.
```

Quand l'export arrive, le cas reprend à l'étape exacte et cherche les consommateurs.

Une référence JNDI identique dans deux dépôts ne prouve pas qu'ils utilisent la même file. Il faut le binding serveur et, si possible, une observation broker.

---

## 9. Alternatives considérées

### Alternative 1 — Agent qui écrit directement les relations

- **Avantages :** rapide.
- **Inconvénients :** viole ADR-0031, pas de revue, pas de preuve, boucle non bornée.
- **Rejetée.**

### Alternative 2 — Matching uniquement code → code

- **Avantages :** simple.
- **Inconvénients :** ne résout pas `${...}`, les passerelles, les JNDI, les serveurs opaques.
- **Rejetée.**

### Alternative 3 — CMDB comme source unique

- **Avantages :** référentiel existant.
- **Inconvénients :** incomplet, politique, non observé.
- **Rejetée comme source unique ; retenue comme binding déclaré.**

### Alternative 4 — Résolution déterministe + cas + agent borné (retenue)

- **Avantages :** preuve, reprise, ambiguïté explicite, accessibilité partielle, coût borné.
- **Inconvénients :** plus d'objets, de sources et de revue.
- **Retenue.**

---

## 10. Pilote

Deux applications : **Antifraude** et **Comptes**.

Sources : deux dépôts, une configuration de déploiement, éventuellement un export de binding et une source de traces.

Cas à vérifier :

1. **lien réel** : `GET /accounts/{id}`, propriété → passerelle → service → Twin ;
2. **front-back** : même `application_id`, lien de composant, pas de relation Mesh ;
3. **destination inconnue** : `ResolutionCase` ouvert, question exacte ;
4. **JNDI/WebSphere** : binding exporté → file → consommateur ;
5. **contradiction** : configuration vs trace, relation `contestee`.

Critère de réussite :

> Flore peut répondre « qui utilise cette application, pour quoi faire, et qu'est-ce qui casse si on la retire ? » avec la chaîne de preuves et les inconnues.

---

## 11. Implémentation du premier lot (2026-11-06)

Implémenté — **étage 1, déterministe** :

- `backend/meridian/domain/decouverte_liens.py` : `Binding`, `DestinationResolution`, `ResolutionCase`, `CandidatResolution`.
- `backend/meridian/application/decouverte_liens.py` : `resolve_destination`, ouverture de cas, investigateur borné, revue de candidat.
- `backend/meridian/adapters/outbound/postgres/decouverte_liens.py` : bindings et cas persistés, investigation, revue.
- `backend/meridian/adapters/inbound/http/cognitif.py` : `GET /boucle/resolutions`, `POST /boucle/resolutions/{id}/resoudre`, `POST /boucle/resolutions/{id}/investiguer`, `POST /boucle/resolutions/{id}/revue`, `POST /boucle/relations/{id}/observation`.
- Tests : `backend/meridian/tests/test_decouverte_liens.py`, `test_cognitif_routes.py`.

Implémenté — **étage 2, investigateur borné** :

- `backend/meridian/adapters/outbound/llm/investigateur_liens.py` : réponse structurée `ReponseInvestigation`, candidats et bindings proposés, aucune confirmation.
- L'investigateur ne reçoit qu'un contexte borné : cas, bindings, Twins, expositions, règles.
- Un candidat dont le `twin_id` n'est pas dans le contexte est ignoré.
- L'investigation est une passe explicite ; la boucle multi-étapes avec budget reste à faire.

Implémenté — **étage 3, humain et observation** :

- revue d'un candidat : `accepter` ou `rejeter` ;
- un candidat accepté crée ses bindings (PROPERTY, GATEWAY_ROUTE, SERVICE, ALIAS, JNDI, QUEUE, TOPIC, DATABASE, FILE), clôt le cas et permet à `resolve_destination` de résoudre la prochaine fois ;
- la clôture est revalidée par le déterministe ; si les bindings acceptés ne résolvent pas la destination, le cas reste ouvert ;
- si la destination est résolue, une `PropositionRelation` `supposee` est créée (mode `INFERRED` pour une hypothèse d'agent, `DECLARED` sinon), avec les propriétaires des deux Twins ;
- un candidat rejeté laisse le cas ouvert ;
- `POST /boucle/relations/{id}/observation` appelle `marquer_observee` avec preuves et date.

Non implémenté dans ce lot :

- `extract_exchanges` ;
- `match_interface` (le matching reste exact) ;
- `observe_exchange` (l'endpoint d'observation de relation existe, pas l'ingestion de traces) ;
- la boucle agentique multi-étapes avec budget/sources visitées ;
- `ask_twin` / `ask_owner` ;
- l'extraction des bindings WebSphere/OpenAPI/gateway.

Limites assumées :

- l'investigateur est une passe unique, pas encore une boucle ;
- la revue humaine n'a pas encore de contrôle de rôle fin : l'acteur est authentifié, le propriétaire reste une chaîne ;
- les bindings acceptés sont déclaratifs et doivent être revus si l'environnement change ;
- l'observation n'est pas encore reliée à une source de traces.

---

## 12. Critères d'acceptation

1. Une propriété `${x}` est suivie jusqu'à un Twin unique, avec sa chaîne et ses preuves.
2. Une destination ambigüe ne produit pas de Twin ; elle produit des candidats.
3. Une destination manquante ouvre un `ResolutionCase` avec la question exacte.
4. Un cas résolu est clôturé avec ses preuves, jamais transformé en relation.
5. Aucun binding ne traverse un tenant.
6. Une route `INTERNAL` / `UNKNOWN` ne produit pas de relation de Mesh.
7. Deux Twins de la même `application_id` ne produisent pas de relation inter-app.
8. Un appel front-back est conservé comme lien de composant.
9. `record_link` n'existe pas : `propose_link` et `review_link` sont séparés.
10. Un LLM ne peut pas produire `confirmee`.
11. La boucle agentique est bornée par étapes, sources, questions et délai.
12. Une absence de trace est `non observé` avec fenêtre et couverture, jamais « n'existe pas ».

---

## 13. Références

- `docs/adr/0031-naissance-relationnelle.md`
- `docs/prd/PRD-001-enterprise-intelligence-mesh.md`
- `docs/adr/0007-polyglot-postgres-graph.md`
- `docs/adr/0012-outbox-idempotence.md`
- `docs/architecture/java-jee-spring-pack.md`
- `docs/architecture/legacy-frameworks-reference.md`
