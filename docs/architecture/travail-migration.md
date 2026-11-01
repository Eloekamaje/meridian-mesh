# Migration progressive du Travail (Mongo → Postgres)

Le Travail (les « cases » du fil Aujourd'hui / Actualités) reste **écrit dans Mongo**.
Ce lot prépare une sortie progressive : un read model Postgres `travail` est alimenté
depuis Mongo par un backfill rejouable puis par un worker de rattrapage. Un drapeau
permet de basculer **uniquement la lecture** d'Actualités, et de revenir en arrière
sans perte.

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
  (`CREATE TABLE IF NOT EXISTS` : aucune migration destructive).
* `donnees` conserve le cas tel quel ; `_id` y est gardé en texte pour le curseur de
  synchronisation, mais n'est pas renvoyé par les lectures.
* Aucune suppression : un cas retiré de Mongo reste dans le read model.
* La table est couverte par `rls.TABLES` ; l'activation RLS reste un geste de déploiement séparé.
  L'isolation repose sur le filtre `tenant_id` de l'adapter.

## Ordre de bascule

Depuis `backend/`, avec l'environnement chargé :

```bash
set -a; . ./.env; set +a

# 1. Backfill à blanc (défaut), puis application.
.venv/bin/python -m jumeau.migrer_travail --tenant local --dry-run
.venv/bin/python -m jumeau.migrer_travail --tenant local --apply

# 2. Worker de rattrapage (writes toujours Mongo), depuis la racine du dépôt.
scripts/dev-travail-worker.sh --une-passe
scripts/dev-travail-worker.sh --intervalle 5          # boucle locale
# En service : scripts/meridian-travail-worker.service

# 3. Bascule de la lecture (API), après vérification du read model.
JUMEAU_TRAVAIL_STORE=postgres
# puis redémarrer l'API
```

Options utiles :

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
Les écritures (`POST /actualites/.../travail`, messages, etc.) restent sur Mongo.

## Correspondance des tenants

Les cas Mongo ne portent pas de tenant. Le backfill et le worker écrivent donc sous :

1. `--tenant` s'il est fourni ;
2. sinon `JUMEAU_TENANT` ;
3. sinon `local` (même défaut que le reste de l'API).

Tous les cas d'un backfill vont dans ce tenant. Pour plusieurs tenants, lancer le
backfill et le worker une fois par tenant (la source Mongo devra alors être filtrée
par tenant dans un lot ultérieur).

## Retour arrière

1. Retirer `JUMEAU_TRAVAIL_STORE=postgres` (ou la remettre à `mongo`) et redémarrer
   l'API : la lecture revient immédiatement à Mongo.
2. Arrêter le worker de sync. La table `travail` peut rester en place sans effet.
3. Aucune écriture n'a été redirigée : il n'y a rien à réconcilier.

## Limites connues

* **Les écritures restent Mongo.** Un travail créé ou modifié n'est visible côté
  Postgres qu'après la passe de sync suivante (intervalle du worker). Tant que le
  drapeau est sur `postgres`, la lecture d'un travail très récent peut donc être en
  retard ; garder un intervalle court pendant la période de bascule.
* Pas de suppression propagée : `travail` ne fait que croître.
* Le curseur compare `maj_le` comme chaîne ISO, comme le fait Mongo. Des formats de
  date hétérogènes (anciens documents) peuvent fausser l'ordre ; un backfill complet
  corrige le read model.
* RLS n'est pas activé automatiquement ; l'adapter filtre explicitement par
  `tenant_id`.
* Le worker ne migre pas les pièces jointes ni les index Mongo ; seuls les documents
  `cases` sont copiés.

## Vérifier

```bash
cd backend
set -a; . ./.env; set +a
.venv/bin/python -m pytest jumeau/tests/test_travail_sync.py jumeau/tests/test_travail_store.py -q
```

Le test de fumée `test_travail_smoke.py` (si `MONGO_URL` et `JUMEAU_PG_DSN` sont
définis) insère un cas de démonstration, applique le backfill, active le drapeau et
appelle la route `/actualites` via `TestClient`, puis nettoie Mongo et Postgres.
