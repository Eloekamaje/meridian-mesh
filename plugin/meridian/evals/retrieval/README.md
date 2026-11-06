# Benchmark retrieval sémantique

Ce benchmark mesure l'apport des embeddings au retrieval documentaire, à corpus et
requêtes identiques :

- **lexical + graphe** : `retrieval_hybride.score` sans vecteur de question ;
- **hybride** : lexical + cosinus entre la question et chaque chunk, avec les
  embeddings réels du provider configuré (Bedrock Titan par défaut).

Le corpus est synthétique et porte sur Conduit et Méridian. Les requêtes sont des
paraphrases : plusieurs n'ont presque aucun mot en commun avec le chunk attendu, ce
qui rend le lexical seul insuffisant.

## Lancer

```bash
# Bedrock Titan en résidence canadienne
export EMBEDDING_PROVIDER=bedrock
export BEDROCK_REGION=ca-central-1
export BEDROCK_EMBEDDING_MODEL=amazon.titan-embed-text-v2:0
export BEDROCK_EMBEDDING_DIMENSIONS=1024

backend/.venv/bin/python plugin/meridian/evals/retrieval/run.py \
  --output /tmp/meridian-retrieval
```

Sans provider sémantique, le runner s'arrête avec un message explicite (code 2) : il
ne fabrique aucun vecteur.

## Sorties

```text
<output>/
  REPORT.md
  summary.json
```

## Résultat du pilote (2026-11-06)

Bedrock Titan Text Embeddings V2, 1024 dimensions, 11 chunks, 12 requêtes :

| Métrique | Lexical + graphe | Hybride Bedrock |
|---|---:|---:|
| Hit@1 | 75 % | **100 %** |
| Hit@3 | 75 % | **100 %** |
| MRR | 0.797 | **1.000** |

Les paraphrases qui échouaient en lexical seul et passent en hybride :

- « Qui a le droit de corriger un texte déjà publié ? » → règles métier (rang 9 → 1) ;
- « Comment un utilisateur prouve-t-il son identité ? » → comptes/authentification (5 → 1) ;
- « Quelles bibliothèques Python font tourner l'application ? » → dépendances (4 → 1).

Détail : [`pilots/2026-11-06/REPORT.md`](pilots/2026-11-06/REPORT.md).

## Prérequis techniques

- `document_chunk` doit avoir les colonnes `embedding`, `embedding_model`,
  `embedding_dim` : `scripts/migrer-document-chunk.py`.
- Les chunks existants doivent être ré-embeddés après un changement de modèle :
  `scripts/reembedder-documentation.py --tenant <tenant>`.
- Vérifier le provider et la similarité de paraphrases :
  `scripts/verifier-embeddings.py`.

## Limites

- Corpus synthétique et petit : les chiffres mesurent la plomberie et la valeur des
  paraphrases, pas la qualité d'un RAG complet.
- Le reranker Bedrock est optionnel et non activé dans ce pilote.
- Les embeddings ne remplacent ni les Claims, ni les preuves, ni les ACL : ils
  produisent des candidats, jamais une vérité.
