# Pont C5f — Cycle de vie Expert et liens de contribution validés

> **Statut :** opérationnel, périmètre UI borné.
> **Dernière mise à jour :** 8 novembre 2026.

## Objet

C5f complète le pont C5e sur deux points restés ouverts :

1. le registre `EXPERT` devient **administrable** : un expert peut être désactivé,
   réactivé ou archivé, avec motif et preuves ;
2. les hypothèses citées par une `EXPERT_CONTRIBUTION`
   (`hypothesis_ids_soutenues`, `hypothesis_ids_contestees`) deviennent des **liens
   validés**, et non plus des identifiants déclaratifs.

Aucun autre type d'objet, aucune route C1/C2/C3/C4/C5a-C5e n'est modifié hors des
extensions additives nécessaires.

## Cycle de vie Expert

### Domaine

```text
ACTIVE   → INACTIVE | ARCHIVED
INACTIVE → ACTIVE   | ARCHIVED
ARCHIVED → (terminal)
```

La table `TRANSITIONS_EXPERT` est définie dans
`backend/meridian/domain/objets_exploitation.py` et exportée par `__all__`. Elle est
dupliquée, de façon assumée, dans `frontend/src/components/boucle/boucleUi.js` ; un test
vérifie chaque table.

`construction_objets_exploitation.muer_expert(expert, vers, *, motif=None,
preuves=None, mode=None)` :

- ne mute jamais la source et rend un nouvel `Expert` ;
- conserve `motif` et `preuves` sur le nouvel objet ;
- lève `ObjetsExploitationInvalide` (422) pour un statut cible inconnu ;
- lève `TransitionObjetRefusee` (409) pour une transition non autorisée.

Le port `BoucleStore.muer_expert` et l'adaptateur
`meridian.adapters.outbound.postgres.boucle.muer_expert` délèguent au constructeur.

### Commande

`commandes_boucle.changer_statut_expert(depot, conn, tenant_id, expert_id, statut, *,
motif=None, preuves=None)` réutilise `_changer_statut_objet` avec
`type_attendu="EXPERT"`, `role="expert"`, `STATUTS_EXPERT` et `depot.muer_expert`.
La source est lue verrouillée (`FOR UPDATE`), la version précédente est conservée dans
`historique`, et l'écriture est atomique.

### Route

`POST /api/boucle/experts/{eid}/statut`

Corps strict (`extra="forbid"`) :

```json
{
  "vers": "INACTIVE",
  "motif": "Congé longue durée",
  "preuves": ["doc://rh"]
}
```

`vers` est obligatoire ; `motif` et `preuves` sont optionnels. Le modèle
`ChangementStatutExpert` est documenté dans l'OpenAPI (`openapi_extra`), comme les autres
transitions strictes C5e.

| Cas | Réponse |
|---|---|
| Transition valide | 200 `ReponseTransition` (`type=EXPERT`, `role=expert`, `chaine=[EXPERT]`, `historique` avec la version précédente) |
| Expert absent ou hors tenant | 404 |
| Transition non autorisée (`ARCHIVED` terminal, etc.) | 409 |
| Statut inconnu, identifiant d'un autre type, champ serveur (`statut`, `mode`, `id`, `tenant_id`) ou corps invalide | 422 |
| JSON malformé, corps non-objet, secret ou données non sérialisables | 400 |
| `Idempotency-Key` | 501 |
| Postgres indisponible | 503 |

## Liens de contribution validés

Dans `backend/meridian/adapters/outbound/postgres/objets_exploitation.py`,
`_valider_pour_persistance` vérifie désormais, pour chaque identifiant de
`hypothesis_ids_soutenues` et `hypothesis_ids_contestees` d'une
`EXPERT_CONTRIBUTION` :

- l'hypothèse existe ;
- son type est `HYPOTHESIS` ;
- elle appartient au même tenant ;
- `hypothesis.investigation_id == contribution.investigation_id`.

Toute violation lève `ObjetsExploitationInvalide` (422) **avant** la persistance : aucune
contribution partielle et aucune mise à jour de `Investigation.expert_ids` ne sont
produites. La validation est rejouée dans l'adaptateur, donc un appel direct à
`enregistrer_objets_exploitation` ne peut pas la contourner.

La route Hypothèse dérive l'Investigation avant la validation
(`_deriver_contributions_hypothese`), puis les hypothèses citées sont collectées avec les
parents et verrouillées dans la même requête triée par identifiant. La validation réutilise
`par_id` et `_resoudre` : aucune requête par citation valide. L'ordre de verrouillage C5e
(`_deriver_contributions_hypothese` avant `_collecter_ids_parents`/`_lire_verrouilles`)
est conservé.

## UI

- `boucleApi.changerStatutExpert(eid, corps)` poste la transition avec un timeout de
  20 s, sans `Idempotency-Key`.
- `ACTIONS_BOUCLE.changer_statut_expert` expose l'action « Changer le statut » sur un
  EXPERT non terminal ; les options du `select` sont calculées depuis `TRANSITIONS_EXPERT`.
- Le formulaire porte `vers`, `motif` et `preuves`. La modale existante fournit
  `role="dialog"`, `aria-modal`, le focus initial, la boucle Tab, la fermeture par
  `Escape` et le fond `inert`.
- Après succès, l'objet est remplacé dans la liste et le détail est rafraîchi ; un 409
  garde la modale ouverte avec un message lisible.

## Tests

- Domaine : table explicite, transitions autorisées/refusées, statut inconnu, absence de
  mutation, motif/preuves/mode.
- Commandes : persistance, historique, 404/409/422, isolation tenant.
- HTTP : contrat `ReponseTransition`, corps strict, 400/404/409/422/501/503, OpenAPI.
- Postgres réels : cycle de vie complet, hypothèse citée inconnue, autre tenant, autre
  Investigation, routes Investigation et Hypothèse, absence d'écriture partielle, appel
  direct à la persistance.
- Frontend : `api.test.js`, `boucleUi.test.js`, `BoucleC5eExperts.test.jsx`.

## Limites

- Pas d'édition ni de suppression du registre : seul le statut est administrable.
- Pas de collecte automatique de contributions.
- Les `claim_ids_proposes` restent des références déclaratives non résolues ; seules les
  hypothèses soutenues/contestées sont validées.
- Pas de liste inverse `contribution_ids` sur l'Investigation (le modèle ne la porte pas).
- Les tables `TRANSITIONS_EXPERT` backend/frontend sont dupliquées et vérifiées par des
  tests, mais aucun endpoint ne les expose.
