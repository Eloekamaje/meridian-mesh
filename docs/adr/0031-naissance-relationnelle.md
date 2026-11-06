# ADR-0031 — Naissance relationnelle : déclaration, résolution et confirmation gouvernée

- **Statut :** proposed
- **Date :** 2026-11-05
- **Décideurs :** Produit, architecture, propriétaires de domaine, sécurité, exploitation
- **Portée :** commande de naissance, Twin, relations du Mesh, déclaration humaine, résolveur, revue par les propriétaires
- **Décisions liées :** ADR-0001 (identité typée), ADR-0003 (Mesh transversal), ADR-0004 (harness capacitaire), ADR-0005 (modèle d'entreprise), ADR-0007 (polyglotte), ADR-0012 (outbox/idempotence), ADR-0022 (projection graphe)
- **Remplace :** l'idée implicite « un Twin existant confirme la relation d'un nouveau Twin »

---

## 1. Contexte

### 1.1 Le problème

Une application qui naît dans Méridian doit pouvoir se situer dans le Mesh :

- ce qu'elle **expose** ;
- ce qu'elle **consomme** ;
- auprès de quels Twins ;
- dans quel environnement ;
- avec quelles preuves ;
- et avec quel niveau de confiance.

Dans beaucoup d'entreprises, l'information n'est pas dans le code :

- le code contient une référence logique (`@EJB PaymentService`, `jms/OrderQueue`, une URL WSDL) ;
- la cible réelle est dans un binding de serveur d'application, un ESB, une gateway ou une file ;
- les serveurs ne sont pas toujours accessibles ;
- les relations déclarées dans une CMDB sont souvent incomplètes, politiques ou périmées.

Une première intuition consiste à faire dialoguer les Twins :

> « Le nouveau Twin envoie un message aux Twins existants ; ceux-ci confirment la relation. »

Cette intuition contient un bon déclencheur — **la naissance** — et une bonne matière — **la déclaration humaine**. Mais elle confond trois choses :

1. **déclarer** une intention ;
2. **attester** un côté de la relation ;
3. **confirmer** une relation d'entreprise.

Un Twin est une **représentation**, pas une autorité. Deux Twins qui se confirment mutuellement peuvent produire une validation circulaire, sans preuve indépendante. Un broadcast à tous les Twins produit du bruit, des fuites d'existence et un coût O(n²). Une confirmation à la naissance ne survit pas aux déploiements, aux changements de contrat et aux migrations.

### 1.2 Ce que le code fournit déjà

| Élément | État | Rôle |
|---|---|---|
| `backend/meridian/application/commandes.py` (`lancer_commande`, `suivre_naissance`, `echec_naissance`) | implémenté | La commande de naissance valide l'identité, les sources, les connecteurs, le runtime, les doublons, puis démarre la naissance. |
| `backend/meridian/domain/graphe.py` (`ETATS_RELATION`) | implémenté | États : `supposee`, `observee`, `validation`, `confirmee`, `contestee`, `obsolete`. |
| `backend/meridian/domain/modele_entreprise.py` (`Relation`) | implémenté | Relation typée avec `mode`, `statut`, `source_id`, `cible_id`, `predicat`, `justification`. |
| `backend/meridian/domain/interfaces.py` | partiel | Assertions `EXPOSE` / `CONSOMME`, contrats, opérations, bindings, modes `declared` / `observed` / `inferred`. |
| `backend/meridian/application/decouverte.py` | partiel | Découverte d'interfaces, impacts, consommateurs touchés. |
| `backend/meridian/adapters/outbound/neo4j/backfill_graphe.py` | partiel | Projection des Twins et relations legacy vers le GraphStore. |
| `backend/meridian/adapters/outbound/postgres/schema.sql`, `outbox` | partiel | Claims, preuves, relations, événements durables. |
| `relations` Mongo en base locale | **0 relation** | La topologie n'est pas encore peuplée. |

Il manque :

- un **manifeste de naissance** qui porte les expositions et consommations déclarées ;
- un **événement `twin.born`** émis au bon moment ;
- un **résolveur** qui joint déclaration, exposition, observation et périmètre ;
- un **protocole de revue** par les propriétaires ;
- une **réconciliation continue** des relations.

### 1.3 Forces en présence

- **Accessibilité.** Les serveurs d'application ne sont pas toujours accessibles ; il faut pouvoir travailler avec le build, les artefacts, les traces, la CMDB ou une déclaration humaine.
- **Preuve.** Une déclaration n'est pas une observation ; une confirmation de Twin n'est pas une preuve.
- **Gouvernance.** Une relation critique engage un propriétaire, un audit et parfois une décision humaine.
- **Échelle.** Un broadcast à tous les Twins n'est pas tenable.
- **Sécurité.** Un nouveau Twin ne doit pas apprendre l'existence de Twins hors de son périmètre.
- **Continuité.** Les relations changent après la naissance ; il faut les réconcilier.
- **Compatibilité.** La commande de naissance existante doit rester le seul point d'entrée ; le protocole relationnel est en aval.

---

## 2. Décision

Méridian adopte une **naissance relationnelle en trois temps** :

1. **La commande de naissance** crée le Twin et produit un **manifeste déclaré** (expositions, consommations, inconnues).
2. **Le résolveur du Mesh** joint ce manifeste aux expositions, aux observations et aux autres Twins, et produit des **propositions de relation ciblées**.
3. **Les propriétaires** confirment ou contestent leur côté ; **l'observation runtime** renforce la relation ; le Twin ne confirme jamais seul.

Formule normative :

> **Le Twin propose et atteste son côté. Le résolveur joint les côtés. Le propriétaire confirme. L'observation renforce. Le Mesh réconcilie en continu.**

---

## 3. Préalables de commande

La relation est **downstream** de la naissance. Aucune proposition de relation ne peut précéder les préalables suivants.

### 3.1 Préalables bloquants avant `twin.created`

| # | Préalable | Où | Bloquant | Preuve |
|---|---|---|---|---|
| C01 | Commande de naissance en `brouillon` | `commandes.lancer_commande` | oui | commande |
| C02 | Identité stable : `twin_id`, `application_id`, `type`, nom | `_identite_lancement` | oui | identité |
| C03 | `tenant_id`, `perimetre_id`, `proprietaire` renseignés | commande / identité | oui | commande |
| C04 | Au moins une source prête | `lancer_commande` | oui | source |
| C05 | Connecteurs des sources prêtes branchés | `lancer_commande` | oui | connecteur |
| C06 | Couche cognitive Postgres disponible | `runtime.disponible()` | oui | runtime |
| C07 | Aucun doublon de Twin / d'Application | `_jumeau_deja_present` | oui | registre |
| C08 | Combinaison de sources admissible | `naissance_possible` | oui | politique |
| C09 | Acteur et espace connus | commande | oui | audit |

### 3.2 Préalables bloquants avant `twin.born`

| # | Préalable | Où | Bloquant | Preuve |
|---|---|---|---|---|
| B01 | Twin inséré avec un identifiant stable | `store.inserer_jumeau` | oui | Twin |
| B02 | Commande marquée `lancee` | `store.marquer_lancee` | oui | commande |
| B03 | Naissance terminée (`naissance.etat = ne`) ou partielle (`sans_substance`) | `suivre_naissance` | oui | run de naissance |
| B04 | Manifeste déclaré produit : expositions, consommations, inconnues | runtime de naissance | oui | manifeste |
| B05 | Preuves du manifeste disponibles : source, claim, artefact | naissance | oui | `evidence_ids` |
| B06 | Périmètre et visibilité connus | commande / politique | oui | politique |
| B07 | Propriétaires identifiés pour les côtés consommateur et fournisseur | Twin / annuaire | oui pour la revue | annuaire |

### 3.3 Règles de séquence

- `twin.created` est émis **après** C01–C09, au moment de l'insertion idempotente.
- `twin.born` est émis **uniquement après** B01–B06, quand la naissance est terminée (`ne`) ou partielle (`sans_substance`).
- Une naissance **échouée** (`echec`) n'émet **jamais** `twin.born`.
- Une naissance **partielle** émet `twin.born` avec `partial=true` et une liste d'`unknowns` ; les relations proposées sont marquées `partial`.
- Le résolveur ne consomme que `twin.born`, jamais `twin.created`.
- Un Twin existant ne peut être cible que s'il est lui-même `twin.born` (ou explicitement `legacy.born`).
- Les Twins antérieurs à cet ADR reçoivent un marqueur de migration `legacy.born` unique, avec la date d'ingestion, le périmètre et les preuves disponibles ; ce marqueur vaut `twin.born` pour le résolveur, mais ne vaut pas confirmation de leurs relations.
- Le protocole relationnel **ne crée jamais** de Twin, ne promeut jamais un Twin, ne modifie jamais l'identité.
- La commande reste **le seul point d'entrée** de la naissance.
- Le rejeu est idempotent : `twin.born` est unique par `(tenant_id, twin_id, birth_run_id)`.
- Le résolveur hérite du `tenant_id`, du `perimetre_id`, de la visibilité et de l'acteur de la commande.
- Le résolveur est un consommateur d'outbox : son échec ne défait pas la naissance ; il est rejoué. La naissance reste valide même si aucune relation n'a encore été proposée.

### 3.4 Événements de commande

```text
commande.creee
  → twin.created
  → naissance.demarree
  → naissance.ne | naissance.sans_substance | naissance.echec
  → twin.born (si `ne` ou `sans_substance`)
```

Le journal de commande reste la source de vérité de l'état de naissance. `twin.born` est un événement **durable** publié dans l'outbox, pas un effet de bord synchrone.

---

## 4. Séquence normative

```text
1. Commande de naissance validée (C01–C09)
2. Twin inséré, commande lancée (B01–B02)
3. Naissance : ingestion, Claims, artefacts, manifeste (B03–B05)
4. twin.born { manifeste, preuves, inconnues, visibilité }
5. Résolveur : matching ciblé
6. relation.proposed { consommateur, fournisseur, objet, mode, preuve, inconnues }
7. Attestation des Twins concernés
8. Revue des propriétaires : confirmer / contester
9. relation.confirmed | relation.challenged
10. Réconciliation continue : observation, déploiement, contrat
```

### 4.1 Manifeste de naissance

Le manifeste est un objet versionné, signé par la commande et attaché au Twin.

```json
{
  "tenant_id": "...",
  "twin_id": "...",
  "application_id": "...",
  "type": "APPLICATION",
  "status": "PROVISIONAL | CONFIRMED",
  "owner": "...",
  "perimetre_id": "...",
  "birth_run_id": "...",
  "partial": false,
  "declared_by": "...",
  "declared_at": "...",
  "exposures": [
    {
      "kind": "HTTP | SOAP | JMS | JNDI | DB | GRPC",
      "operation": "GET /articles",
      "contract_version": "...",
      "environment": "prod",
      "evidence_ids": ["..."],
      "confidence": 0.9
    }
  ],
  "consumptions": [
    {
      "kind": "HTTP | SOAP | JMS | JNDI | DB | GRPC",
      "logical_ref": "jms/OrderQueue",
      "target_hint": "paiements",
      "environment": "prod",
      "evidence_ids": ["..."],
      "confidence": 0.7
    }
  ],
  "unknowns": [
    "binding serveur non disponible",
    "aucune trace observée"
  ],
  "visibility": "TEAM | TWIN | PORTFOLIO | TENANT"
}
```

Le manifeste peut venir de plusieurs sources, dans cet ordre de préférence :

1. manifeste de build (Maven/Gradle/CI) ;
2. descripteurs et bindings dans les artefacts (WAR/EAR, Nexus/Artifactory) ;
3. export serveur read-only ;
4. APM/traces ;
5. CMDB/ESB/gateway ;
6. déclaration humaine.

La déclaration humaine est une **graine**, pas une vérité. Elle est un `Claim` :

```text
mode = DECLARED
statut = PROPOSED
declarant, rôle, date, périmètre
evidence_ids
```

---

## 5. Rôles et autorités

| Acteur | Peut | Ne peut pas |
|---|---|---|
| **Twin nouveau** | Déclarer ses expositions/consommations, publier son manifeste | Confirmer une relation d'entreprise |
| **Twin existant** | Attester son côté : « j'expose », « j'ai observé N appels », « je n'ai pas d'observation » | Confirmer l'intention du consommateur, créer une relation |
| **Résolveur** | Normaliser, matching, proposer, détecter les conflits, cibler les propriétaires | Décider, confirmer, promouvoir |
| **Propriétaire consommateur** | Confirmer l'intention d'appel, contester | Confirmer l'exposition du fournisseur |
| **Propriétaire fournisseur** | Confirmer l'exposition, contester, signaler l'absence d'usage | Confirmer l'intention du consommateur |
| **Observation runtime** | Prouver l'usage réel, la fréquence, la fenêtre | Prouver l'intention ou l'exposition déclarée |
| **LLM** | Rédiger une déclaration, proposer une hypothèse | Confirmer, promouvoir, déclarer une absence |

Règle d'or :

> **Aucune relation n'est `confirmed` sur la seule parole d'un Twin ou d'un modèle.**

---

## 6. Modèle de relation

Une relation est un objet durable, temporel et gouverné :

| Champ | Rôle |
|---|---|
| `relation_id` | Identifiant stable |
| `tenant_id` | Frontière de sécurité |
| `consumer_id` | Twin consommateur |
| `provider_id` | Twin fournisseur |
| `predicate` | `CONSOMME`, `EXPOSE`, `ECOUTE`, `DEPEND_DE`, etc. |
| `object` | Opération, queue, topic, table, endpoint |
| `environment` | `prod`, `preprod`, `recette`, `dev` |
| `mode` | `DECLARED`, `OBSERVED`, `INFERRED`, `PROPOSED`, `CONFIRMED` |
| `state` | `supposee` (proposée), `observee`, `validation`, `confirmee`, `contestee`, `obsolete` |
| `evidence_ids` | Claims, artefacts, traces, déclarations |
| `declared_by` | Déclarant et rôle |
| `consumer_owner` | Propriétaire du consommateur |
| `provider_owner` | Propriétaire du fournisseur |
| `confidence` | Confiance, calculée et explicable |
| `valid_from` / `valid_to` | Temporalité |
| `last_observed_at` | Dernière observation |
| `justification` | Pourquoi la relation existe |
| `unknowns` | Ce qui manque |
| `visibility` | Périmètre de lecture |

### 6.1 États

```text
supposee
  → validation
      → confirmee
      → contestee
  → observee
  → obsolete
```

- `supposee` : déclaration ou inférence, pas encore revue (état « proposée »).
- `validation` : propriétaires notifiés, dossier ouvert.
- `observee` : usage runtime observé, déclaration absente ou incomplète.
- `confirmee` : preuve + revue propriétaire, ou deux sources indépendantes.
- `contestee` : déclaré contre observé, ou désaccord entre propriétaires.
- `obsolete` : plus observée, remplacée, ou source retirée.

### 6.2 Règles de confirmation

| Criticité | Règle minimale |
|---|---|
| **Faible** | Déclaration + un propriétaire + une preuve |
| **Standard** | Déclaration + propriétaire consommateur + propriétaire fournisseur **ou** observation |
| **Critique** | Deux propriétaires + observation, ou deux preuves indépendantes |

Une relation `confirmed` sans observation doit afficher **« déclaré, non observé »**. Une relation `observee` sans déclaration doit afficher **« observé, non déclaré »**. Aucune des deux n'est présentée comme une vérité complète.

### 6.3 Portée et ressources intermédiaires

Une exposition ne devient pas une relation parce qu'elle existe dans le code. Elle doit franchir une **frontière** :

| Portée | Éligible inter-app ? |
|---|---|
| `SERVICE`, `PARTNER`, `PUBLIC` | oui |
| `INTERNAL`, `ADMIN`, `HEALTH`, `DEMO`, `DEBUG` | non |
| `UNKNOWN` | non |

Une consommation doit être `EXTERNAL` ; une consommation `INTERNAL` ou `UNKNOWN` ne produit pas de relation de Mesh. Deux Twins de la même `application_id` ne produisent pas une relation inter-app.

Pour les services qui ne sont pas des endpoints directs — JMS, Kafka, DB, batch, fichier — la relation passe par une **ressource intermédiaire** (`QUEUE`, `TOPIC`, `TABLE`, `FILE`, `ENDPOINT`) :

```text
Application A → ressource → Application B
```

La ressource porte sa portée, sa preuve et son environnement ; la relation finale porte `via = ressource.id` et le `transport` correspondant.

---

## 7. Événements

| Événement | Émis par | Consommé par | Idempotence |
|---|---|---|---|
| `twin.created` | commande | registre, audit | `(tenant_id, twin_id)` |
| `twin.born` | naissance | résolveur, graphe | `(tenant_id, twin_id, birth_run_id)` |
| `relation.proposed` | résolveur | propriétaires, UI | `(tenant_id, relation_id)` |
| `relation.challenged` | propriétaire / Twin | résolveur, situation | `(relation_id, challenge_id)` |
| `relation.confirmed` | revue | graphe, audit | `(relation_id, review_id)` |
| `relation.obsolete` | réconciliation | graphe, audit | `(relation_id, reason, observed_at)` |

Tous les événements portent :

- `event_id`, `tenant_id`, `occurred_at`, `actor`, `correlation_id`, `causation_id` ;
- `visibility` ;
- une signature ou une référence d'audit.

Le résolveur ne diffuse **jamais** à tous les Twins. Il cible :

- le propriétaire du consommateur ;
- le propriétaire du fournisseur ;
- éventuellement un rôle de gouvernance.

Les Twins non concernés ne reçoivent rien. Un Twin existant peut être sollicité pour produire une **attestation** :

- « j'expose cette opération, voici le contrat » ;
- « j'ai observé N appels, voici la trace » ;
- « je n'ai pas d'observation ».

Cette attestation est un ensemble de **Claims**, pas une confirmation de relation. Elle nourrit le dossier du propriétaire, elle ne le remplace pas.

---

## 8. Résolveur et matching

Le résolveur est **déterministe** ; le LLM peut aider à rédiger une déclaration, pas à matcher.

### 8.1 Entrées

- manifeste de naissance ;
- expositions/consommations des Twins existants ;
- interfaces et bindings ;
- observations runtime ;
- CMDB/ESB/gateway ;
- déclarations humaines ;
- visibilité et périmètre.

### 8.2 Normalisation

- opérations HTTP : méthode + chemin normalisé ;
- SOAP : service + port + opération ;
- JMS : queue/topic normalisé ;
- JNDI : nom logique + binding ;
- DB : schéma/table ;
- environnements séparés.

### 8.3 Matching

```text
consommation déclarée
  + exposition déclarée
  + binding serveur (si disponible)
  + trace observée (si disponible)
  = proposition de relation
```

- match exact → confiance haute ;
- match partiel (nom, URL, queue) → `supposee`, à revoir ;
- plusieurs candidats → `AMBIGUOUS`, pas de relation ;
- aucun candidat → `ResolutionCase` + `unknown`, pas d'absence ;
- conflit → `contestee` + situation.

### 8.4 Ce que le résolveur ne fait pas

- il ne crée pas de Twin ;
- il ne promeut pas un Twin ;
- il ne confirme pas une relation ;
- il ne lit pas un secret ;
- il ne traverse pas un tenant ;
- il ne notifie pas un Twin hors visibilité.

---

## 9. Cas limites

| Cas | Comportement |
|---|---|
| Serveur d'application inaccessible | Le manifeste de build et les artefacts suffisent ; la relation reste `declared` / `supposee`. |
| Aucune trace | La relation peut être confirmée par les propriétaires, mais affichée « non observée ». |
| Twin existant muet | `en_attente`, avec SLA et relance ; jamais « pas de relation ». |
| Twin existant périmé | `contestee` ou `unknown` ; la revue humaine tranche. |
| Deux Twins se confirment mutuellement | Refusé : la confirmation exige un propriétaire ou une observation indépendante. |
| Relation déclarée mais jamais observée | `a_verifier` après N jours, puis `obsolete`. |
| Relation observée mais non déclarée | `observee` + situation « relation non déclarée ». |
| Nouveau Twin provisoire | `twin.born` avec `status=PROVISIONAL` ; relations `supposee`, pas `confirmee` avant promotion. |
| Naissance échouée | Aucun `twin.born`, aucune relation proposée. |
| Naissance partielle | `twin.born` avec `partial=true` et `unknowns` ; relations `partial`. |
| Cross-tenant | Interdit ; aucune proposition, aucun message. |
| Rejeu d'événement | Idempotent ; pas de doublon de relation ni de notification. |

---

## 10. Alternatives considérées

### Alternative 1 — Broadcast du nouveau Twin à tous les Twins, confirmation par les Twins

- **Avantages :** simple à raconter ; exploite les Twins existants ; pas de composant central.
- **Inconvénients :** O(n²) messages ; bruit ; fuite d'existence ; validation circulaire ; un Twin n'est pas une autorité ; confirmation sans preuve ; ne survit pas aux changements.
- **Pourquoi rejetée :** elle transforme une représentation en autorité et un message en preuve.

### Alternative 2 — CMDB déclarative comme source de vérité

- **Avantages :** référentiel connu ; relations déclarées ; intégration existante.
- **Inconvénients :** souvent incomplète, politique, en retard ; ne prouve pas l'usage ; ne couvre pas les environnements ; pas de mode/état/fraîcheur.
- **Pourquoi rejetée :** une déclaration CMDB est une **graine**, pas une vérité.

### Alternative 3 — Runtime uniquement (traces/APM)

- **Avantages :** preuve d'usage réelle ; indépendante du code ; couvre les serveurs opaques.
- **Inconvénients :** pas de traces pour tout ; pas d'intention ; pas de relations non appelées ; échantillonnage ; coût ; accès APM parfois fermé.
- **Pourquoi rejetée :** l'observation seule ne dit pas pourquoi la relation existe ni qui l'assume.

### Alternative 4 — Résolveur central + manifeste de naissance + revue des propriétaires (retenue)

- **Avantages :** fonctionne avec peu d'accès ; déclaration humaine valorisée ; matching ciblé ; preuve et observation ; gouvernance ; idempotence ; compatible avec le graphe.
- **Inconvénients :** plus d'objets et d'événements ; charge de revue ; nécessité d'un annuaire de propriétaires ; réconciliation continue.
- **Pourquoi retenue :** c'est la seule qui sépare **déclarer**, **attester**, **observer** et **confirmer**.

### Alternative 5 — Édition manuelle des relations dans le graphe

- **Avantages :** contrôle total ; rapide.
- **Inconvénients :** viole ADR-0001 (relations dérivées), pas de provenance, pas de réconciliation, pas d'audit.
- **Pourquoi rejetée :** une relation éditée à la main est une opinion, pas une connaissance.

---

## 11. Conséquences

### Positives

- La déclaration humaine devient exploitable sans devenir une vérité.
- Les serveurs inaccessibles ne bloquent plus la découverte : le manifeste de build, les artefacts, les traces et la CMDB prennent le relais.
- Les relations ont un mode, un état, une preuve, une fraîcheur et des propriétaires.
- Le volet cognitif peut afficher « déclaré », « observé », « contesté », « inconnu ».
- Le Mesh peut être peuplé sans attendre un accès admin.
- La gouvernance est explicite : le Twin propose, le propriétaire décide, l'observation renforce.

### Négatives

- Plus d'événements et d'objets à maintenir.
- Charge de revue pour les propriétaires.
- Nécessité d'un annuaire de propriétaires fiable.
- Le résolveur doit gérer les ambiguïtés, les doublons et les environnements.
- Les relations partielles restent partielles tant que les sources manquent.

### Risques

- **Déclaration biaisée** : propriétaire qui déclare ce qu'il croit, pas ce qui est. Mitigation : mode `DECLARED`, observation, revue.
- **Validation circulaire** : deux Twins se confirment. Mitigation : confirmation par propriétaire ou observation indépendante.
- **Bruit de notifications** : broadcast. Mitigation : résolveur ciblé, batch, visibilité.
- **Relations fantômes** : matching trop permissif. Mitigation : seuil, `AMBIGUOUS`, revue.
- **Relations périmées** : naissance unique. Mitigation : réconciliation continue, `last_observed_at`, `a_verifier`.
- **Fuite inter-tenant** : message ou relation hors périmètre. Mitigation : tenant, visibilité, tests d'isolation.
- **Événements perdus** : outbox non consommée. Mitigation : outbox durable, idempotence, rejeu, métrique de retard.

---

## 12. Critères d'acceptation

1. **Préalables de commande**
   - Aucun `twin.born` n'est émis avant C01–C09 et B01–B06.
   - Une naissance échouée n'émet aucun `twin.born`.
   - Une naissance partielle émet `twin.born` avec `partial=true` et `unknowns`.

2. **Pas de relation avant naissance**
   - Une proposition de relation pour un Twin non `twin.born` est refusée.
   - Le résolveur ne consomme que `twin.born`.

3. **Autorité**
   - Un Twin ne peut pas confirmer seul une relation.
   - Une relation `confirmee` exige un propriétaire ou une observation indépendante.
   - Un LLM ne peut pas produire un état `confirmee`.

4. **Preuve et état**
   - Toute relation porte `mode`, `state`, `evidence_ids`, `confidence`, `valid_from`, `last_observed_at`.
   - Une relation déclarée sans observation est affichée « déclarée, non observée ».
   - Une relation observée sans déclaration est affichée « observée, non déclarée ».

5. **Ciblage et sécurité**
   - Aucun broadcast à tous les Twins.
   - Aucune notification hors visibilité ou hors tenant.
   - Les secrets ne sont jamais dans un événement, un manifeste ou un log.

6. **Idempotence et rejeu**
   - Le rejeu de `twin.born` ne duplique ni Twin ni relation.
   - Le rejeu de `relation.proposed` ne duplique pas les notifications.
   - Un échec du résolveur ne change pas l'état de naissance ; l'événement est rejoué.

7. **Réconciliation**
   - Un déploiement ou un changement de contrat déclenche une re-résolution.
   - Une relation non observée depuis N jours passe en `a_verifier`, puis `obsolete`.

8. **Silence**
   - Un Twin muet produit `en_attente` + `ResolutionCase`, jamais « pas de relation ».
   - Une source indisponible produit `INCONCLUSIVE`, jamais `NOT_OBSERVED`.

9. **Traçabilité**
   - Depuis une relation, on peut remonter à la déclaration, à la preuve, à l'observation et au propriétaire.
   - Chaque transition d'état a un acteur, une date et un motif.

10. **Produit**
    - Le volet cognitif affiche les relations avec leur mode, état, preuve, fraîcheur et inconnues.
    - L'Atlas distingue déclaré, observé, contesté et inconnu.

---

## 13. Implémentation du premier lot (2026-11-05)

Le premier lot est en place, sans changer la commande de naissance :

- `backend/meridian/domain/naissance_relationnelle.py` : manifeste, exposition, consommation, proposition, revue, observation, **portée** et **ressource intermédiaire**.
- `backend/meridian/application/relations_naissance.py` : construction du manifeste depuis les Claims `EXPOSE` / `CONSOMME`, classification des routes techniques, matching direct et via ressource, propositions.
- `backend/meridian/adapters/outbound/postgres/relations_naissance.py` : manifeste stocké comme `ARTIFACT`, propositions comme `RELATION`, événement `twin.born` dans l'outbox, lecture et revue, backfill/refresh legacy.
- `backend/meridian/adapters/outbound/connectors/naissance.py` : `celebrer_naissance` appelé **après** `naissance.etat = ne`, jamais avant.
- `backend/meridian/adapters/inbound/worker/outbox_worker.py` : consommateur `twin.born` idempotent.
- `backend/meridian/adapters/inbound/http/cognitif.py` : `GET /boucle/twins/{id}/manifeste`, `GET /boucle/relations`, `POST /boucle/relations/{id}/revue`.
- `scripts/backfill-manifestes-naissance.py` : dry-run par défaut, `--apply`, `--refresh`, `--tenant`, `--limite`, `--sans-schema`. Il prépare les Twins existants avec un manifeste de migration, sans promotion ni `twin.born`.
- Tests : `backend/meridian/tests/test_relations_naissance.py`, `test_cognitif_routes.py`, `test_naissance.py`.

État local après backfill/refresh :

- **8 manifestes** créés puis rafraîchis ;
- **170 routes HTTP**, aucune SOAP/JMS/JNDI/DB ;
- **24 routes techniques** classées (`HEALTH`, `ADMIN`, `DEMO`) ;
- **146 routes `UNKNOWN`** : aucun contrat, gateway ou déclaration de frontière ne permet encore de les qualifier `SERVICE` / `PARTNER` / `PUBLIC` ;
- **0 exposition éligible** et **0 consommation** : aucune relation de Mesh ne peut donc être proposée pour l'instant. C'est l'état honnête, pas un échec du résolveur.

Limites assumées de ce premier lot :

- le matching est exact (méthode + chemin, URL normalisée, queue/JNDI) ; la similarité floue et l'ambiguïté explicite viendront ensuite ;
- `sans_candidat` est retourné avec sa raison mais pas encore persisté comme `UNKNOWN` / `ResolutionCase` ;
- un Twin né en observation est `PROVISIONAL` ; ses propositions sont `PROPOSED` et ne peuvent pas être confirmées avant sa promotion ;
- `relation.proposed`, `relation.challenged` et `relation.confirmed` ne sont pas encore émis dans l'outbox ; les propositions sont persistées et consultables ;
- la projection vers le GraphStore reste un lot séparé ;
- la revue critique se fait en deux confirmations propriétaires (état `validation` entre les deux) ;
- aucun pack gateway/OpenAPI/SOAP/JMS/DB/batch n'est encore branché : sans ces sources, les routes restent `UNKNOWN` et non éligibles ;
- une `Ressource` intermédiaire n'est matérialisée que si le manifeste la déclare (`ressource_id`) ; l'extraction des queues/topics/tables/fichiers reste à faire.

---

## 14. Références

- `docs/prd/PRD-001-enterprise-intelligence-mesh.md`
- `docs/adr/0001-identite-typed-twin-discovery.md`
- `docs/adr/0003-mesh-transversal-intelligence.md`
- `docs/adr/0004-capability-first-harness.md`
- `docs/adr/0005-enterprise-object-model.md`
- `docs/adr/0007-polyglot-postgres-graph.md`
- `docs/adr/0012-outbox-idempotence.md`
- `docs/adr/0022-graphe-projection.md`
- `docs/adr/0032-decouverte-liens.md` — résolution de destination et cas non résolus
- `docs/cognitive/PROGRAMME.md`
- `docs/architecture/java-jee-spring-pack.md`
- `docs/architecture/legacy-frameworks-reference.md`
- `backend/meridian/application/commandes.py`
- `backend/meridian/domain/graphe.py`
- `backend/meridian/domain/modele_entreprise.py` (`Relation`)
- `backend/meridian/domain/interfaces.py`
- `backend/meridian/application/decouverte.py`
- `backend/meridian/adapters/outbound/neo4j/backfill_graphe.py`
