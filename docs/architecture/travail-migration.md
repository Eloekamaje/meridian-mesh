# Migration progressive du Travail (Mongo → Postgres)

Le Travail (les « cases » du fil Aujourd'hui / Actualités) est **écrit dans Mongo** par
défaut. La sortie se fait en quatre temps : un read model Postgres `travail`, un backfill
rejouable, une **double écriture** optionnelle, puis la bascule de la lecture et une
bascule opt-in des écritures (`JUMEAU_TRAVAIL_WRITE=postgres`) qui remplace `db.cases`
par une collection Postgres. Le contenu des pièces jointes passe par un adapter
Mongo/GridFS, local ou S3/MinIO (voir [stockage-pieces.md](stockage-pieces.md)).

## Modèle Postgres

```sql
CREATE TABLE travail (
    id        text NOT NULL,
    tenant_id text NOT NULL,
    donnees   jsonb NOT NULL,   -- document de cas complet (Mongo, `_id` sérialisé)
    version   bigint NOT NULL,  -- +1 seulement quand `donnees` change
    maj_le    timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, id)
);
```

* Schéma appliqué par `meridian.adapters.outbound.postgres.depot.appliquer_schema`
  (`CREATE TABLE IF NOT EXISTS` : aucune migration destructive). La double écriture
  l'applique aussi au démarrage avant le premier miroir.
* `donnees` conserve le cas tel quel ; `_id` y est gardé en texte pour le curseur de
  synchronisation, mais n'est pas renvoyé par les lectures.
* Le backfill et le worker ne suppriment jamais de ligne. La double écriture, elle,
  retire du read model les identifiants effectivement supprimés dans Mongo.
* La table est couverte par `rls.TABLES` ; l'activation RLS reste un geste de déploiement séparé.
  L'isolation repose sur le filtre `tenant_id` de l'adapter.

## Double écriture (Mongo → Postgres au fil de l'eau)

Le proxy `meridian.adapters.outbound.mongo.travail_proxy.TravailCollection` enveloppe
`db.cases` **uniquement au démarrage**, quand les deux conditions sont réunies :

```bash
JUMEAU_TRAVAIL_DUAL_WRITE=1      # défaut : désactivé
JUMEAU_PG_DSN=postgresql://…     # sinon rien n'est câblé
```

* Les lectures (`find`, `find_one`, `aggregate`, `count_documents`, curseurs, etc.) sont
  déléguées telles quelles à Mongo ; le proxy ne change ni leur résultat ni leur contrat.
* Les écritures passent d'abord par Mongo, puis le ou les documents résultants sont
  upsertés dans `travail` : `insert_one`, `update_one`, `update_many`,
  `find_one_and_update`, `delete_one`, `delete_many`.
* Les objets de retour Mongo (`InsertOneResult`, `UpdateResult`, document de
  `find_one_and_update`, etc.) sont rendus inchangés.
* Si Postgres échoue après une écriture Mongo réussie, l'erreur est journalisée et
  l'écriture Mongo reste acquise. Le worker de rattrapage peut reprendre depuis `maj_le`.
  Une panne Postgres ne bloque donc pas l'API ; elle retarde seulement le read model.
* Le tenant Postgres vient de `JUMEAU_TRAVAIL_TENANT` (défaut `local`). **Les cas Mongo
  ne portent toujours pas de tenant** : tous les cas écrits par cette instance vont dans
  ce tenant. Une vraie migration multi-tenant demandera une colonne/portée de tenant dans
  les cas ; elle n'est pas inventée ici. Pour que lecture et écriture visent le même
  tenant, garder `JUMEAU_TRAVAIL_TENANT` aligné avec `JUMEAU_TENANT` (ou `--tenant`).
* Si l'application du schéma échoue au démarrage, l'API démarre quand même avec les
  écritures Mongo seules et journalise l'échec.
* Seul l'attribut `db.cases` est enveloppé. Un accès direct `db["cases"]` contournerait
  la double écriture ; les appelants applicatifs utilisent `db.cases`.

## Ordre de bascule

Depuis `backend/`, avec l'environnement chargé :

```bash
set -a; . ./.env; set +a

# 0. Backfill à blanc (défaut), puis application : Postgres part complet.
.venv/bin/python -m meridian.adapters.outbound.postgres.migrer_travail --tenant local --dry-run
.venv/bin/python -m meridian.adapters.outbound.postgres.migrer_travail --tenant local --apply
# avec rattrapage des cas orphelins et pose du tenant Mongo :
.venv/bin/python -m meridian.adapters.outbound.postgres.migrer_travail --tenant local --apply --supprimer-absents --poser-tenant-mongo

# 1. Double écriture : les nouvelles écritures Mongo sont miroitées.
export JUMEAU_TRAVAIL_DUAL_WRITE=1
export JUMEAU_TRAVAIL_TENANT=local     # même tenant que le backfill
# puis redémarrer l'API
scripts/dev-travail-worker.sh --une-passe --reconcilier-chaque 300
# en service : worker continu, réconciliation des suppressions toutes les 300 s
scripts/dev-travail-worker.sh

# 2. Bascule de la lecture (API), après vérification du read model.
export JUMEAU_TRAVAIL_STORE=postgres
# puis redémarrer l'API

# 3. Bascule des écritures : `db.cases` devient une collection Postgres.
export JUMEAU_TRAVAIL_WRITE=postgres
# JUMEAU_TRAVAIL_STORE=postgres reste recommandé pour la lecture Actualités.
# puis redémarrer l'API. Vérifier : création, PATCH, ajout de message, pièce,
# suppression d'une conversation, puis SELECT count(*) FROM travail.
#
# Rollback : retirer JUMEAU_TRAVAIL_WRITE et redémarrer. Les écritures faites
# pendant la bascule ne sont pas dans Mongo ; un export Postgres -> Mongo est
# nécessaire avant de revenir durablement à Mongo.
```

La bascule d'écriture est opt-in et testée par `test_travail_collection_postgres.py`
et une fumée API réelle. Les écritures d'un tenant sont sérialisées par un advisory
lock Postgres (`pg_advisory_lock(hashtext(tenant))`) en plus du verrou asyncio local.

Pendant la phase 2, la double écriture doit rester active : c'est elle qui rend les
écritures immédiatement visibles à la lecture Postgres. Le worker peut rester en filet
de sécurité (intervalle court) mais n'est plus le chemin principal.

## Options utiles du backfill / worker

| Option | Rôle |
| --- | --- |
| `--tenant` | tenant Postgres (défaut `JUMEAU_TENANT`, sinon `local`) |
| `--mongo-url`, `--db-name` | source Mongo (défaut `MONGO_URL`, `DB_NAME`) |
| `--dsn` | Postgres (défaut `JUMEAU_WORKER_PG_DSN`, sinon `JUMEAU_PG_DSN`) |
| `--limite` | documents par lot |
| `--dry-run` / `--apply` | backfill : compter (défaut) ou écrire |
| `--une-passe` | worker : rattraper puis sortir |
| `--depuis` | worker : reprendre après un `maj_le` ISO explicite |
| `--reconcilier-chaque` | worker : secondes entre deux réconciliations des suppressions (défaut 300, 0 pour désactiver) |

Le worker démarre au dernier curseur `(maj_le, _id)` présent dans Postgres. Si la table
est vide, il relit tout (équivalent à un backfill) puis se met à jour.

## Drapeau de lecture

`JUMEAU_TRAVAIL_STORE` :

* `mongo` (défaut) : `actualites.py` lit `db.cases` via `TravailDepot` Mongo ;
* `postgres` : `actualites.py` lit la table `travail` via `TravailPostgres`.

La fabrique est `meridian.adapters.outbound.travail_store.travail_store(db, dsn)`.
Avec la double écriture active, les écritures (`POST /actualites/.../travail`,
messages, etc.) vont dans Mongo **et** dans Postgres. Avec
`JUMEAU_TRAVAIL_WRITE=postgres`, `db.cases` est une collection Postgres et Mongo n'est
plus écrit pour les cas ; le stockage des pièces jointes est indépendant.

## Correspondance des tenants

Le tenant est posé par le middleware d'authentification (demo `X-Tenant`, proxy ou
claim OIDC) et écrit dans le document. Le backfill et le worker écrivent sous :

1. `--tenant` s'il est fourni ;
2. sinon `JUMEAU_TENANT` ;
3. sinon `local` (même défaut que le reste de l'API).

La double écriture suit le contexte de requête puis `JUMEAU_TRAVAIL_TENANT`, avec le même
défaut `local`. Aligner les deux réglages pendant la bascule. Tous les cas d'un
backfill vont dans ce tenant. Pour plusieurs tenants, lancer le backfill et le worker
une fois par tenant (la source Mongo devra alors être filtrée par tenant dans un lot
ultérieur) ; la double écriture, elle, ne sait pas encore distinguer les tenants.

## Retour arrière

1. Retirer `JUMEAU_TRAVAIL_STORE=postgres` (ou le remettre à `mongo`) et redémarrer
   l'API : la lecture revient immédiatement à Mongo.
2. Retirer `JUMEAU_TRAVAIL_DUAL_WRITE=1` et redémarrer l'API : les écritures redeviennent
   purement Mongo. Comme Mongo a toujours été écrit en premier, rien n'est à réconcilier.
3. Arrêter le worker de sync si besoin. La table `travail` peut rester en place sans
   effet ; un backfill complet la remettra à niveau si on réactive la lecture Postgres.

## Limites connues

* **Le tenant est porté par la requête et par le document.** Le middleware
  d'authentification pose le tenant effectif (demo, proxy ou OIDC), le proxy l'écrit
  dans le cas Mongo et Postgres ; `--poser-tenant-mongo` migre les cas historiques.
  La portée multi-tenant reste portée par un seul `tenant_id` par déploiement.
* Le miroir est *best effort* avec trois tentatives et un backoff court : une panne
  Postgres prolongée laisse un retard, rattrapé par le worker ou un backfill. Il n'y a
  pas de transaction distribuée entre les deux bases.
* Les suppressions sont propagées par la double écriture, par `--supprimer-absents`
  au backfill et par `--reconcilier-chaque` (défaut 300 s) dans le worker ; un cas
  supprimé hors de ces chemins reste dans `travail` jusqu'à la prochaine passe.
* Une mise à jour miroite le document complet relu après l'opération Mongo : le coût est
  celui d'une lecture + d'un upsert par document touché (y compris `update_many`).
* Les écritures listées ci-dessus, `replace_one` et `bulk_write` sont miroitées.
  Un `find_one_and_delete` ou une opération bulk inconnue resterait Mongo seul ; les
  appelants actuels n'en utilisent pas.
* Le curseur compare `maj_le` comme chaîne ISO, comme le fait Mongo. Des formats de
  date hétérogènes (anciens documents) peuvent fausser l'ordre ; un backfill complet
  corrige le read model.
* RLS n'est pas activé automatiquement ; l'adapter filtre explicitement par
  `tenant_id`.
* Le worker et la double écriture ne migrent ni les pièces jointes ni les index Mongo ;
  seuls les documents `cases` sont copiés.

## Vérifier

```bash
cd backend
set -a; . ./.env; set +a
.venv/bin/python -m pytest meridian/tests/test_travail_proxy.py \
  meridian/tests/test_travail_sync.py meridian/tests/test_travail_store.py -q
```

Le test de fumée `test_travail_proxy.py::test_fumee_double_ecriture_mongo_postgres`
(si `MONGO_URL` et `JUMEAU_PG_DSN` sont définis) insère, met à jour puis supprime un cas
via le proxy, vérifie chaque étape dans Postgres et nettoie les deux bases.
`test_travail_smoke.py` couvre, lui, le backfill et la lecture Postgres de la route
`/actualites`.
