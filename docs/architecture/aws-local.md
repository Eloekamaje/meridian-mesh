# Vérifier les adapters AWS sans compte AWS

Les adapters `meridian/adapters/outbound/aws/adapters.py` reçoivent un client boto3 injecté. boto3 n'est
chargé qu'au premier appel réel. Les tests unitaires existants utilisent des clients factices ; le harness
ci-dessous ajoute une vérification de bout en bout contre moto, sans credentials ni appel réseau.

Services couverts : Secrets Manager (`GetSecretValue`), SQS (`SendMessage`), EventBridge (`PutEvents`) et
EventBridge Scheduler (`CreateSchedule` / `UpdateSchedule`).

## Option 1 — moto en mémoire (recommandée)

```bash
cd backend
.venv/bin/pip install 'moto[server]>=5,<6'
cd ..
backend/.venv/bin/python scripts/aws-local-smoke.py
```

Sortie attendue : quatre lignes `[ok]` puis `Harness local validé (4/4)`. Le script crée un secret, une file
SQS, un bus EventBridge et un schedule, puis passe par les adapters Méridian, pas par boto3 directement.

Tests automatisés (les tests moto sont ignorés si moto est absent) :

```bash
cd backend
set -a; . ./.env; set +a
.venv/bin/python -m pytest meridian/tests/test_aws_adapters.py meridian/tests/test_aws_adapters_local.py -q
```

## Option 2 — moto_server ou LocalStack, opt-in

Aucun service n'est ajouté au compose par défaut.

```bash
scripts/dev-aws-local.sh                # moto_server sur http://127.0.0.1:5000
scripts/dev-aws-local.sh --localstack   # LocalStack sur http://127.0.0.1:5000 (Docker requis)
```

Dans un autre terminal :

```bash
export AWS_ACCESS_KEY_ID=local AWS_SECRET_ACCESS_KEY=local AWS_DEFAULT_REGION=ca-central-1
export AWS_ENDPOINT_URL=http://127.0.0.1:5000
backend/.venv/bin/python scripts/aws-local-smoke.py --endpoint "$AWS_ENDPOINT_URL"
```

Variables d'endpoint lues par les adapters : `AWS_ENDPOINT_URL`, ou par service
`AWS_ENDPOINT_URL_SECRETS_MANAGER`, `AWS_ENDPOINT_URL_SQS`, `AWS_ENDPOINT_URL_EVENTS`,
`AWS_ENDPOINT_URL_SCHEDULER`. En production, ne pas définir ces variables.

## Passage sur un vrai compte AWS

Checklist avant de brancher Méridian :

- **Région** : `JUMEAU_AWS_REGION` (ou `AWS_REGION`) identique pour Secrets Manager, SQS, EventBridge,
  Scheduler et l'ARN cible. Retirer tout `AWS_ENDPOINT_URL*` et les credentials factices.
- **Identité** : rôle ou utilisateur avec `secretsmanager:GetSecretValue`, `sqs:SendMessage`,
  `events:PutEvents`, `scheduler:CreateSchedule`, `scheduler:UpdateSchedule`, `scheduler:GetSchedule`,
  `scheduler:DeleteSchedule`, et `iam:PassRole` sur le rôle du scheduler.
- **Secrets Manager** : créer le secret, idéalement en JSON (`{"jeton": "..."}`). La référence
  `aws:<secret-id>#<champ>` lit un champ ; `secretsmanager:<secret-id>` rend le `SecretString` brut. Vérifier
  aussi `kms:Decrypt` si le secret utilise une clé gérée par le client.
- **SQS** : file standard ou FIFO. Pour FIFO, `JUMEAU_SQS_QUEUE_URL` doit finir par `.fifo` ; l'adapter ajoute
  `MessageGroupId`. Vérifier la policy de file et, si utilisé, la DLQ.
- **EventBridge** : le bus `JUMEAU_EVENTBRIDGE_BUS` doit exister dans la même région. Sinon l'adapter bascule
  sur SQS dès qu'une URL de file est fournie.
- **Scheduler** : le groupe (`JUMEAU_SCHEDULER_GROUP`) doit exister. Le rôle
  `JUMEAU_SCHEDULER_ROLE_ARN` doit faire confiance à `scheduler.amazonaws.com` et autoriser l'invocation de la
  cible `JUMEAU_SCHEDULER_TARGET_ARN` (par exemple `sqs:SendMessage`). `next_run_at` reste tenu par Postgres :
  le schedule AWS ne fait que réveiller le worker.
- **Vérification** : `aws sts get-caller-identity`, puis un `get-secret-value`, un `send-message`, un
  `put-events` et un `get-schedule` sur les ressources créées. Le smoke local valide le code des adapters, mais
  l'installation IAM, les ARN et les policies restent à vérifier sur le compte réel.
