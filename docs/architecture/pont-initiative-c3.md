# Lot C3 — `initiative.maj` : l'Initiative canonique parente des Outcomes D

Statut : implémenté sur `lot-c3-initiative`. Complète le pont C2
[pont-travail-c2.md](pont-travail-c2.md) et ferme la limite du lot D
[mesure-auto.md](mesure-auto.md) : avant C3, aucune route legacy n'enfilait
`initiative.maj`, donc l'Initiative canonique parente d'un Outcome n'existait qu'après une
insertion Postgres manuelle.

## 1. Producteur

La seule route legacy qui change réellement l'état d'une Initiative est :

```text
POST /initiatives/{iid}/repondre
```

Après la mise à jour Mongo réussie (`statut`, `reponse`, `tenant_id`, `maj_le`), la route
relit l'Initiative et enfile **best-effort** un événement `initiative.maj` construit par
`meridian.application.pont_travail.evenement_initiative_maj`. Aucun identifiant n'est
inventé : le payload porte l'Initiative Mongo et, quand ils existent, les snapshots demandés
par C1 :

```json
{
  "initiative": {"id": "init-…", "statut": "acceptee", "reponse": {…}, "tenant_id": "local"},
  "situation": {"id": "sit-…", "titre": "…", "statut": "active", "priorite": "haute"},
  "investigation": {"id": "inv-sit-…", "situation_id": "sit-…", "statut": "OPEN"}
}
```

- `situation` est relue dans Mongo avec le filtre tenant de la requête.
- `investigation` est dérivée par `pont_travail.snapshot_investigation` : même identifiant
  C1 (`inv-{sid}`) et même statut `OPEN`/`CLOSED` que `objets_depuis_situation`. Aucun
  accès Postgres n'est ajouté à la route.
- Le builder C1 `evenement_depuis_initiative` produit les objets :
  `SITUATION → INVESTIGATION → DECISION (dec-init-{iid}) → INITIATIVE (ini-dec-init-{iid})`.
  Une réponse refusée produit la décision mais aucune Initiative canonique (garde C0a).

## 2. Idempotence

`source_event_id = "initiative:" + hash(initiative utile + snapshots)[:16]`. Les champs
utiles sont le statut, la réponse, la décision déclarée, le résumé (`raison`), le titre,
les liens et `maj_le`.

- un rejeu strict (même document, même `maj_le`, même snapshot) réutilise le même `_id`
  d'outbox ; `$setOnInsert` ne crée pas de doublon ;
- une modification réelle change le hash et crée un nouvel événement, même si l'horloge
  n'a pas bougé ; C1 arbitre ensuite par `source_maj_le` et par le hash des objets, donc
  une réécriture identique ne monte ni version ni historique ;
- une collision d'identifiant avec un contenu différent lève `PontInvalide`. La route la
  traite en best-effort et la journalise (warning expurgé) : l'écriture Mongo reste
  acquise, l'outbox existante n'est jamais remplacée.

## 3. Best-effort et tenant

- Budget global de l'enfilage : `asyncio.timeout(2.0)` ; lecture Mongo de la Situation
  bornée à 1 s, enqueue borné à 1,5 s. Toute erreur de construction, de signature, de
  Mongo outbox ou timeout est journalisée et ne fait jamais échouer `repondre`.
- `PONT_KEY` absent : la construction de l'événement signé échoue, la route répond 200 et
  l'Initiative reste écrite.
- Le tenant vient de `tenant_context` via `_tenant_ecriture` (aucun défaut implicite hors
  mode demo) ; `demo` est canonisé en `local` par l'autorité du domaine. L'Initiative
  Mongo et l'événement portent le même `tenant_id`.

## 4. Parcours D

```text
POST /initiatives/{iid}/repondre
  → initiative.maj
  → worker C1 : SITUATION → INVESTIGATION → DECISION → INITIATIVE
observation mesure_auto_observations (initiative_id = ini-dec-init-{iid})
  → worker D : outcome.mesure
  → worker C1 : OUTCOME + lien inverse initiative.outcome_ids
  → GET /boucle/objets/{outcome}?historique=true : 5 niveaux
```

Le test `backend/tests/test_parcours_d_initiative.py` exécute ce parcours avec Mongo et
Postgres réels, sans insertion manuelle de l'Initiative (opt-in :
`MONGO_URL` et `JUMEAU_PG_DSN`).

## 5. Tests

```bash
cd backend
.venv/bin/python -m pytest tests/test_initiatives_c3.py tests/test_pont_travail.py \
  tests/test_pont_worker.py tests/test_pont_canonique.py \
  tests/test_travaux_tenant_actualites_initiatives.py tests/test_conversation_routes.py \
  meridian/tests/test_mesure_auto.py meridian/tests/test_mesure_auto_worker.py -q

# Parcours D réel (Mongo + Postgres locaux)
MONGO_URL=mongodb://127.0.0.1:27099 \
JUMEAU_PG_DSN=postgresql://…/meridian \
.venv/bin/python -m pytest tests/test_parcours_d_initiative.py -q
```

`tests/test_initiatives_c3.py` couvre : payload et snapshots, chaîne canonique, rejeu,
modification réelle, tenant isolé, `demo → local`, `PONT_KEY` absent, builder qui lève,
outbox lente (budget), et collision `PontInvalide` journalisée sans perte d'écriture.
