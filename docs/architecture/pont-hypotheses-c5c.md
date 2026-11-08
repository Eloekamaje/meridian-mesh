# Pont C5c — Hypothèses canoniques

> **Statut :** opérationnel depuis une Investigation, périmètre UI borné.
> **Dernière mise à jour :** 8 novembre 2026.

## Objet

`Hypothesis` est un objet d'entreprise canonique (`famille = investigation`) qui porte une
explication testable, ses conditions de test, ses claims soutenants et opposants, des
preuves et un cycle de statut. Le domaine conserve aussi `expert_id`, mais ce champ est
réservé à C5e : il n'est pas accepté en entrée HTTP et n'apparaît pas dans le formulaire
tant qu'aucune route `EXPERT` n'existe. Il ne remplace pas les hypothèses internes du dossier de raisonnement :
c'est l'objet durable rattaché à une Investigation canonique.

## Chaîne et persistance

```text
SITUATION → INVESTIGATION → HYPOTHESIS
```

- Table : `objet_entreprise`, type `HYPOTHESIS`, comme tous les objets canoniques.
- Lien inverse : `Investigation.hypothesis_ids` (liste), posé par la persistance
  d'exploitation dans la même transaction que l'hypothèse.
- Création exclusive depuis une Investigation **ouverte** : le serveur force
  `statut=OPEN` et `mode=PROPOSED`. Une autre source est refusée en 422, une Investigation
  absente ou hors tenant en 404, et une Investigation fermée (`CLOSED`, `CLOSE`,
  `CLOTUREE`, `FERMEE`, `ARCHIVED`, `ARCHIVEE`, insensible à la casse) en 409 avant toute
  écriture.
- Lecture : `HYPOTHESIS` est dans `_CLASSES_LECTURE` / `TYPES_LECTURE`, jamais dans
  `TYPES_BOUCLE`. `enregistrer_boucle` refuse toujours ce type.

## Cycle canonique

```text
OPEN        → STRENGTHENED | WEAKENED | REJECTED | CONFIRMED
STRENGTHENED→ WEAKENED | REJECTED | CONFIRMED
WEAKENED    → STRENGTHENED | REJECTED | CONFIRMED
CONFIRMED   → (terminal)
REJECTED    → (terminal)
```

`CONFIRMED` exige au moins une preuve, nouvelle ou déjà portée par l'hypothèse. Une
transition non autorisée répond 409 ; un statut inconnu ou une confirmation sans preuve
répond 422.

## API

| Méthode | Route | Réponse |
|---|---|---|
| `POST` | `/api/boucle/investigations/{iid}/hypotheses` | 201 `ReponseTransition` (`type=HYPOTHESIS`, `role=hypothese`) |
| `GET` | `/api/boucle/hypotheses?investigation_id=&statut=&limite=` | liste tenant |
| `POST` | `/api/boucle/hypotheses/{hid}/statut` | 200 `ReponseTransition` |

Corps de création strict (`extra="forbid"`) : `enonce` obligatoire, `conditions_test`,
`claim_ids_soutenants`, `claim_ids_opposants`, `preuves`, `confiance` (0..1).
`statut`, `mode`, `id`, `investigation_id` et `expert_id` ne sont jamais acceptés du
client (422) ; `expert_id` reste réservé à C5e.

Corps de transition : `vers` obligatoire, `motif` et `preuves` optionnels.

## UI

- Action « Formuler une hypothèse » depuis une Investigation ouverte.
- Formulaire `ModaleTransition` : énoncé, conditions de test, claims soutenants/opposants,
  preuves, confiance. Le champ expert reste réservé à C5e et n'est pas affiché.
- Sélection de l'hypothèse créée, ajout à la liste, refetch du parent pour exposer
  `hypothesis_ids`, affichage de la chaîne.
- Action « Changer le statut » limitée aux seules transitions autorisées.
- `CONFIRMED` sans preuve est bloqué côté UI avec un message explicite.

## Limites

- Formulation manuelle uniquement : aucun pipeline automatique Claims → Hypothesis.
- Pas encore de rattachement aux `Expert` / `ExpertContribution` : `expert_id` existe dans
  le domaine mais reste réservé à C5e, non exposé par l'API ni par l'UI.
- Pas de suppression ni de fusion d'hypothèses concurrentes.
- La table de transitions est dupliquée côté domaine et côté UI, comme pour C5b ; un test
  frontend vérifie la copie exacte.
