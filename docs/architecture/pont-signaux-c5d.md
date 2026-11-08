# Pont C5d — Signaux canoniques

> **Statut :** opérationnel en création, liste et lecture, périmètre UI borné.
> **Dernière mise à jour :** 8 novembre 2026.

## Objet

`Signal` est un objet d'entreprise canonique (`famille = emergence`) qui consigne un
événement, un changement, une dérive, une anomalie, une contradiction, une opportunité, un
risque ou une observation, avec une **source obligatoire**. Il ne remplace ni une
`Situation`, ni une `Expression`, ni une `Hypothesis` : c'est le fait observé qui peut
ensuite être rattaché à une ou plusieurs Situations.

Le domaine existait avant C5d (`backend/meridian/domain/objets_exploitation.py`). C5d
expose les commandes applicatives, le port, les routes, la lecture de chaîne et l'UI, sans
ajouter de cycle de transition.

## Identité et empreinte

- Table : `objet_entreprise`, type `SIGNAL`, comme tous les objets canoniques.
- Le serveur force `statut=DETECTED` et `mode=OBSERVED`.
- `id`, `tenant_id`, `fingerprint`, `statut` et `mode` sont serveur : un client qui les
  envoie est refusé en 422.
- `source` et `libelle` sont obligatoires et non vides.
- `type_signal` optionnel, défaut `OBSERVATION`, validé contre `TYPES_SIGNAL`.
- `fingerprint` est calculé **avant toute écriture**, jamais accepté du client.

Règle d'empreinte (documentée et testée dans le domaine) :

```text
sha256("signal-v1\x1f" + canon(source) + "\x1f" + canon(type_signal)
       + "\x1f" + canon(libelle) + "\x1f" + canon(detecte_le))
```

`canon` applique NFKC, compacte les espaces (une suite d'espaces devient un espace) et
replie la casse. Une `detecte_le` absente vaut la **chaîne vide** : l'heure serveur n'entre
jamais dans l'empreinte. Deux créations identiques, avec la même date ou sans date,
produisent donc la même empreinte et la seconde répond **409**, y compris sous concurrence
réelle (verrou consultatif `pg_advisory_xact_lock` + contrôle d'existence dans la même
transaction). Un 409 n'est jamais un 500.

La date ISO est utilisée telle que fournie (après normalisation de texte, pas de
reformattage sémantique de fuseau) : deux écritures différentes de la même instantanéité
peuvent donc produire deux empreintes distinctes.

## Chaîne et persistance

```text
SITUATION → SIGNAL          (exactement une Situation liée)
SIGNAL                      (aucune Situation, ou plusieurs)
```

- Lien inverse `Situation.signal_ids` (liste), posé par la persistance d'exploitation
  dans la même transaction que le Signal. Un Signal peut porter plusieurs Situations ;
  toutes sont verrouillées et vérifiées avant écriture.
- `GET /api/boucle/objets/{id}?historique=true` accepte `SIGNAL`. La chaîne amont n'est
  exposée que si `situation_ids` contient **exactement un** élément ; un Signal
  multi-Situation ou global est un objet **sans chaîne amont**, sans erreur.
- Lecture : `SIGNAL` est ajouté à `_CLASSES_LECTURE` / `TYPES_LECTURE`, jamais à
  `TYPES_BOUCLE`. `enregistrer_boucle` refuse toujours ce type.

## API

| Méthode | Route | Réponse |
|---|---|---|
| `POST` | `/api/boucle/signals` | 201 `ReponseTransition` (`type=SIGNAL`, `role=signal`) |
| `POST` | `/api/boucle/situations/{sid}/signals` | 201 `ReponseTransition`, Situation forcée |
| `GET` | `/api/boucle/signals?situation_id=&type_signal=&statut=&limite=` | liste tenant |

Corps de création strict (`extra="forbid"`) : `libelle` obligatoire, `source` obligatoire,
`type_signal`, `description`, `intensite` (0..1), `detecte_le` (ISO 8601),
`situation_ids`, `entite_ids`, `liens`, `preuves`, `confiance` (0..1).

Depuis `POST /situations/{sid}/signals`, `situation_ids` peut être absent ; s'il est
présent, il doit correspondre exactement à `[sid]` (sinon 422). En global, `situation_ids`
est optionnel et peut contenir plusieurs identifiants.

Erreurs :

- 404 : Situation absente ou hors tenant ;
- 409 : empreinte de Signal déjà connue (doublon) ;
- 422 : validation, type inconnu, champ serveur ou champ inconnu ;
- 400 : secret dans `preuves`/données non sérialisables, ou JSON malformé ;
- 501 : `Idempotency-Key` (aucun stockage d'idempotence durable) ;
- 503 : Postgres indisponible.

Aucune route de changement de statut n'existe en C5d : les statuts `STATUTS_SIGNAL`
existent dans le domaine pour la suite, mais l'API et l'UI n'exposent ni transition ni
formulaire de statut.

## UI

- Bouton global « Enregistrer un signal » dans l'en-tête de la Boucle.
- Action contextuelle « Enregistrer un signal » depuis une Situation ; la route liée est
  forcée et le champ `situation_ids` est masqué.
- Formulaire `ModaleTransition` : `libelle`, `source`, `type_signal`, `description`,
  `intensite`, `detecte_le`, `situation_ids` en CSV pour le global, `preuves`,
  `confiance`. Aucun champ statut, mode, id ou empreinte.
- Après succès : sélection du Signal, ajout à la liste, refetch du parent pour exposer
  `signal_ids`, affichage de la chaîne amont disponible.
- Un 409 doublon est traduit en message lisible (« Signal déjà enregistré : un signal
  identique existe déjà. ») et garde la modale ouverte ; 400/404/422/503 sont lisibles ;
  un réseau ou un 5xx reste annoncé comme incertain.
- `TYPES_SIGNAL` est exporté par `boucleUi.js` comme source de vérité testable ; `SIGNAL`
  est un stade et un filtre de `TYPES_LECTURE`.

## Tests

- Domaine : normalisation et déterminisme de l'empreinte, indépendance à l'horloge.
- Commandes : création globale, depuis une Situation, multi-Situation, liens inverses,
  doublon, champs serveur, 404, atomicité.
- HTTP : contrat 201, validation 422, doublon 409, secret/non-JSON 400, 501, 503, liste
  filtrée et isolation tenant.
- Postgres réel (opt-in `JUMEAU_PG_DSN`) : chaîne `SITUATION → SIGNAL`, absence de chaîne
  multi/global, concurrence par threads avec une seule écriture, isolation tenant,
  atomicité du lien inverse.
- Frontend : client API, action globale et contextuelle, validation libellé/source,
  doublon 409, filtre/stade SIGNAL, chaîne mono-Situation, absence de chaîne multi.

## Limites

- Création manuelle uniquement : aucun pipeline automatique de détection, de déduplication
  sémantique ou de promotion vers Expression/Hypothesis.
- Pas de route ni d'UI de changement de statut, de fusion, de rejet ou de suppression.
- Un Signal multi-Situation ou global n'a pas de chaîne amont unique ; ce n'est pas une
  erreur, mais l'UI n'affiche alors aucune étape amont.
- L'empreinte est volontairement textuelle : deux dates équivalentes écrites différemment
  restent deux composantes différentes.
- Pas de rattachement automatique des Signaux aux Expressions, Investigations ou
  Décisions au-delà de `situation_ids` et des liens libres.
