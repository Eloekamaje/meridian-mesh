# PRD-001 — Méridian, Enterprise Intelligence Mesh

**Statut :** Accepté comme base de travail  
**Version :** 1.0  
**Date :** 2026-10-30  
**Propriétaire produit :** Méridian  
**Décideurs :** Produit, architecture d'entreprise, données, sécurité  
**Documents fondateurs :** `docs/MÉRIDIAN — Product Vision & Operating Model.md`, `docs/MERIDIAN_Domain_Model_Information_Architecture_v1.md`, `docs/MERIDIAN_Functional_Architecture_v1.md`, `docs/MERIDIAN_Knowledge_Claims_Architecture_v1.md`, `docs/MERIDIAN_Technical_Architecture_v1.md`  
**Décisions liées :** [ADR-0003](../adr/0003-mesh-transversal-intelligence.md), [ADR-0004](../adr/0004-capability-first-harness.md), [ADR-0005](../adr/0005-enterprise-object-model.md)  
**Remplace :** la lecture réductrice « Mesh = outil de vérification / source / boîte à trois outils applicatifs ».

---

## 0. Règle de lecture

Ce PRD décrit le **produit cible** et ses exigences. Il ne décrit pas l'état actuel du code.

L'implémentation actuelle est une **amorce applicative** : elle sait résoudre une application, mobiliser des jumeaux et produire une conception greenfield. Elle ne satisfait pas encore le modèle d'entreprise décrit ici. Les écarts doivent être traités comme des chantiers, pas comme des exceptions.

Le langage normatif suit RFC 2119 : **DOIT**, **NE DOIT PAS**, **DEVRAIT**, **PEUT**.

---

## 1. Problème

Les grandes entreprises ne manquent pas de données. Elles manquent d'une **compréhension vivante, transversale et vérifiable** de leur fonctionnement :

- la connaissance est dispersée entre applications, code, configurations, contrats, runtime, documents, CMDB, incidents et personnes ;
- chaque transformation recommence par reconstruire ce que l'entreprise sait déjà ;
- les outils actuels répondent par application, par silo ou par document, rarement par **situation d'entreprise** ;
- les modèles génératifs produisent des réponses plausibles sans preuve, sans temporalité et sans gouvernance ;
- les organisations confondent souvent « inventaire » et « compréhension », « donnée » et « connaissance », « application » et « entreprise ».

Méridian doit transformer cette dispersion en **intelligence institutionnelle réutilisable**.

---

## 2. Vision

Méridian est un **Enterprise Intelligence Mesh** : une couche qui découvre continuellement le fonctionnement réel de l'entreprise, transforme les observations en connaissance vérifiable, met cette connaissance en relation dans un Mesh, puis l'exploite pour détecter, investiguer, décider, agir, mesurer et apprendre.

Le Mesh n'est **ni une source**, **ni un outil**, **ni le produit visible**. C'est la **couche d'intelligence transversale** de l'entreprise : le système nerveux qui relie, confronte, fait émerger et conserve la mémoire des transformations.

La boucle produit est :

> **Source → Observation → Claim → Mesh → Signal → Expression → Opportunité → Investigation → Décision → Initiative → Outcome → Apprentissage**

Le produit ne doit pas être réduit à un réseau de jumeaux applicatifs. L'application est le **point d'amorçage** ; l'entreprise est la cible.

---

## 3. Principes non négociables

| # | Principe | Conséquence |
|---|---|---|
| P-01 | **Le Mesh est transversal, pas une source.** | Les sources produisent des observations ; le Mesh relie, confronte et fait émerger. |
| P-02 | **Le jumeau comprend localement ; le Mesh comprend transversalement.** | Un jumeau ne porte pas la vérité de l'entreprise à lui seul. |
| P-03 | **La connaissance est un actif temporel et prouvé.** | Chaque Claim a une preuve, une fraîcheur, un mode et une période de validité. |
| P-04 | **Le dépôt Git est un artefact, pas la vérité première.** | Code, config, contrats, runtime, documents, personnes et décisions sont des sources. |
| P-05 | **Le Twin n'est pas limité à l'application.** | Processus, capacité, parcours, organisation, produit et domaine de données sont des types de Twin. |
| P-06 | **L'humain gouverne la décision.** | L'agent propose, relie, explique et alerte ; il ne décide pas seul d'une identité, d'une fusion ou d'une action sensible. |
| P-07 | **Le Mesh doit rester invisible comme produit.** | L'utilisateur voit des situations, des questions, des décisions et des actions, pas un graphe technique. |
| P-08 | **Le harness est capacitaire, pas une liste d'outils figée.** | Les outils sont des adaptateurs à des capacités d'entreprise, découvrables et gouvernés. |
| P-09 | **Une proposition n'est pas un fait.** | Toute conception ou hypothèse est étiquetée, datée et séparée des observations. |
| P-10 | **Aucune conclusion d'absence sans périmètre, source et date.** | Une absence est « non observé », jamais « n'existe pas ». |

---

## 4. Personas et travaux à accomplir

| Persona | Travail principal | Question typique |
|---|---|---|
| Architecte d'entreprise | Comprendre le patrimoine et les transformations | « Que change cette évolution sur le SI ? » |
| Propriétaire de domaine | Piloter une capacité ou un processus | « Où sont les frictions de mon parcours ? » |
| Opérations | Détecter et diagnostiquer | « Pourquoi cette chaîne ralentit-elle ? » |
| Risque / conformité | Vérifier dépendances et contradictions | « Quelles dépendances sont non prouvées ? » |
| Finance | Arbitrer un investissement | « Que finance-t-on déjà ailleurs ? » |
| Data | Relier données, flux et responsabilités | « Qui produit cette donnée et qui la consomme ? » |
| Transformation | Concevoir et suivre une cible | « Quelle architecture cible pour ce nouveau service ? » |
| Employé / conseiller | Comprendre son outil et agir | « Que puis-je faire dans cette situation ? » |

### Jobs-to-be-done

1. **Comprendre** une application, un processus, une capacité ou un parcours.
2. **Détecter** un signal, une dérive, une contradiction ou une opportunité.
3. **Investiguer** avec les bonnes expertises et les bonnes preuves.
4. **Décider** entre des scénarios, avec incertitude et gouvernance.
5. **Agir** et suivre une initiative.
6. **Mesurer** l'outcome et **apprendre**.
7. **Concevoir** une application ou une transformation qui n'existe pas encore.
8. **Comparer** des applications, des options ou des périodes.

---

## 5. Modèle d'entreprise

Le modèle de domaine est organisé en **huit familles** :

1. **Identité & structure** : Twin, Domain, Capability, Application, Process, Journey, Team.
2. **Sources & preuves** : Source, Artifact, Observation, Evidence.
3. **Connaissance** : Claim, Relationship, Unknown, Contradiction.
4. **Émergence** : Signal, Situation, Expression, Opportunity, Risk.
5. **Investigation** : Investigation, Hypothesis, Expert, ExpertContribution.
6. **Décision** : Scenario, Decision, Initiative.
7. **Résultat & apprentissage** : Outcome, Learning.
8. **Interaction & gouvernance** : UserContext, Scope, Permission, Annotation, Subscription.

### Types de Twin

Un Twin représente une entité de l'entreprise dont Méridian maintient une représentation vivante :

`APPLICATION`, `PROCESS`, `CAPABILITY`, `JOURNEY`, `ORGANIZATION`, `PRODUCT`, `DATA_DOMAIN`.

L'application est le premier type implémenté, pas le seul type ontologique.

### Modes de connaissance

Toute connaissance importante distingue :

`DECLARED`, `OBSERVED`, `INFERRED`, `PROPOSED`, `CONFIRMED`.

### Cycle de vie d'une connaissance

`Observation → Hypothèse → Claim → Claim renforcé → Connaissance mature → Décision → Apprentissage`.

---

## 6. Capacités du produit

Le produit doit exposer des **capacités d'entreprise**, pas seulement des outils applicatifs :

| Capacité | Rôle |
|---|---|
| `situer` | Domaines, capacités, processus, parcours, équipes, produits. |
| `observer` | Lire les sources et artefacts. |
| `lire_claims` / `prouver` | Connaissances, preuves, fraîcheur, contradictions. |
| `relier` / `confronter` | Relations, écarts, propagation, domaines émergents. |
| `maturer` | Faire passer une observation vers un Claim. |
| `investiguer` | Hypothèses, experts, contributions. |
| `proposer_decision` / `decider` | Scénarios, arbitrages, gouvernance. |
| `agir` | Initiative, Travail, livrable. |
| `mesurer` / `apprendre` | Outcome, Learning. |
| `concevoir` | Architecture cible, transformation. |
| `mobiliser_expert` | Jumeaux et experts. |
| `chercher_outil` | Découverte d'outils et de sources. |

---

## 7. Exigences fonctionnelles

### 7.1 Modèle et connaissance

- **FR-001** — Le système DOIT modéliser les huit familles d'objets et leurs agrégats.
- **FR-002** — Chaque Claim DOIT porter au minimum : sujet, prédicat, objet, mode, statut, maturité, confiance, preuve(s), source(s), validité temporelle.
- **FR-003** — Le système DOIT distinguer `DECLARED`, `OBSERVED`, `INFERRED`, `PROPOSED` et `CONFIRMED`.
- **FR-004** — Le système DOIT conserver l'historique des versions et des remplacements.
- **FR-005** — Le système DOIT représenter les contradictions et les inconnues explicitement.
- **FR-006** — Un Claim NE DOIT PAS être promu au Mesh sans preuve et sans règle de promotion.

### 7.2 Découverte et sources

- **FR-010** — Le système DOIT accepter des sources hétérogènes : code, configuration, contrats, runtime, documents, CMDB, incidents, personnes.
- **FR-011** — Chaque source DOIT produire des observations avec provenance et fraîcheur.
- **FR-012** — Une source NE DOIT PAS être assimilée à une application, à un Claim ou au Mesh.
- **FR-013** — Le système DOIT pouvoir fonctionner avec une source partielle et marquer l'incertitude.
- **FR-014** — Le système DOIT pouvoir ajouter un adaptateur de source sans modifier le noyau.

### 7.3 Twin local

- **FR-020** — Chaque Twin DOIT avoir une identité stable, un type, un périmètre, un propriétaire et une version.
- **FR-021** — Un Twin DOIT maintenir sa fiche vivante, ses Claims, ses preuves et ses relations.
- **FR-022** — Un Twin DOIT exposer ses inconnues et ses contradictions.
- **FR-023** — Un Twin NE DOIT PAS être la seule autorité sur une connaissance transversale.

### 7.4 Mesh transversal

- **FR-030** — Le Mesh DOIT relier les Twins et les Claims par des relations typées.
- **FR-031** — Le Mesh DOIT confronter les Claims entre sources et entre Twins.
- **FR-032** — Le Mesh DOIT détecter les contradictions, les dépendances, les capacités partagées, les processus et les domaines émergents.
- **FR-033** — Le Mesh DOIT conserver la topologie dans le temps et permettre une lecture à une date donnée.
- **FR-034** — Le Mesh NE DOIT PAS être présenté à l'utilisateur comme un outil de vérification ou un catalogue d'applications.

### 7.5 Émergence et situations

- **FR-040** — Le système DOIT transformer des signaux en situations candidates selon des seuils de maturité.
- **FR-041** — Une situation DOIT porter un périmètre, une priorité, une confiance, une fraîcheur, des preuves et des inconnues.
- **FR-042** — Une situation DOIT pouvoir être exprimée, ignorée, investiguée ou décidée.
- **FR-043** — Le système DOIT distinguer un fait, une hypothèse et une interprétation dans une expression.

### 7.6 Investigation, décision, action, apprentissage

- **FR-050** — Une investigation DOIT pouvoir mobiliser plusieurs Twins, experts et sources.
- **FR-051** — Une décision DOIT conserver les options, les critères, les incertitudes, l'acteur et la date.
- **FR-052** — Une initiative DOIT être reliée à une décision et à un outcome attendu.
- **FR-053** — Un outcome DOIT être mesuré et relié à l'initiative.
- **FR-054** — Un apprentissage DOIT être réutilisable dans une situation future.

### 7.7 Flore

- **FR-060** — Flore DOIT être un agent général situé dans le Mesh, pas un routeur applicatif.
- **FR-061** — Flore DOIT distinguer une question sur l'existant, une conception, une comparaison, une investigation, une décision et une question générale.
- **FR-062** — Pour une conception greenfield, Flore DOIT produire une proposition étiquetée, avec hypothèses, sans mobiliser de jumeau ni afficher l'Atlas.
- **FR-063** — Pour une application existante, Flore DOIT résoudre l'identité, consulter les sources pertinentes et citer les preuves.
- **FR-064** — Flore NE DOIT PAS conclure à l'absence sans périmètre, sources et date.
- **FR-065** — Flore DOIT demander une clarification si l'ambiguïté change la réponse.
- **FR-066** — Flore DOIT exposer sa trace d'orchestration : capacités et outils utilisés, sans secret.

### 7.8 Harness et outils

- **FR-070** — Les outils DOIVENT être déclarés par manifeste : nom, description, schéma, capacité, objet, portée, permissions, coût, timeout, preuve produite.
- **FR-071** — Le registre DOIT filtrer les outils par tenant, persona, périmètre et risque.
- **FR-072** — Le modèle DOIT pouvoir découvrir un outil à la demande sans charger tous les schémas.
- **FR-073** — Les outils DOIVENT être, par défaut, en lecture seule.
- **FR-074** — Une action sensible DOIT exiger une approbation humaine.
- **FR-075** — Un nouvel outil read-only DOIT pouvoir être ajouté par manifeste/MCP sans modifier le noyau.
- **FR-076** — Aucun modèle NE DOIT installer ou auto-autoriser un outil à la volée.

### 7.9 Projections et gouvernance

- **FR-080** — Le Mesh DOIT pouvoir être projeté par rôle : architecture, business, client, employé, opérations, risque, finance, data, transformation.
- **FR-081** — Chaque projection DOIT appliquer les droits et le tenant.
- **FR-082** — Toute action sensible DOIT être auditée.
- **FR-083** — Les secrets NE DOIVENT jamais entrer dans un prompt, un log, une preuve ou une réponse.

### 7.10 Stockage, graphe et recherche

- **FR-090** — Postgres est le store **transactionnel et probatoire** : identité canonique des Twins, sources, observations, preuves, Claims, décisions, initiatives, outcomes, apprentissages et audit.
- **FR-091** — Le **graph store** (Neo4j ou Neptune) possède la **topologie du Mesh** : nœuds Twin référençant l'identité Postgres, relations, domaines, capacités, processus, parcours, situations, impacts. Il n'est **pas** une projection de Postgres.
- **FR-092** — Aucun objet n'est dupliqué intégralement entre Postgres et le graphe ; les références croisées sont des IDs.
- **FR-093** — Une interface `GraphStore` isole le domaine du vendeur ; changer Neo4j/Neptune ne change pas le modèle métier.
- **FR-094** — Aucun store Mongo, Neptune ou Neo4j n'est une projection ou une copie d'un autre store. Une projection est interdite.
- **FR-095** — La découverte est **à paliers** : portefeuille pour tout le parc, déclaré pour les apps importantes, observé pour les critiques, profond pour les apps sélectionnées ou impactées.
- **FR-096** — À 5 000+ applications, le produit NE DOIT PAS charger tout le parc dans un prompt, rendre tous les nœuds ou réveiller un agent par application.

---

### 7.11 Mémoire, contexte et raisonnement

Les exigences détaillées sont définies dans [PRD-002](PRD-002-memoire-contexte-raisonnement.md) :
mémoire de session, épisodique, sémantique, procédurale, organisationnelle et de valeur ; Context Pack
borné et fingerprinté ; trace de raisonnement auditable, abstention et DecisionSupport. Les fiches
produit associées sont indexées dans [PRODUCT-SHEETS.md](PRODUCT-SHEETS.md).

---

## 8. Exigences non fonctionnelles

- **NFR-001 — Preuve** : toute affirmation d'entreprise DOIT citer une source, une preuve et une date.
- **NFR-002 — Temporalité** : toute connaissance importante DOIT avoir une période de validité et une fraîcheur.
- **NFR-003 — Multi-tenant** : tout objet, cache, prompt, outil et log DOIT être tenant-scoped.
- **NFR-004 — Sécurité** : lecture seule par défaut, moindre privilège, secrets par référence, audit append-only.
- **NFR-005 — Explicabilité** : une réponse DOIT distinguer observation, hypothèse, proposition et inconnue.
- **NFR-006 — Latence** : le chemin de réponse standard DEVRAIT rester sous un p95 défini par produit ; la conception et les investigations peuvent être plus longues.
- **NFR-007 — Coût** : chaque tour DOIT exposer son coût et son usage ; les outils doivent avoir un budget.
- **NFR-008 — Extensibilité** : ajouter une source, un outil ou un type de Twin NE DOIT PAS exiger une réécriture du noyau.
- **NFR-009 — Résilience** : une source ou un outil en panne NE DOIT PAS produire une absence ni une conclusion.
- **NFR-010 — Évaluation** : les choix d'outils, les claims et les décisions DOIVENT être mesurés par un jeu d'or.
- **NFR-011 — Indépendance du graphe** : le domaine ne dépend d'aucun langage de graphe propriétaire (Cypher/Gremlin) ; seule l'interface `GraphStore` est exposée.
- **NFR-012 — Cohérence polyglotte** : toute référence croisée entre Postgres et le graphe est résolue par ID, idempotente et testée ; un objet orphelin est signalé, jamais inventé.

---

## 9. Métriques

### North Star

**Décisions et améliorations de l'entreprise fondées sur une connaissance traçable et réutilisable.**

### Métriques de valeur

- temps pour comprendre une situation ;
- taux de situations investiguées puis décidées ;
- taux de décisions reliées à un outcome ;
- réutilisation d'apprentissages dans une nouvelle situation ;
- couverture des sources et des Claims ;
- nombre de contradictions détectées et tranchées.

### Garde-fous

- taux d'affirmations sans preuve ;
- taux de fausses négations ;
- taux de fuites inter-tenant ;
- taux de sélection d'outil incorrecte ;
- fraîcheur des connaissances ;
- p95 de latence et coût par décision ;
- taux de propositions présentées comme des faits.

---

## 10. Périmètre

### Dans le périmètre

- modèle d'entreprise et cycle de connaissance ;
- découverte multi-sources ;
- Mesh transversal et contradictions ;
- émergence, investigation, décision, initiative, outcome, apprentissage ;
- Flore située et harness capacitaire ;
- projections par rôle ;
- gouvernance, sécurité, audit, évaluation.

### Hors périmètre initial

- remplacer les systèmes opérationnels ;
- écrire dans les sources sans décision humaine ;
- devenir un CMDB ou un catalogue d'applications ;
- exposer le Mesh complet à l'utilisateur ;
- auto-promouvoir une identité ou une connaissance ;
- multi-twins par application (non retenu) ;
- agents autonomes décisionnaires.

---

## 11. MVP et tranches

### Tranche 0 — Socle de vérité

Modèle d'objets, Claims, preuves, temporalité, modes, identité, audit, rôles, premier Twin applicatif.

### Tranche 1 — Mesh transversal

Relations, contradictions, domaines, capacités, processus, premières situations.

### Tranche 2 — Boucle d'exploitation

Investigation, décision, initiative, outcome, apprentissage.

### Tranche 3 — Harness capacitaire

Registre de capacités, manifests, MCP/OpenAPI, découverte filtrée, politique, exécuteur, télémétrie.

### Tranche 4 — Projections et échelle

Projections par rôle, multi-tenant, performance, évaluation, gouvernance à l'échelle.

---

## 12. Critères d'acceptation

- **AC-001** — Une question « architecture d'une application de dating » produit une proposition greenfield étiquetée, sans jumeau, sans Atlas et sans preuve inventée.
- **AC-002** — Une question sur une application existante produit une réponse avec Claims, preuves, fraîcheur et contradictions éventuelles.
- **AC-003** — Une question sur une situation transverse peut être reliée à plusieurs Twins et à un domaine.
- **AC-004** — Un Twin `PROCESS`, `CAPABILITY` ou `JOURNEY` peut être créé sans modifier le noyau.
- **AC-005** — Un outil read-only peut être ajouté par manifeste/MCP, filtré par politique et audité, sans changement de code du noyau.
- **AC-006** — Une décision peut être reliée à une initiative, un outcome et un apprentissage.
- **AC-007** — Une absence est formulée « non observé dans tel périmètre, à telle date », jamais « n'existe pas ».
- **AC-008** — Une proposition est toujours distinguée d'une observation dans l'API et l'UI.
- **AC-009** — Un parcours d'impact sur 5 000 applications est exécuté par le graph store, avec tenant et profondeur bornés.
- **AC-010** — Aucun objet canonique n'est copié dans un autre store ; un test d'architecture échoue si une projection est ajoutée sans ADR.
- **AC-011** — Le portefeuille de 5 000 applications est consultable par domaine, capacité, criticité et recherche sans charger tout le parc.

---

## 13. Risques et questions ouvertes

### Risques

- **Dérive applicative** : retomber sur un routeur d'applications. Mitigation : ADR-0003, tests d'architecture, jeu d'or.
- **Dérive « outil = architecture »** : confondre le harness avec le noyau. Mitigation : ADR-0004, capacités et objets explicites.
- **Surcharge du Mesh** : tout relier sans maturité. Mitigation : Claims, preuves, seuils, contradictions.
- **Faux sentiment de vérité** : agents trop confiants. Mitigation : modes, provenance, incertitude, abstention.
- **Complexité multi-tenant** : fuite ou cloisonnement insuffisant. Mitigation : tenant-scoped par défaut, tests d'isolation.

### Questions ouvertes

1. Quels types de Twin après `APPLICATION` : `PROCESS`, `CAPABILITY`, `JOURNEY` ?
2. Quel premier domaine métier pour le Mesh : architecture, opérations, risque, client ?
3. Quel standard pour la découverte d'outils : MCP, OpenAPI, manifeste interne, plusieurs ?
4. Comment mesurer la qualité d'une décision sans biais rétrospectif ?
5. Quelle politique de rétention pour les preuves et les observations ?
6. Quelle gouvernance pour les contradictions non tranchées ?

---

## 14. Traçabilité

| Décision | ADR |
|---|---|
| Mesh transversal, ni source ni outil | [ADR-0003](../adr/0003-mesh-transversal-intelligence.md) |
| Harness capacitaire, registre dynamique | [ADR-0004](../adr/0004-capability-first-harness.md) |
| Modèle d'entreprise et types de Twin | [ADR-0005](../adr/0005-enterprise-object-model.md) |
| Identité typée, Twin provisoire | [ADR-0001](../adr/0001-identite-typed-twin-discovery.md) |
| Orchestrateur général (amendé) | [ADR-0002](../adr/0002-orchestrateur-general.md) |
| Architecture polyglotte Postgres + graph | [ADR-0007](../adr/0007-polyglot-postgres-graph.md) |
| Postgres unique (rejeté) | [ADR-0006](../adr/0006-postgres-unique-sans-projection.md) |
| Travail comme store de travail | [ADR-0008](../adr/0008-travail-work-store.md) |
| Value Ledger | [ADR-0009](../adr/0009-value-ledger.md) |
| Mémoire, contexte et raisonnement | [PRD-002](PRD-002-memoire-contexte-raisonnement.md) |

---

## 15. Journal des versions

| Version | Date | Changement |
|---|---|---|
| 1.0 | 2026-10-30 | Base initiale : Enterprise Intelligence Mesh, modèle d'entreprise, capacités, harness, critères d'acceptation. |
| 1.1 | 2026-10-30 | Stockage polyglotte : Postgres pour la connaissance, graph store pour la topologie ; aucune projection. |
| 1.2 | 2026-10-30 | Ajout du volet mémoire, contexte et raisonnement (PRD-002) et index des fiches produit. |
