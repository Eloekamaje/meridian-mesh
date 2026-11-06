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
