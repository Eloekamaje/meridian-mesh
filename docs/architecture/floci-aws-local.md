# Floci — laboratoire AWS local pour Méridian

> **Statut :** laboratoire de développement et de CI, pas une production.
> **Floci testé :** `2.4.0`, image `floci/floci:latest`.
> **Dépôt Floci :** `../floci` à côté de `meridian-mesh` (clone local, pas un submodule).
> **But :** construire et vérifier la plomberie AWS de Méridian sans compte AWS,
> puis basculer vers le compte réel avec les mêmes noms, ARN et variables.
> **Ce n’est pas l’architecture cible :** voir
> [architecture-cible-aws.md](architecture-cible-aws.md) pour les SLO, le compute,
> les données et les services AgentCore.

## 1. Pourquoi Floci

Floci est un émulateur AWS local (MIT) qui expose les services AWS sur
`http://127.0.0.1:4566`. Il accepte les SDK/CLI AWS standards, Terraform, CDK et
OpenTofu. Pour Méridian, il sert à valider :

- les clients boto3 et les endpoints ;
- les noms et ARN des ressources ;
- les policies IAM et les files SQS ;
- le routage EventBridge → SQS ;
- les schedules EventBridge Scheduler ;
- S3, KMS et CloudWatch Logs ;
- Secrets Manager uniquement comme **adaptateur AWS optionnel** ; Vault reste le
  coffre principal, hors Floci ;
- le câblage Terraform de l'architecture AWS locale.

Il ne sert **pas** à valider Bedrock : le runtime est un stub par défaut (ou un proxy
OpenAI-compatible), pas une inférence Bedrock réelle. Voir
[floci-evaluation.md](floci-evaluation.md).

## 2. Ce qui est réellement lié

Le laboratoire réutilise les **mêmes contrats** que la cible AWS :

| Élément | Local Méridian actuel | Floci | Cible AWS |
|---|---|---|---|
| API / workers | Uvicorn, processus | non démarré par ce compose | ECS/Fargate ou EKS |
| Postgres | conteneur `postgres:16` | RDS Docker-backed (optionnel) | RDS Postgres |
| Neo4j | conteneur `neo4j:5` | Neptune avec backend Neo4j (optionnel) | Neptune ou Neo4j managé |
| Mongo | conteneur `mongo:7` | DocumentDB (optionnel) | DocumentDB ou Postgres |
| Redis | conteneur `redis:7` | ElastiCache (optionnel) | ElastiCache |
| Pièces / index / sessions | disque ou MinIO | **S3** | S3 |
| Outbox | Postgres | **SQS direct + EventBridge alternatif** | SQS + EventBridge |
| Réveil des sources | table `timer` | **EventBridge Scheduler** | EventBridge Scheduler |
| Secrets | Vault (`vault:…`) / `env:` | **Secrets Manager (adaptateur optionnel)** | Vault (principal) ; Secrets Manager optionnel |
| Chiffrement | aucun | **KMS** | KMS |
| Logs | stdout | **CloudWatch Logs** | CloudWatch Logs |
| Identité | RBAC applicatif | **IAM roles/policies** | IAM |
| Modèles | DeepSeek/Bedrock | **stub/proxy, non probant** | Bedrock |
| VPC / PrivateLink | non modélisé | **non routé** | VPC privé + endpoints |

Les services **branchés ou testés par le smoke** sont S3, SQS, EventBridge,
Scheduler, Secrets Manager (adaptateur), KMS, CloudWatch Logs et IAM. Le coffre
principal reste **HashiCorp Vault**, hors Floci. Les services Docker-backed
(RDS, Neptune, ECS, EKS) sont disponibles dans Floci mais ne sont pas encore câblés
à Méridian.

## 3. Architecture locale

```text
Méridian (uvicorn / workers)
        │
        │ AWS_ENDPOINT_URL=http://127.0.0.1:4566
        ▼
Floci :4566
  ├── S3          meridian-pieces, meridian-index, meridian-sessions
  ├── SQS         meridian-outbox (+ DLQ), meridian-source-wakeup
  ├── EventBridge meridian (bus) + règle meridian-outbox → SQS
  ├── Scheduler   groupe meridian + rôle meridian-scheduler
  ├── Secrets     meridian/local
  ├── KMS         alias/meridian-local
  ├── Logs        /meridian/api, /meridian/workers, /meridian/ingestion
  └── IAM         meridian-task, meridian-scheduler
```

Le stack provisionne **deux chemins** :

- **SQS direct** : chemin runtime actuel. `publieur_depuis_env` préfère
  `JUMEAU_SQS_QUEUE_URL` dès qu'elle est définie.
- **EventBridge → SQS** : chemin alternatif provisionné et testé par le smoke. La
  règle `meridian-outbox` route les événements `source = meridian` vers la file SQS.
  Pour le sélectionner au runtime, il faudra un consommateur de file distinct ou une
  évolution du publisher, car l'URL SQS reste nécessaire au consommateur.

La topologie AWS cible peut utiliser l'un ou l'autre ; le laboratoire vérifie les deux
câblages sans prétendre que le runtime bascule automatiquement.

## 4. Ressources Terraform

Le stack est dans [`infra/floci`](../../infra/floci). Il crée :

- **S3** : `meridian-pieces`, `meridian-index`, `meridian-sessions`, versionnés,
  configurés avec SSE-KMS, accès public bloqué ;
- **SQS** : `meridian-outbox` avec DLQ `meridian-outbox-dlq`, et
  `meridian-source-wakeup` ;
- **EventBridge** : bus `meridian`, règle `meridian-outbox`, cible SQS ;
- **Scheduler** : groupe `meridian`, rôle `meridian-scheduler` ;
- **IAM** : rôle `meridian-task` (S3, SQS, EventBridge, Secrets, KMS, Logs, Bedrock)
  et rôle `meridian-scheduler` (SQS SendMessage sur la file de réveil) ;
- **Secrets Manager (adaptateur optionnel)** : `meridian/local` avec `jeton` et
  `webhook_secret` locaux ; Vault reste le coffre principal ;
- **KMS** : clé `alias/meridian-local` ;
- **CloudWatch Logs** : groupes API, workers, ingestion.

Le provider Terraform pointe tous les endpoints vers Floci, avec des credentials
factices. Le state reste local et n'est pas versionné.

## 5. Démarrage

Prérequis : Docker, Terraform ≥ 1.6, le venv backend, et le clone Floci à côté du
dépôt.

```bash
# 1. Démarrer Floci
scripts/dev-floci.sh up

# 2. Charger les variables AWS locales
eval "$(scripts/dev-floci.sh env)"

# 3. Vérifier la plomberie
scripts/dev-floci.sh smoke
```

`up` exécute le compose Floci puis `terraform apply`. Le premier apply peut prendre
environ une minute : Floci crée les files SQS de façon asynchrone.

La console Floci est disponible sur <http://127.0.0.1:4500>, ou via
<http://127.0.0.1:4566/_floci/ui> qui démarre le sidecar à la première visite. Le
premier lancement peut prendre quelques secondes (pull de `floci/floci-ui:0.7.0`).
Elle nécessite le socket Docker monté dans `docker-compose.floci.yml`.

Le compose utilise `FLOCI_HOSTNAME=localhost.floci.io` et un alias réseau du même nom :
l'hôte résout ce nom vers `127.0.0.1`, tandis que le sidecar le résout vers Floci dans
le réseau Compose. Ne pas repasser à `FLOCI_HOSTNAME=localhost` : le sidecar ne
pourrait plus joindre le cœur Floci.

## 6. Lancer Méridian contre Floci

```bash
eval "$(scripts/dev-floci.sh env)"

cd backend
set -a; . ./.env; set +a
.venv/bin/uvicorn server:app --host 127.0.0.1 --port 8001
```

Les variables importantes :

| Variable | Valeur Floci |
|---|---|
| `AWS_ENDPOINT_URL` | `http://127.0.0.1:4566` |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | `test` / `test` |
| `JUMEAU_PIECES_STORAGE` | `s3` |
| `JUMEAU_PIECES_S3_BUCKET` | `meridian-pieces` |
| `JUMEAU_INDEX_STORE` | `s3` |
| `JUMEAU_INDEX_BUCKET` | `meridian-index` |
| `JUMEAU_INDEX_SSE` | `aws:kms` |
| `JUMEAU_INDEX_KMS_KEY` | `alias/meridian-local` |
| `JUMEAU_SESSIONS_S3` | `meridian-sessions/flore` |
| `JUMEAU_SQS_QUEUE_URL` | URL de `meridian-outbox` |
| `JUMEAU_EVENTBRIDGE_BUS` | `meridian` |
| `JUMEAU_SCHEDULER_ROLE_ARN` | `arn:aws:iam::000000000000:role/meridian-scheduler` |
| `JUMEAU_SCHEDULER_TARGET_ARN` | ARN de `meridian-source-wakeup` |
| `JUMEAU_SCHEDULER_GROUP` | `meridian` |

Le fichier [`.env.floci.example`](../../.env.floci.example) reprend ces valeurs.

## 7. Ce que le smoke prouve

`scripts/floci-smoke.py` exerce les adapters Méridian, pas seulement boto3 :

1. santé Floci ;
2. buckets S3 ;
3. rôles IAM ;
4. KMS encrypt/decrypt ;
5. `S3Stockage` write/read/delete ;
6. `S3IndexStore` save/restore/delete avec SSE-KMS ;
7. `PublieurSQS` publish/receive/delete ;
8. `PublieurEventBridge` + règle EventBridge → SQS ;
9. `PlanificateurEventBridge` create/update/delete ;
10. `SecretsManager` ;
11. CloudWatch Logs.

Le smoke est idempotent : il nettoie ses objets et supprime son schedule.

## 8. Ce que Floci ne prouve pas

- **Bedrock** : `Converse`/`ConverseStream` sont un stub ou un proxy OpenAI-compatible ;
  `InvokeModel` reste un stub. Aucune preuve de qualité, de tool use, de citations,
  d'embeddings Titan, de résidence `ca-central-1`, de quotas ou de coûts.
- **VPC / PrivateLink** : Floci ne route pas les VPC, NACL, NAT, peering. Les endpoints
  VPC sont des objets de metadata, pas un réseau réel.
- **IAM** : les rôles et policies sont créés, mais les processus locaux ne sont pas
  réellement contraints par IAM. Le contrôle reste applicatif (RBAC/tenant).
- **RDS / Neptune / ECS / EKS** : Docker-backed, mais non câblés à Méridian dans ce
  laboratoire. Le socket Docker est requis.
- **CloudTrail / X-Ray** : non câblés. Utiliser OTel/CloudWatch pour l'observabilité
  locale.
- **Chiffrement S3 par défaut** : Floci accepte la configuration de bucket, mais le smoke
  prouve le SSE-KMS explicite de `S3IndexStore`, pas l'application automatique à tous les
  objets.
- **Multi-tenant réel** : Floci ne remplace pas les tests RLS/ACL de production.

## 9. Passage au compte AWS réel

Le laboratoire est volontairement aligné sur la cible :

1. Conserver les noms de ressources et les ARN (compte/région à substituer).
2. Retirer `AWS_ENDPOINT_URL*` et les credentials `test`.
3. Utiliser un rôle IAM réel (IRSA/ECS task role) au lieu de clés statiques.
4. Créer le VPC privé, les sous-réseaux, les security groups et les endpoints
   PrivateLink (S3, SQS, KMS, CloudWatch, Bedrock) ; connecter Vault par endpoint
   privé, VPN ou peering selon son hébergement.
5. Remplacer le state local par un backend S3/DynamoDB verrouillé.
6. Restreindre `bedrock_model_arns` aux modèles/profils réellement autorisés.
7. Valider Bedrock sur le compte réel, pas via Floci.

Checklist de bascule :

- [ ] `aws sts get-caller-identity` sur le rôle réel ;
- [ ] buckets S3 chiffrés KMS et accès public bloqué ;
- [ ] files SQS + DLQ + policies ;
- [ ] bus EventBridge + règle + cible SQS ;
- [ ] groupe Scheduler + rôle `scheduler.amazonaws.com` ;
- [ ] secret Vault (`vault:…`) lisible par le rôle, ou secret Secrets Manager si
  l’adaptateur optionnel est utilisé ;
- [ ] logs CloudWatch et rétention ;
- [ ] `JUMEAU_INDEX_KMS_KEY` pointe sur la clé réelle ;
- [ ] tests RLS/tenant et Bedrock réels.

## 10. Dépannage

- **`Connection refused` sur 4566** : `scripts/dev-floci.sh start`, puis
  `docker ps --filter name=meridian-floci`.
- **Console bloquée sur « Starting Floci UI »** : vérifier
  `curl http://127.0.0.1:4566/_floci/ui/status`. Si l'erreur mentionne
  `http://localhost:4566`, le sidecar ne joint pas Floci : conserver
  `FLOCI_HOSTNAME=localhost.floci.io` et l'alias réseau, puis recréer le conteneur
  (`docker compose -f docker-compose.floci.yml up -d --force-recreate`). Vérifier
  aussi `docker ps --filter name=floci-aws-ui` et
  `docker logs meridian-floci | grep -i ui`.
- **`QueueUrl` en `localhost.floci.io` alors que le client utilise `127.0.0.1`** :
  Floci renvoie l'hôte configuré par `FLOCI_HOSTNAME`. `localhost.floci.io` résout
  vers `127.0.0.1` sur l'hôte et vers Floci dans le réseau Compose ; les deux
  fonctionnent.
- **Scheduler `ValidationException`** : vérifier `rate(1 minute)` (singulier) et
  l'existence du groupe `meridian` et du rôle `meridian-scheduler`.
- **`NoSuchBucket`** : le stack Terraform n'est pas appliqué ; `scripts/dev-floci.sh apply`.
- **Secret déjà existant** : `terraform apply` est idempotent ; un ancien secret
  laissé par un test manuel doit être supprimé ou importé.
- **Bedrock renvoie une réponse fixe** : c'est le stub Floci, pas un bug Méridian.

## 11. Prochaines étapes

1. **Conteneuriser Méridian** (API, workers, frontend) et ajouter les images à ECR ;
2. créer les task definitions/services ECS/Fargate ou les manifests EKS dans un
   stack séparé, en réutilisant les rôles `meridian-task` et les files déjà créées ;
3. migrer Postgres/Neo4j/Mongo/Redis vers RDS/Neptune/DocumentDB/ElastiCache Floci,
   puis vers les services AWS réels ;
4. ajouter le VPC, les sous-réseaux, les security groups et les endpoints PrivateLink
   dans le stack AWS réel (Floci ne route pas le VPC) ;
5. instrumenter CloudWatch metrics/alarmes et OTel ;
6. valider Bedrock hors Floci, avec le compte et la région canadiens.

## 12. Références Floci

Le clone local contient les sources et la documentation :

- `README.md` — vue d'ensemble, services, SDK, migration LocalStack ;
- `docs/services/s3.md`, `sqs.md`, `eventbridge.md`, `scheduler.md`,
  `secrets-manager.md`, `iam.md`, `kms.md`, `cloudwatch.md` ;
- `docs/services/bedrock-runtime.md` — stub/proxy et limites ;
- `docs/getting-started/terraform.md` — provider AWS + Floci ;
- `compatibility-tests/compat-terraform/` — stack Terraform de compatibilité ;
- `docker-compose.yml` — compose amont (build local).

Pour construire l'image depuis les sources au lieu de tirer l'image officielle :

```bash
scripts/dev-floci.sh build
FLOCI_IMAGE=floci:local scripts/dev-floci.sh up
```

Le clone est cherché dans `../floci` ; `FLOCI_SOURCE_DIR` permet de pointer ailleurs.
