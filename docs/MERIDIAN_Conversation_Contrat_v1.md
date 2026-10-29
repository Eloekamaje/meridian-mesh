# MÉRIDIAN — Contrat de la conversation unique (P1)

**Statut :** Contrat d'implémentation, validé le 2026-10-28 (option A : versions navigables et branches)
**Documents liés :** Chat Standards v1 (§2, §4, §7 P1), jumeau/flux.py

Une seule conversation sert le panneau Flore et le fil d'un Travail : même rendu, mêmes actions, même activité. Ce
document fixe le contrat entre le serveur et l'interface.

## 1. Le message

Une conversation est une liste de messages, dans l'ordre :

```json
{"role": "utilisateur", "texte": "…", "quand": "…",
 "branches": [{"texte": "…", "suite": [ /* les messages qui suivaient */ ]}], "branche": 0}

{"role": "flore", "texte": "…", "preuves": [], "contributions": [], "comportement": "…",
 "relecture_etat": "relue", "corrige": false, "origine": "modele", "durees": {}, "quand": "…",
 "interrompu": false,
 "versions": [{"texte": "…", "preuves": [], "relecture_etat": "…", "corrige": false, "origine": "…",
               "durees": {}, "quand": "…", "interrompu": false}],
 "version": 0,
 "retour": {"valeur": "utile|faux", "motif": null, "par": "…", "quand": "…"}}
```

- **Les champs du haut d'un message de Flore sont toujours ceux de sa version active** : un client qui ignore
  `versions` affiche la bonne réponse. `versions` contient **toutes** les versions, l'active comprise.
- `branches` (sur une question) garde les fils abandonnés quand la question a été modifiée. `branche` est l'index de
  celui qui est affiché, et la branche courante y figure aussi.
- `interrompu` : la réponse a été arrêtée par l'interlocuteur. Son texte est ce qui avait été écrit.

## 2. Les conversations du panneau (nouveau, persisté côté serveur)

Chaque conversation appartient à son auteur (`X-Persona`) et à son espace (`X-Espace`). Personne d'autre ne la voit.

| Route | Effet |
|---|---|
| `GET /api/conversations?q=` | `[{id, titre, maj_le, nb_messages}]`, plus récentes d'abord ; `q` cherche dans le titre et le texte |
| `POST /api/conversations` | `{titre?}` → `{id, titre, messages: []}` |
| `GET /api/conversations/{id}` | `{id, titre, messages}` |
| `PATCH /api/conversations/{id}` | `{titre}` |
| `DELETE /api/conversations/{id}` | supprime |
| `POST /api/conversations/{id}/messages/flux` | `{question, contexte, selection, domaine}` → flux SSE (§4) ; à la fin, les deux messages sont enregistrés |
| `POST /api/conversations/{id}/messages/{n}/retour` | comme pour un Travail |

Le titre est fixé par défaut d'après la première question (60 caractères au plus).

## 3. Versions, branches, arrêt (panneau ET Travail)

Les mêmes routes existent sous les deux préfixes : `/api/conversations/{id}` et `/api/cases/{cid}`.

| Route | Effet |
|---|---|
| `POST …/messages/{n}/regenerer/flux` | `n` est une réponse de Flore. La question qui la précède repart. La nouvelle réponse **devient une nouvelle version active** de `n`. Flux SSE ; `final.reponse` = le message `n` mis à jour |
| `POST …/messages/{n}/version` | `{index}` → la version choisie devient active. Rend le message `n` |
| `POST …/messages/{n}/modifier/flux` | `n` est une question, `{texte}`. La suite actuelle (messages après `n`) est rangée dans `branches` avec l'ancien texte. La question prend le nouveau texte, la suite est vidée, puis une réponse est générée. Flux SSE ; `final.reponse` = `{messages}` |
| `POST …/messages/{n}/branche` | `{index}` → la branche choisie (texte et suite) est restaurée. La branche courante est rangée. Rend `{messages}` |

**Arrêt.** L'interface interrompt la requête de flux (`AbortController`). Le serveur, constatant la déconnexion,
**annule** la génération. Il enregistre la question, plus la réponse partielle avec `interrompu: true` et le texte déjà
écrit. Une régénération ou une modification arrêtées n'ajoutent pas de version, ou rangent proprement la branche, selon
le cas : rien n'est perdu, rien n'est inventé.

## 4. Le flux

Événements inchangés (jumeau/flux.py) : `etape`, `texte`, `relecture`, `final`, `erreur`. Le passage à AG-UI est
l'étape P2.

## 5. Rendu (interface)

Un seul rendu Markdown pour tout le texte de Flore, avec une bibliothèque qui n'injecte jamais de HTML brut :
- titres, listes, tableaux, liens ;
- code avec coloration et bouton « Copier » ;
- formules ;
- schémas Mermaid (déjà là).

Les trois analyseurs actuels disparaissent : la mise en forme d'`OngletTravail`, `renduMarkdown` et le texte brut du
panneau.
