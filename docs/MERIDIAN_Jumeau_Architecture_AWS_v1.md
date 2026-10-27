# MÉRIDIAN — Architecture AWS du jumeau agentique
## EventBridge, Step Functions, AgentCore Runtime : de la commande d'un jumeau à sa veille continue

**Statut :** Proposition d'architecture de départ, à valider (sécurité, conformité, plateforme) ; variante sans AgentCore en §10  
**Version :** 1.0  
**Date :** 2026-10-27  
**Produit :** MÉRIDIAN  
**Documents liés :** Architecture Jumeau v1, Jumeau Harness Agentique v1, Technical Architecture v1  
**Tagline :** **DÉCOUVRIR · COMPRENDRE · DÉCIDER**

---

# 0. Objet du document

La phase 0 fonctionne sur un poste : ingestion, Flore dans les Travaux, gardien qui veille. Ce document répond à
trois questions avant le passage sur AWS (`ca-central-1`) :

1. Quelle architecture AWS de départ pour nos mécanismes : événements, orchestration, agents ?
2. Dans la commande d'un jumeau, avec un connecteur GitHub : où se fait l'indexation, où est-elle stockée ?
3. Utilisons-nous vraiment codebase-memory-mcp, et ses actions MCP ?

---

# 1. Constats sur l'existant

## 1.1 La commande d'un jumeau est une coquille

L'atelier de commande (`frontend/src/pages/Commande.jsx`, routes `/commandes` de `backend/server.py`) propose bien un
connecteur GitHub (organisation, dépôts, branches, référence de jeton `coffre/gh-token`). Mais :

- le test de connexion est simulé (`_simuler_test`) ;
- l'aperçu d'import renvoie une liste écrite en dur ;
- « Lancer » insère une fiche dans le registre Mongo, **sans appeler l'ingestion réelle**
  (`python -m jumeau.ingerer`).

Il existe donc deux chemins disjoints : l'interface (factice) et la ligne de commande (réelle). Sur AWS, ils doivent
devenir un seul chemin : **la commande déclenche la naissance du jumeau.**

## 1.2 Où vit l'état aujourd'hui

| État | Aujourd'hui (poste) | Problème sur AWS |
|---|---|---|
| Copie du code au SHA | worktree `~/.local/share/meridian/copies/<jumeau>` | calcul éphémère, pas de disque partagé |
| Index de code | SQLite de codebase-memory-mcp dans `~/.cache/codebase-memory-mcp/`, projet nommé d'après le chemin absolu | lié à une machine et à un chemin |
| Claims, preuves, revues, fiches | PostgreSQL (Docker) | → Aurora PostgreSQL |
| Historique Git (le temps) | `git log` lu à la demande dans la copie | suppose une copie Git à chaque question |
| Fils de Flore | fichiers (`FileSessionManager`) | → AgentCore Memory ou S3 |
| Verrou « un flux par fil » | mémoire d'un processus | → verrou partagé |
| Registre, Travaux, situations | MongoDB | → Amazon DocumentDB (compatible), sans réécrire l'application |

## 1.3 Nous n'utilisons pas vraiment codebase-memory-mcp

Nous l'appelons **en ligne de commande** (`cbm.py`), jamais par le protocole MCP, et nous n'utilisons qu'une partie
de ses capacités.

| Action | Usage aujourd'hui | Ce qu'elle apporterait |
|---|---|---|
| `index_repository` | ✅ ingestion | — |
| `query_graph` | ✅ 4 requêtes : routes, paquets, variables, images | bien plus de familles de Claims (ci-dessous) |
| `search_code`, `search_graph`, `trace_path`, `get_architecture` | ✅ outils de Flore | — |
| `compare_graphs` | ❌ | diff du graphe entre deux commits, au niveau des symboles : signaux du gardien bien plus fins que nos 4 familles |
| `detect_changes` | ❌ | rayon d'impact d'un changement avec classement du risque |
| Liens inter-services (`HTTP_CALLS`, `ASYNC_CALLS`, `EMITS` / `LISTENS_ON`) et liens entre dépôts (`CROSS_*`) | ❌ | **les relations entre jumeaux, c'est-à-dire le Mesh**, découvertes depuis le code |
| `Table`, `WRITES`, `DATA_FLOWS` | ❌ | Claims de données : quelles tables l'application écrit, par où passent les données |
| `ingest_traces` | ❌ | valider les appels inter-services par des traces d'exécution : maturité M3 (code + runtime) |
| `check_index_coverage` | ❌ | les **inconnues** : ce que l'index ne couvre pas |
| `get_code_snippet` | ❌ | extraits par symbole plutôt que par lignes |
| `manage_adr` | ❌ | décisions d'architecture de l'équipe, mémoire durable |
| Artefact `graph.db.zst` (`persistence: true`) | ❌ | **index portable** : produit une fois, rechargé n'importe où sans réindexer |

Conclusion : l'outil est bon et rapide, mais nous l'utilisons comme un `grep` amélioré. Le plus précieux
(relations inter-services, diff de graphe, artefact portable) reste à brancher.

---

# 2. Principes de l'architecture

1. **Déterministe dans Step Functions, jugement dans AgentCore.** Ingestion, comparaison, signaux, publication sont
   des étapes rejouables et auditables ; seuls la rédaction et le dialogue passent par un agent.
2. **Le jumeau est un espace de travail stocké, pas une machine.** Chaque version du jumeau est un ensemble
   d'artefacts immuables dans S3 (index, instantané du code) et de lignes dans Aurora (Claims, preuves, historique).
   N'importe quel calcul éphémère peut le recharger.
3. **Événements sortants seulement depuis le SI de la banque.** Le dépôt publie ses événements vers AWS ; aucun
   point d'entrée public n'est nécessaire.
4. **Tout dans `ca-central-1`**, à l'exception de l'inférence tant que la décision de conformité n'est pas prise.

---

# 3. Vue d'ensemble

```text
 GitHub (Enterprise)                                   Utilisateurs (IdP banque → Cognito)
   │ push (GitHub Actions, rôle OIDC : put-events)            │
   ▼                                                          ▼
 EventBridge (bus « meridian »)                     CloudFront → API FastAPI (ECS Fargate)
   │ jumeau.commit.pousse            ◄── Scheduler      │  Travaux, Registre, Commande, Revue
   │ (nuit : passe de réconciliation)                   │  « Lancer » ─► StartExecution(Naissance)
   ▼                                                    │  message ─► AgentCore Runtime (Flore)
 Step Functions « Veille du jumeau »    Step Functions « Naissance du jumeau »
   │ 1 Ingestion  (ECS RunTask .sync) ◄────── même tâche ──────┤
   │ 2 Signaux    (Lambda, déterministe)                        │ + test réel des sources
   │ 3 Publier    (Lambda → situations, EventBridge)            │ + admission humaine (waitForTaskToken)
   │ 4 Fiche      (AgentCore Runtime « gardien »)               │
   │    Retry/Catch : la panne du modèle ne perd rien           │
   ▼                                                            ▼
 ┌──────────────────────────── Espace du jumeau ───────────────────────────────┐
 │ S3 (Object Lock, KMS) : {tenant}/{jumeau}/{sha}/graph.db.zst, source.tar.zst │
 │ Aurora PostgreSQL : Claims, preuves, revues, fiches, commits, signaux        │
 │ DocumentDB : registre, Travaux, situations (application existante)           │
 └──────────────────────────────────────────────────────────────────────────────┘
        ▲                                   ▲
 AgentCore Gateway (MCP, Policy Cedar, Identity) ── outils de Flore et du gardien
   ├─ cible « code-jumeau » : serveur MCP sur AgentCore Runtime (codebase-memory-mcp
   │   chargé depuis l'artefact S3 du jumeau et du SHA)
   ├─ cible « connaissances » : Lambda sur Aurora (Claims, temps, propositions)
   └─ cible « travail » : Lambda d'écriture dans le Travail (plan, hypothèses, options, livrables)
 AgentCore Runtime : « flore » (conversation, Travaux) · « gardien » (fiche, récit)
 AgentCore Memory (fil de chaque membre) · Bedrock (modèle) · Observability · Evaluations
```

---

# 4. Événements : EventBridge

| Événement | Source | Déclenche |
|---|---|---|
| `jumeau.commit.pousse` {tenant, jumeau, depot, branche, sha} | **GitHub Actions** du dépôt : une étape `aws events put-events` avec un rôle IAM assumé par OIDC | Veille du jumeau |
| `jumeau.commande.lancee` | API (bouton « Lancer » de la commande) | Naissance du jumeau |
| `jumeau.reconciliation` | EventBridge **Scheduler** (chaque nuit) | Veille, pour rattraper un événement perdu |
| `jumeau.signal.publie` {jumeau, sha, signaux} | Step Functions (étape Publier) | Plus tard : Flore ouvre un Travail de compréhension |
| `jumeau.ne` | Step Functions (fin de naissance) | Projection au registre, notification de l'équipe |

**Pourquoi GitHub Actions plutôt qu'un webhook.** Un webhook exige un point d'entrée public avec vérification de
signature (API Gateway + Lambda). L'étape dans le pipeline du dépôt **sort** du SI vers AWS avec une identité
fédérée et éphémère : rien n'est exposé. Le webhook reste possible (API Gateway, vérification HMAC, Lambda vers
EventBridge) pour les dépôts qu'on ne peut pas modifier.

La passe nocturne remplace la boucle de surveillance de la phase 0 : elle rattrape un événement perdu, sans
interroger les dépôts en continu.

---

# 5. Orchestration : Step Functions

## 5.1 Veille du jumeau (sur commit)

Même découpage que `jumeau/gardien.py` : **le déterministe d'abord, le modèle ensuite.**

| Étape | Service | Rôle | Si échec |
|---|---|---|---|
| 1. Ingestion | ECS **RunTask .sync** (Fargate) | clone partiel au SHA, index codebase-memory-mcp, Claims vérifiés, artefacts S3, historique des commits dans Aurora | Retry ; l'exécution est rejouable |
| 2. Signaux | Lambda | comparaison des Claims avant et après (Aurora) ; plus tard `compare_graphs` sur les deux artefacts | — |
| 3. Publier | Lambda | situation « changement » (DocumentDB), événement `jumeau.signal.publie`, projection au registre | Retry |
| 4. Fiche | **AgentCore Runtime** (agent « gardien ») | fiche vivante et récit, citations vérifiées | Catch : la fiche sera refaite par la passe suivante |

- **Idempotence** : le nom d'exécution est `{jumeau}-{sha}`. Un même commit n'est jamais traité deux fois.
- **Pourquoi Fargate et pas Lambda pour l'ingestion** : clone et indexation d'un gros dépôt dépassent les limites
  de Lambda (durée, disque) ; Fargate n'a pas ces plafonds et garde la même image que le poste.

## 5.2 Naissance du jumeau (sur commande)

Branche enfin l'atelier de commande sur le vrai pipeline :

```text
Valider la commande → Tester les sources (réel) → Ingestion (même tâche que 5.1) →
Admission humaine (waitForTaskToken : le propriétaire valide identité et périmètre dans l'interface) →
Fiche vivante (gardien) → Publier (registre, jumeau.ne)
```

**Test réel de la source GitHub** : obtenir un jeton d'installation d'une **GitHub App** (lecture seule, périmètre
limité aux dépôts déclarés, durée courte) et vérifier l'accès à la branche (`git ls-remote`). Le champ
« Jeton (référence) » de la commande devient une référence Secrets Manager ou un fournisseur d'identifiants
AgentCore Identity, jamais le jeton lui-même.

---

# 6. L'indexation : où, quand, stockée où

## 6.1 Où elle se fait

Dans la **tâche d'ingestion Fargate**, et nulle part ailleurs :

1. Jeton GitHub App (Secrets Manager), clone partiel au SHA (`--filter=blob:none` : tout l'historique, sans les
   contenus inutiles).
2. Filtrage : liens symboliques retirés, filtre de secrets appliqué avant toute sortie.
3. `codebase-memory-mcp index_repository` avec `persistence: true` : l'index produit l'artefact `graph.db.zst`.
4. Adaptateur Méridian : Claims vérifiés, preuves (locator + hash), écrits dans Aurora.
5. Historique : les commits (SHA, date, auteur, message, fichiers) entre la version précédente et la nouvelle,
   écrits dans Aurora. Le jumeau n'a plus besoin de Git pour répondre « qu'est-ce qui a changé ? ».
6. Instantané du code suivi au SHA (`source.tar.zst`) et artefact d'index déposés dans S3.

## 6.2 Où elle est stockée

| Quoi | Où | Pourquoi |
|---|---|---|
| Index de code (`graph.db.zst`) | S3 `{tenant}/{jumeau}/{sha}/` | portable : rechargé par n'importe quel calcul sans réindexer |
| Instantané du code au SHA | S3, même préfixe, **Object Lock** (mode conformité), KMS | les preuves restent vérifiables même si le dépôt est réécrit |
| Manifeste (hash des artefacts, version de l'outil) | S3, même préfixe | audit, reproductibilité |
| Claims, preuves, revues, fiches, commits, signaux | Aurora PostgreSQL | système de référence, requêtes, invariants SQL |
| Situations, registre, Travaux | DocumentDB | application existante |

Le jumeau est donc un **ensemble d'artefacts immuables par commit** plus des lignes en base, et non une copie de
travail sur une machine.

## 6.3 Comment Flore s'en sert à la question

Un serveur MCP **« code-jumeau »** est hébergé sur AgentCore Runtime (conteneur HTTP sur le port 8000, chemin `/mcp`,
le contrat attendu par Runtime). Au début d'une session, il télécharge l'artefact et l'instantané du jumeau et du SHA
demandés (stockage de session, mis en cache) puis répond.

C'est une **enveloppe mince** autour de codebase-memory-mcp, qui expose une liste blanche d'actions, valide les
arguments (aucune option injectée) et fixe le projet au jumeau autorisé. Elle est publiée derrière AgentCore Gateway
avec ses politiques Cedar.

Alternative plus simple pour démarrer : embarquer codebase-memory-mcp dans l'image de Flore. Moins de sauts réseau,
mais l'outil n'est pas réutilisable par d'autres agents et échappe à la Gateway. Je recommande la Gateway dès que
d'autres agents (experts) doivent lire le code.

---

# 7. Les agents : AgentCore

| Agent | Déclenché par | Outils (via Gateway) | État |
|---|---|---|---|
| **Flore** (Strands) | message d'un membre dans un Travail ou dans le panneau Flore | code-jumeau, connaissances, temps, travail, méthodes | fil du Travail ou du membre (AgentCore Memory) ; état du Travail (DocumentDB) |
| **Gardien** (Strands) | étape 4 de la veille | code-jumeau, connaissances, temps | aucun fil : une rédaction par commit |
| **Contradicteur** | Flore et le gardien, avant envoi | aucun outil | aucun |

- **Policy (Cedar)** : Flore peut proposer des Claims et écrire dans un Travail, jamais valider ni décider ; le
  gardien ne peut pas écrire dans un Travail ; chaque appel d'outil est journalisé.
- **Identity** : Flore agit au nom du membre ; la Gateway ne renvoie que les jumeaux et preuves de son périmètre.
- **Modèle** : Bedrock. DeepSeek, utilisé en phase 0 sur le code de Méridian, ne doit jamais recevoir de code
  bancaire.

---

# 8. Ce qui change dans le code de la phase 0

| Phase 0 | AWS | Effort |
|---|---|---|
| `copie_au_sha` (worktree local) | clone partiel dans la tâche Fargate + instantané S3 | faible |
| projet codebase-memory-mcp nommé d'après le chemin | artefact `graph.db.zst` par jumeau et SHA, rechargé à la demande | moyen |
| `source_git.lire_au_sha` (git) | lecture dans l'instantané S3 | faible |
| `temps.historique` (git log) | table `commit` dans Aurora, remplie à l'ingestion | faible |
| `cbm.texte` (ligne de commande) | appels MCP au serveur « code-jumeau » via Gateway | moyen |
| `FileSessionManager` | AgentCore Memory (ou `S3SessionManager` de Strands) | faible |
| `FilsActifs` (mémoire) | verrou consultatif Postgres ou DynamoDB | faible |
| boucle `--surveiller` | événements + passe nocturne | supprimée |
| commande factice | Step Functions « Naissance » | moyen |

---

# 9. Trajectoire de démarrage (avec AgentCore ; voir §10.5 sans AgentCore)

| Étape | Contenu | Résultat |
|---|---|---|
| **1** | Image d'ingestion (git, codebase-memory-mcp, `jumeau`), Aurora Serverless v2, S3 avec Object Lock, Step Functions « Veille » à 3 étapes déterministes, événement depuis GitHub Actions, passe nocturne | un commit fait évoluer le jumeau et publie ses signaux, sans agent |
| **2** | Gardien sur AgentCore Runtime (étape 4), modèle Bedrock | fiche vivante produite sur AWS |
| **3** | Commande branchée sur « Naissance », GitHub App et test réel, admission humaine | un jumeau naît depuis l'interface |
| **4** | Serveur MCP « code-jumeau », Gateway avec Policy et Identity, Flore sur Runtime, Memory | Flore gouvernée, au nom de l'utilisateur |
| **5** | Plus de familles de Claims (tables, appels inter-services, messages), `compare_graphs`, liens entre dépôts | premières relations entre jumeaux : le Mesh |

---

# 10. Variante de départ sans AgentCore

Si AgentCore n'est pas encore accessible, l'architecture reste la même pour tout ce qui n'est pas agent
(EventBridge, Step Functions, Fargate, S3, Aurora, DocumentDB). Seul l'hébergement des agents et de leurs outils
change. Les agents étant écrits avec Strands, qui tourne dans n'importe quel conteneur, **le code ne change pas** ;
la bascule vers AgentCore se fera en enveloppant le même code (`BedrockAgentCoreApp`).

## 10.1 Vue d'ensemble

```text
 GitHub Actions (rôle OIDC) ──put-events──► EventBridge ◄── Scheduler (passe nocturne)
                                               │
                                               ▼
 Step Functions « Veille »   1 Ingestion (Fargate) → 2 Signaux (Lambda) → 3 Publier (Lambda)
                             → 4 Fiche : tâche Fargate « gardien » (Strands + Bedrock)   [Catch : rien n'est perdu]
 Step Functions « Naissance » (commande → test réel → ingestion → admission humaine → fiche → publier)

 Utilisateurs ─► CloudFront ─► ALB ─► ECS Fargate « api-flore »
                                        FastAPI + Flore (Strands), outils dans le processus,
                                        codebase-memory-mcp embarqué, artefacts en cache sur EFS
                                        Cognito (IdP de la banque) · Verified Permissions (Cedar)
                                        fils de Flore : S3SessionManager

 Données : Aurora PostgreSQL · S3 (Object Lock, KMS) · DocumentDB · Secrets Manager (GitHub App)
 Modèle  : Bedrock via point de terminaison VPC          Observabilité : ADOT → CloudWatch, X-Ray
 Réseau  : VPC privé, points de terminaison VPC (Bedrock, S3, Secrets Manager, ECR, Logs, Events, States),
           sortie limitée à la forge Git
```

## 10.2 Correspondance

| Cible AgentCore | Variante de départ | Ce qu'on perd en attendant |
|---|---|---|
| Runtime (Flore, gardien) | service ECS Fargate « api-flore » ; tâche Fargate « gardien » lancée par Step Functions | l'isolation d'une microVM par session : les fils partagent un conteneur |
| Gateway (outils MCP) | outils dans le processus de Flore ; codebase-memory-mcp embarqué dans l'image, artefacts S3 mis en cache sur EFS | réutilisation des outils par d'autres agents, journal centralisé des appels d'outils |
| Policy (Cedar) | règles dans le code (aucun outil de validation ni de décision, budgets, arguments filtrés) et **Amazon Verified Permissions** pour les droits de l'application | contrôle hors du code de l'agent |
| Identity | **Cognito** fédéré à l'IdP de la banque ; périmètre appliqué par l'API avant l'appel de l'agent ; identifiants GitHub App dans **Secrets Manager** | coffre de jetons OAuth géré |
| Memory | `S3SessionManager` de Strands (ou table Aurora) | stratégies de mémoire longue (préférences, résumés) |
| Observability | télémétrie OpenTelemetry de Strands → ADOT → CloudWatch, X-Ray | tableaux de bord agents prêts à l'emploi |
| Evaluations | jeu de questions de référence par profil, rejoué en CI (Contradicteur comme juge) | évaluation en ligne gérée |

## 10.3 Sans aucune infrastructure AWS (rôle Bedrock seulement)

Pour les démonstrations ou un pilote très restreint : une VM de la banque en `docker compose` (Postgres, Mongo,
API avec Flore, gardien en service), workflows durables avec **DBOS** (déjà utilisé dans `laboratoire-autonome`)
à la place de Step Functions, et seul l'appel au modèle sortant vers Bedrock.

## 10.4 Ajustements de code qui rendent la bascule gratuite

1. Fils de Flore sur `S3SessionManager` (ou Aurora) plutôt que des fichiers locaux.
2. Outils de code par le `MCPClient` de Strands vers codebase-memory-mcp, plutôt que par sa ligne de commande :
   le jour venu, seule l'adresse change (Gateway).
3. Identité réelle (OIDC) à la place de l'en-tête `X-Persona`.

## 10.5 Trajectoire réajustée

| Étape | Contenu | AgentCore requis ? |
|---|---|---|
| 1 | Veille déterministe : ingestion Fargate, Step Functions, EventBridge, Aurora, S3 | non |
| 2 | Gardien en tâche Fargate, Bedrock | non |
| 3 | API et Flore sur ECS Fargate, Cognito, Verified Permissions, fils sur S3, codebase-memory-mcp embarqué | non |
| 4 | Commande branchée sur « Naissance », GitHub App, admission humaine | non |
| 5 | **Bascule AgentCore** : Runtime, Gateway, Policy, Identity, Memory, sans réécriture | oui |
| 6 | Mesh : liens inter-services, `compare_graphs`, liens entre dépôts | non |

---

# 11. Points à vérifier

1. Disponibilité en `ca-central-1` de chaque service AgentCore utilisé (Runtime, Gateway, Identity, Memory, Policy)
   et de la session storage de Runtime (en préversion en 2026).
2. Hébergement GitHub de la banque (Enterprise Cloud, Enterprise Server, ou autre forge) et politique d'installation
   d'une GitHub App.
3. Revue de sécurité de codebase-memory-mcp : version épinglée, compilation depuis les sources, absence de sortie
   réseau, comportement du démon de coordination dans un conteneur.
4. Décision de conformité sur le profil d'inférence Bedrock (Architecture Jumeau §10).
5. Durée de conservation des instantanés de code sous Object Lock (au regard de la politique d'archivage).
