# Indexation fédérée du legacy

**Date :** 2026-11-03  
**Statut :** socle implémenté, packs métier à poursuivre

## Décision

Le legacy n’est ni « étendu » dans Graphify ni forké dans CBM.  
Méridian fédère :

```text
CBM              → index de code principal (à brancher sur ce socle)
sidecars Méridian → JSP, Java, descripteurs Java, COBOL, JCL, SQL
Graphify          → carte documentaire et communautés, pas parsing legacy
ChunkHound/cgr    → recherche et code moderne, pas legacy
Méridian          → observations, liens, puis Claims et preuves
```

Un sidecar est un adaptateur de parsing spécialisé. Il ne produit jamais un Claim :
il produit des observations localisées, avec provenance, version de parser et statut.

## Socle livré

- `backend/meridian/domain/code_index.py`
  - `Observation` ;
  - `CouvertureFichier` ;
  - `fusionner` ;
  - `couverture`.
- `backend/meridian/ports/code_index.py`
  - `CodeIndexPort`.
- `backend/meridian/application/code_index_orchestrator.py`
  - registre d’adapters ;
  - découverte et exclusions ;
  - panne d’un adapter tolérée ;
  - couverture explicite ;
  - conflits inter-providers conservés.
- `backend/meridian/application/code_links.py`
  - liens JSP → Servlet → Java ;
  - JSP → route Spring ;
  - Java → JPA ;
  - SQL FK → table/colonne ;
  - SQL ↔ JPA ;
  - COBOL CALL/COPY ;
  - JCL → programme/dataset/procédure.
- `backend/meridian/adapters/outbound/connectors/`
  - `jsp.py` ;
  - `java_source.py` ;
  - `java_descriptors.py` ;
  - `cobol.py` ;
  - `jcl.py` ;
  - `sql_schema.py` ;
  - `legacy_index.py` (composition).
- `scripts/indexer-legacy.py`
  - CLI de rapport JSON.

## Commande

```bash
backend/.venv/bin/python scripts/indexer-legacy.py \
  --racine /chemin/vers/application \
  --sortie /tmp/legacy-index.json
```

Avec CBM :

```bash
backend/.venv/bin/python scripts/indexer-legacy.py \
  --racine /chemin/vers/application \
  --projet-cbm nom-du-projet-cbm \
  --commit <sha> \
  --sortie /tmp/legacy-index.json
```

## Introspection SQL live

L’introspection est désactivée par défaut : sans `--sql-live`, le CLI ne lit aucune
variable et n’ouvre aucune connexion. Le mode automatique est explicite :

```bash
JUMEAU_SQL_LIVE=postgres \
JUMEAU_SQL_DSN='postgresql://...' \
JUMEAU_SQL_SCHEMA=public \
backend/.venv/bin/python scripts/indexer-legacy.py \
  --racine /chemin/vers/application \
  --sql-live auto \
  --sortie /tmp/legacy-index.json
```

Variables :

| Variable | Rôle |
| --- | --- |
| `JUMEAU_SQL_LIVE` | `postgres` ou `oracle` ; vide = aucune introspection. Lu uniquement par `--sql-live auto`. |
| `JUMEAU_SQL_DSN` | DSN de secours ; `--sql-dsn` prime. `JUMEAU_PG_DSN` reste accepté pour PostgreSQL. |
| `JUMEAU_SQL_SCHEMA` | Schéma de secours ; `--sql-schema` prime. |

Garanties : `--sql-live postgres|oracle` prime sur `JUMEAU_SQL_LIVE` ; `auto` avec
variable vide n’ouvre aucune connexion et l’annonce avec `--verbose` ; une valeur
inconnue échoue explicitement ; Oracle sans `oracledb` échoue avant toute connexion ;
seuls des `SELECT` sont admis et la connexion est toujours fermée.

Le rapport contient :

```text
providers, fichiers_decouverts,
observations, couvertures, compteurs,
liens (détail + compteurs), packs, claims_promouvables, erreurs
```

Le commit des preuves est explicite :

```bash
--commit <sha>
```

Sans `--commit`, un arbre Git propre utilise `HEAD`; un arbre modifié ne promeut aucun Claim.
C’est volontaire : une preuve ne doit pas citer un commit qui ne contient pas le fichier.

## Règles de couverture

- un fichier sans observation est `non_supporte`, jamais invisible ;
- un fichier partiellement lu est `partiel` ;
- un fichier ambigu est `ambiguous` ;
- deux providers qui se contredisent produisent `conflit` ;
- un lien ambigu n’est pas émis ;
- une relation n’est jamais inventée pour « compléter » un graphe.

## Ce qui reste

1. Tester sur des corpus legacy réels, avec taux de couverture mesuré.
2. Brancher le CLI SQL live dans un planificateur d’ingestion.
3. Ajouter les dialectes et objets propriétaires rencontrés sur les corpus clients.

## Deuxième vague livrée

### Persistance et API

Tables ajoutées à `schema.sql` :

- `code_observation` ;
- `code_coverage` ;
- `code_link`.

Toutes portent `tenant_id` et `jumeau_id`. Elles sont ajoutées à `rls.TABLES`.
Le magasin `code_index_store.py` remplace atomiquement les lignes d’un couple
`(tenant_id, jumeau_id)` et ne lit jamais hors de ce couple.

Endpoints de lecture :

```text
GET /api/jumeaux/{jumeau_id}/code-index/resume
GET /api/jumeaux/{jumeau_id}/code-index/coverage
GET /api/jumeaux/{jumeau_id}/code-index/observations
GET /api/jumeaux/{jumeau_id}/code-index/links
```

Aucun endpoint n’écrit de fichier ni ne lance d’indexation arbitraire.

### Packs

`application/legacy_packs.py` transforme observations et liens en `Finding` :

- `EXPOSE` Spring ;
- `INTERFACE_UTILISATEUR` JSP ;
- `COMPOSANT_JEE`, `STOCKE_DANS`, `INJECTE` ;
- `APPELLE`, `COPIE`, `EXECUTE`, `LIT_DATASET` ;
- `TABLE`, `REFERENCE` SQL.

Les prédicats structurels `APPELLE`, `COPIE`, `EXECUTE`, `LIT_DATASET`, `REFERENCE` et `EXPOSE`
sont promouvables (ADR-0026). `TABLE`, `STOCKE_DANS`, `COMPOSANT_JEE`, `INJECTE` et
`INTERFACE_UTILISATEUR` le sont aussi quand la preuve localisée établit le lien (ADR-0027).
La recette est rejouée sur les lignes citées ; sans citation, hash, locator ou commit, aucun
Claim n’est produit. Une preuve insuffisante laisse le Finding `candidate`.

### CBM validé

CBM a été réindexé sur le repo courant (`meridian-mesh-current`) : **27 366 nœuds**, **83 188 arêtes**.
`CbmObservations` a été validé sur `backend/meridian/domain/code_index.py` : **109 observations**
(nœuds et relations). CBM borne ses résultats à 200 lignes ; l’adaptateur pagine par `SKIP` et
filtre par fichiers pour éviter de parcourir tout le graphe.

### SQL vivant

`sql_live.py` lit les catalogues PostgreSQL/Oracle par `SELECT` uniquement, avec paramètres liés.
Il ne remplace pas le sidecar DDL : il observe l’état réel de la base. Il est branché via
`indexer_legacy(..., sql_live=...)` et le CLI `--sql-live postgres|oracle|auto` ; `auto`
lit `JUMEAU_SQL_LIVE` et reste sans connexion si la variable est vide.
Sur le catalogue local `public`, l’introspection a produit **1 010 observations** SQL live.

### Analyseurs sémantiques

ABAP, RPGLE et PL/I passent désormais par des moteurs AST/parse tree quand ils sont installés :
abaplint, rpgleparser et la grammaire ANTLR PL/I. Les sidecars regex restent le fallback.
PowerBuilder extrait les sources des `.pbl` ; Oracle Forms utilise les exports XML.
Voir [semantic-analyzers.md](semantic-analyzers.md) et ADR-0028.

### Sidecars étendus

- ABAP : programmes, classes, méthodes, forms, function modules, appels, SQL.
- RPG : fichiers, procédures, sous-routines, variables, DataStructures, opérations, SQL.
- PL/I : procédures, entrées, variables, appels, includes, SQL.
- Oracle Forms : modules, blocs, items, triggers, relations, LOV, record groups.
- PowerBuilder : objets, fonctions, événements, SQL, DataWindows ; les `.pbl` binaires restent partiels.

### Corpus

`backend/meridian/tests/fixtures/legacy_corpus/` couvre JSP, Servlet, Spring, JPA, EJB, COBOL,
JCL et SQL. Des tests unitaires couvrent ABAP, RPG, PL/I, Oracle Forms et PowerBuilder.
Il sert de test de non-régression sans CBM, sans base et sans réseau.

## Limites restantes

- Les preuves legacy n’ont de SHA Git que si `--commit` est fourni ; un arbre modifié ne promeut rien.
- Les prédicats sans preuve localisée restent candidats ; c’est voulu.
- CBM est validé sur un index à jour ; l’index complet reste coûteux à paginer.
- Le CLI SQL live choisit `auto` via `JUMEAU_SQL_LIVE` ; une variable vide désactive l’introspection.
- Les parsers ABAP/RPG/PL-I/Forms/PowerBuilder sont structurels, pas des analyseurs sémantiques complets.
