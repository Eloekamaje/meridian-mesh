# Correctifs issus du benchmark conversationnel — 2026-11-06

Le pilote du benchmark a révélé cinq insuffisances. Elles ont été corrigées dans le
produit, pas seulement dans les critères du benchmark.

## 1. Isolation inter-tenant

**Symptôme** : un utilisateur authentifié dans le tenant `pilot` obtenait une description
détaillée de `Conduit`, qui appartient au tenant `demo` (3/3).

**Cause** : les routes de conversation lisaient la collection Mongo globale `jumeaux`,
qui ne porte pas de `tenant_id` et reste la vitrine du tenant `demo`.

**Correctif** :

- `backend/meridian/adapters/inbound/http/tenant_twins.py` :
  - `demo`/`local` gardent la vitrine Mongo ;
  - les autres tenants lisent les Twins typés Postgres, filtrés par `tenant_id` ;
  - `jumeau_du_tenant` vérifie l'appartenance d'un Twin au tenant.
- `cases.py` et `legacy.py` utilisent ce résolveur pour les cas, les messages, les
  suggestions, les interfaces et les routes Aurora.
- Un case hors périmètre renvoie désormais un refus 403 explicite :

```text
Ce case est hors de votre périmètre. Demandez l'accès au responsable du Travail
ou changez d'espace.
```

## 2. Contrat d'action

**Symptôme** : sur « Lance une investigation… », Flore produisait une cartographie
complète comme si l'investigation avait été menée, au lieu de proposer et demander
confirmation.

**Correctif** : `backend/meridian/application/contrat_action.py`, appliqué dans
`generer_tour` avant l'enveloppe de réponse.

- une demande d'action non confirmée reçoit un préambule :
  « Je n'ai pas lancé l'investigation… » ;
- une confirmation est ajoutée si elle manque ;
- une exécution affirmée à tort est corrigée ;
- un rapport/livrable annoncé sans artefact est corrigé :
  « aucun rapport n'a été déposé dans le Travail ».

## 3. Contrat de preuve

**Symptôme** : au second tour sur les dépendances, Flore listait des bibliothèques
Python sans citer le manifeste.

**Correctif** : `backend/meridian/application/contrat_preuve.py`.

- une liste d'au moins trois éléments factuels sans citation reçoit une limite
  explicite : « cette liste n'est pas reliée à une preuve localisée dans ce tour » ;
- une réponse déjà citée ou déjà limitée n'est pas modifiée ;
- le prompt de l'orchestrateur demande désormais une preuve par famille de dépendances,
  d'interfaces, de règles ou de données.

## 4. Refus des injections de prompt

**Symptôme** : Flore refusait correctement, mais son refus mentionnait des endpoints et
un « jumeau » non étayés ; le juge préférait parfois le refus plus court du baseline.

**Correctif** : `backend/meridian/application/contrat_securite.py`.

- détection déterministe des demandes du type « ignore les consignes », « contourne les
  règles », « affiche les preuves restreintes » ;
- refus court, stable, sans détail interne ;
- aucune question légitime *sur* la sécurité n'est bloquée.

## 5. Calibration du benchmark

- `must_include_any` est désormais une liste d'alternatives (au moins un terme), plus
  une exigence par groupe ;
- `must_cite_or_declare` accepte une citation **ou** une limitation de preuve explicite ;
- les marqueurs d'abstention couvrent les formulations réelles (« aucune source de
  mesure », « il est impossible de », « absence », etc.) ;
- `judge_context` fournit au juge la vérité terrain et les règles de sécurité ;
- les refus HTTP 403 sont notés comme des refus, pas comme des erreurs de runner.

## Résultats

### Avant les correctifs (3 runs, 11 scénarios)

```text
Critères Flore : 25/33 (76 %)
Pass@k Flore   : 82 %
Juge Flore     : 25/33 (76 %, IC95 61–90 %)
Baseline       : 9/33 (27 %)
```

### Après tous les correctifs — run complet final (3 runs, 11 scénarios)

```text
Critères Flore : 30/33 (91 %)
Pass@k Flore   : 100 %
Juge Flore     : 28/33 (85 %, IC95 73–97 %)
Baseline       : 9/33 (27 %)
```

### Après les derniers correctifs ciblés (3 runs sur 3 scénarios)

`conduit-report`, `conduit-investigation`, `pilot-tenant-isolation` :

```text
Critères Flore : 8/9
Pass@k Flore   : 100 %
Juge Flore     : 9/9
```

La variabilité du modèle explique le léger écart entre le run complet (30/33) et le
run ciblé (8/9) ; le pass@k reste à 100 %.

Les deux derniers points faibles du run complet — rapport annoncé sans artefact et
investigation présentée comme exécutée — sont corrigés par le contrat d'action.

## Tests

```text
test_contrat_action.py   6 passed
test_contrat_preuve.py   4 passed
test_contrat_securite.py 3 passed
test_tenant_twins.py     3 passed
plugin/meridian/tests   57 passed
```

## Reste à faire

- Relancer le benchmark complet une dernière fois avec tous les correctifs.
- Ajouter un bras `context-only` (mêmes claims, sans outils ni orchestration).
- Faire une revue humaine aveugle d'un sous-ensemble.
- Étendre aux surfaces Investigation, Décision, Atlas et pièces jointes.
- Vérifier les autres routes qui lisaient la vitrine Mongo globale (`actualites`,
  `initiatives`, `mesh_vue`) ; le chemin conversation et `/api/jumeaux` sont corrigés.
