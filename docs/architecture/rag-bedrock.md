# RAG documentaire et Bedrock — configuration

## Principe

Le retrieval produit des **candidats**. Les Claims, preuves, ACL, versions et gates restent
l'autorité. Aucun fournisseur ne crée de vérité : sans provider réel, le retrieval continue en
lexical + graphe.

## Variables

### Retrieval

| Variable | Valeur | Effet |
|---|---|---|
| `EMBEDDING_PROVIDER` | `bedrock`, `openai`, vide | provider réel ; vide = Bedrock si `JUMEAU_MODELE=bedrock`, sinon OpenAI |
| `BEDROCK_EMBEDDING_MODEL` | `amazon.titan-embed-text-v2:0` | modèle Titan, ou modèle `cohere.` |
| `BEDROCK_EMBEDDING_DIMENSIONS` | `1024` | dimension Titan |
| `BEDROCK_REGION` | `ca-central-1` | région Bedrock |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | modèle OpenAI |
| `RERANK_PROVIDER` | `none`, `bedrock` | reranking optionnel |
| `BEDROCK_RERANK_MODEL` | — | modèle Cohere/Bedrock de rerank |

### Bedrock

| Variable | Effet |
|---|---|
| `JUMEAU_MODELE=bedrock` | chat, embeddings et vision passent par Bedrock par défaut |
| `BEDROCK_MODELE` | modèle de chat |
| `BEDROCK_VISION_MODEL` | modèle multimodal |
| `VISION_PROVIDER=bedrock\|deepseek` | force le fournisseur Vision |

### Documents

| Variable | Effet |
|---|---|
| `JUMEAU_PG_DSN` | stockage `document_chunk` |
| `CONFLUENCE_*` | source Confluence déclarée |
| `SHAREPOINT_TENANT_ID`, `SHAREPOINT_CLIENT_ID`, `SHAREPOINT_CLIENT_SECRET` | Graph |
| `SHAREPOINT_SITE_ID` | site Graph si l'URL ne suffit pas |

## Backfill

```bash
backend/.venv/bin/python scripts/indexer-documentation.py --tenant local --limite 500
```

L'indexation indexe les documents énumérables des sources configurées. Le chat continue
d'indexer à la demande les documents trouvés par recherche.

## GraphRAG

- `GRAPH_RAG_MODE=local|global`
- `GRAPH_GLOBAL_SUMMARY=llm` pour une synthèse du contexte global
- `COMMUNITY_SUMMARY=llm` pour les rapports de communautés
- `backend/.venv/bin/python scripts/calculer-communautes.py --tenant local`

Les communautés sont un index dérivé : elles ne créent ni Claim ni preuve.

## ACL

Une source peut porter une ACL dans sa configuration :

```json
{"acl": {"users": ["usr-1"], "roles": ["Architecte"], "espaces": ["finance"], "public": false}}
```

Une ACL absente ou vide signifie « tenant » en pilote. Le filtrage ACL est appliqué avant le
prompt, y compris aux documents lus en direct. En production, une ACL absente doit être refusée
(fail-closed) ou dériver des permissions de la source.

## Changement de provider

Les dimensions ne sont pas mélangeables :

- Titan : 1024 ;
- OpenAI `text-embedding-3-small` : 1536.

Après un changement de modèle, vider `document_chunk` et relancer le backfill.
