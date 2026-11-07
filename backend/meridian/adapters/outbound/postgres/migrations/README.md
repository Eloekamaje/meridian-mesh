# Migrations SQL idempotentes

Le dépôt n'utilise pas Alembic (`alembic.ini` et `backend/alembic` n'existent pas). Le schéma de référence
reste `schema.sql`, appliqué par `meridian.adapters.outbound.postgres.depot.appliquer_schema`.

Les évolutions des bases existantes vivent dans ce répertoire, un fichier par révision, nommé
`<numéro>_<sujet>.sql`. `appliquer_schema` exécute `schema.sql` puis les fichiers dans l'ordre
lexicographique ; chaque migration doit donc être réexécutable sans erreur (`IF NOT EXISTS`,
`ADD COLUMN IF NOT EXISTS`, etc.).

**Une révision déjà appliquée n'est jamais modifiée.** Un correctif d'index ou de contrainte prend une
nouvelle révision. Les `DROP INDEX` sont conditionnels (`IF EXISTS`) et les recréations utilisent
`IF NOT EXISTS` : une révision peut donc être rejouée sur une base fraîche comme sur une base déjà
migrée. Les index sont créés dans la transaction de `appliquer_schema` ; `CREATE INDEX CONCURRENTLY`
n'est pas utilisable dans ce cadre et reste une opération de déploiement séparée.

Révisions :

- `0001_objets_exploitation` — index partiels initiaux des liens et de l'empreinte des Signaux.
- `0002_objets_exploitation_index_v2` — remplace les index partiels de liens par des index non partiels
  utilisables par `lister_objets_exploitation`, et ajoute l'index GIN des `situation_ids` d'un Signal.
- `0003_objets_exploitation_expression_index` — index non partiel du filtre `expression_id` de `lister`.
  L'unicité de l'empreinte reste applicative : un verrou consultatif sérialise les inserts concurrents,
  mais aucun index unique n'est posé, car une base historique peut déjà contenir des doublons. Un
  backfill de dédoublonnage est un prérequis avant toute contrainte unique future.

## Exécution en production

`appliquer_schema` exécute le DDL dans une transaction et prend un verrou `SHARE` sur
`objet_entreprise`. En production, poser un `lock_timeout` de session (par exemple
`SET lock_timeout = '5s'`) avant l'application, prévoir une fenêtre de maintenance courte et
relancer l'application si le timeout est atteint. Le `lock_timeout` n'est pas posé par le code :
il casserait les suites parallèles qui partagent les mêmes catalogues.

Pour éviter le verrou bloquant, appliquer les index hors ligne avec
`scripts/creer-index-objets-exploitation-concurrently.sql` (`CREATE INDEX CONCURRENTLY`, aucun
`BEGIN`), puis démarrer l'application. Ce script n'est volontairement pas dans ce répertoire :
`appliquer_schema` exécuterait son contenu en transaction, ce que `CONCURRENTLY` interdit.
