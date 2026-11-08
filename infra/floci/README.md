# Infrastructure AWS locale — Floci

Ce stack Terraform crée la plomberie AWS de Méridian dans Floci :

- S3 : pièces, index, sessions ;
- SQS : outbox + DLQ, réveil des sources ;
- EventBridge : bus `meridian`, règle outbox → SQS ;
- EventBridge Scheduler : groupe `meridian`, rôle `meridian-scheduler` ;
- IAM : `meridian-task`, `meridian-scheduler` ;
- Secrets Manager : `meridian/local` (adaptateur optionnel ; Vault reste le coffre principal) ;
- KMS : `alias/meridian-local` ;
- CloudWatch Logs : API, workers, ingestion.

Depuis la racine du dépôt :

```bash
scripts/dev-floci.sh up
eval "$(scripts/dev-floci.sh env)"
scripts/dev-floci.sh smoke
```

Le state reste local (`terraform.tfstate`, ignoré par Git). Ne pas appliquer ce stack
sur un compte AWS réel : il est configuré pour l'endpoint Floci et des credentials
factices. Le runbook et les limites sont dans
[`docs/architecture/floci-aws-local.md`](../../docs/architecture/floci-aws-local.md).
