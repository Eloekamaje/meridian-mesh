# Migration progressive du Travail (Mongo → Postgres)

Le Travail (les « cases » du fil Aujourd'hui / Actualités) reste **écrit dans Mongo**
comme source de référence. La sortie se fait en quatre temps : un read model Postgres
`travail`, un backfill rejouable, une **double écriture** optionnelle qui garde Postgres
à jour, puis la bascule de la lecture et, plus tard, la suppression des écritures Mongo.

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

# 1. Double écriture : les nouvelles écritures Mongo sont miroitées.
export JUMEAU_TRAVAIL_DUAL_WRITE=1
export JUMEAU_TRAVAIL_TENANT=local     # même tenant que le backfill
# puis redémarrer l'API
scripts/dev-travail-worker.sh --une-passe   # vérification/rattrapage ponctuel

# 2. Bascule de la lecture (API), après vérification du read model.
export JUMEAU_TRAVAIL_STORE=postgres
# puis redémarrer l'API

# 3. Plus tard : retirer les écritures Mongo.
#    C'est un changement de code (écrire directement dans TravailPostgres), pas un
#    simple drapeau. Une fois ce chemin livré, retirer le proxy, le worker de sync
#    et ce document ; la table `travail` devient la source d'écriture.
```

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

Le worker démarre au dernier curseur `(maj_le, _id)` présent dans Postgres. Si la table
est vide, il relit tout (équivalent à un backfill) puis se met à jour.

## Drapeau de lecture

`JUMEAU_TRAVAIL_STORE` :

* `mongo` (défaut) : `actualites.py` lit `db.cases` via `TravailDepot` Mongo ;
* `postgres` : `actualites.py` lit la table `travail` via `TravailPostgres`.

La fabrique est `meridian.adapters.outbound.travail_store.travail_store(db, dsn)`.
Avec la double écriture active, les écritures (`POST /actualites/.../travail`,
messages, etc.) vont dans Mongo **et** dans Postgres.

## Correspondance des tenants

Les cas Mongo ne portent pas de tenant. Le backfill et le worker écrivent donc sous :

1. `--tenant` s'il est fourni ;
2. sinon `JUMEAU_TENANT` ;
3. sinon `local` (même défaut que le reste de l'API).

La double écriture suit un réglage distinct, `JUMEAU_TRAVAIL_TENANT`, avec le même
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

* **Les cas sont toujours sans tenant.** La double écriture range tout sous
  `JUMEAU_TRAVAIL_TENANT` ; un déploiement multi-tenant réel exige une colonne/portée de
  tenant dans les cas.
* Le miroir est *best effort* : une panne Postgres après une écriture Mongo réussie
  laisse un retard, rattrapé par le worker ou un backfill. Il n'y a pas de transaction
  distribuée entre les deux bases.
* Le worker et le backfill ne propagent pas les suppressions ; seule la double écriture
  le fait. Un cas supprimé pendant que la double écriture est désactivée reste dans
  `travail` jusqu'à un nettoyage manuel.
* Une mise à jour miroite le document complet relu après l'opération Mongo : le coût est
  celui d'une lecture + d'un upsert par document touché (y compris `update_many`).
* Seules les écritures listées ci-dessus sont miroitées. Un `replace_one`, `bulk_write`
  ou `find_one_and_delete` appelé sur `db.cases` resterait Mongo seul ; les appelants
  actuels n'en utilisent pas.
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
