# Méridian

> **État actuel et reste à faire :** [docs/architecture/etat-actuel.md](docs/architecture/etat-actuel.md).
> **Écarts avec la vision :** [docs/architecture/ecarts-vision.md](docs/architecture/ecarts-vision.md).
> **Architecture de référence :** [docs/MERIDIAN_Architecture_Master_v1.md](docs/MERIDIAN_Architecture_Master_v1.md).
> Ce README décrit le produit, l’usage et les points d’entrée ; le document d’état actuel décrit
> l’implémentation réelle, la matrice de traçabilité doc → code → test et les dettes restantes.

**Méridian** est un **système d’intelligence vivante de l’entreprise**. Sa fondation cognitive est un réseau de **Twins** — représentations d’entités de l’entreprise (application, processus, capacité, parcours, organisation, produit, domaine de données, ressource, fournisseur, équipe, écosystème) — et de connaissances reliées : **Claims**, preuves, sources et relations ; le **Mesh** et l’**Atlas** les rendent navigables. Le système est organisé autour de **Situations** (incidents, changements, découvertes) et suit la boucle **Découvrir → Maturer → Exprimer → Investiguer → Décider → Agir → Mesurer → Apprendre**, mécanique opérationnelle du triptyque **Découvrir · Comprendre · Décider**.

**Ce que Méridian n’est pas.** Méridian n’est pas un Twin. Flore est l’interface conversationnelle, pas Méridian ; Atlas est la géographie du Mesh, pas le produit. Méridian n’est pas non plus un simple Knowledge Graph, une CMDB augmentée, un outil d’observabilité, de documentation, de process mining, de recherche ou d’architecture, un assistant conversationnel, une plateforme multi-agents ou un Digital Twin. Il peut incorporer certaines de ces capacités ; sa différence est la boucle complète d’observation, de maturation, d’investigation, de décision, de mesure et d’apprentissage.

> Dans Méridian, sélectionner le SI revient à donner du contexte à Flore. Interroger Flore revient à transformer la vue du SI.

## La cible et l’écart

Méridian doit permettre à l’entreprise de passer de la découverte à l’amélioration continue.
La question utile n’est donc pas « quelles pages existent ? », mais **où en est la boucle
vivante**.

| Génération | Cible | État réel | Ce qui existe déjà |
|---|---|---|---|
| **Méridian 1 — Comprendre** | Représentation vivante et fiable de l’entreprise : Twins, Mesh, Claims, sources, découverte, relations, Atlas, compréhension | **Solide sur le socle ; partiel sur la couverture** | Twins typés, ingestion Git/CBM, claims et preuves, liens entre composants, Atlas, revue humaine |
| **Méridian 2 — Exploiter** | Transformer la compréhension en attention, investigation et décision : maturation, expressions, risques/opportunités, experts, investigations, scénarios, Flore, priorisation | **Partiel** | Travail, Flore, Actualités, décisions/passation/veille, dossiers de raisonnement, planification. Mais le chemin live et la boucle canonique ne sont pas unifiés |
| **Méridian 3 — Améliorer** | Mesurer les décisions, apprendre des résultats et améliorer continuellement : initiatives, outcomes, apprentissage, mémoire de transformation | **Embryonnaire** | Outcome/Learning, calibration, réutilisation mesurée, veille. Pas encore de mémoire de transformation interrogeable ni de collecte automatique |

**Statuts** : *Solide* = branché dans un chemin réel et testé ; *Partiel* = code présent mais
chaîne produit incomplète ; *Embryonnaire* = début de boucle, pas encore exploitable.

### L’expérience cible

- **Aujourd’hui** — une file d’attention qui explique pourquoi chaque sujet compte, ce qui est
  prouvé, ce qui reste incertain et ce qui demande une décision.
- **Atlas** — la géographie du Mesh : où le phénomène se produit, quelles entités et relations
  sont touchées, quelle propagation est possible.
- **Flore** — la conversation avec l’entreprise vivante : expliquer, prouver, lancer une
  investigation, comparer des scénarios, suivre un outcome.
- **Travail** — l’espace où une situation devient investigation, décision, initiative et
  résultat, avec une chaîne de preuve continue.
- **Boucle** — la lecture de bout en bout : Situation → Expression → Investigation → Décision →
  Initiative → Outcome → Learning.

**Lecture honnête.** Méridian sait aujourd’hui découvrir et comprendre un SI, et commence à
exploiter cette compréhension dans le Travail, Flore et l’Atlas. Il ne sait pas encore dérouler
la boucle complète de façon canonique et homogène : une décision prise dans Travail ne crée pas
de `Decision` canonique, et un `Outcome` canonique exige une `Initiative` canonique que le
chemin live ne crée pas encore.

**Ce qui manque en priorité**

- **Unifier la chaîne** : Travail/Actualités (Mongo legacy), boucle canonique (Postgres) et
  dossier de raisonnement doivent converger vers un même parcours traçable. Une même Situation
  doit garder un identifiant unique de la découverte jusqu’au Learning.
- **Rendre la boucle opérable** : API et UI de création/transition pour Signal → Situation →
  Expression → Investigation → Décision → Initiative → Outcome → Learning, pas seulement la
  lecture et l’Outcome.
- **Compléter les objets** : `Signal`, `Expression`, `Scenario`, `Hypothesis`, `Expert` et
  `ExpertContribution` sont canoniques ; il reste à administrer le registre Expert, à
  résoudre les liens cités par les contributions et à automatiser la maturation.
- **Brancher la mesure et l’apprentissage** sur les décisions et les sources réelles, avec
  attendu/observé et effets secondaires.
- **Construire la mémoire de transformation** et les actions Flore : comparer des scénarios,
  lancer une investigation, interroger les experts, reviser un outcome.

Le détail — étape par étape, objet par objet, surface par surface — est dans
[docs/architecture/ecarts-vision.md](docs/architecture/ecarts-vision.md).

## Sommaire

- [La cible et l’écart](#la-cible-et-lécart)
- [Les espaces](#les-espaces)
- [Flore / Aurora](#flore--aurora--copilote-contextuel)
- [Ce qui est déjà solide](#ce-qui-est-déjà-solide)
- [Architecture visuelle](#architecture-visuelle)
- [Pile technique](#pile-technique)
- [Démarrage](#démarrage)
- [Découverte, mémoire et agentique](#découverte-mémoire-et-agentique)
- [API principale](#api-principale)
- [Tests](#tests)
- [Reste à faire](#reste-à-faire)

## Les espaces

| Page | Route | Rôle |
|---|---|---|
| **Aujourd'hui** | `/actualites`, `/aujourdhui` ; `/` y redirige | Observatoire : nouvelles connaissances, anomalies, activité |
| **Atlas** | `/atlas` | Carte 2D à zoom sémantique, territoires et portes |
| **Travaux** | `/travaux`, `/travaux/:cid` ; `/investigations` et `/decisions` y redirigent | Fil de travail, pièces, décisions et livrables |
| **Boucle** | `/boucle` | Lecture de la boucle canonique, synthèse, création d’Outcome et de Twin ; création/transition des autres objets à venir |
| **Cognition** | `/cognition` | Dossier de raisonnement, croyances, évaluation |
| **Jumeaux** | `/jumeaux`, `/jumeaux/:jid/revue` | Registre, revue et promotion des Twins |
| **Administration** | `/administration` | Sources, couverture, propriétaires, journal d'audit |

## L'Atlas — navigation hiérarchique

Hiérarchie du zoom : **Mesh global → Domaine → Jumeau** (puis Relation → Claim → Preuve via le panneau latéral).

Règle essentielle : **sélectionner ≠ prendre le focus**.

| Action | Domaine | Jumeau |
|---|---|---|
| Survol | Aperçu (jumeaux, découvertes, relations) | Aperçu rapide (mission, état, couverture) |
| Clic | Sélection dans le contexte Flore | Sélection dans le contexte Flore |
| Double-clic | **Focus** : entrée dans le domaine | **Focus** : vue locale radiale du jumeau |
| Molette avant | Entrée progressive dans l'élément survolé | Idem |
| Molette arrière | Retour au Mesh | Retour au domaine |
| Clic sur une porte pointillée | Transfert du focus vers le domaine voisin | Transfert du focus vers le jumeau voisin |

- **Territoires** : résumé dynamique « N jumeaux · N découvertes · N investigations · N zones inconnues » + point d'activité temps réel.
- **Portes externes** : les domaines connexes restent visibles en périphérie (pointillé = accessible, cadenas = accès limité) ; le survol affiche un aperçu avant de naviguer.
- **Focus jumeau** : le jumeau est centré, ses voisins disposés en portes radiales avec l'état de chaque relation ; cliquer un voisin transfère le focus — on parcourt le SI par ses relations.
- **Navigation** : fil d'Ariane cliquable (`Mesh global › Domaine › Jumeau`), historique ←/→, « Revenir à ma sélection », mini-carte.
- **Sélection multiple** : Ctrl/Maj+clic (toggle), lasso (union avec la sélection existante), focus contextuel (le reste s'estompe).
- **Zoom sémantique** : niveau 1 = corridors agrégés entre domaines, niveau 2 = domaines, niveau 3 = relations détaillées.
- **Périmètre de travail** : un domaine peut devenir un filtre de travail volontaire (distinct de la sécurité RBAC).
- **Liens profonds** : l'URL reflète le contexte (`?domaine=X&interne=1&jumeau=Y&sel=Z`) — partageable et restaurable.

## Flore / Aurora — copilote contextuel

**Flore** est le nom visible du copilote dans le Travail ; l’API historique reste
`/api/aurora`. La barre est persistante en bas de l’application, **synchronisée
bidirectionnellement avec l’Atlas** :

- **Atlas → Flore** : toute sélection (clic, Maj+clic, lasso, domaine) met à jour le contexte actif de Flore (chips avec retrait individuel) et propose des intentions : *Comprendre leurs relations · Dépendances inconnues · Analyser un changement · Points critiques · Optimiser ce parcours · Ouvrir une investigation*.
- **Flore → Atlas** : Flore commande la carte (éclairer des relations, isoler un parcours, naviguer vers un domaine) et propose des voisins pertinents avec justification — jamais sans confirmation (*Ajouter au contexte / Examiner / Ignorer*).
- **Focus visuel ≠ sélection analytique** : entrer dans un domaine conserve la sélection ; Flore propose alors de la conserver, la retirer ou d'ajouter les jumeaux du domaine.
- Réponses **calculées depuis le vrai Mesh** (toujours filtrées par les autorisations serveur) : recherche plein texte avec scoring de pertinence, scénarios prescriptés pour le parcours de démonstration, accusé de contexte sans analyse automatique.
- **Mentions et commandes** : dans le Travail, `@Nom` ouvre la liste des jumeaux visibles et route explicitement la question vers celui qui est mentionné (les droits serveur filtrent toujours) ; `/resumer`, `/investiguer`, `/decision`, `/preuves`, `/pieces` et `/aide` remplissent une consigne explicite, que l'on relit avant l'envoi. Aucune commande n'exécute une action cachée.
- **Sources & Jumeaux** : le volet est groupé en **Jumeaux** (ceux du Travail et ceux réellement consultés, avec badge et sources), **Preuves du dossier** (démonstration) et **Pièces jointes**. Toutes les rubriques et sous-rubriques sont **pliées par défaut** ; un clic les ouvre. Il s'ouvre une fois quand une réponse apporte une source, puis reste fermé si l'utilisateur le referme. Les preuves d'une réponse restent sous le message (pastilles), pas dans ce volet.
- **Partage par lien** : le bouton « Partager » copie le lien du Travail et rappelle que la portée et le périmètre s'appliquent à l'ouverture ; le lien n'élargit jamais les droits.
- La barre se replie en pastille flottante sans perdre le contexte (`⌘K` pour la rappeler).

## Sécurité — RBAC côté serveur

En mode `demo` (local), l'acteur vaut `demo` et le périmètre se pilote via le sélecteur d'espace de la barre supérieure, envoyé au backend par l'en-tête `X-Espace`. En production, `AUTH_MODE=proxy` ou `oidc` authentifie l'acteur côté serveur. **Tout le filtrage est fait côté serveur** — les données non autorisées ne quittent jamais l'API.

Niveaux d'autorisation par jumeau : `existence` → `résumé` → `preuves` → `complet`. Flore refuse les questions hors périmètre et filtre ses analyses au niveau « résumé » minimum.

## Ce qui est déjà solide

- **Comprendre un SI** : Twins, situations, relations, preuves, claims, maturité, contradictions.
- **Découvrir les liens entre composants** : code, contrats, configuration, Kubernetes/Helm,
  ingress, traces, JNDI ; CBM comme source principale, parseurs locaux en repli.
- **Enquêter de façon bornée** : harness agentique, planificateur déterministe ou LLM, outils
  read-only, budgets, arrêt explicite, revue humaine.
- **Mémoire multi-niveaux** : mémoire de travail, épisodique, sémantique, procédurale,
  relationnelle, réflexive, prospective, organisationnelle et documentaire.
- **Boucle canonique (lecture/backfill)** : Situation → Investigation → Décision → Initiative →
  Outcome → Learning, avec transitions validées, calibration et réutilisation mesurée. Le
  chemin Travail/Actualités utilise encore son modèle Mongo ; l’unification est l’écart P0.
- **Planifier** : capacité, charge, prévision, budget, adaptateurs de synchronisation ;
  connecteur Jira présent, Azure DevOps non identifié.
- **Gouverner** : auth `proxy`/`oidc`, RBAC serveur, tenant, RLS opt-in, rétention, export,
  suppression.

## Architecture visuelle

Le schéma d’architecture actuel :

![Architecture actuelle de Méridian](docs/diagrammes/architecture-etat-actuel.png)

[Ouvrir en grand (HTML)](docs/diagrammes/architecture-etat-actuel.html) ·
[SVG](docs/diagrammes/architecture-etat-actuel.svg)

La carte des mémoires de l’agent :

![Mémoire de l’agent Méridian](docs/diagrammes/memoire-agent.png)

[Ouvrir en grand (HTML)](docs/diagrammes/memoire-agent.html) ·
[SVG](docs/diagrammes/memoire-agent.svg)

La boucle cognitive (cadrage → contexte → dossier → critique → décision → Learning) :
[diagramme cognitif](docs/diagrammes/architecture-cognitive.html) ·
[SVG](docs/diagrammes/architecture-cognitive.svg).

Le cycle de vie d’un Twin (commande → préalables → sources → claims → manifeste →
`twin.born` → découverte → revue → veille) :
[diagramme Twin](docs/diagrammes/cycle-vie-twin.html) ·
[SVG](docs/diagrammes/cycle-vie-twin.svg).

Le déploiement AWS cible (edge, VPC, ECS/Fargate, Aurora, Neo4j, Redis, S3, Bedrock,
AgentCore, SQS/EventBridge) :

![Déploiement AWS cible](docs/diagrammes/deploiement-aws.png)

[Ouvrir en grand (HTML)](docs/diagrammes/deploiement-aws.html) ·
[SVG](docs/diagrammes/deploiement-aws.svg)

Les diagrammes sont produits avec le profil `diagram-design` `meridian` et validés par
`self_check.py --offline` et `verify-geometry.py`.

## Pile technique

- **Frontend** : React 19, Tailwind CSS, `@xyflow/react`, Phosphor Icons, React Router 7,
  Recharts, Mermaid.
- **Backend** : FastAPI, Pydantic v2, psycopg 3, Motor/PyMongo, Neo4j, Redis, boto3.
- **Stockages** :
  - **Postgres** : source canonique (claims, preuves, objets d’entreprise, décisions,
    mémoire durable et prospective, exécution, planification, chunks, communautés) ;
  - **MongoDB** : Travail, cas, conversations, pièces, legacy ;
  - **Neo4j** : projection graphe (Twins, relations, parcours, communautés) ;
  - **Redis** : SSE, état des tours, rate limiting, multi-worker ;
  - **local / S3 / MinIO** : artefacts d’index reconstructibles ;
  - **CBM / Graphify** : graphe de code et contexte d’architecture.
- **Modèles** : DeepSeek, Bedrock ou autre fournisseur compatible ; planificateurs LLM bornés
  avec repli déterministe.

```
backend/
├── server.py                  # point d'entrée ASGI
├── meridian/
│   ├── domain/                # modèles purs et invariants
│   ├── application/           # cas d'usage, moteurs, harness, mémoire
│   ├── ports/                 # contrats
│   ├── adapters/
│   │   ├── inbound/http/      # FastAPI
│   │   ├── inbound/worker/    # source, outbox, travail, planification, réconciliation
│   │   └── outbound/          # postgres, mongo, neo4j, redis, llm, connectors, aws
│   └── tests/                 # pytest
├── requirements.txt
└── pytest.ini
frontend/src/
├── pages/                     # Atlas, Aujourd'hui, Travail, Boucle, Jumeaux, Administration
├── components/map/            # Atlas, panneau Twin, revue, liens
├── components/case/           # Travail, pièces, décisions
└── lib/                       # api, contexte, rendu du graphe
scripts/                        # workers, évaluation, réconciliation, maintenance
docs/                           # architecture, ADR, PRD, état actuel
```

## Découverte, mémoire et agentique

**Découverte des liens.** CBM fournit le graphe de code multi-langages (routes, appels HTTP,
variables, tables, ressources) ; les parseurs locaux ne servent que de repli. Les contrats, la
configuration, Kubernetes/Helm, les ingress et les traces complètent les observations. Le
moteur produit des liens `suggere`, des questions et des contradictions ; **aucun lien n’est
confirmé automatiquement**. Namespace, rewrites d’ingress statiques et JNDI sont modélisés.

**Mémoire.** Méridian sépare les mémoires au lieu d’empiler un unique vector store :

| Mémoire | Usage |
|---|---|
| Travail / session | contexte du tour, résumé borné |
| Épisodique | sessions, dossiers, décisions, outcomes |
| Sémantique | Claims, preuves, connaissances, documents |
| Procédurale | compétences, méthodes, recettes, Learnings |
| Relationnelle | Twins, liens, topologie, communautés |
| Réflexive | croyances, calibration, consolidation, leçons |
| Prospective | intentions datées, échéances, rappels |
| Organisationnelle | mémoire d’équipe et de tenant |
| Documentaire | chunks, embeddings, communautés, RAG |

La récupération est unifiée et hiérarchisée : `claim` > `learning` > `intention` >
`annotation` > `durable`. Les Learnings sont réutilisables et leur réutilisation peut être
mesurée (`succes`, `echec`, `inconnu`, outcome et preuves).

**Agentique.** Le harness choisit des outils read-only, observe, s’arrête sur budget ou
impasse, et produit des candidats. Il ne confirme rien : la revue humaine reste la seule voie
de confirmation. Le détail est dans
[docs/architecture/etat-actuel.md](docs/architecture/etat-actuel.md).

**Méridian n’est pas un Twin.** C’est un système d’intelligence vivante de l’entreprise :
le Mesh, les Twins, les Claims, les sources et l’Atlas sont sa fondation cognitive, mais la
valeur est la boucle complète **Découvrir → Maturer → Exprimer → Investiguer → Décider →
Agir → Mesurer → Apprendre**. Flore est l’interface conversationnelle, pas Méridian ; Atlas
est la géographie du Mesh, pas le produit. Le `meridian` des tests ou d’un backfill local est
une donnée de déploiement, pas un concept produit.

## Démarrage

```bash
# 1. Moteurs locaux : Mongo, Redis, Postgres
export JUMEAU_PG_PASSWORD="motdepasse"
docker compose up -d mongodb redis postgres

# 2. Backend (port 8001)
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt
export JUMEAU_PG_DSN="postgresql://meridian:motdepasse@127.0.0.1:5434/meridian"
export MONGO_URL="mongodb://127.0.0.1:27017"
export DB_NAME="meridian_db"
.venv/bin/uvicorn server:app --host 0.0.0.0 --port 8001 --reload

# 3. Frontend (port 3000)
cd ../frontend
yarn install
yarn start
```

Neo4j est optionnel pour la projection graphe :
`scripts/dev-neo4j-light.sh up` (ou `docker compose -f docker-compose.neo4j.yml up -d` avec
`NEO4J_PASSWORD`).

### Laboratoire AWS local (Floci)

Pour tester la plomberie AWS sans compte réel — S3, SQS, EventBridge, Scheduler,
KMS, CloudWatch Logs et IAM ; Secrets Manager y est un adaptateur optionnel, Vault
reste le coffre principal :

```bash
scripts/dev-floci.sh up
eval "$(scripts/dev-floci.sh env)"
scripts/dev-floci.sh smoke
```

Floci ne valide pas Bedrock : son runtime est un stub/proxy. Le détail est dans
[docs/architecture/floci-aws-local.md](docs/architecture/floci-aws-local.md).

Le schéma Postgres est idempotent (`depot.appliquer_schema`, `schema.sql`) et appliqué par les
workers et les scripts de maintenance. Sur une base neuve, l’appliquer une fois avant la
première écriture :

```bash
cd backend
.venv/bin/python - <<'PY'
import os, psycopg
from meridian.adapters.outbound.postgres import depot
with psycopg.connect(os.environ["JUMEAU_PG_DSN"]) as conn:
    depot.appliquer_schema(conn)
PY
```

Variables principales : `JUMEAU_PG_DSN`, `MONGO_URL`, `DB_NAME`, `REDIS_URL`,
`JUMEAU_MODELE`, `CBM_BIN`, `AUTH_MODE` (`demo` en local, `proxy`/`oidc` en production) et
`REACT_APP_BACKEND_URL` côté frontend. Le détail est dans
[docs/architecture/etat-actuel.md](docs/architecture/etat-actuel.md).

Parseur PL/I ANTLR (facultatif, tests sémantiques) :

```bash
cd tools/pli && ./generate.sh
```

Voir [tools/pli/README.md](tools/pli/README.md).

### Alimentation continue des jumeaux

La naissance d'un jumeau ingère sa première version dans le processus de l'API. Les mises à jour suivantes
sont pull-first : lancer le worker dans un terminal séparé.

```bash
scripts/dev-source-worker.sh          # polling continu
scripts/dev-source-worker.sh --une-passe
```

En production, superviser `scripts/meridian-source-worker.service` (unité systemd fournie, chemins à adapter).
Sans worker, les runs restent `QUEUED` ; le webhook signé ne fait qu'avancer leur échéance.

### Plusieurs workers (Redis)

Le bus SSE et l'état des tours partagés passent par Redis dès que `REDIS_URL` est défini. Avec plusieurs
workers uvicorn, Redis est **obligatoire** : le démarrage échoue plutôt que de laisser chaque worker croire
qu'il est seul.

```bash
docker compose up -d redis
export REDIS_URL=redis://127.0.0.1:6379/0
cd backend && uvicorn server:app --host 0.0.0.0 --port 8001 --workers 2
```

`TOUR_TTL` (secondes, défaut 600) règle la conservation du flux et des métadonnées d'un tour.
`TOUR_HEARTBEAT` (5 s), `TOUR_STALE` (30 s) et `TOUR_REAPER` (10 s) règlent le battement de cœur du worker
propriétaire et le ramassage d'un tour dont le worker a disparu. Le flux SSE porte un `id:` Redis Stream :
une reprise utilise cet identifiant opaque, pas un index de tableau. Les notifications restent persistées
dans Mongo ; Redis ne porte que le temps réel. En production, Redis doit être authentifié (ACL/TLS) et
l'URL ne doit pas apparaître dans les logs.

## Identité

`AUTH_MODE` décide comment l'acteur est authentifié :

- `demo` (défaut local) : aucun utilisateur authentifié ; l'acteur vaut `demo`. **Interdit en production.**
- `proxy` : un proxy authentifiant (oauth2-proxy, ALB, etc.) fournit `X-Auth-Request-User` et
  `X-Auth-Proxy-Secret`. L'acteur est cet utilisateur ; aucun en-tête client ne le choisit.
- `oidc` : l'API vérifie un JWT `Authorization: Bearer` avec `AUTH_OIDC_JWKS_URL` (ou `AUTH_OIDC_SECRET`
  pour HS256), `AUTH_AUDIENCE`, `AUTH_ISSUER`, puis prend `name`, `preferred_username`, `email` ou `sub`.

`GET /api/moi` expose l'acteur, le tenant et le mode. En production, définir `APP_ENV=production` :
`AUTH_MODE=demo` est refusé au démarrage.

## Pièces jointes d'un Travail

Un Travail accepte des pièces jointes : PDF, Word (`.doc`/`.docx`), PowerPoint (`.ppt`/`.pptx`/`.pps`/`.ppsx`/`.pot`),
Excel (`.xls`/`.xlsx`/`.xlsb`), OpenDocument (`.odt`/`.ods`/`.odp`), RTF, EPUB, CSV, texte, Markdown, JSON, HTML.
Les formats bureautiques passent par [anydoc](https://github.com/firecrawl/anydoc) (MIT, conversion locale en
Markdown, détection par le contenu) ; en cas d'absence du wheel natif, PDF/Word/Excel gardent un extracteur Python
de repli. anydoc est un wheel natif (Linux/macOS/Windows, Python ≥ 3.10) : sur une plateforme sans wheel, prévoir
Rust, ou retirer la dépendance et accepter le repli. **Aucun OCR hébergé** : un PDF scanné reste une pièce sans
texte, jamais envoyée à un service externe. Les variantes macro (`.docm`, `.xlsm`, `.pptm`, `.ppsm`) sont refusées.

Elles sont **versées comme sources du Travail, jamais comme des connaissances** : Flore les lit avec leur nom,
leur auteur et leur date, dit « d'après la pièce jointe … » et ne les cite jamais comme du code. Un document joint
ne crée ni Claim ni relation ; il reste dans le travail et disparaît avec lui.

Le Markdown est découpé en **sections** à l'upload (titres ATX, slides PowerPoint, préambule). À chaque tour, Flore
reçoit un **sommaire** et les sections les plus pertinentes pour la question (sélection lexicale bornée, budget
réservé par pièce), pas le document entier. Une section non fournie se lit avec `lire_piece` (fenêtre `debut`),
et les passages peuvent être recherchés avec `chercher_pieces` ; les deux sont limités au Travail courant et à un
plafond de lectures. Les tableaux (CSV, Excel, OpenDocument) exposent leurs feuilles/colonnes/lignes via
`lire_table`, qui rend une fenêtre bornée en Markdown — jamais de SQL ni de code exécuté.

Une citation de pièce est formulée « d'après la pièce “nom”, § titre » et porte le repère vérifiable
`pièce:<id>#<section>` (ou `pièce:<id>#table:<feuille>:<début>-<fin>`) : le contradicteur le contrôle contre le
sommaire réel, sans le confondre avec une preuve de code. Les citations de section sont cliquables dans le Travail
et ouvrent la section source. Ce n'est jamais un Claim. Les images distantes ne sont jamais chargées depuis une
réponse.

Seuls le **responsable** et les **participants** du Travail peuvent déposer une pièce ; un lecteur simple peut la
télécharger mais pas en ajouter. En mode `proxy`/`oidc`, les pièces ne sont transmises au modèle que si
`PIECES_ENVOI_MODELE_EXTERNE=1` (ou si `JUMEAU_MODELE` n'est pas un modèle externe) ; en `demo`, l'envoi est
autorisé par défaut. Sinon Flore dit qu'elle ne les a pas reçues — le fichier reste dans le Travail.

Limites par défaut (variables d'environnement) :

- `PIECES_MAX_OCTETS` (10 Mo) : taille d'un fichier ; `PIECES_MAX_PAR_CASE` (10) : nombre par travail.
- `PIECES_MAX_CARACTERES` (200 000) : texte conservé par pièce ; `PIECES_MAX_CARACTERES_PROMPT` (40 000) et
  `PIECES_MAX_CARACTERES_PIECE_PROMPT` (12 000) : budget du contexte envoyé à Flore à chaque tour.
- `PIECES_MAX_PAGES_PDF` (300) et `PIECES_MAX_FEUILLES_XLSX` (20) : bornes du **repli Python** ; le chemin anydoc
  a ses propres limites de ressources et le texte est de toute façon tronqué après conversion.
- `PIECES_DUREE_EXTRACTION` (15 s) : durée au-delà de laquelle l'ajout est refusé (le fil d'extraction ne peut pas
  être tué ; le pool dédié en borne l'impact).
- `PIECES_MAX_DECOMPRESSE` (40 Mo) : refus des archives bureautiques qui se décompressent au-delà.
- `PIECES_CONCURRENCE` (2) : extractions simultanées au plus par worker (un pool dédié, borné).
- `PIECES_MAX_CARACTERES_TOC` (4 000), `PIECES_MAX_SECTIONS` (300) et `PIECES_MAX_SECTIONS_PIECE_PROMPT` (4) :
  bornes du sommaire et du nombre de sections proposées à Flore.

Le contenu est stocké dans Mongo (GridFS) et partagé par les workers ; la réinitialisation de la démo et la
suppression d'une conversation suppriment aussi les fichiers. Retirer une pièce purge ses dérivés dans le fil
(`pieces_lectures`, `pieces_selection`, activité des outils de pièces) ; les citations déjà écrites peuvent rester
dans le texte, mais ne pointent plus vers un fichier. Les formats non lisibles (scan sans OCR, images) sont
refusés, ou conservés sans texte avec un état affiché honnêtement.

La recherche de sections est **lexicale** (titres + texte), complétée par `chercher_pieces` et `lire_piece` ; c'est
le choix complet à l'échelle d'un Travail (10 pièces), sans dépendance à un modèle d'embedding ni envoi de texte à
un service tiers. `evaluation_pieces` mesure recall@k/MRR ; une extension sémantique reste possible mais n'est pas
nécessaire au fonctionnement. Les images distantes d'une réponse ne sont jamais chargées.

Le contenu des pièces n'entre **jamais dans le prompt système** : il est fourni comme données balisées dans le
message utilisateur. Avec des pièces, Flore n'écrit dans le Travail que si l'utilisateur coche « Autoriser Flore à
modifier le travail » pour le tour ; sinon elle propose l'action sans l'exécuter. L'extraction (anydoc, pypdf,
python-docx, openpyxl) tourne dans un **processus séparé** avec timeout, mémoire/CPU bornés et réseau coupé
(`PIECES_EXTRACTION_PROCESSUS=0` pour les tests/développement). Au démarrage, les compteurs de quota des pièces sont
réconciliés avec la base.

| Endpoint | Rôle |
|---|---|
| `GET /api/cases/{cid}/pieces` | Métadonnées des pièces (jamais le texte) |
| `POST /api/cases/{cid}/pieces` | Dépôt multipart (`fichier`) |
| `GET /api/cases/{cid}/pieces/{pid}` | Téléchargement en pièce jointe (`nosniff`) |
| `GET /api/cases/{cid}/pieces/{pid}/extrait` | Texte extrait, borné |
| `GET /api/cases/{cid}/pieces/{pid}/sections/{sid}` | Fenêtre d'une section (`debut`, `limite`) |
| `DELETE /api/cases/{cid}/pieces/{pid}` | Retrait par l'auteur ou le responsable |

## Évaluation de la sélection de sections

Un harnais reproductible mesure la sélection lexicale sans base :
`backend/evaluation_pieces.py` lit un JSONL `{question, piece, section}` et un JSON de pièces, puis calcule
`recall@k` et `MRR` sur les sections réellement incluses par `sections_pour_prompt_detail`.

```bash
cd backend
python -m evaluation_pieces --docs docs.json --questions questions.jsonl --k 4
```

## Limites de plateforme

- `PATCH /api/cases/{cid}` ne modifie **jamais** la conversation (400) ; elle s'ajoute par `POST /messages` ou
  `POST /cases/{cid}/fusion`. Toutes les mutations de conversation (messages, versions, branches, régénération,
  modification) sont réservées au **responsable ou aux participants**.
- La fusion est réservée au **responsable** de la cible : elle réserve la source, déplace ses pièces sous quota
  atomique, normalise les messages importés (sans preuves/approbations clientes), puis supprime la source.
- Le journal est filtré par périmètre et les conversations privées n'y exposent ni titre ni nom de pièce ;
  `POST /api/journal` n'accepte que les changements d'identité/périmètre, avec un détail dérivé serveur.
- Décider ou agir sur une situation exige que **tous ses jumeaux** soient dans le périmètre (la lecture peut être
  partielle) ; l'audit est écrit dans l'espace résolu, jamais dans le header brut.
- Rate limiting : `TOURS_RATE_MAX` (30/60 s par défaut en production, appliqué aussi à `/aurora` et aux
  régénérations), `PIECES_RATE_UPLOAD_MAX` (30/300 s) et `PIECES_RATE_LECTURE_MAX` (240/60 s) ; désactivé hors
  production sauf réglage explicite. Redis partage les compteurs (script Lua atomique), avec repli mémoire hors Redis.
- CORS : `allow_credentials=False` (auth par en-têtes) ; `APP_ENV=production` refuse `CORS_ORIGINS=*` au démarrage.
- Suppression : pièces, fichiers GridFS, dérivés de conversation et entrées `retours` du Travail sont purgés.
- Mongo du compose de démonstration est **local** (127.0.0.1, sans auth). Pour un déploiement partagé :
  `docker compose --env-file .env.prod -f docker-compose.prod.yml up -d` (Mongo `--auth`, Redis mot de passe,
  Postgres, ports en boucle locale) ; copier `.env.prod.example` vers `.env.prod` et renseigner les secrets.
- `starlette>=1.6,<2` est requis par le middleware de limite de corps ; les embeddings
  utilisent Bedrock ou OpenAI et sont stockés en `double precision[]`. Sans provider, le
  retrieval reste lexical + graphe ; pgvector reste une option d’infrastructure, pas un
  prérequis.

## Canvas des documents

Les documents produits par Flore dans un Travail réel (`livrables`) apparaissent dans **Résultats** : un clic
ouvre le Canvas avec le Markdown du livrable, copiable, téléchargeable et affichable en plein écran. Un livrable
déposé pendant un tour ouvre le Canvas une fois ; une mise à jour du même livrable rafraîchit la liste sans
réouvrir le Canvas.

## Coût et temps affichés

Chaque réponse de Flore conserve ses **durées** (total, premier mot, phases) et son **usage** (jetons d'entrée,
de sortie, cache) — agent principal, relecture et sous-agents compris. Le message affiche une ligne discrète
`12,4 s · premier mot 1,8 s · 3 245 jetons · ~0,0034 $`, avec le détail des phases au survol.

Le coût est une **estimation** : `JUMEAU_COUT_ENTREE_MILLION` (0,27 par défaut pour DeepSeek),
`JUMEAU_COUT_SORTIE_MILLION` (1,10) et `JUMEAU_COUT_DEVISE` (USD). Mettre les deux tarifs à `0` masque le coût.
Pour Bedrock ou un autre fournisseur, renseigner ses propres tarifs.

## Données de démonstration

Au démarrage, `SEED_VERSION` réinitialise les collections de travail si sa valeur change, puis les jumeaux réels sont projetés. Aucun jeu de démonstration n'est injecté et le bouton « Réinitialiser la démo » a été supprimé avec les personas (ADR-0018).

## API principale

| Endpoint | Rôle |
|---|---|
| `GET /api/mesh` | Mesh complet filtré par périmètre (jumeaux, relations, régions, parcours) |
| `GET /api/jumeaux` · `/api/relations` · `/api/situations` | Collections filtrées RBAC |
| `POST /api/aurora/demander` | Copilote : `{contexte, question, selection, domaine}` → réponse + propositions + commandes carte |
| `GET /api/activite` | Flux d'événements temps réel (simulé) |
| `GET /api/perimetre` | Espace global et autorisations actives |
| `POST /api/commandes/{cid}/import/apercu` | Analyse d'un import CMDB/manifeste avant identité et sources |
| `GET /api/boucle/sources/sante` · `POST /api/boucle/sources/{id}/ingest` | Santé et ingestion manuelle des sources |
| `POST /api/boucle/sources/{id}/webhook` | Accélérateur signé : enfile un run si la branche/dépôt/SHA change |
| `PATCH /api/boucle/sources/{id}/branche` | Change la branche suivie et enfile un run |
| `GET /api/jumeaux/{id}/code-index/resume` · `/coverage` · `/observations` · `/links` | Index de code fédéré et couverture |
| `GET /api/boucle/relations` · `POST /api/boucle/relations/{id}/revue` | Propositions de liens et revue humaine |
| `GET /api/boucle/resolutions` · `POST /api/boucle/resolutions/{id}/revue` · `/enqueter` | Cas non résolus, revue et enquête bornée |
| `GET/POST /api/boucle/intentions` · `POST /api/boucle/intentions/{id}/clore` · `/reporter` | Mémoire prospective |
| `POST /api/boucle/learnings/{id}/reutilisations` · `GET /api/boucle/learnings/metriques` | Réutilisation mesurée des Learnings |
| `POST /api/cases/{cid}/fusion` | Ajout serveur d'une conversation à un Travail (append-only) |
| `POST /api/relations/{id}/confirmer` | Confirmation A2A d'une relation |
| `GET /api/journal` | Journal d'audit (accès, décisions, exports) |

## Tests

```bash
# suite canonique (Postgres requis)
cd backend && JUMEAU_PG_DSN='postgresql://...' .venv/bin/python -m pytest meridian/tests -q

# frontend
cd frontend && CI=true npm test -- --watchAll=false && npm run build
```

`backend/tests/` contient des scripts e2e historiques qui visent un backend externe via
`REACT_APP_BACKEND_URL` ; ils ne font pas partie de la suite locale.

Au 6 novembre 2026, la suite complète donne **2 977 tests passés et 4 ignorés**, hors quatre
tests dépendants de l’environnement (timing heartbeat, quota LLM simulé, données `demo` et
périmètre de naissance).

## Documentation

- **État actuel, composants, Twin, cognition, mémoire et dettes :**
  [docs/architecture/etat-actuel.md](docs/architecture/etat-actuel.md)
- **Écarts avec la vision, objet par objet et étape par étape :**
  [docs/architecture/ecarts-vision.md](docs/architecture/ecarts-vision.md)
- **Architecture cible AWS (performance et agentique) :**
  [docs/architecture/architecture-cible-aws.md](docs/architecture/architecture-cible-aws.md)
- **Laboratoire AWS local Floci :**
  [docs/architecture/floci-aws-local.md](docs/architecture/floci-aws-local.md)
- **Index de la documentation :** [docs/README.md](docs/README.md)
- **Découverte des liens et boucle agentique :**
  [docs/architecture/decouverte-liens-agentique.md](docs/architecture/decouverte-liens-agentique.md)
- **ADR :** [docs/adr/README.md](docs/adr/README.md)
- **Architecture maître :**
  [docs/MERIDIAN_Architecture_Master_v1.md](docs/MERIDIAN_Architecture_Master_v1.md)
- **Diagrammes :** [docs/diagrammes/README.md](docs/diagrammes/README.md)

## Reste à faire

La liste détaillée, avec critères d’acceptation, est dans
[docs/architecture/etat-actuel.md](docs/architecture/etat-actuel.md), section « Reste à faire ».
Les écarts produit par rapport à la vision sont dans
[docs/architecture/ecarts-vision.md](docs/architecture/ecarts-vision.md).

### P0 — avant pilote réel

- unification du chemin live (Travail/Actualités) et de la boucle canonique en une seule chaîne
  Situation → Investigation → Décision → Initiative → Outcome → Learning ;
- corpus de production labellisé + shadow mode ;
- activation RLS et validation des workers multi-tenant ;
- déploiement supervisé des workers source/outbox/travail/réconciliation ;
- validation des connecteurs live (ServiceNow, Datadog, gateway, portail) ;
- installation et mesure de CBM dans l’environnement cible.

### P1 — qualité et couverture

- enregistrement automatique des réutilisations de Learnings depuis les Context Packs ;
- UI des intentions et des métriques de réutilisation ;
- rewrites d’ingress paramétrés et matrice WebSphere/JNDI ;
- rafraîchissement incrémental des liens à l’échelle ;
- unification des deux chargeurs de fichiers ;
- persistance cognitive unifiée `/boucle/analyser` et `/aurora` ;
- révision traçable des croyances après un outcome ;
- unification du vocabulaire de statut Twin (`PROVISOIRE`/`PROVISIONAL`, `ACTIF`/`CONFIRMED`) ;
- décision sur un store dédié des liens ;
- autres forges (GitLab, Azure DevOps) ;
- mesure de la couverture CBM Go/PHP/Ruby/batch.

### P2 — industrialisation

- connecteurs live portail API et gateway externe ;
- verrou multi-instance du worker de réconciliation ;
- observabilité (métriques, traces, coûts, files) ;
- versionnement formel du schéma Postgres ;
- réduction de la double écriture Mongo/Postgres ;
- performance grands graphes et retrieval ;
- instrumentation de la boucle complète Découvrir → Maturer → Exprimer → Investiguer →
  Décider → Agir → Mesurer → Apprendre.
