# Migrations SQL idempotentes

Le dépôt n'utilise pas Alembic (`alembic.ini` et `backend/alembic` n'existent pas). Le schéma de référence
reste `schema.sql`, appliqué par `meridian.adapters.outbound.postgres.depot.appliquer_schema`.

Les évolutions des bases existantes vivent dans ce répertoire, un fichier par révision, nommé
`<numéro>_<sujet>.sql`. `appliquer_schema` exécute `schema.sql` puis les fichiers dans l'ordre
lexicographique ; chaque migration doit donc être réexécutable sans erreur (`IF NOT EXISTS`,
`ADD COLUMN IF NOT EXISTS`, etc.).

Révision courante : `0001_objets_exploitation` — index non partiels des liens pour `lister`, index GIN
des Situations d'un Signal et index de recherche de l'empreinte des Signaux. L'unicité de l'empreinte
est appliquée par l'adaptateur avec un verrou consultatif, pas par un index unique (les bases
historiques peuvent déjà contenir des doublons). Aucune table n'est ajoutée : les objets restent dans
`objet_entreprise`.
