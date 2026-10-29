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

## 2. Une conversation est un Travail privé, à l'état « conversation » (décision du 2026-10-28)

Décision prise sur recommandation de l'expert UX, d'après les standards observés : ChatGPT, Claude, Gemini,
Notion et Slack gardent toutes les conversations, privées à leur auteur, et le passage à un espace durable y est
toujours explicite.

**Il n'y a pas de seconde liste de conversations.** Les Travaux sont les sessions, et la barre latérale
(`SidebarGauche`, « Récents ») est leur historique (règle « suivre l'existant »).

- **Création.** À la première question d'une conversation, le panneau Flore crée un Travail (`POST /api/cases`) avec
  `statut: "conversation"` et `auteur` = l'interlocuteur (`X-Persona`). Les questions suivantes vont dans ce même
  Travail (`POST /api/cases/{cid}/messages/flux`). Rouvrir le panneau le reprend, et « Nouvelle conversation » en
  démarre un autre.
- **Visibilité.** Une conversation n'est visible que de son auteur :
  - `GET /api/cases` ne la renvoie qu'à lui ;
  - toute route `/api/cases/{cid}/…` refuse les autres (404, sans révéler qu'elle existe).
  
  Dans les Récents de la barre latérale, l'auteur la voit avec une marque discrète (« conversation »). La page
  Travaux liste par défaut les Travaux conservés, et les conversations sur un filtre.
- **Conserver.** « Conserver comme travail » fait `PATCH /api/cases/{cid}` `{statut: "actif"}` : le même Travail
  devient partagé selon sa portée, et l'onglet complet apparaît (plan, hypothèses, décisions, veille). On ne crée
  plus de copie.
- **Proposer de conserver.** Le bandeau de proposition existant se déclenche quand Flore produit un plan, une
  option, une décision ou un livrable. Il ne promeut jamais sans un clic.
- **Ajouter à un travail existant.** Les messages de la conversation sont rattachés au Travail choisi, puis la
  conversation est retirée.
- **Recherche.** `GET /api/cases?q=` cherche dans le titre et le texte des messages, parmi ce que l'interlocuteur a
  le droit de voir (insensible à la casse, jamais une expression régulière fournie par le client). Elle est offerte
  dans la barre latérale (Récents) et sur la page Travaux.
- **Renommer, supprimer** : les routes existantes des Travaux, réservées à l'auteur pour une conversation.
- **Pas de mode éphémère** pour l'instant, sauf exigence de conformité de la banque.
- **Limite connue.** L'auteur est l'en-tête `X-Persona`, non authentifié. Un persona inconnu est ramené au premier
  persona (`resoudre_perimetre`). La confidentialité réelle attend l'identité OIDC.

## 3. Versions, branches, arrêt (panneau ET Travail)

Toutes ces routes sont sous `/api/cases/{cid}` (le panneau converse dans un Travail, §2).

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
