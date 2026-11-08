# Méridian — écarts avec la vision

> **Photographie :** 8 novembre 2026, HEAD `ef2cf7a` + lot C5d.
> **Cible :** [Product Vision](../MÉRIDIAN%20%E2%80%94%20Product%20Vision%20%26%20Operating%20Model.md),
> [Product Blueprint](../MERIDIAN_Product_Blueprint_v1.md),
> [Domain Model](../MERIDIAN_Domain_Model_Information_Architecture_v1.md).
> **État :** [etat-actuel.md](etat-actuel.md).
>
> Ce document ne remplace pas l’état actuel : il confronte la cible au code réel et répond à
> trois questions : **que doit faire Méridian ? que fait-il déjà ? que manque-t-il ?**

## 0. Règle de lecture

- **Solide** : branché dans un chemin réel et couvert par des tests.
- **Partiel** : le code existe, mais le chemin produit complet manque.
- **Cible** : décrit dans la vision ou le modèle, pas encore dans le code.
- **Absent** : ni classe, ni route, ni persistance, ni surface.

Une capacité n’est **solide** que si elle est utilisable de bout en bout, pas seulement si son
modèle ou son test unitaire existe.

### Trois modèles à ne pas confondre

Le produit actuel combine trois modèles qui ne forment pas encore une seule chaîne :

| Modèle | Où | Rôle | Utilisé par |
|---|---|---|---|
| **Travail / Actualités (legacy)** | MongoDB `cases`, `situations`, `initiatives`, `relations` | Surface produit actuelle : histoires, travaux, décisions, passation, veille, priorités | `/actualites`, `/cases`, `/initiatives`, couche Situations de l’Atlas |
| **Boucle canonique** | PostgreSQL `objet_entreprise`, `boucle.py` | Modèle d’entreprise validé : Situation → Investigation → Decision → Initiative → Outcome → Learning ; transitions et création d’une Situation racine exposées dans l’UI | `/boucle/objets` (lecture), `POST /boucle/situations` (création racine), transitions de l’UI Boucle, `/boucle/outcomes`, backfill partiel `migration_canonique` (situations, initiatives) |
| **Dossier de raisonnement** | PostgreSQL `dossiers_raisonnement` | Trace cognitive d’une réponse : croyances, hypothèses, options, critique, décision de réponse, gates | `/boucle/analyser`, `/aurora`, page Cognition |

Conséquence : le socle « Comprendre » est cohérent, mais l’exploitation vit encore dans le
legacy et le raisonnement, tandis que la boucle canonique est désormais opérable depuis l’UI
(création d’une Situation racine et transitions jusqu’au Learning), tout en restant alimentée
en parallèle par le backfill et le pont C2. **C’est l’écart structurant principal.**

---

## 1. La cible

> **Méridian est un système d’intelligence vivante de l’entreprise. Il découvre continuellement
> son fonctionnement réel, fait mûrir la connaissance, révèle risques et opportunités, mobilise
> les expertises nécessaires, accompagne les décisions et apprend de leurs résultats.**

Cycle cible :

```text
Découvrir → Maturer → Exprimer → Investiguer → Décider → Agir → Mesurer → Apprendre
```

| Étape | Question à laquelle elle répond | Objet / sortie attendue |
|---|---|---|
| **Découvrir** | Que sait-on de l’entreprise, de son SI et de ses usages ? | Sources, observations, Twins, relations, claims, preuves |
| **Maturer** | Ce que l’on croit est-il assez solide pour être présenté ? | Hypothèses, claims renforcés, contradictions, confiance |
| **Exprimer** | Que semble signifier ce phénomène ? | Expression datée, typée, prouvée, avec incertitudes |
| **Investiguer** | Pourquoi, depuis quand, pour qui, avec quelles dépendances ? | Investigation, hypothèses concurrentes, experts, preuves |
| **Décider** | Quelles options existent et laquelle est préférable ? | Scénarios comparés, décision humaine, rationale |
| **Agir** | Comment traduire la décision en action suivie ? | Initiative, plan, responsables, dépendances, critères |
| **Mesurer** | Qu’a-t-on réellement obtenu, y compris les effets secondaires ? | Outcome observé, écart attendu/observé |
| **Apprendre** | Que faut-il retenir pour les prochaines décisions ? | Learning, patterns, mémoire de transformation |

### Les objets vivants

Le Domain Model définit un modèle plus riche que la boucle canonique actuelle :

```text
Signal · Situation candidate · Expression · Opportunity · Risk
Investigation · Hypothesis · Expert · ExpertContribution · Scenario
Decision · Initiative · Outcome · Learning
```

### Les surfaces

- **Aujourd’hui** : ce qui mérite l’attention, ce qui demande une décision, ce qui change, ce qui apprend.
- **Atlas** : la géographie du Mesh, pas le produit entier.
- **Flore** : l’interface conversationnelle d’exploitation.
- **Travail / Boucle** : l’espace où une situation devient investigation, décision, initiative et résultat.

### Les trois générations

| Génération | Cible | État réel |
|---|---|---|
| **Méridian 1 — Comprendre** | Représentation vivante et fiable de l’entreprise : Twins, Mesh, Claims, sources, découverte, relations, Atlas, compréhension | **Solide sur le socle ; partiel sur la couverture** |
| **Méridian 2 — Exploiter** | Transformer la compréhension en attention, investigation et décision : maturation, expressions, risques/opportunités, experts, investigations, scénarios, Flore, priorisation | **Partiel** |
| **Méridian 3 — Améliorer** | Mesurer les décisions, apprendre des résultats, améliorer continuellement : initiatives, outcomes, apprentissage, mémoire de transformation | **Embryonnaire** |

---

## 2. Ce qui existe déjà

### 2.1 Socle « Comprendre »

- **Twin typé** : 11 types, identité stable, `application_id` optionnelle, naissance gouvernée,
  manifeste, `twin.born`, revue humaine (`domain/modele_entreprise.py`,
  `postgres/relations_naissance.py`).
- **Sources et ingestion** : Git, Confluence, SharePoint, ServiceNow, Datadog, OTLP, Jira,
  CBM, Graphify, legacy (`adapters/outbound/connectors/*`, `source_worker`).
- **Claims et preuves** : sujet-prédicat-objet, mode, maturité, preuves localisées, contradictions
  conservées (`postgres/connaissance.py`).
- **Découverte des liens** : code, contrats, configuration, Kubernetes/Helm, ingress, JNDI,
  traces, appels HTTP/JMS/SOAP (`application/moteur_liens.py`, `connectors/extraction_*`,
  `connectors/cbm_liens.py`).
- **Atlas** : navigation Mesh → Domaine → Twin, focus, sélection, portes, situations
  (`frontend/src/pages/Atlas.jsx`).
- **Revue** : confirmation/rejet/contestation humaine, promotion auditée
  (`frontend/src/pages/Jumeaux.jsx`, `RevueJumeau.jsx`).

### 2.2 Cognition et mémoire

- **Dossier de raisonnement** : demande, cadre, plan, croyances, constats, options, critique,
  décision de réponse, validation, gates (`domain/dossier_raisonnement.py`,
  `application/noyau_raisonnement.py`).
- **Composition bornée** : profils, méthodes, compétences, spécialistes, budgets
  (`application/composition.py`, `domain/profils.py`).
- **Spécialistes cognitifs** : découverte, preuve, impact, outcome, critique, risque
  (`application/specialiste_*.py`, `domain/specialistes.py`).
- **Mémoire multi-niveaux** : travail, épisodique, sémantique, procédurale, relationnelle,
  réflexive, prospective, organisationnelle, documentaire (`postgres/memoire_*.py`,
  `retrieval_memoire.py`).
- **Calibration et apprentissage** : prédictions, outcomes, révision de croyances, réutilisation
  mesurée des Learnings (`calibration_croyances.py`, `outcomes.py`, `retrieval_memoire.py`).

### 2.3 Exploitation

- **Travail** : conversation, pièces, hypothèses, options, décisions, passation, veille
  (`adapters/inbound/http/cases.py`, `frontend/src/pages/TravailDetail.jsx`).
- **Flore** : contexte Atlas, citations, preuves, commandes explicites, mobilisation bornée des
  Twins (`adapters/inbound/http/legacy.py`, `components/ComposerFlore.jsx`).
- **Aujourd’hui / Actualités** : histoires interprétées, « pourquoi maintenant », sections
  opportunités/découvertes/transformations/surveillance (`actualites.py`, `Actualites.jsx`).
- **Planification** : capacité, charge, prévision, budget, scénarios de capacité, connecteur
  Jira ; Azure DevOps non identifié (`application/planification/*`,
  `adapters/inbound/http/planification.py`).
- **Gouvernance** : auth `proxy`/`oidc`, RBAC serveur, tenant, RLS opt-in, audit, rétention.

### 2.4 Ce qu’on peut démontrer aujourd’hui

1. Faire naître un Twin depuis un dépôt Git, avec claims, preuves et manifeste.
2. Découvrir des liens entre composants et les faire réviser par un humain.
3. Explorer le Mesh dans l’Atlas et ouvrir un Travail depuis une actualité.
4. Questionner Flore avec citations et preuves.
5. Consigner une décision, sa note de passation et surveiller ses effets.
6. Retrouver des Learnings, mesurer leur réutilisation et calibrer des croyances.
7. Planifier capacité/charge et projeter les Twins dans Neo4j.

---

## 3. Matrice des écarts par étape

| Étape | Cible | Existant | Preuve code | Écart | Statut | Priorité |
|---|---|---|---|---|---|---|
| **Découvrir** | Observer applications, services, API, données, messages, dépendances, règles, processus, équipes, documents, changements, incidents, usages, parcours, tâches, événements | Twins 11 types, ingestion multi-sources, CBM, claims/preuves, liens, Atlas, revue | `modele_entreprise.py`, `ingerer.py`, `cbm_liens.py`, `moteur_liens.py` | Couverture inégale : code/topologie solides, métier/parcours/tâches/employés/clients peu outillés ; connecteurs live et CBM à valider | **Solide sur le code ; partiel sur le métier et les usages** | P1 couverture, P0 CBM/live |
| **Maturer** | Observation → Hypothèse → Claim → renforcé → mature ; multi-source, historique, fréquence, cohérence temporelle, contradictions, qualité des preuves, expertise, confiance | Maturité des Claims, contradictions conservées, calibration confiance/outcome, spécialiste preuve, score d’attention ; `Hypothesis` canonique depuis C5c avec cycle de renforcement/affaiblissement/confirmation ; `Signal` canonique depuis C5d (création/liste/lecture, sans cycle de statut) | `connaissance.py`, `calibration_croyances.py`, `specialiste_preuve.py`, `attention.py`, `objets_exploitation.py` | Pas de pipeline automatique de maturation des phénomènes ; `Signal` est saisi manuellement, sans agrégation fréquence/temporalité ni promotion automatique ; promotion encore peu outillée | **Partiel** | P0/P1 |
| **Exprimer** | Formuler une lecture du réel : faits, hypothèses, preuves, incertitudes, confiance ; types opportunité/risque/anomalie/dérive/contradiction/changement/simplification/duplication/comportement | Histoires `Actualités` (legacy) avec récit, « pourquoi maintenant », reste à comprendre, opportunité ; `Expression` canonique et `Situation.expression_id` (C5a) ; qualification manuelle d'une Expression en `Opportunity`/`Risk` (C5b) | `actualites.py`, `Actualites.jsx`, `objets_exploitation.py`, `commandes_boucle.py`, `boucle.py`, `Boucle.jsx` | La classe, la typologie, une Expression unique par Situation et la qualification canonique en opportunité/risque sont opérationnelles ; pas de pipeline automatique Expression → Opportunity/Risk ; surface `Actualités` encore alimentée par Mongo legacy | **Partiel** | P0 |
| **Investiguer** | Investigation structurée : contexte, problème, preuves, timeline, hypothèses concurrentes, experts, contradictions, sous-questions, découvertes, scénarios | Travail/case : hypothèses, options, investigations, décisions, passation, veille ; dossier de raisonnement : croyances, hypothèses, options, critique, gates ; contrats d’investigation et spécialistes ; `Hypothesis` canonique depuis C5c | `cases.py`, `dossier_raisonnement.py`, `noyau_raisonnement.py`, `investigation.py`, `specialistes.py`, `objets_exploitation.py` | Investigation canonique créée par le pont C2 depuis Travail ; Hypothesis canonique créée manuellement depuis une Investigation ; pas d'objet Expert/ExpertContribution canonique ; pas d’UI investigation unifiée ; les experts sont des profils/spécialistes, pas des experts métier avec contributions | **Partiel** | P0/P1 |
| **Décider** | Options/scénarios évalués (valeur, coût, complexité, risque, dépendances, délai, impacts client/employé/réglementaire, réversibilité, confiance) ; décision humaine tracée | Décision legacy dans Travail + note de passation ; `Decision` canonique et transitions ; `Scenario` canonique avec comparaison déterministe dans la Boucle ; contrefactuel pur ; scénarios de capacité | `cases.py`, `DecisionPassation.jsx`, `objets_exploitation.py`, `commandes_boucle.py`, `boucle.py`, `contrefactuel.py`, `planification/scenario.py` | Scénarios canoniques et comparaison exposés ; pas de scénarios de capacité reliés à la décision ; la décision ne sélectionne pas encore explicitement un scénario ; critères non homogènes | **Partiel** | P0/P1 |
| **Agir** | Décision → initiative ; étapes, responsables, dépendances, plan, critères de succès, traçabilité | Planification capacité/charge/prévision/budget ; initiatives legacy ; `Initiative` canonique créée par C3 après réponse ; connecteur Jira ; délégations | `application/planification/*`, `initiatives.py`, `legacy.py`, `boucle.py`, `initiatives_auto.py` | Pas d’API/UI canonique de création ou de transition d’Initiative ; planification et boucle non reliées ; Jira live partiel ; Azure DevOps non identifié ; pas de plan d’action canonique | **Partiel** | P0/P1 |
| **Mesurer** | Observer les conséquences réelles, comparer attendu/observé, détecter les effets secondaires | `Outcome` canonique + `/boucle/outcomes` ; worker D observations → Outcome ; note de passation + veille legacy ; calibration ; observations de Twins | `outcomes.py`, `mesure_auto.py`, `cognitif.py`, `cases.py` (veille), `moteur_veille`, `calibration_croyances.py` | Mesure automatique branchée sur observations, mais pas encore sur le chemin veille legacy complet ; dépend d’une Initiative canonique ; deux chemins de mesure non unifiés | **Partiel** | P1 |
| **Apprendre** | Mémoire de transformation : quelles recommandations ont marché, récurrences, effets secondaires, dépendances sous-estimées, valeur | Learning canonique, retrieval, réutilisation mesurée, calibration, consolidation mémoire, propositions depuis dossier | `outcomes.py`, `retrieval_memoire.py`, `apprentissage_raisonnement.py`, `consolidation_memoire.py`, `cognitif.py` | Pas de mémoire de transformation interrogeable ; pas de détection de patterns ; réutilisation non enregistrée automatiquement ; promotion humaine ; pas de lien veille legacy → Learning canonique | **Partiel / embryonnaire** | P1 |

---

## 4. Matrice des objets

| Objet | Modèle | Persistance | Création live | Statut |
|---|---|---|---|---|
| **Signal** | `objets_exploitation.Signal`, `construction_objets_exploitation.nouveau_signal` | `objet_entreprise` + liens inverses `Situation.signal_ids`, empreinte SHA-256 serveur | `POST /api/boucle/signals`, `POST /api/boucle/situations/{id}/signals`, `GET /api/boucle/signals` et actions « Enregistrer un signal » dans Boucle ; statut initial `DETECTED`, mode `OBSERVED`, sans route de transition en C5d | **Opérationnel en création/liste/lecture, périmètre UI borné** |
| **Situation candidate** | `modele_entreprise.Situation` | `objet_entreprise` + backfill `migration_canonique` | `POST /boucle/situations` et bouton « Nouvelle situation » dans Boucle ; le live crée encore des `situations` Mongo | **Partiel** |
| **Expression** | `objets_exploitation.Expression` | `objet_entreprise` + lien inverse `Situation.expression_id` | `POST /api/boucle/situations/{id}/expressions` et action « Exprimer la situation » dans Boucle ; une seule Expression par Situation | **Opérationnel, une par Situation** |
| **Opportunity** | `modele_entreprise.Opportunity` | `objet_entreprise` + lien inverse `Expression.opportunity_ids` | `POST /api/boucle/expressions/{id}/opportunities`, `GET /api/boucle/expressions/{id}/opportunities`, `POST /api/boucle/opportunities/{id}/statut` et actions « Qualifier une opportunité » / « Changer le statut » dans Boucle | **Opérationnel depuis une Expression, périmètre UI borné** |
| **Risk** | `modele_entreprise.Risk` | `objet_entreprise` + lien inverse `Expression.risk_ids` | `POST /api/boucle/expressions/{id}/risks`, `GET /api/boucle/expressions/{id}/risks`, `POST /api/boucle/risks/{id}/statut` et actions « Qualifier un risque » / « Changer le statut » dans Boucle | **Opérationnel depuis une Expression, périmètre UI borné** |
| **Investigation** | `modele_entreprise.Investigation` | `objet_entreprise` possible | Créée par `POST /boucle/situations/{id}/investigations` (UI) ou par le pont C2 | **Partiel** |
| **Hypothesis** | `objets_exploitation.Hypothesis`, `construction_objets_exploitation.nouvelle_hypothese` | `objet_entreprise` + lien inverse `Investigation.hypothesis_ids` | `POST /api/boucle/investigations/{iid}/hypotheses`, `GET /api/boucle/hypotheses`, `POST /api/boucle/hypotheses/{hid}/statut` et actions « Formuler une hypothèse » / « Changer le statut » dans Boucle ; statut initial `OPEN`, cycle `OPEN → STRENGTHENED|WEAKENED|REJECTED|CONFIRMED` | **Opérationnel depuis une Investigation, périmètre UI borné** |
| **Expert** | `profils.Profil`, spécialistes cognitifs | Aucune | Aucune | **Partiel** |
| **ExpertContribution** | `Proposition`, contributions de mobilisation | Dossier de raisonnement / réponse | Pas d’objet canonique | **Partiel** |
| **Scenario** | `objets_exploitation.Scenario`, `construction_objets_exploitation.nouveau_scenario` | `objet_entreprise` + liens inverses `scenario_ids` / `scenario_id` | `POST /boucle/scenarios`, `GET /boucle/scenarios`, `POST /boucle/scenarios/comparer` et UI Boucle ; formulaire de création exposant titre, description, hypothèses/actions, valeur, coût, délai, risque, complexité, confiance, dépendances, impacts, preuves, réversibilité et statut ; comparaison plafonnée à 50 | **Opérationnel, périmètre UI borné** |
| **Decision** | `modele_entreprise.Decision` | `objet_entreprise` possible | Créée par le pont C2 ou par `POST /boucle/investigations/{id}/decisions` (UI) | **Partiel** |
| **Initiative** | `modele_entreprise.Initiative` | `objet_entreprise` + backfill `migration_canonique` | Créée par C3 après `POST /initiatives/{iid}/repondre` ou par `POST /boucle/decisions/{id}/initiatives` (UI) | **Partiel** |
| **Outcome** | `modele_entreprise.Outcome` | `objet_entreprise` | `POST /boucle/outcomes` ou worker D observations → Outcome ; exige une Initiative canonique | **Partiel** |
| **Learning** | `modele_entreprise.Learning` | `objet_entreprise` | Via `/boucle/outcomes` ou `/raisonnement/apprentissage` | **Partiel** |

Les objets **Twin**, **Claim**, **Relation**, **Source** et **Preuve** sont, eux, réellement
branchés dans le chemin de découverte et de revue.

---

## 5. Matrice des surfaces

| Surface | Cible | Existant | Écart | Statut |
|---|---|---|---|---|
| **Aujourd’hui / Actualités** | Ce qui émerge, ce qui demande une décision, ce qui change, ce qui apprend | Onglets Brief/Radar/À traiter/Suivis ; sections opportunités/découvertes/transformations/surveillance ; « pourquoi maintenant » | Alimentée par Mongo legacy ; pas de lien canonique vers Expression/Opportunity/Risk ; pas de lecture unifiée de la boucle | **Partiel** |
| **Atlas** | Géographie du Mesh | Navigation hiérarchique, focus, sélection, portes, couche Situations | Couche Situations encore legacy ; pas de lien direct vers la boucle canonique | **Solide** |
| **Flore** | Interface conversationnelle d’exploitation | Contexte, citations, preuves, commandes, mobilisation des Twins | Pas de comparaison de scénarios, de requête « quels experts ont participé ? », ni d’action canonique sur la boucle | **Partiel** |
| **Travail** | Espace investigation/décision/action | Conversation, pièces, hypothèses, options, décisions, passation, veille | Modèle Mongo ; crée les objets canoniques via le pont C2 | **Solide pour le travail, branché pour la boucle** |
| **Boucle** | Boucle opérationnelle complète | Lecture des objets canoniques et synthèse ; création d’une Situation racine ; transitions Investigation → Decision → Initiative → Outcome → Learning ; création et comparaison de Scénarios ; qualification d’une Expression en Opportunity/Risk et transitions de statut ; création d’Outcome et de Twin | La qualification Opportunity/Risk est manuelle et bornée à l’UI ; édition et suppression non exposées ; la décision ne sélectionne pas encore un scénario ; pas de rattachement automatique Opportunity/Risk → Investigation | **Opérationnelle, périmètre Opportunity/Risk borné** |
| **Jumeaux** | Registre, revue, promotion | Fiche, revue, claims, contradictions, cartes | Extension P2/P3 à faire | **Solide** |
| **Administration** | Sources, couverture, propriétaires, audit | Sources, santé, rôles, couverture, journal | Connecteurs live à valider | **Solide** |
| **Cognition** | Dossier, croyances, mémoire, calibration | Approbations, mémoire, dossiers, calibration | Pas de mémoire de transformation interrogeable | **Solide / partiel** |

---

## 6. Les écarts structurants

### 6.1 Trois modèles au lieu d’une chaîne

Le live utilise le legacy Travail/Actualités et le dossier de raisonnement. La boucle canonique
est un modèle Postgres validé, alimenté par backfill et par le pont C2 : les actions/décisions
de Travail enfilent des événements et le worker crée ou met à jour Situation, Investigation,
Decision et Initiative. Le lot D mesure les observations et crée des `Outcome` ; le `Learning`
reste une validation humaine. La chaîne est branchée mais pas encore supervisée de bout en bout
en production (workers, migration tenant rétroactive, RLS).

**Conséquence** : une même Situation peut désormais être suivie jusqu'à l'Outcome via la trace
`boucle` de Travail ; il reste à activer et superviser le parcours complet jusqu'au Learning.

### 6.2 Les objets de l’exploitation manquent

`Signal`, `Expert` et `ExpertContribution` n’existent pas encore tous comme objets
canoniques opérationnels. `Signal` est canonique depuis C5d en création, liste et lecture
(global ou rattaché à une ou plusieurs Situations), mais sans cycle de statut exposé ni
pipeline de détection. `Expression` est désormais canonique, créable depuis une Situation
(C5a), et `Scenario` est canonique et comparable dans la Boucle. `Opportunity` et `Risk`
sont opérationnels depuis une Expression (C5b) : qualification manuelle, statut initial
`DETECTED`, cycle de maturation et liens inverses. `Hypothesis` est canonique depuis C5c,
créable depuis une Investigation, avec conditions de test, claims soutenants/opposants,
cycle de renforcement/affaiblissement/rejet/confirmation et lien inverse
`Investigation.hypothesis_ids` ; la confirmation exige une preuve. Le champ `expert_id`
reste réservé à C5e : il n'est pas accepté en entrée HTTP et n'apparaît pas dans le
formulaire. La vision fait pourtant
de l’Opportunité un objet majeur et attend encore un pipeline automatique de
détection/qualification et de formulation d’hypothèses.

### 6.3 La boucle est opérable, mais pas encore complète

`/boucle/objets` est en lecture et l’UI Boucle expose désormais les écritures canoniques :

- créer une Situation racine (`POST /boucle/situations`, bouton « Nouvelle situation ») ;
- exprimer une Situation (`POST /boucle/situations/{id}/expressions`, action
  « Exprimer la situation ») ;
- qualifier une Expression en Opportunité ou en Risque
  (`POST /boucle/expressions/{id}/opportunities`, `POST /boucle/expressions/{id}/risks`,
  actions « Qualifier une opportunité » / « Qualifier un risque ») et faire évoluer leur
  statut (`POST /boucle/opportunities/{id}/statut`, `POST /boucle/risks/{id}/statut`) ;
- ouvrir une Investigation (`POST /boucle/situations/{id}/investigations`) ;
- formuler une Hypothèse depuis une Investigation
  (`POST /boucle/investigations/{id}/hypotheses`, `GET /boucle/hypotheses`) et faire
  évoluer son statut (`POST /boucle/hypotheses/{id}/statut`) ;
- enregistrer un Signal global ou depuis une Situation
  (`POST /boucle/signals`, `POST /boucle/situations/{id}/signals`,
  `GET /boucle/signals`), avec empreinte serveur, doublon 409 et lecture
  `SITUATION → SIGNAL` quand une seule Situation est liée ;
- proposer puis trancher une Decision (`POST /boucle/investigations/{id}/decisions`,
  `POST /boucle/decisions/{id}/trancher`) ;
- lancer une Initiative (`POST /boucle/decisions/{id}/initiatives`) ;
- créer, lister et comparer des Scénarios (`POST /boucle/scenarios`,
  `GET /boucle/scenarios`, `POST /boucle/scenarios/comparer`) ; la liste est filtrée
  **directement** par `investigation_id`/`decision_id`, donc un scénario decision-only
  n’apparaît pas sous l’investigation.
- mesurer un Outcome et capitaliser un Learning (`POST /boucle/initiatives/{id}/outcomes`,
  `POST /boucle/outcomes/{id}/learnings`, `POST /boucle/investigations/{id}/learnings`).

Il reste sans API/UI canonique :

- rattacher une Expertise (`Expert`, `ExpertContribution`).

#### Contrat C5a — Expression canonique

- `POST /api/boucle/situations/{sid}/expressions` répond 201 avec l'enveloppe
  `{tenant, objet, type: "EXPRESSION", role: "expression", chaine, historique}`.
- Corps strict `extra="forbid"` : `type_expression` (défaut `IDEE`), `formulation`
  obligatoire, `canal`, `auteur`, `exprime_le`, `claim_ids`, `hypothesis_ids`, `inconnues`,
  `preuves`, `confiance` (0..1), `mode` (défaut `DECLARED`). Le serveur force
  `statut=PROPOSED` ; un `statut` client est refusé en 422.
- Une Situation ne porte qu'une Expression : doublon 409, Situation absente ou hors tenant
  404, secret ou données non sérialisables 400, JSON malformé 422 (validation FastAPI),
  `Idempotency-Key` 501, Postgres indisponible 503.
- `GET /api/boucle/objets/{eid}?historique=true` renvoie la chaîne
  `[SITUATION, EXPRESSION]`.
- L'écriture passe par le port d'exploitation ; `enregistrer_boucle` continue de refuser
  `EXPRESSION`. La lecture est validée par `TYPES_LECTURE`, dérivé de la vraie source
  `_CLASSES_LECTURE` (classes canoniques + `Expression`).
- L'index unique partiel `objet_entreprise_expression_situation_unique` garantit le 1:1
  même hors de l'application. `Situation.expression_id` n'est jamais accepté en entrée :
  le lien inverse est posé uniquement par `creer_expression`.

#### Contrat C5b — Opportunité et Risk canoniques depuis une Expression

- `POST /api/boucle/expressions/{eid}/opportunities` et
  `POST /api/boucle/expressions/{eid}/risks` répondent 201 avec l'enveloppe
  `{tenant, objet, type: "OPPORTUNITY"|"RISK", role: "opportunite"|"risque", chaine,
  historique}`. Les libellés métier `OPPORTUNITE`/`RISQUE` désignent ces deux types
  canoniques ; le type persisté reste `OPPORTUNITY`/`RISK`.
- Corps strict `extra="forbid"` : `titre` obligatoire, `description`, `valeur_potentielle`
  (>= 0), `probabilite` (0..1), `impact` (texte libre), `horizon`, `criteres` (liste),
  `preuves`, `confiance` (0..1), `mode` (défaut `INFERRED`) ; `type_opportunite`,
  `type_risque` et `severite` restent optionnels selon le type. Le serveur force
  `statut=DETECTED` ; `statut`, `id`, `expression_id` et `situation_id` ne sont pas
  acceptés du client (422).
- L'Expression source est verrouillée (`FOR UPDATE`), doit appartenir au tenant et être de
  type `EXPRESSION` (une autre source est refusée en 422) ; absente ou hors tenant 404.
  Elle doit être `PROPOSED` ou `CONFIRMED` : une Expression `REJECTED`/`ARCHIVED` est
  refusée en 409 (`TransitionRefusee`), comme l'action UI. La règle ne s'applique pas aux
  GET/listes. L'objet et le lien inverse `Expression.opportunity_ids` /
  `Expression.risk_ids` sont écrits dans la même transaction : un échec du lien ne laisse
  aucun objet ni lien partiel. Une Expression peut porter plusieurs opportunités et
  plusieurs risques ; il n'existe pas de contrainte d'unicité 1:1.
- `GET /api/boucle/expressions/{eid}/opportunities` et `/risks` listent les objets du
  tenant filtrés par `expression_id`, avec `limite` 1..1000.
- `POST /api/boucle/opportunities/{oid}/statut` et `POST /api/boucle/risks/{rid}/statut`
  répondent 200 avec l'enveloppe de transition. Corps `{statut, motif?, preuves?}` ;
  `maj_le` est posé par le serveur et la version précédente reste dans `historique`. Le
  motif courant est conservé dans `motif` ; `justification` n'est pas modifiée et reste
  vide pour une création depuis une Expression (la traçabilité vient de `expression_id`).
  Transition non autorisée 409, statut inconnu 422, source absente/hors tenant 404,
  identifiant d'un autre type sur la route de statut 422 (choix de contrat), secret ou
  données non sérialisables 400, JSON malformé 422 (validation FastAPI),
  `Idempotency-Key` 501, Postgres indisponible 503.
- Le domaine ne portait pas de table de transitions avant C5b : `TRANSITIONS_OPPORTUNITE`
  et `TRANSITIONS_RISQUE` sont introduites à partir des états canoniques du Domain Model
  (§ 20.3), sans ajouter d'état. Les deux tables sont des copies explicites. Cycle complet :
  `DETECTED → {MATURING, QUALIFIED, REJECTED, DORMANT}`,
  `MATURING → {QUALIFIED, REJECTED, DORMANT}`,
  `QUALIFIED → {INVESTIGATING, SCENARIOS_AVAILABLE, REJECTED, DORMANT}`,
  `INVESTIGATING → {SCENARIOS_AVAILABLE, DECIDED, REJECTED, DORMANT}`,
  `SCENARIOS_AVAILABLE → {DECIDED, REJECTED, DORMANT}`,
  `DECIDED → {INITIATED, REJECTED, DORMANT}`,
  `INITIATED → {MEASURED, REJECTED}`, `MEASURED → {LEARNED}`,
  `DORMANT → {MATURING, REJECTED}`. Les raccourcis `DETECTED → QUALIFIED` et
  `QUALIFIED → SCENARIOS_AVAILABLE` sont donc autorisés ; `LEARNED` et `REJECTED` sont
  terminaux.
- Duplication assumée : la table des transitions existe côté domaine et côté UI
  (`frontend/src/components/boucle/boucleUi.js`). Aucun endpoint ne l'expose et il n'y a
  pas de promesse de source unique ; les deux copies doivent rester synchronisées et un
  test frontend vérifie la table exacte. C'est un risque accepté pour éviter un aller-retour
  réseau et un couplage de démarrage.
- Lecture : `OPPORTUNITY` et `RISK` sont ajoutés à `_CLASSES_LECTURE`, donc à
  `TYPES_LECTURE`, jamais à `TYPES_BOUCLE`. `_source_principale` suit `expression_id`, puis
  `situation_id`, puis `investigation_id`. `GET /api/boucle/objets/{id}?historique=true`
  renvoie `[SITUATION, EXPRESSION, OPPORTUNITY|RISK]` quand le rattachement est l'Expression,
  et `enregistrer_boucle` refuse toujours ces types B.
- UI : actions « Qualifier une opportunité » / « Qualifier un risque » sur une Expression
  `PROPOSED` ou `CONFIRMED` ; formulaire `ModaleTransition` avec titre, description, valeur
  potentielle, probabilité, impact, horizon, critères, preuves, confiance, puis
  `type_opportunite` pour l'opportunité ou `type_risque`/`severite` pour le risque (`mode`
  reste un champ API, défaut `INFERRED`, non exposé dans ce formulaire) ; actions de
  changement de statut avec les seules transitions autorisées, sélection/refetch après
  création et rafraîchissement du lien inverse de l'Expression.
- Limites : qualification manuelle uniquement, aucun pipeline automatique
  Signal/Situation → Expression → Opportunité/Risque, pas de score composite, pas de
  suppression, pas de rattachement automatique à une Investigation, une Decision ou un
  Scenario. `impact` et `criteres` sont des champs optionnels ajoutés aux dataclasses pour
  porter le contrat ; `valeur_potentielle` est revalidée à la persistance et
  `probabilite` reste borné.

#### Contrat C5c — Hypothèse canonique depuis une Investigation

- `POST /api/boucle/investigations/{iid}/hypotheses` répond 201 avec l'enveloppe
  `{tenant, objet, type: "HYPOTHESIS", role: "hypothese", chaine, historique}`.
- Corps strict `extra="forbid"` : `enonce` obligatoire (non vide), `conditions_test`,
  `claim_ids_soutenants`, `claim_ids_opposants`, `preuves`, `confiance` (0..1). Le
  serveur force `statut=OPEN` et `mode=PROPOSED` ; `statut`, `mode`, `id`,
  `investigation_id`, `expert_id` et tout champ inconnu sont refusés en 422. `expert_id`
  reste réservé à C5e tant qu'aucune route EXPERT n'existe.
- L'Investigation est verrouillée (`FOR UPDATE`), doit appartenir au tenant et être de
  type `INVESTIGATION` (une autre source est refusée en 422) ; absente ou hors tenant 404.
  Une Investigation fermée (`CLOSED`, `CLOSE`, `CLOTUREE`, `FERMEE`, `ARCHIVED`,
  `ARCHIVEE`, insensible à la casse) est refusée en 409 avant toute écriture.
  L'Hypothèse et le lien inverse `Investigation.hypothesis_ids` sont écrits dans la même
  transaction : un échec du lien ne laisse aucun objet ni lien partiel. Une Investigation
  peut porter plusieurs Hypothèses.
- `GET /api/boucle/hypotheses` liste les Hypothèses du tenant, filtrables par
  `investigation_id` et `statut`, avec `limite` 1..1000. Une Investigation filtrée
  absente ou hors tenant répond 404 ; un statut inconnu 422.
- `POST /api/boucle/hypotheses/{hid}/statut` répond 200 avec l'enveloppe de transition.
  Corps `{vers, motif?, preuves?}`. Cycle canonique :
  `OPEN → {STRENGTHENED, WEAKENED, REJECTED, CONFIRMED}`,
  `STRENGTHENED → {WEAKENED, REJECTED, CONFIRMED}`,
  `WEAKENED → {STRENGTHENED, REJECTED, CONFIRMED}`, `CONFIRMED` et `REJECTED` terminaux.
  Une transition non autorisée est un 409 ; un statut inconnu, un `CONFIRMED` sans preuve
  (ni nouvelle ni existante) et un identifiant d'un autre type sont des 422 ; une cible
  absente ou hors tenant est un 404 ; un secret ou des données non sérialisables sont un
  400 ; `Idempotency-Key` est refusé en 501 ; Postgres indisponible est un 503.
- Lecture : `HYPOTHESIS` est ajouté à `_CLASSES_LECTURE`, donc à `TYPES_LECTURE`, jamais à
  `TYPES_BOUCLE`. `_source_principale` suit `investigation_id`.
  `GET /api/boucle/objets/{id}?historique=true` renvoie donc
  `[SITUATION, INVESTIGATION, HYPOTHESIS]` quand l'Investigation est elle-même rattachée
  à une Situation. `enregistrer_boucle` refuse toujours `HYPOTHESIS`.
- Duplication assumée de `TRANSITIONS_HYPOTHESIS` côté domaine et de
  `TRANSITIONS_HYPOTHESE` côté UI (`frontend/src/components/boucle/boucleUi.js`), comme
  pour C5b : aucun endpoint n'expose la table, les deux copies doivent rester
  synchronisées et un test frontend vérifie la table exacte.
- UI : action « Formuler une hypothèse » sur une Investigation ouverte, formulaire
  `ModaleTransition` (énoncé, conditions de test, claims soutenants/opposants, preuves,
  confiance), sélection/refetch du parent après création, affichage de la chaîne, action
  « Changer le statut » limitée aux transitions autorisées, et blocage côté UI de
  `CONFIRMED` sans preuve avec un message explicite. `expert_id` reste réservé à C5e et
  n'est pas affiché.
- Limites : formulation manuelle uniquement, aucun pipeline automatique Claims → Hypothesis,
  pas de rattachement aux Experts/Contributions (`expert_id` réservé à C5e), pas de
  suppression.

#### Contrat C5d — Signal canonique

- `POST /api/boucle/signals` et `POST /api/boucle/situations/{sid}/signals` répondent 201
  avec l'enveloppe `{tenant, objet, type: "SIGNAL", role: "signal", chaine, historique}`.
- Corps strict `extra="forbid"` : `libelle` et `source` obligatoires (non vides),
  `type_signal` (défaut `OBSERVATION`, validé contre `TYPES_SIGNAL`), `description`,
  `intensite` (0..1), `detecte_le` (ISO 8601), `situation_ids`, `entite_ids`, `liens`,
  `preuves`, `confiance` (0..1). `statut`, `mode`, `id`, `tenant_id`, `fingerprint` et tout
  champ inconnu sont refusés en 422 ; le serveur force `DETECTED`/`OBSERVED`.
- Empreinte serveur : SHA-256 versionné de `source + type_signal + libelle + detecte_le`,
  textes normalisés NFKC, espaces compactés, casse repliée ; date absente = chaîne vide,
  jamais l'heure serveur. Deux créations identiques (avec la même date ou sans date)
  produisent un 409, pas un 500. La persistance conserve le verrou consultatif et l'index
  non unique `objet_entreprise_signal_fingerprint` comme filet historique.
- Depuis une Situation, `situation_ids` est absent ou exactement `[sid]` (sinon 422) ; la
  Situation est verrouillée et absente/hors tenant répond 404. En global, plusieurs
  Situations sont autorisées, toutes verrouillées et vérifiées. Le lien inverse
  `Situation.signal_ids` est écrit dans la même transaction ; un échec ne laisse aucun
  objet ni lien partiel.
- `GET /api/boucle/signals` liste les Signaux du tenant, filtrés par `situation_id`,
  `type_signal` et `statut`, avec `limite` 1..1000. Une Situation filtrée absente ou hors
  tenant répond 404 ; un type ou un statut inconnu 422.
- Erreurs : 404 Situation absente/hors tenant, 409 doublon d'empreinte (exception dédiée,
  indépendante du message), 422 validation, 400 secret/jeton brut/JSON malformé, 501
  `Idempotency-Key`, 503 Postgres. Le contrôle de jeton strict s'applique au `titre`
  persisté, à l'`id` fourni, au `tenant` brut/normalisé et à toutes les chaînes de
  `donnees` ; la prose `Bearer authentication`/`Bearer implementation` et les composés
  `- / _ .` dont tous les segments sont prose restent acceptés, ainsi que
  `sk-learn-tutorial`. Un secret opaque sans préfixe connu peut passer : détection non
  exhaustive, documentée.
- Lecture : `SIGNAL` est ajouté à `_CLASSES_LECTURE`, donc à `TYPES_LECTURE`, jamais à
  `TYPES_BOUCLE`. `_source_principale` ne suit `situation_ids[0]` que si la liste contient
  exactement un élément ; un Signal multi-Situation ou global est sans chaîne amont.
  `GET /api/boucle/objets/{id}?historique=true` renvoie `[SITUATION, SIGNAL]` dans le cas
  mono-Situation et `[SIGNAL]` sinon. `enregistrer_boucle` refuse toujours `SIGNAL`.
- C5d n'expose **aucune** route de changement de statut : `STATUTS_SIGNAL` reste une table
  de domaine pour la suite, sans `TRANSITIONS_SIGNAL` ni `muer_signal`.
- UI : bouton global « Enregistrer un signal » et action contextuelle depuis une Situation,
  formulaire `ModaleTransition` sans champ statut/mode/id/empreinte, `situation_ids` en CSV
  uniquement en global, sélection/refetch après création, affichage de la chaîne,
  traduction lisible du 409 doublon.
- Limites : création manuelle uniquement, aucune détection automatique, aucune fusion,
  aucun rejet/suppression, aucune promotion automatique vers Expression ou Hypothesis.
  La date serveur posée quand `detecte_le` est absent n'entre pas dans l'empreinte
  initiale : la rejouer explicitement crée un second Signal (piège documenté dans
  [pont-signaux-c5d.md](pont-signaux-c5d.md)).

### 6.4 La maturation et l’expression ne sont pas un pipeline

Les Claims ont une maturité et une calibration. Le passage **phénomène → hypothèse →
expression → opportunité/risque** n’est pas un pipeline canonique : le `Signal` (C5d),
l’Expression, sa qualification manuelle en Opportunity/Risk et la formulation manuelle
d’Hypotheses depuis une Investigation sont canoniques (C5a/C5b/C5c/C5d), mais la maturation
automatique et la dérivation depuis les Claims restent soit dans le legacy Mongo, soit dans
le dossier de raisonnement. La « maturation » au sens de la vision reste à construire
au-dessus des Claims.

### 6.5 La mémoire de transformation n’est pas une capacité produit

Les Learnings, la calibration et la réutilisation existent. Il manque la lecture d’histoire :
« avons-nous déjà vu une situation similaire ? qu’avions-nous décidé ? pourquoi ? quel résultat ?
quels effets secondaires ? ». La mémoire est présente, la transformation n’est pas encore
interrogeable comme un capital.

---

## 7. Priorités

### P0 — rendre la vision vraie sur un premier parcours

1. **Unifier la chaîne** : choisir un parcours live (Situation → Investigation → Decision →
   Initiative → Outcome → Learning) et le brancher sur les objets canoniques, avec un identifiant
   unique et une trace visible dans Travail et Boucle.
2. **Compléter la boucle opérable** : les transitions canoniques, la création d’une
   Situation racine et la comparaison de Scénarios sont exposées dans l’UI ; il reste à
   rattacher l’Expertise et à relier les scénarios de capacité à la décision.
3. **Compléter les objets** : `Signal` est canonique depuis C5d en création/liste/lecture
   (sans cycle de statut), `Expert` et `ExpertContribution` restent à construire ;
   `Hypothesis` est canonique depuis C5c, `Opportunity` et `Risk` depuis C5b ; relier les
   hypothèses aux Experts/Contributions et construire la maturation automatique.
4. **Relier Travail et canonique** : une décision consignée dans Travail doit créer ou mettre à
   jour la `Decision` canonique ; la veille doit produire des `Outcome` et des `Learning`
   canoniques.
5. **Automatiser la mesure** : relier les observations de sources et de Twins aux Outcomes,
   avec attendu/observé et effets secondaires.

### P1 — enrichir l’exploitation

6. **Détection et qualification des opportunités et risques** : au-delà des anomalies, chercher
   ce qui peut mieux fonctionner.
7. **Orchestration des experts** : experts métier, processus, employés, clients, stratégie,
   avec méthodes, preuves, responsabilités et contributions traçables.
8. **Comparaison de scénarios enrichie** : valeur, coût, complexité, risque, dépendances, délai,
   impacts, réversibilité, confiance ; la comparaison canonique existe, il reste à l’intégrer à
   la décision et aux scénarios de capacité.
9. **Aujourd’hui canonique** : surface d’attention alimentée par les objets canoniques, avec
   « Pourquoi Méridian pense cela ».
10. **Actions Flore** : lancer une investigation, comparer des scénarios, interroger les experts,
    reviser un outcome, expliquer une décision passée.
11. **Mémoire de transformation** : recherche par similarité de situations, patterns de décisions,
    effets secondaires récurrents, dépendances sous-estimées.

### P2 — industrialiser

12. Corpus de production labellisé, shadow mode, RLS active, workers supervisés, connecteurs live,
    couverture CBM Go/PHP/Ruby/batch, performance graphes/retrieval.

---

## 8. Conclusion

Méridian a déjà construit un **socle « Comprendre » crédible** : Twins, claims, preuves,
découverte de liens, Atlas, revue humaine, mémoire et raisonnement.

Le manque n’est pas un manque de volume de code. C’est un manque de **continuité** :

- un seul modèle d’objet ;
- une seule chaîne de traçabilité ;
- une boucle réellement opérable ;
- une mémoire de transformation lisible.

Le prochain pas utile n’est pas d’ajouter une nouvelle surface. C’est de choisir **un parcours
de bout en bout** et de le brancher sur la boucle canonique, puis d’étendre les objets et les
experts autour de ce parcours.
