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

## Mise en service locale (Bedrock Titan)

```bash
# 1. Colonnes d'embedding sur une base existante
backend/.venv/bin/python scripts/migrer-document-chunk.py

# 2. Vérifier le provider et les similarités de paraphrases
backend/.venv/bin/python scripts/verifier-embeddings.py

# 3. Ré-embedder les chunks absents ou d'un autre modèle
backend/.venv/bin/python scripts/reembedder-documentation.py --tenant demo

# 4. Mesurer lexical vs hybride
backend/.venv/bin/python plugin/meridian/evals/retrieval/run.py --output /tmp/retrieval
```

`/api/health` expose une dépendance `embeddings` avec `provider`, `modele`, `dimension`
et `semantique`. Sans provider, le retrieval continue en lexical + graphe et le statut
est `absent` ; aucune erreur silencieuse : `chunk_store` journalise désormais les échecs
d'indexation, de recherche et d'ACL.

Le pilote local 2026-11-06 (Titan V2, 1024 dimensions) passe de **75 % à 100 % de
Hit@1** et de **0,797 à 1,000 de MRR** sur 12 requêtes paraphrasées. Détail :
`plugin/meridian/evals/retrieval/PILOT-2026-11-06.md`.

## Accès chat et embeddings : deux vérifications distinctes

Les embeddings Titan ont été validés en `ca-central-1` (1024 dimensions). L'accès aux
modèles de **chat** est indépendant : sur le compte réel, `ca.amazon.nova-lite-v1:0`
fonctionne en streaming et avec tool use, tandis que les modèles Anthropic sont bloqués
par le formulaire d'usage ou l'instrument de paiement Marketplace. Voir
[`aws-bedrock-target.md`](aws-bedrock-target.md)
et le pilote [`PILOT-2026-11-06-bedrock.md`](../../plugin/meridian/evals/conversations/PILOT-2026-11-06-bedrock.md).

Floci ne remplace pas cette vérification : son Bedrock Runtime est un stub.
