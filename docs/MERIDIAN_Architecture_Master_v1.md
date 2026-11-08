# Méridian — Architecture Master

**Version :** 1.0  
**Date :** 2026-11-03  
**Statut :** document de travail canonique proposé  
**Périmètre :** architecture existante, cible, écarts et décisions  
**Public :** architecture, produit, sécurité, développement, exploitation

> Ce document est le point d’entrée unique. Il ne remplace pas les ADR : il les indexe et
> indique ce qui est décidé, proposé, implémenté ou encore manquant.

---

## 0. Règle de lecture

Méridian n’est pas un chatbot documentaire et n’est pas un RAG. C’est un système de
compréhension et de décision d’entreprise :

```text
Sources → Observations → Claims → Preuves → Contexte → Raisonnement → Décision → Outcome
```

Le RAG, les embeddings et GraphRAG sont des **capacités internes de récupération de candidats**.
Ils ne créent ni Claim, ni preuve, ni décision.

### Hiérarchie documentaire

| Rôle | Source canonique |
|---|---|
| Vision et exigences | `docs/prd/PRD-001` à `PRD-004` |
| Décisions durables | `docs/adr/` |
| Architecture maître | ce document |
| Architecture technique détaillée | `docs/MERIDIAN_Technical_Architecture_v1.md` |
| Retrieval et Bedrock | `docs/architecture/rag-bedrock.md` |
| Revue RAG | `docs/architecture/rag-review.md` |
| Cible AWS | `docs/architecture/aws-bedrock-target.md` |
| Revue connecteurs | `docs/architecture/connectors-review.md` |
| Écosystème de ressources tierces | `docs/architecture/ecosysteme-tiers.md` |
| Code legacy | `docs/architecture/legacy-code-coverage.md` |
| Index legacy fédéré | `docs/architecture/legacy-index-federation.md` |
| Analyseurs sémantiques legacy | `docs/architecture/semantic-analyzers.md` |
| Legacy et frameworks | `docs/architecture/legacy-frameworks-reference.md` |
| Pack Java/JEE/Spring | `docs/architecture/java-jee-spring-pack.md` |
| État opérationnel | à remplacer : `docs/cognitive/ETAT.md` est daté |

### Statuts

- **Implémenté** : branché dans un chemin réel et couvert par des tests.
- **Partiel** : présent, mais pas généralisé ou pas encore fiable en production.
- **Proposé** : décision écrite, non acceptée.
- **Cible** : architecturalement voulu, non implémenté.
- **Interdit** : choix explicitement rejeté.

---

## 1. Vision et non-objectifs

### Vision

Méridian doit permettre à une organisation de :

1. découvrir son système d’information ;
2. comprendre les relations, dépendances et contradictions ;
3. décider avec des preuves, des options et des limites ;
4. mesurer les outcomes et réutiliser les learnings ;
5. conserver la gouvernance humaine.

### Non-objectifs

- chatbot généraliste ;
- moteur de Q&A documentaire ;
- vector store comme source de vérité ;
- graphe comme seconde vérité non reconstructible ;
- agent qui décide seul d’une action sensible ;
- prompt géant comme substitut à un modèle de données.

---

## 2. Principes

- **P-01** — Le workflow possède les états, gates et budgets ; le modèle propose.
- **P-02** — La profondeur de raisonnement est proportionnée.
- **P-03** — Une proposition n’est pas un fait.
- **P-04** — Une clarification n’est posée que si elle change la réponse.
- **P-05** — La critique est indépendante.
- **P-06** — Toute affirmation importante est liée à une preuve ou marquée hypothèse.
- **P-07** — L’humain gouverne.
- **P-08** — Le fournisseur de modèle est remplaçable.
- **P-09** — Le contexte est borné, filtré et traçable.
- **P-10** — Le retrieval produit des candidats, pas des vérités.

---

## 3. Contexte système

### Acteurs

- analyste, architecte, product owner, développeur, scrum master, directeur ;
- risk / conformité, finance, support, data steward ;
- administrateur de la plateforme.

### Systèmes

- sources de code : GitHub, dépôts Git ;
- documentation : Confluence, SharePoint ;
- trajectoire : Jira, Azure DevOps, Linear ;
- incidents : ServiceNow, Datadog, OTLP ;
- données : PostgreSQL, sources métier ;
- modèles : Bedrock en cible AWS ; DeepSeek/OpenAI en local ou pilote.

### Frontière

Méridian **observe** les systèmes ; il ne les remplace pas.  
Une écriture externe passe par un outil gouverné, une autorisation et un audit.

---

## 4. Architecture logique

Méridian est un **monolithe modulaire hexagonal**.

```text
┌─────────────────────────────────────────────────────────────┐
│ Frontend React : Aujourd'hui, Atlas, Travaux, Cognition,   │
│ Boucle, Administration, Préférences                         │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTP / SSE
┌──────────────────────────────▼──────────────────────────────┐
│ Inbound HTTP : legacy, cases, cognitif, raisonnement,       │
│ sources, planification, runs, boucle, flux, pièces          │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│ Application : noyau de raisonnement, analyse, dialogue,    │
│ cadrage, retrieval, composition, exécution, planification   │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│ Domaine : dossier, demande, cadre, preuve, Claim, graphe,   │
│ profils, méthodes, compétences, planification, valeur       │
└──────────────────────────────┬──────────────────────────────┘
                               │ ports
┌──────────────────────────────▼──────────────────────────────┐
│ Adapters : Postgres, Mongo, Neo4j, Redis, S3, LLM,          │
│ connecteurs, workers, DeepSeek, Bedrock                     │
└─────────────────────────────────────────────────────────────┘
```

### Règle de dépendance

Le domaine n’importe ni FastAPI, ni Strands, ni boto3, ni Neo4j, ni psycopg.  
Les adapters traduisent ; ils ne portent pas la politique métier.

---

## 5. Modèle d’entreprise

### Objets

- Twin — identité d’une application ou d’une entité d’entreprise ;
- Source — système ou artefact observé ;
- Observation — ce qui est lu ;
- Claim — connaissance formalisée, temporelle et contestable ;
- Preuve — soutien, contradiction ou contexte d’un Claim ;
- Situation — signal, incident, changement, découverte ;
- Investigation — travail de compréhension ;
- Décision — arbitrage humain ;
- Initiative — action engagée ;
- Outcome — mesure observée ;
- Learning — enseignement réutilisable ;
- Valeur — hypothèse, baseline, cible, mesure, attribution.

### Autorité

| Objet | Autorité |
|---|---|
| Claim | agent proposition, humain validation |
| Preuve | immuable, source versionnée |
| Décision | humaine |
| Action | humaine + politique + audit |
| Learning | issue d’un outcome, réutilisation traçable |

---

## 6. Topologie runtime

### API

- FastAPI, point d’entrée `backend/server.py` ;
- routes montées sous `/api` ;
- auth locale/demo/proxy/OIDC ;
- SSE pour les tours et événements.

### UI

- React, routes dans `frontend/src/App.js` ;
- contextes `mesh`, `perimetre`, `contexte`, `evenements` ;
- pages Aujourd'hui, Atlas, Travaux, Cognition, Boucle, Administration, Préférences.

### Workers

- `source_worker` — ingestion pull-first ;
- `outbox_worker` — projection graphe ;
- `execution_worker` — runs durables ;
- `travail_worker` — synchronisation Travail ;
- `planification_worker` — synchronisation capacité/charge.

### Stores

| Store | Usage | Autorité |
|---|---|---|
| PostgreSQL | Claims, preuves, décisions, mémoire, exécution, planification, chunks, communautés | canonique pour la connaissance |
| Mongo | Travail historique, relations legacy, situations de démonstration | legacy / read model |
| Neo4j | topologie du Mesh | projection cible |
| Redis | SSE, verrous, limiteurs | état partagé |
| S3/GridFS/local | pièces et artefacts | stockage binaire |
| Vault (principal) / Secrets Manager (optionnel) | secrets | externe |

---

## 7. Flux de connaissance

```text
Source
→ ingestion (worker)
→ lecture normalisée
→ observations
→ Claims + preuves
→ découverte d’interfaces
→ projection graphe
→ situations
→ Travail / décision
```

### Règles

- une source ne devient jamais un Claim sans extraction traçable ;
- une preuve est versionnée ;
- une relation du graphe est une projection ou une observation, pas une vérité inventée ;
- un changement de version peut produire une situation ;
- une décision humaine peut produire une initiative et un outcome.

---

## 8. Retrieval, RAG et GraphRAG

### Contrat

```text
Question + état de dialogue
→ RetrievalService
→ candidats : Claims, preuves, mémoire, documents, communautés
→ filtrage tenant / ACL / version
→ scoring hybride
→ ContextePack borné
→ modèle
→ réponse + citations + gates
```

### As-built

- **Chat Travail** : `adapters/outbound/retrieval_chat.py` agrège mémoire, documentation et
  graphe/communautés.
- **Documentation** : `postgres/documentation.py` cherche Confluence/SharePoint, indexe des
  chunks et appelle `chunk_store`.
- **Chunks** : `document_chunk` avec texte, locator, version, ACL, embedding optionnel.
- **Embeddings** : Bedrock Titan/Cohere ou OpenAI ; sans provider, lexical seul.
- **Scoring** : `application/retrieval_hybride.py` combine lexical, cosinus, graphe et fraîcheur.
- **Reranking** : optionnel, Bedrock/Cohere.
- **GraphRAG local** : voisins de Twins jusqu’à profondeur 2.
- **GraphRAG global** : communautés hiérarchiques par label propagation, rapports précompilés,
  `graph_community`, script `scripts/calculer-communautes.py`.
- **UI** : panneau « Contexte retrouvé » avec documents, scores, mémoire, graphe global.

### Limites connues

- `/analyser` utilise désormais le même port de documentation/communautés, mais pas encore la même
  façade de dialogue ;
- pas de pgvector/ANN : scan borné en Python ;
- `ACL_STRICT=0` par défaut ;
- ACL natives Confluence/SharePoint non synchronisées ;
- communautés sans ACL ;
- indexation et communautés par scripts, pas workers planifiés ;
- dimension d’embedding stockée, mais pas encore de migration/contrôle de ré-embedding complet ;
- `recherche_refutation` corrigé pendant la revue.

### Décisions

- ADR-0021 — Retrieval unifié ;
- ADR-0022 — Graphe projection Postgres ;
- ADR-0023 — ACL fail-closed ;
- ADR-0024 — Cycle de vie embeddings ;
- ADR-0025 — GraphRAG local/global.

Ces ADR sont **proposed** : ils ne sont pas encore acceptés.

---

## 9. Flore et dialogue

### Composants

- `application/dialogue.py` : actes, références, sujet, entités, corrections ;
- `application/cadrage_conversationnel.py` : slots, une question à la fois, inférence après budget ;
- `domain/cadrage.py` : état explicite, slots et provenance ;
- `domain/dialogue.py` : état de fil ;
- `cases.py` : session par Travail, persistance, retrieval ;
- `orchestrateur.py` : agent Strands, outils, budget ;
- `noyau_raisonnement.py` : qualification, cadre, plan, gates, dossier.

### Comportement

- un tour = une question, un état, un dossier ;
- une clarification ne redemande pas ce qui est déjà répondu ;
- une correction remplace explicitement l’hypothèse précédente ;
- une référence (« en », « lesquels ») utilise les entités actives ;
- une session de Travail est partagée, avec verrou Redis et attribution des interlocuteurs.

### Limites

- détection d’actes encore heuristique ;
- pas de résumé de conversation évalué ;
- pas de multi-utilisateurs concurrent complet ;
- pas de trace de chaîne de pensée privée — volontaire.

---

## 10. Agents, outils, exécution

### Agents

- Flore orchestratrice ;
- jumeaux mobilisés ;
- spécialistes indépendants : preuve, impact, risque, critique, découverte ;
- gardien de jumeau ;
- juge / critique croisée.

### Outils

- harness capacitaire à manifestes ;
- budget d’appels ;
- audit ;
- outils read-only par défaut ;
- écritures soumises à approbation ;
- ToolGateway pour l’exécution externe.

### Limites

- `EXECUTION_TOOLS`/`EXECUTION_ALLOWLIST` à configurer ;
- MCP/OpenAPI découverts mais `tools/call` non exécuté ;
- critique croisée conditionnelle ;
- orchestration encore partiellement mono-tour.

---

## 11. Sécurité, tenant, auth

### Auth

- `AUTH_MODE=demo|local|proxy|oidc` ;
- local : cookie HttpOnly, bcrypt, invitations ;
- proxy/OIDC : identité vérifiée, tenant issu de l’identité ;
- pas de SSO/OIDC actif dans le pilote.

### Tenant et ACL

- tenant de requête prioritaire ;
- `ACL_STRICT=1` en production ;
- ACL par chunk, rôle, utilisateur, espace ;
- RLS opt-in ;
- documents live filtrés avant prompt ;
- pas d’ACL native Confluence/SharePoint.

### Risques bloquants production

- ACL absente par défaut ;
- résidence des données si DeepSeek/OpenAI ;
- injection de prompt via documents/web ;
- rétention/suppression non unifiée ;
- audit de retrieval incomplet ;
- `/vision` sans ACL métier.

---

## 12. AWS et Bedrock

### Cible

- Bedrock uniquement dans le profil bancaire ;
- `ca-central-1` par défaut ;
- VPC privé, PrivateLink ;
- RDS Postgres, Neptune/Neo4j, S3, SQS/EventBridge, Vault (principal), KMS, CloudWatch ; Secrets Manager en adaptateur optionnel ;
- ECS/Fargate ou EKS pour API, UI, workers ;
- AgentCore possible plus tard, pas obligatoire.

### Routage multi-modèles

```json
{
  "chat": "…",
  "fast": "…",
  "judge": "…",
  "vision": "…",
  "embedding": "amazon.titan-embed-text-v2:0",
  "rerank": "…"
}
```

Variables :

```env
JUMEAU_MODELE=bedrock
AWS_PROFILE=meridian-bedrock
BEDROCK_REGION=ca-central-1
BEDROCK_MODELES='{"chat":"…","vision":"…","embedding":"…","rerank":"…"}'
WEB_PROVIDER=none
```

### Deux étapes

1. machine préparatoire avec profil AWS, Bedrock seul ;
2. AWS complet, réseau privé et workers managés.

### Cible consolidée

L’architecture AWS de référence pour la performance et les services agentic est
[architecture-cible-aws.md](architecture/architecture-cible-aws.md) : chemins chaud
et froid, SLO, choix de services, dimensionnement et migration en trois étapes.

### Laboratoire local

[Floci](architecture/floci-aws-local.md) porte la plomberie AWS locale : S3, SQS,
EventBridge, Scheduler, Secrets Manager (adaptateur optionnel), KMS, CloudWatch Logs
et IAM, avec Terraform et un smoke des adapters. Vault reste le coffre principal,
hors Floci. Il ne valide pas Bedrock : son runtime est un stub/proxy.

### À faire

- déploiement VPC/IAM ;
- coûts et p95 ;
- tests live ;
- migration des workers ;
- suppression des derniers chemins DeepSeek en AWS.

---

## 13. Opérations et observabilité

### Workers

- ingestion ;
- outbox ;
- exécution ;
- Travail ;
- planification ;
- index documentaire (à créer) ;
- communautés (à créer).

### Observabilité

- durées par phase ;
- usage modèle ;
- audit outils ;
- SSE ;
- scores de retrieval exposés dans la réponse ;
- pas encore de tableau de bord recall/groundedness.

### Runbooks

- `docs/architecture/projection-graphe.md`
- `docs/architecture/rls.md`
- `docs/architecture/ingestion-continue.md`
- `docs/architecture/stockage-pieces.md`
- `docs/architecture/travail-migration.md`

---

## 14. Évaluation

### Existant

- tests unitaires ;
- tests d’architecture ;
- jeu d’or outils/Claims/décisions ;
- scénarios de dialogue ;
- tests RLS ;
- tests design-diagram.

### Manquant

- benchmark multi-tours réel ;
- recall/précision de retrieval ;
- groundedness ;
- fuite ACL ;
- coût et latence ;
- calibration des communautés ;
- régression sur corpus client.

---

## 15. Matrice as-built

| Capacité | État | Preuve |
|---|---|---|
| Auth locale | implémenté | routes `/api/auth`, tests |
| Auth OIDC/proxy | partiel | middleware, pas de live |
| Travail persistant | implémenté | Mongo/Postgres, tests |
| Ingestion pull-first | implémenté | `source_worker` |
| Claims/preuves | implémenté | Postgres, tests |
| Graphe | partiel | Neo4j optionnel, projection |
| RAG documents | partiel | Confluence/SharePoint, chunks, embeddings |
| GraphRAG local | implémenté | voisins, boost |
| GraphRAG global | partiel | script, rapports, pas worker |
| Dialogue | implémenté | actes, cadrage, session |
| Préférences | implémenté | API + page |
| Bedrock | préparé | routeur, adapters, pas live |
| DeepSeek Search/Fetch/Vision | implémenté | test réel |
| ACL | partiel | chunks, strict off |
| RLS | opt-in | script, pas activé |
| pgvector/ANN | absent | scan Python |
| Workers index/communautés | absent | scripts manuels |

---

## 16. Écarts vs vision

| Vision | Écart | Priorité |
|---|---|---|
| Preuve homogène | chat et `/analyser` diffèrent | P0 |
| Graphe reconstructible | ADR-0007/0013/0022 non tranché | P0 |
| ACL fail-closed | défaut permissif | P0 |
| Retrieval unifié | deux politiques | P0 |
| RAG à l’échelle | pas d’ANN | P1 |
| GraphRAG global | pas de worker/ACL | P1 |
| AWS bancaire | non déployé | P1 |
| Évaluation retrieval | absente | P1 |
| Multi-utilisateurs | partiel | P2 |

Ce tableau couvre les écarts **techniques**. Les écarts **produit** — boucle vivante, objets de
la vision, surfaces, experts, mémoire de transformation — sont détaillés dans
[ecarts-vision.md](architecture/ecarts-vision.md).

---

## 17. ADR et décisions

| ADR | Sujet | Statut |
|---|---|---|
| 0001 | identité typée | accepted |
| 0005 | modèle d’entreprise | accepted |
| 0007 | Postgres + graphe | accepted, contredit 0013 |
| 0013 | projection graphe | accepted |
| 0010 | hexagonal | accepted |
| 0014 | AWS sans lock-in | accepted |
| 0015 | frontière agent/workflow | accepted |
| 0019 | planification | accepted |
| 0020 | rôles/lentilles | accepted |
| 0021 | retrieval unifié | proposed |
| 0022 | graphe projection | proposed |
| 0023 | ACL fail-closed | proposed |
| 0024 | embeddings | proposed |
| 0025 | GraphRAG | proposed |

### Décision urgente

Trancher **ADR-0022** puis amender ADR-0007/PRD-001.  
Sans cela, le graphe reste à deux vérités.

---

## 18. Documentation governance

### Rôles

- **Constitution** : AGENTS/CLAUDE, règles de contribution ;
- **Map** : ce document ;
- **Status** : à remplacer, `docs/cognitive/ETAT.md` est daté ;
- **History** : `docs/adr/`.

### Règles

- une seule source canonique par fait ;
- un ADR accepté est immuable ;
- toute correction de doc est datée ;
- un document obsolète est marqué, pas supprimé silencieusement ;
- pas de secret dans les docs.

---

## 19. Roadmap de convergence

1. Accepter ADR-0022 et amender 0007/0013.
2. Unifier `/analyser` et le chat sur un RetrievalService.
3. Passer `ACL_STRICT=1` et tester l’isolation.
4. Ajouter `embedding_dim`, migration et worker de ré-embedding.
5. Ajouter pgvector/ANN.
6. Créer le worker de communautés.
7. Brancher les ACL natives Confluence/SharePoint.
8. Déployer AWS Bedrock et désactiver les providers externes.
9. Mesurer retrieval, coût, latence.
10. Mettre à jour `ETAT` et `README`.

---

## 20. Vérification

```bash
cd backend
set -a; . ./.env; set +a
.venv/bin/python -m pytest meridian/tests -q

cd ../frontend
npm test -- --watchAll=false --runInBand
npm run build
```

Commandes cibles :

```bash
backend/.venv/bin/python scripts/indexer-documentation.py --tenant local
backend/.venv/bin/python scripts/synchroniser-acl.py --tenant local
backend/.venv/bin/python scripts/calculer-communautes.py --tenant local
```

---

## 21. Glossaire

- **Twin** — entité d’entreprise observée.
- **Claim** — connaissance formalisée, temporelle, contestable.
- **Preuve** — artefact versionné soutenant ou contredisant.
- **ContextePack** — contexte borné et empreinté.
- **Dossier** — trace de raisonnement.
- **GraphRAG local** — retrieval autour d’entités du graphe.
- **GraphRAG global** — synthèse de communautés.
- **ACL** — autorisation d’accès.
- **RLS** — Row-Level Security Postgres.

---

## 22. Questions ouvertes

1. Twin = application uniquement, ou types non applicatifs ?
2. Graphe projection ou propriétaire de la topologie ?
3. Store de mémoire durable ?
4. Seuil de bascule pgvector/ANN ?
5. ACL natives ou ACL de source ?
6. Politique de rétention des chunks et communautés ?
7. Quel modèle Bedrock pour quel rôle ?
8. Quel niveau de détail exposer dans l’UI de retrieval ?
