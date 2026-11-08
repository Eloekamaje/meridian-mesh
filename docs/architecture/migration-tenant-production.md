# Migration tenant en production — runbook

Cette procédure est **forward-only** et doit être exécutée pendant une fenêtre à faible trafic.
Elle couvre deux périmètres distincts :

1. **Mongo legacy** — `situations`, `cases`, `initiatives` : estampillage `tenant_id` et alias `demo → local`.
2. **Postgres canonique** — objets déjà écrits sous `demo` : bascule contrôlée vers `local`.

> **Prérequis absolu** : la migration Mongo est mono-tenant. Elle estampille tous les documents
> sans tenant avec **un seul** propriétaire (`JUMEAU_LEGACY_TENANT`). Si la base contient plusieurs
> tenants métier, ne pas lancer `--apply` : partitionner d'abord les données par propriétaire.

## 0. Sauvegardes et gel

- Sauvegarde Mongo (`mongodump`) et Postgres (`pg_dump`) vérifiée.
- Relever les compteurs de départ :
  - `situations`, `cases`, `initiatives` par `tenant_id` (y compris absent/null) ;
  - `objet_entreprise` et `travail` par `tenant_id` dans Postgres.
- Arrêter ou mettre en pause les workers C1/D et les writers legacy pendant l'`--apply`
  (sinon une écriture concurrente peut recréer un document sans tenant juste après la migration).
- Vérifier `JUMEAU_LEGACY_TENANT` et que `JUMEAU_LEGACY_TENANT_ADOPTION` est **désactivé**
  après la migration.

## 1. Dry-run Mongo

```bash
export MONGO_URL='mongodb://…'
export DB_NAME='…'
export JUMEAU_LEGACY_TENANT='local'   # propriétaire unique des données legacy

python -m meridian.adapters.outbound.mongo.migrer_tenant_travail \
  --tenant "$JUMEAU_LEGACY_TENANT" --dry-run
```

Attendu : un bilan par collection avec `sans tenant`, `alias demo`, `0 écrit`.
Contrôler que les volumes correspondent à l'inventaire. Un volume inattendu = arrêt.

## 2. Apply Mongo

```bash
python -m meridian.adapters.outbound.mongo.migrer_tenant_travail \
  --tenant "$JUMEAU_LEGACY_TENANT" --apply
```

La commande est idempotente et crée les index de lecture `travail_tenant_situation_0` et
`travail_tenant_situations`. Rejouer immédiatement un dry-run : il doit afficher `0` partout.

## 3. Bascule Postgres `demo → local`

À exécuter dans une transaction, après avoir vérifié qu'aucune collision d'ID n'existe entre
les deux tenants (la clé primaire est `(tenant_id, id)`) :

```sql
BEGIN;

-- Aucun id ne doit exister à la fois sous demo et local.
SELECT id FROM objet_entreprise
WHERE tenant_id = 'demo'
  AND id IN (SELECT id FROM objet_entreprise WHERE tenant_id = 'local');

SELECT id FROM travail
WHERE tenant_id = 'demo'
  AND id IN (SELECT id FROM travail WHERE tenant_id = 'local');

-- Si les deux requêtes précédentes renvoient 0 ligne :
UPDATE objet_entreprise SET tenant_id = 'local', maj_le = now()
WHERE tenant_id = 'demo';

UPDATE travail SET tenant_id = 'local', maj_le = now()
WHERE tenant_id = 'demo';

COMMIT;
```

Ne pas utiliser un `UPDATE` générique sur toutes les tables portant `tenant_id` : certaines
ont des contraintes d'unicité et des triggers d'immutabilité. Traiter les autres tables au cas
par cas, avec un inventaire préalable.

## 4. Redémarrage et vérifications

- Redémarrer l'API, le worker C1 (`pont_worker`) et le worker D (`mesure_auto_worker`) avec les
  flags explicites (`JUMEAU_PONT_CANONIQUE=1`, `JUMEAU_MESURE_AUTO=1`) et `JUMEAU_WORKER_TENANT`
  / `JUMEAU_WORKER_TENANTS`.
- Vérifier le dry-run Mongo une dernière fois : `0` sans tenant, `0` alias.
- Contrôler l'outbox : `pont_events_pending`, `pont_events_dead`, `pont_lag_seconds`.
- Lire un Travail avec `GET /api/cases/{id}` : `boucle` doit être présente, avec une chaîne
  racine → courant.
- Lire un Outcome avec `GET /api/boucle/objets/{id}?historique=true` : la chaîne doit remonter
  jusqu'à la Situation.
- Vérifier qu'aucun tenant non prévu n'apparaît dans les compteurs.

## 5. Rollback

La migration est forward-only. En cas d'erreur :

- arrêter les workers ;
- restaurer la sauvegarde Mongo/Postgres si l'`--apply` a corrompu les données ;
- sinon, corriger uniquement les documents identifiés par l'inventaire (ne pas faire un
  `unset tenant_id` global, qui rouvrirait la faille d'adoption).

## 6. Nettoyage

Après validation :

- laisser `JUMEAU_LEGACY_TENANT_ADOPTION` désactivé ;
- retirer la variable `JUMEAU_LEGACY_TENANT` si elle n'est plus utilisée ;
- conserver le bilan dry-run/apply et les compteurs Postgres dans le ticket d'exploitation.
