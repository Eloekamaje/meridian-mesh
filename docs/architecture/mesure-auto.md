# Mesure automatique : observations → Outcomes

> **Lot D.** Transforme automatiquement des observations de sources, de Twins ou de la veille
> legacy en `Outcome` canoniques. **Aucun `Learning` n'est créé automatiquement** : la
> capitalisation reste une décision humaine.

## 1. Principe

```text
observation (Mongo)
  → normalisation pure (tenant, initiative, métrique, attendu, observé, effets, période)
  → événement d'outbox C1 signé, origine « exploitation »
  → worker du pont C1
  → Outcome canonique (Postgres)
```

Le module `meridian.application.mesure_auto` est **pur** : il ne lit ni Mongo ni Postgres. Le
worker `meridian.adapters.inbound.worker.mesure_auto_worker` ne fait qu'enfiler dans l'outbox
Mongo `pont_canonique` ; c'est le worker C1 qui applique les Outcomes dans Postgres.

Une observation incomplète ou ambiguë ne produit **rien** : la raison est retournée par le module
pur et journalisée par le worker. Une décision non tranchée, un tenant contradictoire, une mesure
vide ou booléenne, une valeur non numérique quand la veille l'exige, une cible inconnue, une
période illisible ou un `quand`/`maj_le` futur sont refusés.

## 2. Collection d'observations

Collection : `mesure_auto_observations`. Chaque document porte explicitement son tenant
**normalisé** (`banque`, pas `Banque`).

### 2.1 Observation générique (source ou Twin)

```json
{
  "id": "obs-2026-11-05-1",
  "tenant_id": "banque",
  "maj_le": "2026-11-05T09:01:00.000000+00:00",
  "sequence": "00000000000000000042",
  "initiative_id": "ini-dec-case-c1-1",
  "metrique": "delai_moyen_jours",
  "attendu": {"valeur": 5, "unite": "j"},
  "observe": {"valeur": 7, "unite": "j"},
  "effets_secondaires": [{"type": "rework", "observe": 3}],
  "periode": "2026-11",
  "quand": "2026-11-05T09:00:00.000000+00:00",
  "source": {"type": "twin", "nom": "tbt"},
  "interpretation": "Le délai augmente malgré l'automatisation."
}
```

- `id` : identifiant stable de l'observation (chaîne, unique par tenant).
- `maj_le` : date d'ingestion/dernière mise à jour, **UTC**, utilisée comme curseur. Une
  correction doit avancer `maj_le` pour être relue. Une chaîne ISO avec offset ou un BSON Date
  sont acceptés puis ramenés en UTC par l'adaptateur.
- `sequence` : tie-breaker monotone optionnel (ULID, numéro producteur). À défaut, `_id` Mongo
  sert de tie-breaker. Deux documents de la même microseconde restent ainsi ordonnés.
- `quand` : date de la mesure, utilisée pour la période et l'ordonnancement de l'Outcome.
- `initiative_id` : initiative canonique, ou `decision_id` (l'identifiant d'initiative est alors
  dérivé exactement comme C1 : `ini-<decision_id>`).
- `periode` : optionnelle ; sinon dérivée de `quand` en **UTC** (`AAAA-MM`). Une période
  explicite doit être `AAAA-MM` (mois valide) ou `AAAA-MM-JJ/AAAA-MM-JJ` (plage valide, début
  ≤ fin).
- `attendu`/`observe` : valeurs scalaires ou objets (`{"valeur": …}`). `Outcome.valeur_attendue`
  reçoit la valeur scalaire ; l'objet complet reste dans `Outcome.donnees.mesure.attendu`.
- `effets_secondaires` : liste de libellés ou d'objets ; conservée dans
  `Outcome.donnees.mesure.effets_secondaires` et `Outcome.donnees.effets_secondaires`.
- Taille maximale sérialisée : **256 Kio**. Au-delà, l'observation est refusée (permanent) et
  dead-letterée.

### 2.2 Observation de veille legacy

Le normaliseur accepte la forme réellement produite par la veille après décision :
`case.veille.passation` + `observation` (`cible`, `valeur`, `unite`, `conclusion`, `quand`,
`jumeau`, `source`). Cette forme doit être projetée dans `mesure_auto_observations` avec son
contexte `case` **et un lien canonique explicite**.

- **attendu** : unité et `sens` (`hausse`/`baisse`) obligatoires ; observé = valeur.
- **risque** : unité et `sens` obligatoires ; un effet secondaire
  `risque_materialise`/`risque_maitrise` est produit. La métrique stable est `risque:<cible>`.
- **inconnue** : conclusion non vide ; métrique stable `inconnue:<cible>`.
- Le lien canonique (`initiative_id` ou `decision_id`) est **explicite** : le worker ne devine
  jamais « la dernière décision » du case et ne duplique pas les règles C1. Une observation de
  veille sans ce lien est refusée avec sa raison.

## 3. Checkpoint durable

Collection : `mesure_auto_checkpoints`. Un document par tenant, `_id` = tenant normalisé.

```json
{
  "_id": "banque",
  "tenant_id": "banque",
  "dernier_maj_le": "2026-11-05T09:02:00.000000+00:00",
  "dernier_sequence": "00000000000000000042",
  "dernier_id": "obs-2",
  "maj_le": "2026-11-07T12:00:00.000000+00:00"
}
```

Le worker lit les observations d'un tenant par curseur `(maj_le, sequence, id)` strictement
supérieur au checkpoint. Le checkpoint est écrit en **CAS** : un worker lent ne peut pas faire
régresser un curseur plus avancé. L'idempotence de l'outbox rend deux instances tolérantes, mais
**une instance par tenant est la configuration supportée** (pas de bail distribué dans ce lot).

Deux types de `maj_le` sont lus : chaîne ISO (offset accepté) et BSON Date. L'adaptateur applique
un **type bracketing** et une borne basse conservatrice (curseur − 1 jour), puis trie et filtre le
curseur exact en Python.

## 4. Idempotence et corrections

- `outcome_id` (C1) : `out-<initiative>-<métrique>-<période>`.
- `source_event_id` du worker :
  `mesure-auto:<type>:<observation_id>:<sha256(payload_complet)[:16]>`.
- Identifiant d'événement (C1) :
  `sha256(tenant | operation | outcome_id | source_event_id)`.
- Le payload complet inclut `maj_le`, `interpretation`, `decision_id`, `source`, `attendu`,
  `observe`, `effets_secondaires` et `periode` : une correction de l'un de ces champs produit un
  **nouvel** `_id`, donc jamais de collision d'idempotence.
- `maj_le` (date d'ingestion) devient `source_maj_le` de l'Outcome ; `mesure_le` reste `quand`.
  Une correction à `quand` égal mais `maj_le` plus récent est donc appliquée par C1 (qui reste
  strictement ordonné).
- L'outbox C1 utilise `$setOnInsert` sur `_id` : un rejeu strict ne crée pas de doublon.

## 5. Worker, erreurs et dead-letter

```bash
# Depuis la racine du dépôt :
cd backend
JUMEAU_MESURE_AUTO=1 \
PONT_KEY=... MONGO_URL=mongodb://127.0.0.1:27017 DB_NAME=meridian_db \
.venv/bin/python -m meridian.adapters.inbound.worker.mesure_auto_worker --once

# Ou via le script de développement (depuis la racine) :
scripts/dev-mesure-auto-worker.sh --une-passe --tenant banque --lot 100
```

Options : `--once`/`--une-passe`, `--lot`, `--intervalle`, `--tenant` (répétable),
`--mongo-url`, `--db-name`, `--depuis`.

- **Flag** : `JUMEAU_MESURE_AUTO` désactivé par défaut. Sans lui, le worker ne lit rien et sort
  avec le code 0.
- **Tenants** : `--tenant`, sinon `JUMEAU_WORKER_TENANTS`/`JUMEAU_WORKER_TENANT`, sinon `local`.
  Chaque tenant a son checkpoint et ses événements ; aucun état n'est partagé.
- **Postgres** : aucune dépendance. Le worker n'ouvre que des collections Mongo.
- **Clé** : `PONT_KEY` est requis pour signer les événements ; sans elle, le worker refuse de
  démarrer (code 2).
- **Enfilement** : le worker utilise `enfiler` (pas `enfiler_best_effort`) et classe l'erreur avec
  la même règle que C1 (`_est_permanent`).
  - **Permanente** (`PontInvalide`, `SignatureInvalide`, collision, schéma, taille, observation
    incomplète) : dead-letter dans `mesure_auto_rejets`, checkpoint avancé, alerte loguée.
  - **Transitoire** (timeout/PyMongo, `quand`/`maj_le` futur, signature momentanément
    indisponible) : le checkpoint **n'avance pas** ; l'observation est retentée. Après
    `tentatives_max` (5 par défaut), elle est dead-letterée et le checkpoint avance.
- **Audit** : au démarrage, `count_documents` compte les documents sans `id`/`maj_le` conformes
  dans chaque tenant et logue `mesure_auto_documents_non_conformes`. Ces documents ne sont jamais
  lus (filtre), donc ne bloquent pas le flux.
- **Métriques de log** : `mesure_auto_lues`, `mesure_auto_outcomes`, `mesure_auto_doublons`,
  `mesure_auto_rejets`, `mesure_auto_echecs`, `mesure_auto_non_conformes`.

### 5.1 Dead-letter

Collection : `mesure_auto_rejets`. Clé = `sha256(tenant | observation_id | empreinte_contenu)`.
Le document porte `tentatives`, `derniere_raison`, `permanent`, `etat` (`retry`/`dead`) et
`maj_le`. Les messages sont bornés et expurgés (jetons Bearer/sk-/ghp_/xox, credentials d'URL)
avant log ou stockage.

## 6. Exploitation, sécurité et validation

- **JSON Schema** : `SCHEMA_OBSERVATION` est fourni par l'adaptateur. Le repo n'a pas de
  convention de validateur Mongo ; `assurer_validateur()` tente un `collMod` avec
  `validationAction: "warn"` (best-effort, jamais bloquant). La validation applicative reste la
  source de vérité.
- **ACL** :
  - producteur : `insert`/`update` sur `mesure_auto_observations` uniquement ;
  - worker : lecture sur `mesure_auto_observations`, écriture sur `mesure_auto_checkpoints`,
    `mesure_auto_rejets` et `pont_canonique` ;
  - worker C1 : lecture/claim sur `pont_canonique` et écriture Postgres canonique.
- **Rétention/PII** : les observations peuvent contenir des données métier (indicateurs, libellés
  de risques, conclusions). Définir une rétention courte sur `mesure_auto_observations` et
  `mesure_auto_rejets` ; ne jamais y déposer de secret ni de donnée personnelle non nécessaire.
  Les preuves et liens restent dans le canonique, pas dans les logs.
- **Instance unique** : une instance par tenant. Le CAS du checkpoint empêche une régression ;
  l'idempotence de l'outbox rend les doublons inoffensifs, mais aucun bail distribué n'est fourni.

## 7. Limites assumées

- Le producteur d'observations doit garantir `tenant_id` normalisé, `id` string et `maj_le`
  string/date. Un document sans ces champs n'est pas lu et est compté par l'audit.
- Aucun `Learning` n'est produit, même quand l'Outcome est un écart majeur.
- La mesure reste dépendante d'une initiative canonique existante côté Postgres : le worker
  enfile, le pont C1 applique. Si l'initiative n'existe pas, C1 rejette l'événement (permanent) ;
  ce lot ne crée pas d'initiative.
- Le worker ne supprime ni ne réécrit les observations : une correction passe par `maj_le`.
