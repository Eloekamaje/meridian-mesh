# Lot C2 — pont Travail → canonique et producteur `cas.boucle`

Statut : implémenté sur `lot-c2-pont`. Complète le contrat UI
[lot-e-ui-contrat-c2.md](lot-e-ui-contrat-c2.md) et s'appuie sur l'outbox C1
[ADR-0012](../adr/0012-outbox-idempotence.md) et le store de travail
[ADR-0008](../adr/0008-travail-work-store.md).

## 1. Écritures legacy → outbox canonique

Deux routes legacy enfilent désormais des événements **après** l'écriture Mongo réussie :

| Route | Événement Situation | Événements des Travaux liés |
|---|---|---|
| `POST /situations/{sid}/action` | `situation.maj` avec le nouveau statut | `case.maj` si le case a `situations[0] == sid` et produit des objets |
| `POST /situations/{sid}/decision` | `situation.maj` avec `statut=décidée`, `decision`, `decidee_par` | idem |

- L'écriture Mongo reste la première et la seule obligatoire. L'enfilage passe par
  `enfiler_lot_best_effort` avec **un seul budget global de 2 s** pour tout le lot ; une
  panne Mongo/outbox, une erreur de construction ou un timeout est journalisé et
  **n'annule ni ne fait échouer** la route legacy. Les lectures Mongo du pont sont bornées
  à 1 s.
- `POST /cases/{cid}/decisions`, `decision-attendue`, les réponses d'initiative et les
  confirmations/écarts de maturation enfilent aussi un `case.maj` après l'écriture.
- Le worker C1 peut être désactivé : la route ne fait qu'écrire dans `pont_canonique`.
- Aucune sérialisation/signature n'est réimplémentée : les événements sortent de
  `meridian.application.pont_canonique` (`evenement_depuis_situation`,
  `evenement_depuis_case`).
- ADR-0008 : un `case` n'est jamais recopié comme objet métier. Seul le Travail dont
  `situations[0]` référence la Situation traitée est projeté, et uniquement par ses
  décisions. Un case sans Situation liée ne produit rien, même s'il porte des décisions.
- L'événement `case.maj` embarque le snapshot de Situation comme ancre, avec une version
  **strictement antérieure** au `maj_le` écrit (`maj_le - 1 µs` si le snapshot n'a aucune
  date ou porte la même version). Il est autosuffisant : le worker peut traiter le case
  avant l'événement de Situation, et ne régresse jamais la Situation ni
  `dec-sit-{sid}-1`. Des tests couvrent les deux ordres d'application.
- Chaque action/décision pose `maj_le` sur la Situation. Sans cette version, le worker C1
  ignorerait en bloc un second événement de Situation de même `source_maj_le`. Un rejeu ne
  change ni `maj_le`, ni `decidee_le`, donc le `case.maj` et le `situation.maj` restent
  identiques.

### Correspondance des identifiants

Aucune table de correspondance n'est nécessaire. C1 utilise déjà l'identifiant Mongo comme
identifiant canonique :

```text
situation Mongo sid  →  SITUATION sid
                    →  INVESTIGATION inv-{sid}
                    →  DECISION dec-sit-{sid}-{n}
case Mongo cid      →  DECISION dec-case-{cid}-{n}
```

### Idempotence

La clé d'outbox est `sha256(tenant|operation|canonical_id|source_event_id)[:32]`.

- Action : `source_event_id = action:{action}:{statut}:{maj_le}`. Un rejeu de la même
  action ne change pas `maj_le` ; l'upsert `$setOnInsert` ne crée pas de doublon. Une
  nouvelle transition change `maj_le` et donc la clé.
- Décision : `source_event_id = decision:{hash(texte|acteur|decidee_le)[:16]}`. La route
  conserve le premier `decidee_le` lors d'un rejeu identique, donc le payload reste stable.
- Case : `source_event_id = hash(case utile + snapshot d'ancre)[:16]`. Une modification
  réelle change la clé même si `maj_le` n'a pas bougé ; un rejeu identique la conserve.
  Le dédoublonnage canonique reste assuré par `source_maj_le` et le hash des objets.

## 2. Producteur `boucle` dans `GET /cases/{id}`

`obtenir_case` enrichit la vue legacy après `vue_case` :

```json
{"boucle": {"id": "...", "statut": "...",
            "chaine": [{"id": "...", "type": "...", "titre": "...", "statut": "..."}]}}
```

- Objet courant choisi sans ambiguïté, dans cet ordre :
  1. dernière décision du Travail (`dec-case-{cid}-{n}`) ;
  2. dernière décision de la Situation (`dec-sit-{sid}-{n}`) ;
  3. Investigation (`inv-{sid}`).
- Les candidats sont lus successivement jusqu'au premier objet lisible. Chaque candidat
  fait **une** lecture `boucle.lire_boucle(..., historique=True)` (la chaîne ascendante est
  gérée par C1, pas par une boucle applicative par étape). Maximum trois lectures par
  requête, jamais une lecture par Travail d'une liste.
- Dégradation gracieuse : sans `JUMEAU_PG_DSN`, sans objet canonique, sur panne Postgres
  ou après un timeout de 3 s, la réponse legacy est rendue intacte. `boucle_id` n'est
  exposé que si **aucun** candidat n'est lisible ; sinon la trace partielle du premier
  candidat lisible est renvoyée. Sans Situation liée, aucun champ `boucle*` n'est ajouté.
- La trace publique ne contient que `id`, `type`, `titre`, `statut` : ni `donnees`, ni
  secrets, ni `_historique`.

## 3. Tenant P0

Constat d'audit : les collections legacy `situations`, `initiatives` et `cases` ne
portaient pas systématiquement `tenant_id`.

Choix retenu : **strict par défaut, adoption legacy opt-in, migration idempotente**.

- `pont_travail.filtre_tenant` ne rend que `tenant_id` du tenant courant (alias
  `demo → local` canonisé une seule fois). Un document non estampillé n'est visible par
  personne en mode strict.
- L'adoption des documents historiques exige **deux** variables :
  `JUMEAU_LEGACY_TENANT_ADOPTION=1` et `JUMEAU_LEGACY_TENANT=<tenant propriétaire>`.
  Seul ce tenant voit alors les documents sans `tenant_id` ; un second tenant ne les voit
  jamais.
- La migration `python -m meridian.adapters.outbound.mongo.migrer_tenant_travail
  --tenant <tenant> --dry-run|--apply` estampille `situations`, `cases` et `initiatives`.
  Elle est idempotente, ramène `demo` vers `local` (sauf `--sans-alias`) et crée les index
  `(tenant_id, situations.0)` et `(tenant_id, situations)` (le second est le filet multikey
  si Mongo refuse le chemin positionnel).
- Toutes les créations et mises à jour C2 posent `tenant_id` et `maj_le` :
  `cases.py` (création, PATCH, visite, décision, décision attendue, observations,
  maturation), `actualites.py`, `initiatives.py`, `legacy.py`.
- Les writers de fond `gardien.py`, `pulls_runtime.py` et `initiatives_auto.py`
  propagent le tenant du jumeau/de la situation et ne remplacent jamais un `tenant_id`
  existant par null.
- Toute référence `case.situations` est validée à la création/PATCH et à la lecture
  (`charger_case`, liste) contre le tenant courant ; un id inconnu ou hors tenant rend le
  Travail inaccessible sans révéler son existence. Les routes `brouillon_passation`,
  `decision_attendue` et `agir_sur_maturation` relisent la Situation avec le filtre tenant
  et refusent par 404.
- Deux tenants ne peuvent pas créer deux objets canoniques pour le même document `demo` :
  l'alias est canonisé avant construction de l'événement.

## 4. Tests

```bash
cd backend
.venv/bin/python -m pytest tests/test_pont_travail.py tests/test_conversation_routes.py \
  tests/test_migrer_tenant_travail.py tests/test_travaux_tenant_actualites_initiatives.py \
  tests/test_pont_canonique.py -q
```

Couvrent : mapping action/décision/case, clés d'idempotence, case sans situation,
isolation tenant stricte/adoption, migration idempotente, références `situations`
étrangères refusées, panne outbox, rejeu avec case lié, trace en cascade, >200 Travaux,
deux ordres d'application `case.maj`/`situation.maj`, budgets de timeout, absence de DSN
et panne Postgres. Le test live `tests/test_pont_travail_pg.py` est opt-in via
`JUMEAU_PG_DSN`.
