# Benchmark retrieval — lexical vs hybride

- Provider : `bedrock`
- Modèle : `amazon.titan-embed-text-v2:0`
- Dimension : 1024
- Requêtes : 12

| Métrique | Lexical + graphe | Hybride (Bedrock) |
|---|---:|---:|
| Hit@1 | 75% | 100% |
| Hit@3 | 75% | 100% |
| MRR | 0.797 | 1.000 |

## Détail

| Requête | Attendu | Rang lexical | Rang hybride |
|---|---|---:|---:|
| `corriger-article` | `conduit-regles` | 9 | 1 |
| `proteger-mots-de-passe` | `conduit-comptes` | 1 | 1 |
| `ou-sont-les-donnees` | `conduit-donnees` | 1 | 1 |
| `garder-article` | `conduit-favoris` | 1 | 1 |
| `titre-dans-adresse` | `conduit-articles` | 1 | 1 |
| `prouver-identite` | `conduit-comptes` | 5 | 1 |
| `bibliotheques-python` | `conduit-dependances` | 4 | 1 |
| `retirer-commentaire` | `conduit-commentaires` | 1 | 1 |
| `limites-exploitation` | `conduit-limites` | 1 | 1 |
| `claim-sans-preuve` | `meridian-preuve` | 1 | 1 |
| `role-du-mesh` | `meridian-mesh` | 1 | 1 |
| `usages-sociaux` | `conduit-plateforme` | 1 | 1 |

## Lecture

- Le classement lexical seul est calculé avec `retrieval_hybride.score` sans vecteur.
- Le classement hybride ajoute la similarité cosinus entre la question et chaque chunk.
- Le corpus est synthétique et petit : les chiffres mesurent la plomberie et la valeur
  des paraphrases, pas la qualité d'un RAG complet.
