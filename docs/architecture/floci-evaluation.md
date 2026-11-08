# Floci — évaluation pour les tests AWS de Méridian

> **Mise à jour :** Floci est désormais intégré comme **laboratoire AWS local de la
> plomberie** Méridian (S3, SQS, EventBridge, Scheduler, Secrets, KMS, Logs, IAM).
> Voir [floci-aws-local.md](floci-aws-local.md). La conclusion sur Bedrock reste
> inchangée : Floci ne valide pas les modèles.

## Ce que c'est

[Floci](https://github.com/floci-io/floci) est un émulateur AWS local sous licence MIT,
présenté comme un remplacement direct de LocalStack : un conteneur Docker, un endpoint
`http://localhost:4566`, des clients AWS SDK/CLI pointés par `AWS_ENDPOINT_URL`, sans
compte ni jeton. Il couvre de nombreux services (IAM, STS, S3, SQS, DynamoDB, RDS,
CloudFormation, etc.) et s'intègre à Docker Compose/Testcontainers.

## Support Bedrock réel

Floci **n'exécute aucun modèle Bedrock réel**. Sa documentation et son code le disent
explicitement :

| Élément | Floci | Conséquence pour Méridian |
|---|---|---|
| `Converse` (Bedrock Runtime) | Backend `stub` par défaut : réponse factice fixe | Ne prouve ni la qualité, ni le tool use, ni les citations |
| `Converse` (proxy) | Peut transmettre à un endpoint OpenAI-compatible (Ollama, LiteLLM, vLLM…) | Utile pour un développement local sans AWS, pas pour valider Bedrock |
| `InvokeModel` | Toujours `stub`, même en mode proxy | Les embeddings Titan réels ne passent pas |
| `InvokeModelWithResponseStream` | 501 | Pas de streaming d'inférence |
| `ConverseStream` | Stub ou proxy ; pas d'inférence Bedrock | Ne valide pas le streaming Anthropic/Nova réel |
| Plan de contrôle Bedrock | Guardrails seulement | Pas de `ListFoundationModels`, ni profils d'inférence, ni évaluation |
| Résidence `ca-central-1` | Non modélisée | Aucune preuve de résidence canadienne |
| Quotas, coûts, accès Marketplace | Non modélisés | Aucune preuve d'accès réel au compte |

En résumé : Floci est adapté au **câblage AWS local** (signature SigV4, endpoints, IAM,
S3, files d'attente, tests CI sans credentials), pas à la **validation des modèles
Bedrock**.

## Ce qu'il pouvait valider dans Méridian

- `bedrock_router.session()` et `client()` : endpoint, région, signature, profil ;
- les appels S3 des sessions (`JUMEAU_SESSIONS_S3`) ;
- les files SQS/outbox et les policies IAM en test d'intégration ;
- un smoke test opt-in avec credentials factices et `AWS_ENDPOINT_URL=http://localhost:4566`.

Le dépôt possède déjà un harness local pour ces services :
`scripts/dev-aws-local.sh` (moto ou LocalStack) et `scripts/aws-local-smoke.py`
(Secrets Manager, SQS, EventBridge, Scheduler). Floci peut être essayé comme simple
endpoint de ce harness :

```bash
docker compose up -d          # dans le dépôt Floci
backend/.venv/bin/python scripts/aws-local-smoke.py \
  --endpoint http://127.0.0.1:4566
```

Mais ce smoke ne touche pas Bedrock : il ne remplace pas la validation réelle des
modèles.

## Ce qu'il ne pouvait pas valider

- l'accès réel aux modèles de chat, juge, vision, embedding et rerank ;
- la qualité des réponses, le tool use, les citations et les refus ;
- les embeddings Titan et la similarité sémantique ;
- les profils d'inférence canadiens (`ca.amazon.nova-lite-v1:0`, etc.) ;
- les erreurs réelles de compte : formulaire d'usage Anthropic, instrument de paiement
  Marketplace, quotas, throttling ;
- le coût et la latence réels.

## Décision

Pour le pilote Bedrock réel du 2026-11-06, **Floci n'a pas été utilisé** : il n'aurait
produit que des réponses factices et n'aurait pas prouvé l'accès au compte AWS. Le test
réel est resté sur AWS, en `ca-central-1`, avec le profil par défaut de la machine.

Floci est maintenant utilisé comme **laboratoire AWS local de plomberie** :
[floci-aws-local.md](floci-aws-local.md). Il reste :

- opt-in (`AWS_ENDPOINT_URL=http://localhost:4566`, credentials factices) ;
- sans changer le défaut de production ;
- limité à des assertions de câblage, jamais à des assertions de qualité ou de preuve ;
- documenté comme « stub », pour qu'aucun rapport ne présente ses réponses comme un
  résultat Bedrock.

Le laboratoire vérifie S3, SQS, EventBridge, Scheduler, Secrets Manager (adaptateur
optionnel), KMS, CloudWatch Logs et IAM avec les adapters réels de Méridian. Vault
reste le coffre principal. Bedrock reste validé sur le compte AWS réel, pas via Floci.

## Lancer Floci localement (rappel)

```bash
scripts/dev-floci.sh up
eval "$(scripts/dev-floci.sh env)"

aws bedrock-runtime converse \
  --model-id anthropic.claude-3-haiku-20240307-v1:0 \
  --messages '[{"role":"user","content":[{"text":"bonjour"}]}]'
```

La réponse est celle du stub : elle ne prouve rien sur le modèle réel. Le runbook
complet est dans [floci-aws-local.md](floci-aws-local.md).

## Références

- Dépôt : <https://github.com/floci-io/floci>
- Documentation Bedrock Runtime : `docs/services/bedrock-runtime.md` du dépôt Floci
- Documentation Bedrock (plan de contrôle) : `docs/services/bedrock.md` du dépôt Floci
- Pilote réel : [`plugin/meridian/evals/conversations/PILOT-2026-11-06-bedrock.md`](../../plugin/meridian/evals/conversations/PILOT-2026-11-06-bedrock.md)
