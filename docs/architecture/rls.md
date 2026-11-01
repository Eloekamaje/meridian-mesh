# RLS multi-tenant

Les policies RLS de Méridian sont une **défense en profondeur** : le code filtre déjà par tenant,
mais Postgres refuse en plus toute ligne hors du tenant courant. Elles sont **opt-in** et ne sont
jamais activées au démarrage de l'API ou des workers.

- Code : `backend/meridian/adapters/outbound/postgres/rls.py`
  (compatibilité : `backend/jumeau/rls.py`).
- Contexte : `JUMEAU_RLS=1` fait poser `meridian.tenant_id` par transaction (ou par session sur
  une connexion worker dédiée à un tenant).
- Activation : commande explicite `python -m jumeau.rls --activer`.
- Vérification : `python -m jumeau.rls --verifier`.
- Workers : DSN dédié `JUMEAU_WORKER_PG_DSN` (repli `JUMEAU_PG_DSN`), rôle
  `meridian_worker` pour le balayage global ou `meridian_app` + `JUMEAU_WORKER_TENANTS`
  pour une passe par tenant.

## Tables couvertes

`rls.TABLES` couvre les tables qui portent directement `tenant_id` :

```text
jumeau, source, preuve, claim, revue, contradiction, ancre, consigne,
interface_contract, interface_operation, interface_binding, interface_assertion,
discovery_run, identity_decision, objet_entreprise, outil_audit,
valeur, memoire_durable, prediction_calibration,
execution_run, execution_evenement, execution_outbox, execution_timer,
execution_effet, execution_approbation, execution_etape,
source_schedule, ingestion_run, travail
```

`rls.TABLES_DERIVEES` couvre les tables filles sans `tenant_id`, via une policy `EXISTS` sur leur
parent :

| Table fille | Parent | Jointure |
|---|---|---|
| `claim_preuve` | `claim` | `claim_id` |
| `claim_source` | `claim` | `claim_id` |
| `verification` | `claim` | `claim_id` |
| `fiche_vivante` | `jumeau` | `jumeau_id` |
| `evaluation` | `jumeau` | `jumeau_id` |

La policy est toujours nommée `tenant_isolation` et utilise :

```sql
tenant_id = current_setting('meridian.tenant_id', true)
```

sans setting, `current_setting(..., true)` vaut `NULL` et aucune ligne n'est visible.

## Prérequis : rôles applicatif et worker

Les policies ne protègent pas un rôle `SUPERUSER` ou `BYPASSRLS`. Le CLI **refuse** d'activer RLS
avec un tel rôle.

Deux rôles sont attendus en production :

| Rôle | Attributs | Usage |
|---|---|---|
| `meridian_app` | `NOSUPERUSER NOBYPASSRLS` | API et workers **par tenant** ; les policies s'appliquent. |
| `meridian_worker` | `NOSUPERUSER BYPASSRLS` | Workers qui balaient **tous** les tenants ; les policies ne s'appliquent pas. |

```sql
-- API et workers par tenant : défense en profondeur conservée.
CREATE ROLE meridian_app LOGIN PASSWORD '...' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;

-- Workers multi-tenant : policies contournées, secret et accès réseau distincts.
CREATE ROLE meridian_worker LOGIN PASSWORD '...' NOSUPERUSER BYPASSRLS NOCREATEDB NOCREATEROLE;

GRANT USAGE ON SCHEMA public TO meridian_app, meridian_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO meridian_app, meridian_worker;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO meridian_app, meridian_worker;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO meridian_app, meridian_worker;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO meridian_app, meridian_worker;
```

### `NOSUPERUSER` vs `BYPASSRLS`

- **`meridian_app` (`NOBYPASSRLS`)** : chaque transaction doit poser `meridian.tenant_id`.
  C'est le seul rôle utilisable par l'API. Pour un worker, il exige une passe par tenant
  (source worker) ou un processus par tenant (outbox, exécution). Si le worker n'a pas de liste
  de tenants, il **refuse de démarrer** au lieu de balayer les tenants à vide.
- **`meridian_worker` (`BYPASSRLS`)** : voit et écrit tous les tenants sans contexte. C'est le
  mode simple pour un worker qui doit scanner toute la base, mais il **annule la défense en
  profondeur** pour ce processus. Il ne doit jamais servir l'API, doit avoir un secret distinct,
  un accès réseau restreint et un audit de ses accès. `SUPERUSER` est encore plus large : ne pas
  l'utiliser pour un worker.

1. Faire porter les tables par un rôle de déploiement/propriétaire distinct, ou par `meridian_app`
   lui-même. `FORCE ROW LEVEL SECURITY` fait que le propriétaire est aussi soumis aux policies.

2. Exécuter `--activer` / `--desactiver` avec un rôle qui possède les tables (ou a les droits DDL)
   **et** qui est lui-même `NOSUPERUSER NOBYPASSRLS` : le CLI refuse un rôle superuser/BYPASSRLS.
   Si les tables appartiennent à un rôle de déploiement, utiliser son DSN pour l'activation ;
   l'API utilise ensuite `meridian_app`.

3. Utiliser le DSN de `meridian_app` pour l'API (`JUMEAU_PG_DSN`). Utiliser
   `JUMEAU_WORKER_PG_DSN` pour les workers ; le repli est `JUMEAU_PG_DSN` si la variable worker
   est absente, ce qui préserve le développement local.

Vérifier le rôle effectif avant toute activation :

```sql
SELECT current_user, rolsuper, rolbypassrls
FROM pg_roles
WHERE rolname = current_user;
```

Attendu pour l'API : `rolsuper = false` et `rolbypassrls = false`.
Attendu pour `meridian_worker` : `rolsuper = false`, `rolbypassrls = true`.

## Ordre d'activation

Les commandes ci-dessous supposent que `.env` porte le DSN du rôle d'activation (propriétaire des
tables, `NOSUPERUSER NOBYPASSRLS`). Si l'API utilise `meridian_app`, remplacer `JUMEAU_PG_DSN` par
le DSN du propriétaire le temps de l'activation, puis restaurer le DSN applicatif.

1. **Sauvegarder** la base (snapshot RDS ou `pg_dump`).
2. Vérifier l'état courant, sans rien modifier :

   ```bash
   cd backend
   set -a; . ./.env; set +a
   .venv/bin/python -m jumeau.rls --verifier
   ```

   Sortie `KO` ou code retour `1` = policy manquante, RLS non activé/non forcé, ou rôle qui
   contourne RLS.
3. Activer les policies. L'opération est idempotente : `DROP POLICY IF EXISTS` précède chaque
   `CREATE POLICY`, dans une transaction.

   ```bash
   .venv/bin/python -m jumeau.rls --activer
   ```

   `--tables` permet de restreindre l'activation à un sous-ensemble (syntaxe :
   `--tables objet_entreprise`). Ne l'utiliser que si **tous** les writers de ces tables posent le
   contexte : un worker, un trigger ou un CLI de maintenance qui écrit sans contexte échouera. En
   pratique, l'activation par défaut suppose que les workers sont adaptés (voir
   [Workers multi-tenant](#workers-multi-tenant)).

4. Vérifier après activation :

   ```bash
   .venv/bin/python -m jumeau.rls --verifier
   ```

5. Configurer les workers **avant** de les relancer. Le DSN worker est prioritaire :

   ```bash
   # Rôle global, pour un worker qui balaie tous les tenants (source, outbox, exécution).
   export JUMEAU_WORKER_PG_DSN="postgresql://meridian_worker:...@.../meridian"

   # OU rôle applicatif sans BYPASSRLS + liste explicite pour le source worker.
   export JUMEAU_WORKER_PG_DSN="postgresql://meridian_app:...@.../meridian"
   export JUMEAU_WORKER_TENANTS="tenant-a,tenant-b"
   ```

   Si `JUMEAU_WORKER_PG_DSN` est absente, les workers retombent sur `JUMEAU_PG_DSN` (compatibilité
   locale). Le mode retenu est vérifié au démarrage et journalisé (voir
   [Workers multi-tenant](#workers-multi-tenant)).

6. Activer le contexte côté API **après** que tous les chemins appelés par l'API posent leur
   tenant :

   ```bash
   JUMEAU_RLS=1
   ```

   `JUMEAU_RLS` ne crée ni ne supprime les policies : une policy déjà créée s'applique à tout rôle
   non-superuser, même avec `JUMEAU_RLS=0`. Le flag ne fait que demander à l'application de poser
   `meridian.tenant_id`. Les workers détectent aussi les policies actives en base : ils refusent un
   balayage global avec un rôle `NOBYPASSRLS`, même si `JUMEAU_RLS` a été oublié.

7. Redémarrer l'API et les workers, puis vérifier les parcours critiques (Boucle, catalogue
   d'outils, runs, ingestion). Vérifier le rôle réellement utilisé par chaque worker :

   ```bash
   psql "$JUMEAU_WORKER_PG_DSN" -c \
     "SELECT current_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user;"
   ```

   Attendu : `meridian_app` → `false/false` ; `meridian_worker` → `false/true` ; jamais
   `rolsuper = true`. Le log de démarrage doit indiquer le mode : passe par tenant, ou
   avertissement `BYPASSRLS`.

Ne jamais activer RLS sur une base de développement sans le vouloir : la commande est explicite et
le CLI refuse les rôles superuser/BYPASSRLS.

## Utilisation côté routes et workers

Le helper `rls.contexte_tenant(conn, tenant)` valide le slug puis exécute :

```python
SELECT set_config('meridian.tenant_id', %s, true)
```

`true` rend le réglage **local à la transaction**. Le helper ouvre lui-même une transaction (ou un
savepoint si l'appelant en a déjà une), donc il fonctionne aussi sur une connexion
`autocommit=True`. Il remet le setting à vide en sortie.

Pour un worker qui enchaîne plusieurs transactions courtes sur une connexion dédiée à un seul
tenant, `rls.contexte_tenant_session(conn, tenant)` pose le réglage au niveau **session**
(`set_config(..., false)`) et le retire en sortie. Il ne faut jamais l'utiliser sur une connexion
mutualisée : le tenant survivrait à la transaction. `source_worker` s'en sert uniquement pendant
l'ingestion, qui peut durer plus longtemps que le bail et ne doit pas garder une transaction ouverte
ni bloquer le heartbeat.

Route ou service synchrone :

```python
from jumeau import rls

with psycopg.connect(dsn, autocommit=True) as conn:
    if rls.est_actif():
        with rls.contexte_tenant(conn, tenant):
            return action(conn)
    return action(conn)
```

Règles :

- ne jamais poser `meridian.tenant_id` avec `set_config(..., false)` sur une connexion d'API
  (fuite entre transactions) ; seul `contexte_tenant_session` le fait, sur une connexion worker
  dédiée à un seul tenant et avec un reset garanti ;
- ne jamais prendre le tenant dans le body ou un header non authentifié ;
- toute nouvelle route qui touche une table couverte doit passer par `contexte_tenant` quand
  `JUMEAU_RLS=1` ;
- une connexion worker qui traite **un seul tenant** doit appeler `contexte_tenant` autour de sa
  transaction ; un worker qui balaie **plusieurs tenants** utilise une passe par tenant
  (`JUMEAU_WORKER_TENANTS`) ou un rôle `BYPASSRLS` dédié (voir ci-dessous).

## Vérification

Diagnostic du CLI :

```bash
.venv/bin/python -m jumeau.rls --verifier
```

Le rapport liste chaque table (`ok`/`KO`), le schéma, le rôle et les politiques supplémentaires.
Une policy supplémentaire est signalée : elle peut élargir l'accès (les policies permissives se
combinent en `OR`).

Requêtes SQL de contrôle :

```sql
-- RLS activé et forcé sur chaque table
SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = current_schema()
  AND c.relname = ANY (ARRAY[
    'jumeau','source','preuve','claim','revue','contradiction','ancre','consigne',
    'interface_contract','interface_operation','interface_binding','interface_assertion',
    'discovery_run','identity_decision','objet_entreprise','outil_audit',
    'valeur','memoire_durable','prediction_calibration',
    'execution_run','execution_evenement','execution_outbox','execution_timer',
    'execution_effet','execution_approbation','execution_etape',
    'source_schedule','ingestion_run','travail',
    'claim_preuve','claim_source','verification','fiche_vivante','evaluation'])
ORDER BY c.relname;

-- Une seule policy tenant_isolation par table
SELECT schemaname, tablename, policyname, cmd, qual, with_check
FROM pg_policies
WHERE schemaname = current_schema()
ORDER BY tablename, policyname;
```

Test fonctionnel (avec le rôle applicatif, hors superuser) :

```sql
-- Dans une transaction, avec le tenant A
BEGIN;
SELECT set_config('meridian.tenant_id', 'tenant-a', true);
SELECT count(*) FROM objet_entreprise;  -- uniquement tenant-a
COMMIT;
```

## Rollback

Le retour arrière est explicite et immédiat :

```bash
cd backend
set -a; . ./.env; set +a
.venv/bin/python -m jumeau.rls --desactiver
```

Puis retirer `JUMEAU_RLS=1` de l'environnement de l'API **et des workers**, et redémarrer les
processus. `--desactiver` retire les policies et désactive RLS sur les tables sélectionnées ; il ne
supprime aucune donnée.

En cas d'incident, si le rôle applicatif n'a pas les droits DDL, exécuter la désactivation avec le
rôle de déploiement. Si un worker refuse de démarrer, ne pas lui donner `SUPERUSER` : soit fournir
`JUMEAU_WORKER_TENANTS`, soit utiliser le rôle `meridian_worker` dédié.

## Workers multi-tenant

Le worker d'ingestion écrit notamment `jumeau`, `source`, `preuve`, `claim`, `claim_preuve`,
`claim_source`, `verification` (trigger), `fiche_vivante`, `source_schedule`, `ingestion_run`, les
tables `interface_*` et l'outbox ; le worker d'exécution réclame et met à jour les tables
`execution_*` pour n'importe quel tenant ; le dispatcher outbox publie `execution_outbox`.

Avec RLS actif et un rôle `NOBYPASSRLS` :

- une lecture sans `meridian.tenant_id` ne voit **aucune ligne** ;
- un `INSERT` sans contexte est refusé par le `WITH CHECK` ;
- un `UPDATE ... RETURNING` ou un `FOR UPDATE SKIP LOCKED` sans contexte ne réclame **aucun run**.

Chaque worker choisit donc explicitement l'un des deux modes ci-dessous. Il ne démarre jamais en
silence avec un balayage global et un rôle soumis aux policies.

### Mode 1 — passe par tenant (recommandé pour le source worker)

```bash
export JUMEAU_WORKER_PG_DSN="postgresql://meridian_app:...@.../meridian"
export JUMEAU_WORKER_TENANTS="tenant-a,tenant-b"
```

Ce mode exige des policies **actives** : sans policy, `set_config` ne filtre aucune requête et le
worker refuserait de démarrer. `source_worker` boucle alors tenant par tenant : les étapes courtes
(reprise, planification, enfilement, claim) utilisent `rls.contexte_tenant(conn, tenant)` par
transaction, et l'ingestion utilise `rls.contexte_tenant_session` pour ne pas garder une transaction
ouverte pendant les appels réseau. Le heartbeat du run repose le tenant sur sa connexion dédiée. Les
runs d'un tenant ne sont jamais réclamés sous le contexte d'un autre. Pendant la passe, le worker
expose aussi `JUMEAU_PG_DSN` scopé au tenant pour les connexions auxiliaires (rédaction, outils) qui
ouvrent leur propre connexion. La liste est explicite : aucun annuaire de tenants n'est interrogé
(une lecture d'annuaire serait elle-même soumise à RLS).

`outbox_worker` et `execution.worker` acceptent **un seul** tenant par processus dans ce mode : la
connexion pose `-c meridian.tenant_id=<slug>` au niveau session, donc le claim et le dispatch ne
voient que ce tenant. Lancer un processus par tenant.

Le source worker applique `schema.sql` au démarrage par défaut. Avec un rôle `meridian_app` ou
`meridian_worker` limité aux DML, lancer le service avec `--sans-schema` : le schéma doit être créé
par le déploiement, pas par un rôle d'exécution.

### Mode 2 — rôle `BYPASSRLS` dédié (balayage global)

```bash
export JUMEAU_WORKER_PG_DSN="postgresql://meridian_worker:...@.../meridian"
# Ne pas définir JUMEAU_WORKER_TENANTS.
```

Les workers balaient tous les tenants sans contexte. Au démarrage, ils journalisent un
avertissement : les policies ne protègent pas ce processus. Ce rôle est réservé aux workers, jamais
à l'API, et doit avoir un secret distinct. `JUMEAU_WORKER_TENANTS` est refusé avec ce rôle : un
`BYPASSRLS` ignore les policies, donc le contexte ne limiterait pas les lignes.

### Refus explicites

- RLS actif (flag `JUMEAU_RLS=1` ou policies détectées en base) + rôle `NOBYPASSRLS` + aucune liste
  de tenants → **démarrage refusé** par `rls.configurer_worker` avec un message qui renvoie ici.
- `JUMEAU_WORKER_TENANTS` + activation **partielle** (`--tables`) → **démarrage refusé** : une table
  sans policy laisserait passer tous les tenants. Le mode par tenant exige `--activer` sans
  `--tables`.
- `outbox_worker` ou `execution.worker` + rôle `NOBYPASSRLS` + plusieurs tenants → **démarrage
  refusé** : un processus par tenant.
- Le CLI `--activer` couvre par défaut **toutes** les tables ; `--tables` reste disponible pour un
  sous-ensemble dont tous les writers (API, workers, triggers, CLI de maintenance) posent le
  contexte.

## Vérification après activation des workers

1. Vérifier que le worker démarre avec le mode attendu (log de démarrage).
2. Source worker, une passe bornée, rôle `meridian_app` et un tenant :

   ```bash
   cd backend
   set -a; . ./.env; set +a
   export JUMEAU_WORKER_PG_DSN="postgresql://meridian_app:...@.../meridian"
   JUMEAU_WORKER_TENANTS=tenant-a \
     .venv/bin/python -m jumeau.source_worker --une-passe --sans-schema
   ```

   Avec un rôle `NOBYPASSRLS`, la même commande **sans** `JUMEAU_WORKER_TENANTS` doit échouer au
   démarrage : c'est le test du refus explicite.
3. Exécution et outbox, un tenant par processus :

   ```bash
   JUMEAU_WORKER_TENANTS=tenant-a .venv/bin/python -m jumeau.execution.worker
   JUMEAU_WORKER_TENANTS=tenant-a .venv/bin/python -m jumeau.execution.outbox_worker
   ```
4. Contrôle SQL du rôle et des policies, avec le DSN worker :

   ```bash
   psql "$JUMEAU_WORKER_PG_DSN" -c \
     "SELECT current_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user;"
   ```
