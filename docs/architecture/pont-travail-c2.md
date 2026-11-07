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
  `enfiler_best_effort` ; une panne Mongo/outbox, une erreur de construction ou un timeout
  (2 s) est journalisé et **n'annule ni ne fait échouer** la route legacy.
- Le worker C1 peut être désactivé : la route ne fait qu'écrire dans `pont_canonique`.
- Aucune sérialisation/signature n'est réimplémentée : les événements sortent de
  `meridian.application.pont_canonique` (`evenement_depuis_situation`,
  `evenement_depuis_case`).
- ADR-0008 : un `case` n'est jamais recopié comme objet métier. Seul le Travail dont
  `situations[0]` référence la Situation traitée est projeté, et uniquement par ses
  décisions. Un case sans Situation liée ne produit rien, même s'il porte des décisions.
- L'événement `case.maj` embarque le snapshot de Situation **d'avant l'écriture** comme
  ancre. Il est ainsi autosuffisant : le worker peut traiter le case avant l'événement de
  Situation. Le snapshot antérieur porte un `source_maj_le` plus ancien ; une fois la
  Situation à jour, il ne la réécrit pas.
- Chaque action/décision pose `maj_le` sur la Situation. Sans cette version, le worker C1
  ignorerait en bloc un second événement de Situation de même `source_maj_le` (et la
  décision canonique ne serait jamais créée). Un rejeu ne change ni `maj_le`, ni
  `decidee_le`, donc son événement reste identique.

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
- Case : `source_event_id` par défaut de C1 (`maj_le` du case), stable tant que le Travail
  n'a pas changé.

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
- Une seule lecture canonique : `boucle.lire_boucle(conn, tenant, id, historique=True)`
  via l'adapter Postgres existant. Aucune boucle N+1 sur les étapes.
- Dégradation gracieuse : sans `JUMEAU_PG_DSN`, sans objet canonique, sur panne Postgres
  ou après un timeout de 3 s, la réponse legacy est rendue intacte avec seulement
  `boucle_id`. Sans Situation liée, aucun champ `boucle*` n'est ajouté.
- La trace publique ne contient que `id`, `type`, `titre`, `statut` : ni `donnees`, ni
  secrets, ni `_historique`.

## 3. Tenant P0

Constat d'audit : les collections legacy `situations`, `initiatives` et `cases` ne
portaient pas systématiquement `tenant_id`.

Choix retenu : **normalisation applicative, pas de migration rétroactive risquée**.

- toutes les créations applicatives de `cases` et de `situations` posent désormais
  `tenant_id` (`cases.py`, `actualites.py`, `initiatives.py`) ;
- les routes legacy d'action/décision posent `tenant_id` sur la Situation écrite et
  refusent (404) un document qui déclare un autre tenant ;
- les lectures sont filtrées par tenant via `pont_travail.filtre_tenant` :
  `tenant_id == courant` (`local` et `demo` restent équivalents pour la démo) **ou**
  `tenant_id` absent/null. Le second cas est le compromis
  de reprise pour les documents historiques : ils sont adoptés par le tenant courant à
  leur première écriture. Un document qui déclare explicitement un autre tenant est
  toujours exclu ;
- le tenant de la lecture canonique est celui de la requête (`_tenant_requete` /
  contexte d'authentification), pas un défaut codé en dur.

Limite assumée : un document historique sans `tenant_id` ne peut pas être attribué de
façon fiable à un tenant précis avant sa première réécriture. Une migration rétroactive
reste un chantier séparé si un déploiement multi-tenant réel l'exige.

## 4. Tests

```bash
cd backend
.venv/bin/python -m pytest tests/test_pont_travail.py tests/test_conversation_routes.py -q
```

Couvrent : mapping action/décision/case, clés d'idempotence, case sans situation,
isolation tenant, panne outbox, rejeu sans doublon, trace complète, `boucle_id` seul,
absence de DSN et panne Postgres.
