# MÉRIDIAN — Architecture du Jumeau Applicatif
## Architecture de référence du premier jumeau : Strands, AgentCore, espaces, couche cognitive et amélioration continue

**Statut :** Proposition d'architecture, à valider (ADR en §12)  
**Version :** 1.0  
**Date :** 2026-10-27  
**Produit :** MÉRIDIAN  
**Documents amendés :** Technical_Architecture v1, Domain_Model v1, Knowledge_Claims v1, Security_Governance_Trust_Model v1, Continuous_Improvement_Learning_Model v1, MVP_Definition v1  
**Tagline :** **DÉCOUVRIR · COMPRENDRE · DÉCIDER**

---

# 0. Objet du document

Ce document fixe l'architecture du **premier jumeau applicatif** de Méridian, dans les contraintes réelles du projet :

- environnement **AWS, région Canada (`ca-central-1`)** ;
- agents construits avec **Strands Agents** et opérés sur **Amazon Bedrock AgentCore** ;
- premières sources : **code (Git)** et **documentation (Confluence)** ;
- contexte **bancaire** : sécurité du code, souveraineté, gestion du risque de modèle ;
- le jumeau **appartient à une équipe** (celle qui développe et exploite l'application) et **chaque membre l'exploite à sa façon**.

Il répond à la question :

> **Quelle est l'architecture la plus simple, conforme aux standards, qui fait naître un jumeau prouvé, gouverné par son équipe et utilisable personnellement par chacun de ses membres ?**

Les écarts avec les documents existants sont signalés **[CORR]** et justifiés. Tout ce qui n'est pas corrigé reste valide.

---

# 1. Le jumeau applicatif : définition opérationnelle

Un jumeau applicatif est un **modèle vivant et prouvé d'une application**.

Il n'est ni une fiche CMDB, ni une page Confluence, ni un graphe de code, ni un chatbot RAG. Il répond à six questions, et **chaque réponse est un ensemble de Claims adossés à des preuves** :

| Question | Exemples | Sources principales |
|---|---|---|
| Qui est-elle ? | Nom, alias, mission, équipe propriétaire, criticité | Admission, Confluence |
| De quoi est-elle faite ? | Langages, frameworks, bases, déploiement | Code (manifestes, Dockerfile, IaC) |
| Avec qui parle-t-elle ? | APIs exposées et consommées, files, tables lues/écrites | Code (routes, clients, config) |
| Que fait-elle pour le métier ? | Capacités, règles métier | Confluence, code |
| Qu'est-ce qui est contesté ? | La doc dit X, le code fait Y | Réconciliation |
| Qu'est-ce qu'on ne sait pas ? | Consommateurs inconnus d'une API | Inconnues détectées |

Exemple de Claim :

```text
TBT ──CALLS──▶ Service-Clients
  preuve 1 : git://tbt@a3f9c1:src/main/resources/application.yml#L42-L44   (CODE)
  preuve 2 : confluence://TBT/123456?v=17#Architecture                       (DOCUMENT)
  statut ACCEPTED · maturité M4 · confiance 0.86 · valide depuis 2026-10-27
```

Trois propriétés le distinguent d'une documentation :

1. **Synchronisation** : un commit ou une nouvelle version de page ne réévalue que les Claims touchés.
2. **Incomplétude assumée** : le jumeau expose ses inconnues et ses contradictions.
3. **Gouvernance** : l'équipe propriétaire valide ; aucun agent ne valide.

---

# 2. Normes et standards de référence

| Domaine | Référence |
|---|---|
| Cadre cloud | AWS Well-Architected Framework + Generative AI Lens ; multi-comptes (Control Tower : dev / test / prod) ; IaC CDK |
| Réglementation | BSIF **B-13** (risque technologique et cyber), **B-10** (risque lié aux tiers : AWS, Anthropic), **E-23** (gestion du risque de modèle, incluant l'IA) ; Loi 25 si données personnelles |
| IA responsable | NIST AI RMF, ISO/IEC 42001, OWASP Top 10 for LLM Applications et Agentic AI |
| Protocoles | **MCP** (outils), **A2A** (agent ↔ agent), **AG-UI** ou SSE (agent ↔ UI), OIDC / OAuth 2.0 |
| Autorisation | **Cedar** : Amazon Verified Permissions (application), AgentCore Policy (outils des agents) |
| Provenance | **W3C PROV** (Entity / Activity / Agent) |
| Observabilité | OpenTelemetry (conventions sémantiques GenAI) → CloudWatch |

---

# 3. Vue d'ensemble

```text
┌──────────────────────────── UI (React + TypeScript, CloudFront/S3) ─────────────────────┐
│  Atlas · Fiche Jumeau · File de revue · Espace Équipe · Espace Personnel · Flore (AG-UI) │
└───────────────┬──────────────────────────────────────────────────────────────┬──────────┘
                │ OIDC (IdP banque → Cognito)                                  │ stream
┌───────────────▼──────────── API / BFF (FastAPI, ECS Fargate) ────────────────▼──────────┐
│  Espaces · Claims · Revue · Admission    ──►  Amazon Verified Permissions (Cedar)        │
└───────┬───────────────────────────────┬──────────────────────────────────────────────────┘
        │                               │ invoke (identité utilisateur, on-behalf-of)
        │               ┌───────────────▼─────────── AgentCore Runtime ───────────────────┐
        │               │  Flore (Strands, orchestratrice)                                │
        │               │    └─ Agents-as-Tools : Expert Code · Expert Doc · Contradicteur│
        │               │  AgentCore Memory : court terme (session), long terme (membre)  │
        │               └───────────────┬─────────────────────────────────────────────────┘
        │                               │ MCP
        │               ┌───────────────▼── AgentCore Gateway + Policy + Identity ────────┐
        │               │  claims.read · claims.propose · evidence.fetch · code.* (cbm)   │
        │               │  confluence.read      ✗ claims.validate (humain uniquement)     │
        │               └──────┬──────────────────────┬──────────────────┬────────────────┘
┌───────▼──── Couche cognitive ─▼─────┐   ┌───────────▼─────────┐  ┌────▼──────────────────┐
│ Aurora PostgreSQL (ca-central-1)    │   │ codebase-memory-mcp  │  │ Confluence            │
│ Observations · Preuves (PROV) ·     │   │ (ECS privé, index    │  │ (lecture seule)       │
│ Claims bitemporels · Relations ·    │   │  reconstructible)    │  └────▲──────────────────┘
│ Inconnues · Contradictions ·        │   └───────────▲─────────┘       │
│ Espaces · Calibration · Learnings   │               │                 │
│ pgvector                            │   ┌───────────┴─────────────────┴─────────────────┐
│ S3 + Object Lock : instantanés      │◄──┤ Ingestion : EventBridge → Step Functions      │
└─────────────────────────────────────┘   │ instantané → cbm → adaptateur → extraction LLM│
                                          │ → vérification → réconciliation → confiance   │
                                          └───────────────────────────────────────────────┘
 Transverse : Bedrock (profil d'inférence) · KMS · VPC privé + PrivateLink · CloudTrail · OTel
 Qualité    : AgentCore Evaluations à chaque changement de prompt ou de modèle
```

Principe directeur : **déterministe partout où c'est possible, agentique seulement où il faut du jugement**.

---

# 4. Couches et composants

## 4.1 Interface utilisateur

- React + **TypeScript** (cible de Technical_Architecture §97). Le code actuel est en JavaScript : migration progressive, fichier par fichier.
- Composants repris de l'existant : Atlas (`@xyflow/react`, libavoid), atelier de création (`Commande.jsx`) qui devient l'**admission**, format de réponse de Flore (preuves, indicateurs, action).
- Nouveaux écrans : Fiche Jumeau prouvée, File de revue, Espace Personnel.
- Streaming agent → UI via **AG-UI** (ou SSE, Technical_Architecture §6).
- Toute affirmation affichée ouvre sa preuve (ligne de code, paragraphe Confluence).

## 4.2 API / BFF

- **FastAPI** (existant), déployé sur ECS Fargate.
- Authentification OIDC : IdP de la banque fédéré dans Cognito.
- Chaque requête est autorisée par **Amazon Verified Permissions** (Cedar) avant tout accès aux données.
- `[CORR]` Les en-têtes `X-Persona` / `X-Espace` de la démo sont remplacés par l'identité du jeton.

## 4.3 Agents (Strands sur AgentCore Runtime)

| Agent | Rôle | Autonomie (Agentic §69) |
|---|---|---|
| **Flore** | Orchestratrice conversationnelle : intention → contexte → plan → preuves → réponse | L3 maximum (MVP) |
| **Expert Code** | Interprète le graphe de code (mission, capacités, règles métier) | L2 |
| **Expert Doc** | Extrait les Claims de Confluence | L2 |
| **Contradicteur** | Cherche les contre-preuves et les écarts doc ↔ code | L1 |

- Patron **Agents-as-Tools** (MVP §41). Swarm reporté.
- **Un seul déploiement, paramétré par `twin_id`** : pas un déploiement par jumeau.
- Le code Strands est identique en local et sur AgentCore (enveloppe `BedrockAgentCoreApp`).
- Les agents **proposent** ; ils ne valident jamais.

## 4.4 Services AgentCore

| Service | Usage | Ce qu'il ne fait pas |
|---|---|---|
| **Runtime** | Héberge Flore et les experts, sessions isolées | — |
| **Gateway** | Expose les outils en MCP (Claims API, preuves, codebase-memory-mcp, Confluence) | — |
| **Identity** | Agit **au nom de l'utilisateur** ; garde les secrets des connecteurs | — |
| **Policy** (Cedar) | Interdit `claims.validate` aux agents, limite les outils par rôle | — |
| **Memory** | Mémoire de session ; mémoire longue **par membre** | Ne stocke **jamais** le savoir du jumeau (Technical_Architecture l. 496) |
| **Observability** | Traces OTel de chaque appel modèle et outil | — |
| **Evaluations** | Évaluation hors ligne (jeu de référence) et en ligne (ancrage des réponses) | — |

## 4.5 Ingestion

`[CORR]` L'ingestion est un **pipeline déterministe orchestré par Step Functions**, pas un essaim d'agents.

```text
Événement (push Git, page Confluence modifiée, déclenchement manuel)
  → EventBridge
  → Step Functions :
      1. Instantané         SHA du commit / version de page ; copie immuable S3 si politique l'autorise
      2. Index code         codebase-memory-mcp (sans LLM) : routes, appels inter-services, tables,
                            variables d'environnement, Dockerfile/K8s/Helm, dépendances
      3. Adaptateur         nœuds et arêtes → Observations + Preuves (fichier#lignes @SHA)
      4. Filtre de secrets  exclusions (.env, clés, certificats) + motifs type gitleaks
      5. Extraction LLM     Expert Code (interprétation), Expert Doc (Confluence) → Claims candidats
      6. Vérification       la citation doit exister aux lignes indiquées, sinon rejet
      7. Réconciliation     rapprochement des noms (alias d'admission) ; CORROBORÉ / CONTRADICTION /
                            DOC SEULE / CODE SEUL
      8. Confiance          règles + calibration (§8)
      9. Publication        TwinUpdated → UI, file de revue
```

- Incrémental : seuls les fichiers modifiés (cache par hash) et les pages dont la version a changé.
- `compare_graphs` de codebase-memory-mcp alimente l'historique d'évolution du jumeau.
- `ingest_traces` de codebase-memory-mcp prépare la future source runtime (P1).

## 4.6 Couche cognitive (stockage)

| Store | Rôle | Statut |
|---|---|---|
| **Aurora PostgreSQL** (ca-central-1) | Système de référence : jumeaux, sources, observations, preuves, Claims, relations, inconnues, contradictions, espaces, calibration, learnings ; pgvector | MVP |
| **S3 + Object Lock + KMS** | Instantanés et preuves immuables | MVP |
| **codebase-memory-mcp** (SQLite) | Index de code **dérivé et reconstructible** | MVP |
| Neptune | Graphe du Mesh multi-jumeaux | `[CORR]` Reporté (P3) |
| OpenSearch | Recherche à grande échelle | `[CORR]` Reporté (P3) |

`[CORR]` Le graphe local d'un jumeau (quelques centaines à quelques milliers de nœuds) tient dans Postgres avec des requêtes récursives. Neptune et OpenSearch arrivent avec le Mesh.

---

# 5. Modèle de données du MVP

```text
tenant ─┬─ domain ─┬─ team ─┬─ membership (user, role)
        │          │        └─ twin ─┬─ source (type, locator, cursor, owner)
        │          │                 ├─ observation (source, snapshot, raw_ref)
        │          │                 ├─ evidence   (PROV : entity, activity, agent ; locator, hash, access_policy)
        │          │                 ├─ claim      (subject, predicate, object, type, status, maturity,
        │          │                 │              confidence, valid_from/to, recorded_at, supersedes)
        │          │                 ├─ claim_evidence (claim, evidence, role : support | contre)
        │          │                 ├─ relation   (vue matérialisée des Claims de relation)
        │          │                 ├─ unknown    (question, priorité, source qui y répondrait)
        │          │                 ├─ contradiction (claims en conflit, état)
        │          │                 └─ review     (claim, acteur, décision, motif, horodatage)
        │          └─ workspace (owner : team | user, twin, kind)
        │                └─ workspace_item (fil, note, hypothèse, brouillon de Claim, épingle)
        ├─ calibration (claim_type, extractor, source_type, accepted, rejected, prior)
        └─ learning (portée, conditions, exceptions, confiance, preuves)    [P2]
```

Invariants (testés en SQL, sur le modèle de `laboratoire-autonome`) :

1. Aucun objet sans `tenant_id`.
2. Aucun Claim `ACCEPTED` sans au moins une preuve et une `review` humaine.
3. Une preuve est immuable ; une correction crée une nouvelle preuve.
4. Une relation n'est jamais écrite directement : elle est recalculée à partir des Claims.
5. Un `workspace_item` personnel n'est lisible que par son propriétaire.

---

# 6. Gestion des espaces

`[CORR]` Les documents existants ne spécifient ni l'équipe propriétaire avec ses membres, ni l'espace personnel. Cette section les définit.

## 6.1 Hiérarchie et rôles

```text
Tenant (banque) ─► Domaine ─► Équipe ──possède──► Jumeau(x)
                                 └─ Membres (un rôle par équipe)
```

| Rôle | Droits |
|---|---|
| `APPLICATION_OWNER` | Admission du jumeau, validation finale, gestion des accès et des sources |
| `MAINTAINER` | Valide et invalide les Claims de son périmètre |
| `MEMBER` | Propose, conteste, commente |
| `VIEWER` | Lecture |

Les autres équipes accèdent au jumeau par **niveaux de projection** : `existence`, `resume`, `relations`, `preuves`, `complet`. On reprend `NIVEAUX` (`backend/server.py:90-148`), traduit en politiques Cedar.

`[CORR]` `APPLICATION_OWNER` est ajouté aux rôles MVP (Security §224).

## 6.2 Les trois espaces

| Espace | Propriétaire | Contenu | Écriture |
|---|---|---|---|
| **Jumeau** | Équipe | Claims, preuves, relations, inconnues, contradictions | Pipeline (propositions), humains habilités (validation) |
| **Équipe** | Équipe | Investigations partagées, file de revue, décisions en préparation | Membres |
| **Personnel** | Un membre × un jumeau | Fils Flore, notes, hypothèses, brouillons de Claims, épingles, vue selon le rôle, mémoire longue AgentCore | Le membre seul |

## 6.3 Règles

1. Le contenu personnel n'est lisible ni par un autre membre, ni par l'agent d'un autre membre (`actorId` AgentCore = utilisateur).
2. Personnel → Équipe : **promotion explicite**, qui crée un Claim `PROPOSED` avec une preuve `HUMAN` portant l'auteur.
3. Équipe → Jumeau : **validation** par un `MAINTAINER` ou l'`APPLICATION_OWNER`, tracée (qui, quand, sur quelles preuves).
4. Chaque membre voit le même jumeau, à travers sa vue de rôle (développeur, PO, exploitation).

---

# 7. Le volet cognitif

La chaîne de Knowledge_Claims §3 est conservée :

```text
Donnée brute → Observation → Preuve → Claim → Relation → Expression
```

## 7.1 Corrections

| # | Problème | Correction |
|---|---|---|
| 1 | Trois échelles de maturité concurrentes (Domain_Model §32, Knowledge_Claims §25, strates d'ATLAS.md) | **Échelle unique M0–M5** (Knowledge_Claims §25), calculée à partir des preuves. La maturité d'un jumeau reste un **vecteur** (Domain_Model §85). Les strates d'ATLAS.md deviennent des vues d'interface. |
| 2 | Statut et maturité se recouvrent (SUPPORTED ≈ M2) | **Deux axes indépendants.** Statut = gouvernance : `PROPOSED`, `ACCEPTED`, `CONTESTED`, `INVALIDATED`, `SUPERSEDED`. Maturité = force des preuves : M0–M5. |
| 3 | « Admission » absente de l'architecture | `TwinBorn` devient une étape de contrôle : identité, sources et périmètre approuvés par l'`APPLICATION_OWNER`. |
| 4 | Calcul de confiance non spécifié | `confiance = f(type de preuve, indépendance, fraîcheur, validation humaine)` × calibration (§8). La certitude du LLM n'est qu'une entrée. |
| 5 | Relations parfois éditées directement | Une relation est **toujours** une projection des Claims. |
| 6 | « Aurora » désigne le copilote et la base | Le copilote s'appelle **Flore** partout. |
| 7 | Swarm, Discovery Engine (signaux, situations) dans le périmètre initial | Reportés en P1/P2 ; le MVP utilise Agents-as-Tools + Contradicteur. |

## 7.2 Règles de maturité (MVP)

| Niveau | Condition |
|---|---|
| M0 RAW | Observation brute, non interprétée |
| M1 EXTRACTED | Claim extrait, citation vérifiée |
| M2 EVIDENCED | Au moins une preuve exploitable |
| M3 CORRELATED | Deux sources **indépendantes** concordantes (ex. code + Confluence) |
| M4 CROSS_VALIDATED | M3 + validation humaine ou troisième source |
| M5 MATURE | M4 + stable sur une durée définie, sans contradiction ouverte |

Une page Confluence recopiée d'un ticket Jira ne compte pas comme source indépendante (Knowledge_Claims §11–15).

---

# 8. L'amélioration cognitive

`[CORR]` Le Continuous_Improvement_Learning_Model décrit une boucle **Décision → Initiative → Résultat → Apprentissage**. Elle demande des mois de recul et des décisions déjà prises : elle ne peut pas nourrir un premier jumeau. On ajoute une **boucle courte, active dès le premier jour**.

## 8.1 Boucle A — Qualité de la connaissance (MVP)

1. **Chaque geste humain est une donnée étiquetée** : valider, contester, corriger, juger une réponse de Flore utile ou non.
2. **Preuve** : le geste devient une preuve `HUMAN` sur le Claim.
3. **Calibration** : précision observée par (type de Claim × extracteur × type de source), avec un a priori Beta-binomial :

   ```text
   prior(type, extracteur, source) = (acceptés + α) / (acceptés + rejetés + α + β)
   ```

   Si 40 % des Claims `DATA_FLOW` issus de Confluence sont contestés, leur confiance de départ baisse automatiquement.
4. **Jeu de référence** : les Claims validés ou corrigés alimentent un jeu de test. Les prompts sont versionnés dans Git ; tout changement de prompt ou de modèle passe par **AgentCore Evaluations** avant production (exigence E-23).
5. **Inconnues prioritaires** : les questions posées à Flore sans réponse deviennent des `unknown` qui orientent les prochaines ingestions.
6. **Pas de fine-tuning** : on améliore prompts, règles et calibration. Tout est versionné et réversible.

## 8.2 Boucle B — Apprentissage des décisions (P2)

Conception d'origine conservée : Décision → Initiative → Observation Plan → Outcome → Attribution → Learning.

- Les Learnings vont dans le Learning Store (Postgres), avec portée, conditions, exceptions et generalization gate.
- **Un Learning reste un a priori, jamais une preuve du cas courant** (§72).
- Aucune promotion automatique.

## 8.3 Mémoire personnelle

Les stratégies de mémoire longue d'AgentCore (préférences, faits sémantiques, résumés) servent **au membre seul**. Elles n'alimentent jamais le jumeau sans promotion explicite (§6.3).

---

# 9. Sécurité

- **Connecteurs en lecture seule**, jetons dans AgentCore Identity / Secrets Manager.
- **Autorisation avant récupération** : Cedar filtre preuves et Claims avant qu'ils n'atteignent le modèle.
- **Filtre de secrets** avant chaque appel modèle.
- **Pas de copie du code dans le jumeau** : pointeurs + hash ; extrait affiché à la demande si l'utilisateur a les droits sur la source.
- **Contenu Confluence = donnée, jamais instruction** (défense contre l'injection de prompt).
- **Journal d'audit** de chaque appel modèle : fichiers et pages envoyés, SHA, version de prompt, modèle.
- **Réseau** : VPC privé, points de terminaison PrivateLink (Bedrock, AgentCore, S3), proxy de sortie journalisé.
- **codebase-memory-mcp** : compilé depuis les sources à une version épinglée, installé avec `--skip-config`, `auto_index` et watcher désactivés, artefact `graph.db.zst` non produit, absence de sortie réseau vérifiée par le proxy.

---

# 10. Souveraineté

| Élément | Localisation |
|---|---|
| Aurora, S3, index codebase-memory-mcp, AgentCore Memory (stockage) | `ca-central-1` |
| Inférence Claude (modèles récents) | Profils `us.*` ou `global.*` uniquement depuis `ca-central-1` (constaté le 2026-10-27 sur le compte de développement) |
| AgentCore Policy, et en partie Memory | Inférence routée hors Canada (documentation AWS) |
| Modèles exécutés en région | Claude 3 Sonnet, Claude 3 Haiku (anciens) |

Conséquences :

1. **Décision formelle de conformité requise** (B-10) avant d'envoyer du code ou des pages Confluence au modèle.
2. **Minimisation** : codebase-memory-mcp extrait sans LLM ; le modèle reçoit des métadonnées et des extraits autorisés.
3. Disponibilité de chaque service AgentCore en `ca-central-1` à confirmer sur les pages AWS officielles.

---

# 11. Trajectoire

| Phase | Accès requis | Contenu | Critère de sortie |
|---|---|---|---|
| **0** | Rôle Bedrock | Strands en local ; Postgres et codebase-memory-mcp en Docker ; FastAPI existant. Tranche « One Source → One Claim » : un dépôt → Claims prouvés dans l'UI | Un Claim cliquable jusqu'à sa ligne de code |
| **1** | AgentCore Runtime, Gateway, Identity, Memory ; Aurora ; S3 | Même code Strands déployé ; espaces et Cedar ; Confluence ; réconciliation ; Boucle A | VS1 (MVP §8) sur 2 sources : identité stable, Claims prouvés code + doc, dépendances, inconnues, validation par l'équipe |
| **2** | Evaluations, Policy, Step Functions | Jeu de référence et évaluations ; politiques d'outils ; ingestion événementielle | Aucun changement de prompt en production sans évaluation |
| **3** | Neptune, OpenSearch si besoin | Mesh multi-jumeaux, Discovery Engine, Boucle B, source runtime (traces) | Second jumeau d'une autre équipe relié au premier |

Réutilisation : moteur de droits, états de relation et confirmation humaine, format de réponse Flore, Atlas, atelier de création (dépôt `meridian-mesh`) ; worker durable, invariants SQL, passerelle LiteLLM et proxy de sortie (dépôt `laboratoire-autonome`) ; codebase-memory-mcp.

---

# 12. Décisions d'architecture (ADR)

| ADR | Décision | Alternative écartée | Raison |
|---|---|---|---|
| ADR-J01 | Aurora PostgreSQL comme système de référence | Neptune dès le MVP | Le graphe d'un jumeau tient dans Postgres ; un seul store à sécuriser et auditer |
| ADR-J02 | Ingestion en Step Functions | Agents d'ingestion | Pipeline déterministe, rejouable, auditable ; agents réservés au jugement |
| ADR-J03 | Cedar (Verified Permissions + AgentCore Policy) | OpenFGA | Standard AWS natif, même langage côté application et côté agents |
| ADR-J04 | Statut et maturité comme deux axes | Échelle unique mêlée | Supprime l'ambiguïté entre documents |
| ADR-J05 | Profil d'inférence soumis à décision de conformité, minimisation des données | Envoi du code brut au modèle | Souveraineté (B-10) |
| ADR-J06 | codebase-memory-mcp comme index de code reconstructible | Indexation par LLM (type graphify) | Local, sans LLM, rapide, incrémental |
| ADR-J07 | Mémoire personnelle cloisonnée, promotion explicite | Mémoire partagée par défaut | Usage personnel sans pollution du jumeau |
| ADR-J08 | Agents-as-Tools, autonomie ≤ L3 | Swarm | Traçabilité, contrôle humain (Security §225) |
| ADR-J09 | Boucle A (calibration) dès le MVP, Boucle B en P2 | Boucle décisionnelle seule | Amélioration mesurable dès le premier jumeau |

---

# 13. Questions ouvertes

1. Accord de conformité sur les profils `us.*` / `global.*`, ou démarrage limité au déterministe ?
2. Confluence Cloud ou Data Center ? Hébergeur Git ?
3. Application cible du premier jumeau (TBT ?) et accès à son dépôt et à son espace Confluence.
4. Disponibilité confirmée de chaque service AgentCore en `ca-central-1`.
5. IdP de la banque et modèle de groupes (pour alimenter équipes et rôles).
