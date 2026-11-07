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
vide ou booléenne, une valeur non numérique quand la veille l'exige, une cible inconnue ou un
`quand` illisible sont refusés.

## 2. Collection d'observations

Collection : `mesure_auto_observations`. Chaque document porte explicitement son tenant.

### 2.1 Observation générique (source ou Twin)

```json
{
  "id": "obs-2026-11-05-1",
  "tenant_id": "banque",
  "maj_le": "2026-11-05T09:01:00+00:00",
  "initiative_id": "ini-dec-case-c1-1",
  "metrique": "delai_moyen_jours",
  "attendu": 5,
  "observe": 7,
  "effets_secondaires": [{"type": "rework", "observe": 3}],
  "periode": "2026-11",
  "quand": "2026-11-05T09:00:00+00:00",
  "source": {"type": "twin", "nom": "tbt"},
  "interpretation": "Le délai augmente malgré l'automatisation."
}
```

- `id` : identifiant stable de l'observation.
- `maj_le` : date d'ingestion/dernière mise à jour, utilisée comme **curseur**. Une correction
  doit avancer `maj_le` pour être relue.
- `quand` : date de la mesure, utilisée pour la période et l'ordonnancement de l'Outcome.
- `initiative_id` : initiative canonique, ou `decision_id` (l'identifiant d'initiative est alors
  dérivé comme le fait C1).
- `periode` : optionnelle ; sinon dérivée de `quand` (`AAAA-MM`).
- `attendu`/`observe` : valeurs scalaires ou objets (`{"valeur": …}`).
- `effets_secondaires` : liste de libellés ou d'objets ; conservée dans
  `Outcome.donnees.mesure.effets_secondaires` et `Outcome.donnees.effets_secondaires`.

### 2.2 Observation de veille legacy

Le normaliseur accepte aussi la forme réellement produite par la veille après décision :
`case.veille.passation` + `observation` (`cible`, `valeur`, `unite`, `conclusion`, `quand`,
`jumeau`, `source`). Cette forme peut être projetée dans `mesure_auto_observations` avec son
contexte `case`.

- **attendu** : `attendu` = indicateur + départ + cible + sens + unité ; observé = valeur.
- **risque** : `attendu` = seuil ; observé = valeur ; un effet secondaire
  `risque_materialise`/`risque_maitrise` est produit.
- **inconnue** : la conclusion non vide lève l'inconnue ; `attendu` reste `None`.
- L'initiative canonique est dérivée de la dernière décision tranchée du case
  (`ini-dec-case-<case_id>-<rang>`), ou d'un `initiative_id`/`decision_id` explicite.

## 3. Checkpoint durable

Collection : `mesure_auto_checkpoints`. Un document par tenant, `_id` = tenant normalisé.

```json
{
  "_id": "banque",
  "tenant_id": "banque",
  "dernier_maj_le": "2026-11-05T09:02:00+00:00",
  "dernier_id": "obs-2",
  "maj_le": "2026-11-07T12:00:00+00:00"
}
```

Le worker lit les observations d'un tenant par `(maj_le, id)` strictement supérieur au
checkpoint, puis avance le checkpoint après chaque observation traitée (ou ignorée avec raison).
Une panne d'enfilage **n'avance pas** le checkpoint : l'observation sera rejouée.

## 4. Idempotence

- Identifiant d'événement : `sha256(tenant | outcome.mesure | outcome_id | source_event_id)`.
- `outcome_id` (C1) : `out-<initiative>-<métrique>-<période>` ; une observation ultérieure de la
  même période met à jour le même Outcome.
- `source_event_id` inclut l'empreinte du contenu mesuré : un rejeu strict produit le même
  événement, une correction produit un nouvel événement (même Outcome, version plus récente).
- L'outbox C1 utilise `$setOnInsert` sur `_id` : un rejeu ne crée pas de doublon.

## 5. Worker

```bash
JUMEAU_MESURE_AUTO=1 \
PONT_KEY=... MONGO_URL=mongodb://127.0.0.1:27017 DB_NAME=meridian_db \
backend/.venv/bin/python -m meridian.adapters.inbound.worker.mesure_auto_worker --once

# Ou via le script de développement :
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

## 6. Limites assumées

- Le producteur d'observations doit garantir `tenant_id`, `id` et `maj_le`. Un document sans ces
  champs n'est pas lu (curseur) ou est refusé avec sa raison.
- Aucun `Learning` n'est produit, même quand l'Outcome est un écart majeur.
- La mesure reste dépendante d'une initiative canonique existante côté Postgres : le worker
  enfile, le pont C1 applique. Si l'initiative n'existe pas encore, le worker C1 signalera
  l'événement en échec ; ce lot ne crée pas d'initiative.
- Le worker ne supprime ni ne réécrit les observations : une correction passe par `maj_le`.
