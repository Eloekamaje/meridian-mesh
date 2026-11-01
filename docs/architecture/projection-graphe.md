# Projection graphe : direct ou outbox

## Décision

Le graphe reste une **projection reconstructible** de Postgres/Mongo (ADR-0013). La bascule
`JUMEAU_GRAPH_PROJECTION` permet de choisir le chemin sans changer le code du Gardien :

| Valeur | Comportement |
|---|---|
| `direct` (défaut) | upsert immédiat dans le `GraphStore`, puis planification de l'outbox. Compatibilité avec le pilote. |
| `outbox` | aucun upsert direct : la passe planifie seulement `graph.synchroniser` dans `execution_outbox`. |
| inconnue | refusée : aucune écriture graphe ni outbox, erreur `JUMEAU_GRAPH_PROJECTION inconnu` journalisée. |

Une valeur inconnue ne retombe jamais silencieusement sur `direct`.

## Worker

```bash
# développement (Postgres et Neo4j déjà lancés)
scripts/dev-outbox-worker.sh              # boucle continue
scripts/dev-outbox-worker.sh --une-passe  # une file bornée (100 événements) puis quitte

# production
systemctl enable --now meridian-outbox-worker
```

Équivalent direct : `python -m jumeau.execution.outbox_worker` (ou `--une-passe`).

Variables requises côté worker :

- `JUMEAU_PG_DSN` (ou `--dsn`) ;
- `GRAPH_STORE=neo4j`, `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`.

Le worker refuse de démarrer avec le store mémoire : une projection mémoire serait perdue tout en
marquant les événements publiés.

## Neo4j local optionnel

Deux options écoutent sur `bolt://127.0.0.1:7687` :

- le conteneur existant `meridian-neo4j` (`scripts/dev-neo4j.sh`) ;
- le Neo4j léger opt-in `docker-compose.neo4j.yml` : image `neo4j:5-community`, heap 256–512 Mo,
  pagecache 256 Mo, volume dédié, ports liés à `127.0.0.1`, jamais lancé par le compose par défaut.

```bash
scripts/dev-neo4j-light.sh up      # démarre, attend Bolt, écrit /tmp/meridian-neo4j.env (0600)
scripts/dev-neo4j-light.sh status
scripts/dev-neo4j-light.sh down    # --volumes pour supprimer aussi les données
scripts/dev-neo4j-light.sh env     # affiche seulement : source /tmp/meridian-neo4j.env
```

Le wrapper refuse de démarrer si `meridian-neo4j` occupe déjà 7687. Pour un second conteneur :

```bash
NEO4J_PORT=7688 NEO4J_HTTP_PORT=7475 NEO4J_ENV_FILE=/tmp/meridian-neo4j-light.env \
  scripts/dev-neo4j-light.sh up
```

Il réutilise `NEO4J_PASSWORD`
ou le fichier `/tmp/meridian-neo4j.env`, sinon génère un mot de passe aléatoire. Le fichier contient
`GRAPH_STORE=neo4j`, `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` ; il est ignoré
par Git et ne doit jamais être collé dans un ticket ou un log. Pour le conteneur existant, extraire
`NEO4J_AUTH` de `docker inspect meridian-neo4j` sans l'afficher, puis régénérer ce fichier.

## Backfill et vérification

Postgres `jumeau` porte les Twins, Mongo `relations` porte les liens. Le backfill lit ces deux
sources et délègue l'upsert idempotent à `jumeau.graphe_sync` ; il ne supprime jamais rien.

```bash
cd backend
set -a; . ./.env; set +a
set -a; . /tmp/meridian-neo4j.env; set +a

.venv/bin/python -m jumeau.backfill_graphe --tenant demo --dry-run   # défaut, n'ouvre pas Neo4j
.venv/bin/python -m jumeau.backfill_graphe --tenant demo --apply     # exige GRAPH_STORE=neo4j
```

`--dry-run` calcule le mapping, les orphelins et les erreurs sur un graphe mémoire. `--apply` refuse
un store mémoire et rend en plus les compteurs `graphe.noeuds` / `graphe.aretes` du tenant. Un
deuxième `--apply` ne duplique rien (upsert par `tenant_id` + `id`) ; une relation dont une extrémité
manque est ignorée et listée dans `ignores`, jamais inventée. Code de sortie `2` si `erreurs` est
non vide.

Smoke de bout en bout (outbox → worker → Neo4j → lecture Bolt → nettoyage du seul tenant de test) :

```bash
scripts/dev-graphe-e2e.sh
```

Le script enfile un `graph.synchroniser` pour `__smoke_graphe__`, lance
`.venv/bin/python -m jumeau.execution.outbox_worker --une-passe` avec `GRAPH_STORE=neo4j`, vérifie
que `publie_le` est posé et que la relation est lisible dans Neo4j, puis supprime les nœuds du
tenant de smoke. Pour rejouer seulement la projection : `scripts/dev-outbox-worker.sh --une-passe`.

## Runbook de bascule

1. Vérifier que Neo4j est joignable et que le worker est supervisé :
   `systemctl status meridian-outbox-worker`.
2. Démarrer l'API/le Gardien avec `JUMEAU_GRAPH_PROJECTION=outbox`.
3. Déclencher une passe (`python -m jumeau.gardien --jumeau <id>`) et vérifier la file :

   ```sql
   SELECT id, tenant_id, type, cree_le, publie_le, tentatives
   FROM execution_outbox
   WHERE type = 'graph.synchroniser'
   ORDER BY id DESC LIMIT 20;
   ```

4. Vérifier que `publie_le` avance et que le worker ne journalise pas de cycle en échec.
5. Contrôler le graphe : `curl -H 'X-Tenant: <tenant>' .../api/boucle/graphe/resume`.

Retour arrière : remettre `JUMEAU_GRAPH_PROJECTION=direct` pour le Gardien. Le worker peut rester
actif : les upserts sont idempotents.

## Diagnostic

- `publie_le IS NULL` qui ne diminue pas : worker arrêté, Neo4j injoignable ou événement en échec ;
  la transaction du lot est annulée, donc l'événement sera rejoué.
- `tentatives` figé à 0 avec `publie_le IS NULL` : la transaction du lot a été annulée avant le
  marquage ; vérifier les logs `meridian.execution.outbox_worker` et la joignabilité Neo4j.
- Erreur `JUMEAU_GRAPH_PROJECTION inconnu` : corriger la variable ; aucune projection n'a eu lieu.
- `GRAPH_STORE=neo4j requis` : le worker a été lancé sans store persistant.

## Dead letter queue et reprise (proposition)

État actuel : `publier_outbox` sélectionne les lignes dues, appelle le publieur puis marque
`publie_le` dans la même transaction. Si le publieur lève, tout le lot est annulé ; un événement
empoisonné peut donc bloquer la file. Il n'y a pas encore de DLQ ni de backoff dédié.

Proposition minimale, compatible avec le contrat actuel :

```sql
ALTER TABLE execution_outbox
  ADD COLUMN IF NOT EXISTS prochaine_tentative_le timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS derniere_erreur text,
  ADD COLUMN IF NOT EXISTS dead_letter_le timestamptz;

CREATE INDEX IF NOT EXISTS execution_outbox_a_rejouer
  ON execution_outbox (prochaine_tentative_le, id)
  WHERE publie_le IS NULL AND dead_letter_le IS NULL;
```

Comportement proposé :

- sélection : `publie_le IS NULL AND dead_letter_le IS NULL AND prochaine_tentative_le <= now()`,
  toujours `ORDER BY id FOR UPDATE SKIP LOCKED` ;
- par ligne, un savepoint isole l'échec : succès → `publie_le = now()` ; échec → `tentatives + 1`,
  `derniere_erreur` tronquée à 2000 caractères, backoff exponentiel plafonné (par exemple
  5 s, 15 s, 60 s, 300 s) dans `prochaine_tentative_le` ;
- au-delà de `max_tentatives` (par exemple 8), `dead_letter_le = now()` : la ligne reste auditable
  mais n'est plus sélectionnée ; les autres lignes du lot continuent d'avancer ;
- le worker journalise et expose `publiés / en retry / en DLQ` ; une alerte se déclenche dès que
  `dead_letter_le IS NOT NULL`.

Requêtes opérateur :

```sql
-- file en attente ou en retry
SELECT id, tenant_id, type, tentatives, prochaine_tentative_le, derniere_erreur
FROM execution_outbox
WHERE publie_le IS NULL AND dead_letter_le IS NULL
ORDER BY prochaine_tentative_le, id;

-- dead letters
SELECT id, tenant_id, type, tentatives, derniere_erreur, dead_letter_le
FROM execution_outbox
WHERE dead_letter_le IS NOT NULL
ORDER BY dead_letter_le DESC;

-- rejeu explicite d'une dead letter
UPDATE execution_outbox
SET dead_letter_le = NULL, prochaine_tentative_le = now(), tentatives = 0
WHERE id = :id AND dead_letter_le IS NOT NULL;
```

Cette section est un design ; elle n'est pas implémentée dans ce lot.

## Limites

- Le mode `direct` reste le défaut tant que le worker outbox n'est pas supervisé en production.
- La projection porte la topologie Twins/relations ; les Claims et preuves restent en Postgres.
- La DLQ et le backoff exponentiel restent une proposition : aujourd'hui un échec annule la
  transaction du lot et sera rejoué au cycle suivant.
