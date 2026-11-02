# Dépendances runtime

`GET /api/health` expose un diagnostic stable, sans secret :

```json
{
  "status": "ok | degraded | down",
  "service": "meridian",
  "dependances": [
    {"nom": "postgres", "statut": "ok", "requis": true},
    {"nom": "codebase-memory-mcp", "statut": "indisponible", "requis": false}
  ],
  "manquantes": ["codebase-memory-mcp"]
}
```

## Nécessaires à l’API

- **Postgres** : `JUMEAU_PG_DSN` (ou `JUMEAU_WORKER_PG_DSN`).
- **MongoDB** : `MONGO_URL` et `DB_NAME`.
- **Git** : binaire `git` dans `PATH` (ou `GIT_BIN`).
- **Modèle** : `DEEPSEEK_API_KEY` si `JUMEAU_MODELE=deepseek` ; mode Bedrock possible.

## Nécessaires à l’ingestion de code

- **codebase-memory-mcp** : `CBM_BIN` ou binaire `codebase-memory-mcp` dans `PATH`.
  Son absence laisse l’API démarrer mais rend l’ingestion de code indisponible ; le worker
  d’ingestion le signale et les outils de code échouent clairement.
- **Git** pour le clone, les SHA et l’historique.
- **anydoc** (`firecrawl-anydoc`) pour l’extraction bureautique, optionnel selon les formats.

## Optionnels

- Redis (`REDIS_URL`) : SSE/notifications.
- Neo4j (`NEO4J_URI`/`NEO4J_URL` ou `GRAPH_STORE=neo4j`) : projection graphe.
- AWS/Vault, stockage S3/MinIO/local, Playwright/Chromium pour la validation visuelle des diagrammes.

## Préflight

`meridian.application.dependances.etat()` ne fait aucun appel réseau et ne lit aucun secret.
`exiger("codebase-memory-mcp")` permet à un CLI d’échouer avec la dépendance exacte plutôt qu’avec
une erreur d’ingestion opaque.
