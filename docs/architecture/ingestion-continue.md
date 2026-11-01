# Alimentation continue des jumeaux

## Décision

L’alimentation reste **pull-first** : le worker planifie chaque source, vérifie son SHA, crée un
`ingestion_run` durable et exécute la passe du Gardien. Un webhook entrant est un **accélérateur optionnel** :
il ne fait qu’enfiler un run, et le SHA est toujours revérifié par le gardien.

```text
source_schedule → ingestion_run → réclamation sous bail → Gardien
→ Claims/preuves → interfaces → outbox → graphe → situations
```

## Exécution

- `python -m jumeau.source_worker` : polling continu.
- `scripts/dev-source-worker.sh` : même boucle en développement.
- `scripts/meridian-source-worker.service` : unité systemd de supervision (`Restart=always`).
- `--une-passe` : une passe bornée.
- `GET /api/boucle/sources/sante` : état, dernier succès, lag, erreur assainie.
- `POST /api/boucle/sources/{id}/ingest` : ingestion manuelle, `202` (le worker réclame le run).
- `PATCH /api/boucle/sources/{id}/branche` : valide `source.branche` (charset Git, pas de `-` initial), puis
  enfile un run forcé `202`. La requête ne clone pas le dépôt et reste bornée au tenant ; le worker ingère la
  nouvelle branche à la passe suivante.
- `POST /pause` / `/resume`.
- Un seul run vivant par source ; bail, fencing, retry/backoff, reprise après crash.

## Webhook (accélérateur)

`POST /api/boucle/sources/{id}/webhook` vérifie la signature HMAC-SHA256
(`X-Hub-Signature-256`) avec `JUMEAU_WEBHOOK_SECRET`, puis enfile un run `202` si :

- la référence est une branche (`refs/heads/...`) ;
- elle correspond à `source.branche` (ou `main` par défaut) ;
- le dépôt `repository.full_name` correspond au chemin de `source.url` ;
- le SHA `after` diffère de `source.curseur`.

Un `ping`, une branche/dépôt non suivi ou un SHA déjà ingéré est acquitté sans run. Le webhook ne remplace
jamais le worker : sans worker, les runs restent `QUEUED`. Il réduit seulement le délai d’attente de la
prochaine échéance `source_schedule`.

## Index et copies

- Workspace configurable : `JUMEAU_WORKSPACE` (défaut local : `~/.local/share/meridian`).
- Copies de travail : `JUMEAU_COPIES`.
- Artefact d’index : `JUMEAU_INDEX_STORE=local|s3|none`.
- Local : `JUMEAU_INDEX_DIR`.
- S3/MinIO : `JUMEAU_INDEX_BUCKET`, `JUMEAU_INDEX_ENDPOINT`, `JUMEAU_INDEX_REGION`,
  `JUMEAU_INDEX_PREFIX`, `JUMEAU_INDEX_SSE`, `JUMEAU_INDEX_KMS_KEY`.
- `none` : zéro-rétention, la copie est supprimée après ingestion.
- L’artefact est une copie source au SHA, réindexable ; le cache binaire codebase-memory reste local
  au worker. Le manifeste contient hash, taille, source, SHA et date, jamais de secret.

## Cible cloud

- ECS/Fargate pour l’API et les workers ; AWS Batch/EC2+EBS pour les gros index.
- SQS pour la file, EventBridge Scheduler pour le polling, S3 pour les artefacts, RDS pour les runs,
  Neo4j/Neptune pour le graphe, Secrets Manager pour les jetons.
- Adapters optionnels dans `jumeau/aws_adapters.py` : Secrets Manager (`aws:<secret>#champ`), publication
  SQS/EventBridge pour l'outbox, et mapping `source_schedule` → EventBridge Scheduler. boto3 n'est importé
  qu'au premier appel ; les tests utilisent des doubles, sans réseau. Aucun déploiement AWS n'est revendiqué.
- Aucun port entrant requis pour le pull. Si le webhook est activé, n'exposer que `POST /api/boucle/sources/{id}/webhook` via l'API Gateway/ALB, avec HMAC. Alternative Kubernetes : CronJob + Job + S3/MinIO.

## Authentification des sources

Pour l'instant, seul le PAT est utilisé : `PATSource` résout une référence `env:`, `vault:` ou
`aws:`/`secretsmanager:`, sans jamais stocker le token dans `source.configuration`. L'adapter Secrets Manager
rend uniquement la valeur au appelant. Le port `AuthSource` reste prêt à recevoir un autre adaptateur plus tard,
mais aucun adaptateur GitHub App n'est embarqué.

## Commande d'identité

L'identité d'un jumeau est portée par un **`application_id` stable**, distinct du nom affiché :

- formulaire : `application_id` (App ID), `nom`, `propriétaire` uniquement ;
- import CMDB : JSON ou CSV avec `application_id`, `nom`, `proprietaire` ; aucun domaine, mission ou environnement d’identité.
- import manifeste : JSON `{jumeau: {...}, sources: [...]}` ou liste d'identités ;
- l'`application_id` devient l'`id` du jumeau ; il est validé minuscules/chiffres/`. _ -` ;
- l'import remplit l'identité et peut ajouter des sources à la commande ;
- aucune source n'est inventée si le contenu est vide.

Toutes les sources restent en **PAT** aujourd'hui : le PAT est résolu par `vault:`/`env:`, jamais persisté, et GitHub App n'est pas embarqué.

## Limites connues

- Seule la branche configurée est suivie (`source.branche`, `main` par défaut) ; une PR ou une branche
  feature n'est vue qu'après `PATCH /api/boucle/sources/{id}/branche` (ou modification de la source). Le
  changement n'écrit que la base et enfile un run : le clone/fetch reste fait par le worker.
- Un dépôt local sans `url` distante n'est pas rafraîchi par le worker : le mettre à jour avec Git.
- Sans worker supervisé, les runs restent `QUEUED` ; le webhook ne fait qu'avancer l'échéance.
- Un échec de fetch/ingestion est réessayé avec backoff ; le jumeau conserve sa dernière connaissance.
