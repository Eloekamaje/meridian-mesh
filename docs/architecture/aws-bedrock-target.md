# Cible AWS et Bedrock — architecture de préparation

## Décision directrice

Méridian reste un **système de raisonnement et de preuve**. Bedrock est le fournisseur de modèles
de l'écosystème AWS ; le RAG, les embeddings et GraphRAG restent des capacités internes.

Aucun appel DeepSeek/OpenAI ne doit subsister dans le profil AWS bancaire.

## Deux étapes

### Étape A — machine préparatoire avec profil AWS

- même code, même dépôt ;
- credentials par `AWS_PROFILE` / rôle IAM de la machine ;
- Bedrock uniquement ;
- Postgres/Neo4j locaux ou managés hors AWS ;
- objectif : valider les modèles, embeddings, vision et coûts avant migration.

### Étape B — AWS

- VPC privé, sous-réseaux privés ;
- ECS/Fargate ou EKS pour API, UI et workers ;
- RDS Postgres, Neptune ou Neo4j managé pour la projection ;
- S3 pour pièces et artefacts ;
- SQS/EventBridge pour outbox et ingestion ;
- Secrets Manager + KMS ;
- CloudWatch, X-Ray/OTel, CloudTrail ;
- Bedrock via endpoint VPC/PrivateLink.

## Routage multi-modèles Bedrock

Un rôle, un modèle, une région :

```json
{
  "chat": "anthropic.claude-...",
  "fast": "amazon.nova-lite-...",
  "judge": "anthropic.claude-...",
  "vision": "amazon.nova-pro-...",
  "embedding": "amazon.titan-embed-text-v2:0",
  "rerank": "cohere.rerank-..."
}
```

Variable :

```env
JUMEAU_MODELE=bedrock
AWS_PROFILE=meridian-bedrock
BEDROCK_REGION=ca-central-1
BEDROCK_MODELES='{"chat":"...","fast":"...","judge":"...","vision":"...","embedding":"amazon.titan-embed-text-v2:0","rerank":"..."}'
WEB_PROVIDER=none
```

Le routeur ne choisit pas le modèle à la place du produit : il résout un rôle demandé par le
workflow (chat, juge, vision, embedding, rerank). La politique de sensibilité peut imposer un
modèle/région ; elle ne doit jamais élargir les droits.

## Réseau et sécurité

- Aucun accès public aux bases ni à Bedrock ;
- VPC endpoints : Bedrock, S3, Secrets Manager, KMS, CloudWatch ;
- IAM least privilege : `bedrock:InvokeModel`, `bedrock:Converse` sur les ARN des modèles ;
- pas de clé API dans les variables d'environnement AWS ;
- chiffrement KMS au repos et TLS en transit ;
- journaux d'audit sans contenu sensible ;
- résidence canadienne : `ca-central-1` par défaut.

## Données

| Donnée | Store cible |
|---|---|
| Identité, Claims, preuves, décisions | RDS Postgres |
| Topologie | Neptune/Neo4j, projection Postgres |
| Chunks, embeddings, communautés | RDS Postgres + pgvector si activé |
| Pièces et artefacts | S3 |
| Sessions et événements | Redis/ElastiCache + SQS |
| Secrets | Secrets Manager |

## Workers

- ingestion/source worker ;
- document index worker : backfill et ré-indexation ;
- community worker : recalcul des communautés ;
- outbox worker : projection graphe ;
- exécution des runs : ECS service séparé.

Chaque worker est idempotent, tenant-scopé, et peut tourner sans l'API.

## Ce qui est interdit

- DeepSeek ou OpenAI dans le profil bancaire AWS ;
- web DeepSeek sans `WEB_PROVIDER=deepseek` explicite ;
- embeddings mélangés sans version ;
- graphe comme seconde vérité ;
- chunks sans ACL ;
- RAG global calculé à la volée ;
- clé API Bedrock dans Git ou dans un prompt.

## Critères de bascule

1. Tous les appels modèles passent par Bedrock en `ca-central-1`.
2. Un test d'isolation tenant/ACL passe.
3. Un backfill complet et un rejeu de communautés passent.
4. Les workers tournent sans l'API.
5. Les coûts et latences p95 sont mesurés.

## Accès réel constaté (2026-11-06, `ca-central-1`)

Le câblage Bedrock a été exercé avec un compte AWS réel. Les embeddings Titan V2
fonctionnent. Pour le chat, l'accès dépend fortement du modèle et du compte :

| Modèle | `Converse` | `ConverseStream` | Tool use streaming |
|---|---|---|---|
| `amazon.titan-embed-text-v2:0` | ✅ (embeddings) | — | — |
| `ca.amazon.nova-lite-v1:0` | ✅ | ✅ | ✅ |
| `anthropic.claude-3-sonnet-20240229-v1:0` | ✅ | ❌ formulaire d'usage Anthropic | — |
| `anthropic.claude-3-haiku-20240307-v1:0` | ⚠️ instable (un appel a réussi, puis formulaire d'usage) | ❌ | — |
| `ca.anthropic.claude-haiku-5-5` | ❌ instrument de paiement Marketplace | ❌ | — |
| `mistral.mistral-large-2402-v1:0` | ✅ | ✅ | ❌ |
| `meta.llama3-70b-instruct-v1:0` | ✅ | ✅ | ❌ |

Un second compte, profil `meridian-bedrock` (compte `267949810690`), est en cours de
vérification AWS. Son plan de contrôle répond et le runtime est partiellement accessible :
Titan embeddings, Mistral Large et le streaming Nova Lite fonctionnent ; certains appels
`Converse` échouent encore avec « Your account is currently being verified » (moins de
2 heures annoncées), et le streaming Anthropic reste bloqué par le formulaire d'usage.
Il faut attendre la fin de la vérification avant de conclure.

Mistral Large est la meilleure alternative canadienne sans Claude : il supporte le tool
use en `Converse` non-streaming, et `agent.py` le bascule automatiquement dans ce mode.
Mais dans l'agent Flore complet, il émet parfois les appels d'outils en texte JSON au
lieu de blocs `toolUse` ; il faut adapter le prompt ou forcer/parser les appels avant de
le retenir comme orchestrateur. Llama/Mixtral ne supportent pas le tool use via Bedrock
`Converse`.

Les modèles **GPT-OSS** (`openai.gpt-oss-120b-1:0`, `openai.gpt-oss-20b-1:0`) sont
disponibles en `us-east-1` en `ON_DEMAND`, avec `Converse`, `ConverseStream` et tool use.
Ils sont **absents de `ca-central-1`** : ils ne conviennent pas au profil bancaire
canadien, mais servent de banc d'essai de qualité hors résidence (79 % de critères
déterministes, 67 % au juge). Les GPT propriétaires (GPT-5/6) ne sont pas accessibles au
compte. En `us-east-1`, les profils `ca.*` sont invalides et les anciens
`claude-3-sonnet`/`claude-3-haiku` sont en fin de vie ; les modèles de chat utilisables
sont Mistral Large, Llama 70B et GPT-OSS.

**Kimi K3** (`us.moonshotai.kimi-k3` / `global.moonshotai.kimi-k3`) est accessible et
outillé, mais n'a **pas de profil canadien** : `us.`/`global.` routent hors Canada. Il
donne 9/11 (82 %) aux critères déterministes et 8/11 au juge, avec une latence de **87 s
en moyenne** (jusqu'à 3,5 min) : qualité réelle, mais incompatible avec un chat temps
réel. Voir `plugin/meridian/evals/conversations/PILOT-2026-11-06-kimi-k3-us-east-1.md`.

La **comparaison équitable** (juge unique Mistral Large, 3×11 runs pour DeepSeek/GPT-OSS/
Nova Lite, 1×11 pour Kimi, température 0 quand le modèle l'accepte) donne : DeepSeek
33/33 (100 %) et 29/33 au juge, Kimi 11/11 et 10/11 (101 s), GPT-OSS 24/33 (73 %) et
26/33 (79 %), Nova Lite 16/33 (48 %) et 21/33 (64 %). Voir
`plugin/meridian/evals/conversations/PILOT-2026-11-06-equitable.md`. Les modèles GPT propriétaires (GPT-5/6) ont
un accès intermittent (`INVALID_PAYMENT_INSTRUMENT` sur le profil `default`, absents du
profil `meridian-bedrock`) : ils ne sont pas retenus pour un benchmark reproductible.

Conséquences :

- le formulaire d'usage Anthropic et l'instrument de paiement Marketplace doivent être
  réglés côté compte AWS avant de retenir un modèle Anthropic comme chat principal ;
- les modèles Mistral/Llama ne savent pas faire de tool use en streaming, donc ils ne
  conviennent pas à l'agent Flore ;
- les profils `global.*` et `us.*` routent hors Canada et ne doivent pas être utilisés
  pour le profil bancaire canadien ;
- Floci ne peut pas valider cette matrice : son Bedrock Runtime est un stub. Voir
  [`floci-evaluation.md`](floci-evaluation.md).

Détail du pilote et résultats :
[`plugin/meridian/evals/conversations/PILOT-2026-11-06-bedrock.md`](../../plugin/meridian/evals/conversations/PILOT-2026-11-06-bedrock.md).
