# Pont C5e — Experts canoniques et contributions

> **Statut :** opérationnel en inscription, contribution, liste, lecture et transition de
> contribution, périmètre UI borné.
> **Dernière mise à jour :** 8 novembre 2026.

## Objet

`Expert` est un objet d'entreprise canonique (`famille = investigation`) qui inscrit une
capacité spécialisée de raisonnement : nom, domaine, rôle, méthodes, responsabilités,
périmètre, sources et outils autorisés, limites et statut d'activité. Il ne remplace ni un
profil de spécialiste cognitif, ni un utilisateur authentifié.

`ExpertContribution` est la contribution datée d'un Expert à une Investigation ou à une
Hypothesis : contenu, constats, claims proposés, hypothèses soutenues ou contestées,
inconnues, preuves, confiance et statut de relecture. Elle ne modifie jamais directement
l'Investigation, l'Hypothesis ou un Claim : elle est enregistrée, puis acceptée, rejetée ou
archivée par un humain.

Les deux types existaient dans le domaine avant C5e. C5e expose les commandes applicatives,
le port, les routes, la lecture de chaîne et l'UI, sans pipeline de collecte automatique.

## Registre des experts

- Table : `objet_entreprise`, type `EXPERT`, comme tous les objets canoniques.
- Le serveur force `statut=ACTIVE` et `mode=DECLARED`. `id`, `tenant_id`, `statut` et
  `mode` fournis par le client sont refusés en 422 (`extra="forbid"`).
- `nom` et `domaine` sont obligatoires et non vides ; les listes vides sont ignorées.
- Aucune route de changement de statut Expert n'existe en C5e : un expert inactif ou
  archivé se gère hors du périmètre de ce lot. Le registre est donc **inscriptible et
  lisible**, pas encore administrable depuis l'UI.
- Un EXPERT est un objet racine : sa chaîne canonique est `[EXPERT]`, sans amont.

## Contributions

### Création

| Méthode | Route | Parent |
|---|---|---|
| `POST` | `/api/boucle/investigations/{iid}/contributions` | Investigation du tenant |
| `POST` | `/api/boucle/hypotheses/{hid}/contributions` | Hypothesis du tenant, Investigation dérivée |

Corps strict (`extra="forbid"`) : `expert_id` et `contenu` obligatoires ; optionnels
`hypothesis_id` (route Investigation seulement), `constats`, `claim_ids_proposes`,
`hypothesis_ids_soutenues`, `hypothesis_ids_contestees`, `inconnues`, `contribution_le`
(ISO 8601), `preuves`, `confiance` (0..1). Le serveur force `statut=PROPOSED` et
`mode=DECLARED` ; `statut`, `mode`, `id`, `tenant_id` et `investigation_id` sont refusés
en 422. Depuis une Hypothesis, `hypothesis_id` est également refusé : la route le décide.

L'Investigation est verrouillée (`FOR UPDATE`) et doit être ouverte. Les statuts fermés
reconnus sont `CLOSED`, `CLOSE`, `CLOTUREE`, `FERMEE`, `ARCHIVED`, `ARCHIVEE`,
insensibles à la casse. L'Expert est verrouillé et doit exister dans le même tenant.
Absent ou hors tenant : 404. Mauvais type : 422.

### Invariant fort hypothèse / investigation

Si une contribution porte à la fois une Investigation et une Hypothesis, l'Hypothesis doit
appartenir à cette Investigation (`hypothesis.investigation_id == investigation.id`).
Sinon la commande répond 409 et aucune écriture n'a lieu.

Si seule l'Hypothesis est fournie, son `investigation_id` est dérivé pour compléter la
contribution et la chaîne. L'invariant est rejoué dans le constructeur de domaine **et**
dans l'adaptateur de persistance : un appel direct à `enregistrer_objets_exploitation` ne
peut pas le contourner.

### Liens inverses

`Investigation.expert_ids` reçoit l'Expert de chaque contribution rattachée à
l'Investigation, dans la même transaction que la contribution. Le modèle ne porte pas de
`contribution_ids` : aucune liste inverse de contributions n'est maintenue. L'Expert reste
dans `expert_ids` tant qu'une contribution non retirée le cite ; un retrait ne supprime pas
l'expert du registre.

### Cycle de statut

```text
PROPOSED → ACCEPTED | REJECTED | ARCHIVED
ACCEPTED → ARCHIVED
REJECTED → ARCHIVED
ARCHIVED → (terminal)
```

`POST /api/boucle/contributions/{cid}/statut` accepte `{vers, motif?, preuves?}`. Une
transition non autorisée est un 409 ; un statut inconnu ou un identifiant d'un autre type
est un 422 ; une contribution absente ou hors tenant est un 404. Le motif et les preuves
sont conservés avec la contribution et la version précédente reste dans `historique`.

## Chaînes canoniques

```text
EXPERT
INVESTIGATION → EXPERT_CONTRIBUTION
SITUATION → INVESTIGATION → EXPERT_CONTRIBUTION
SITUATION → INVESTIGATION → HYPOTHESIS → EXPERT_CONTRIBUTION   (contribution ciblant une hypothèse)
```

`_source_principale` suit `hypothesis_id` puis `investigation_id` pour une contribution ;
un EXPERT n'a pas de source principale. `EXPERT` et `EXPERT_CONTRIBUTION` sont ajoutés à
`_CLASSES_LECTURE` / `TYPES_LECTURE`, jamais à `TYPES_BOUCLE` : `enregistrer_boucle`
continue de les refuser.

## API

| Méthode | Route | Réponse |
|---|---|---|
| `POST` | `/api/boucle/experts` | 201 `ReponseTransition` (`type=EXPERT`, `role=expert`) |
| `GET` | `/api/boucle/experts?domaine=&statut=&limite=` | liste tenant |
| `POST` | `/api/boucle/investigations/{iid}/contributions` | 201 `ReponseTransition` (`role=contribution`) |
| `POST` | `/api/boucle/hypotheses/{hid}/contributions` | 201 `ReponseTransition` |
| `GET` | `/api/boucle/contributions?expert_id=&investigation_id=&hypothesis_id=&statut=&limite=` | liste tenant triée |
| `POST` | `/api/boucle/contributions/{cid}/statut` | 200 `ReponseTransition` |

Erreurs transverses : 400 pour un JSON malformé, un secret ou des données non
sérialisables ; 501 pour `Idempotency-Key` (aucun stockage d'idempotence durable) ; 503
pour Postgres indisponible. Les réponses HTTP passent par `_assainir` : aucun secret connu
n'est renvoyé.

## UI

- Action globale « Inscrire un expert » et formulaire registre (nom, domaine, rôle,
  méthodes, responsabilités, périmètre, sources/outils autorisés, limites, preuves,
  confiance). `statut`, `mode`, `id` et `tenant_id` ne sont pas exposés.
- Action contextuelle « Solliciter un expert » depuis une Investigation ouverte et depuis
  une Hypothesis. Le formulaire charge le registre (`GET /experts?statut=ACTIVE&limite=100`)
  et propose l'expert dans un `select` ; il porte contenu, constats, claims, hypothèses
  soutenues/contestées, inconnues, date, preuves et confiance.
- Après succès, l'objet créé est ajouté à la liste et l'objet source est rafraîchi
  (liens inverses). Les stades `EXPERT` et `EXPERT_CONTRIBUTION` apparaissent dans les
  sections, les compteurs et le filtre de type.
- Le panneau détail affiche les champs du registre et de la contribution, ainsi que la
  chaîne amont. L'action de statut n'est proposée que sur une contribution non terminale,
  avec un `select` limité aux transitions autorisées, un motif et des preuves.
- Accessibilité : la modale existante fournit `role="dialog"`, `aria-modal`, le focus
  initial, la boucle Tab, la fermeture par `Escape` et le fond `inert`.

## Limites assumées

- Pas de route de changement de statut Expert, ni d'édition ou de suppression du registre.
- Pas de collecte automatique de contributions : tout est déclaré manuellement.
- `expert_id` reste refusé sur `POST /investigations/{iid}/hypotheses` : le rattachement
  passe par une contribution, pas par le champ de l'hypothèse.
- Pas de liste inverse `contribution_ids` sur l'Investigation (le modèle ne la porte pas).
- Pas de résolution automatique des `claim_ids_proposes`, `hypothesis_ids_soutenues` ou
  `hypothesis_ids_contestees` : ce sont des références déclaratives, pas encore des liens
  validés.
- Les tables `TRANSITIONS_EXPERT_CONTRIBUTION` (backend) et `TRANSITIONS_CONTRIBUTION`
  (frontend) sont dupliquées ; aucun endpoint ne les expose. Un test vérifie chaque table.
