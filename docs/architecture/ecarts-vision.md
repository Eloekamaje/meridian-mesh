# Méridian — écarts avec la vision

> **Photographie :** 6 novembre 2026, HEAD `974cc4e` + corrections documentaires en cours.
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
| **Maturer** | Observation → Hypothèse → Claim → renforcé → mature ; multi-source, historique, fréquence, cohérence temporelle, contradictions, qualité des preuves, expertise, confiance | Maturité des Claims, contradictions conservées, calibration confiance/outcome, spécialiste preuve, score d’attention | `connaissance.py`, `calibration_croyances.py`, `specialiste_preuve.py`, `attention.py` | Pas de pipeline de maturation des phénomènes ; pas de Signal/Observation/Hypothesis canonique ; pas d’agrégation fréquence/temporalité ; promotion encore peu outillée | **Partiel** | P0/P1 |
| **Exprimer** | Formuler une lecture du réel : faits, hypothèses, preuves, incertitudes, confiance ; types opportunité/risque/anomalie/dérive/contradiction/changement/simplification/duplication/comportement | Histoires `Actualités` (legacy) avec récit, « pourquoi maintenant », reste à comprendre, opportunité ; `Situation.expression_id` | `actualites.py`, `Actualites.jsx`, `modele_entreprise.py` | Pas de classe `Expression` ; pas de typologie canonique ; pas de lien canonique Situation → Expression → Opportunity/Risk ; surface alimentée par Mongo legacy | **Partiel / legacy** | P0 |
| **Investiguer** | Investigation structurée : contexte, problème, preuves, timeline, hypothèses concurrentes, experts, contradictions, sous-questions, découvertes, scénarios | Travail/case : hypothèses, options, investigations, décisions, passation, veille ; dossier de raisonnement : croyances, hypothèses, options, critique, gates ; contrats d’investigation et spécialistes | `cases.py`, `dossier_raisonnement.py`, `noyau_raisonnement.py`, `investigation.py`, `specialistes.py` | Investigation canonique créée par le pont C2 depuis Travail ; pas d'objet Hypothesis/Expert/ExpertContribution canonique ; pas d’UI investigation unifiée ; les experts sont des profils/spécialistes, pas des experts métier avec contributions | **Partiel** | P0/P1 |
| **Décider** | Options/scénarios évalués (valeur, coût, complexité, risque, dépendances, délai, impacts client/employé/réglementaire, réversibilité, confiance) ; décision humaine tracée | Décision legacy dans Travail + note de passation ; `Decision` canonique et transitions ; `Scenario` canonique avec comparaison déterministe dans la Boucle ; contrefactuel pur ; scénarios de capacité | `cases.py`, `DecisionPassation.jsx`, `objets_exploitation.py`, `commandes_boucle.py`, `boucle.py`, `contrefactuel.py`, `planification/scenario.py` | Scénarios canoniques et comparaison exposés ; pas de scénarios de capacité reliés à la décision ; la décision ne sélectionne pas encore explicitement un scénario ; critères non homogènes | **Partiel** | P0/P1 |
| **Agir** | Décision → initiative ; étapes, responsables, dépendances, plan, critères de succès, traçabilité | Planification capacité/charge/prévision/budget ; initiatives legacy ; `Initiative` canonique créée par C3 après réponse ; connecteur Jira ; délégations | `application/planification/*`, `initiatives.py`, `legacy.py`, `boucle.py`, `initiatives_auto.py` | Pas d’API/UI canonique de création ou de transition d’Initiative ; planification et boucle non reliées ; Jira live partiel ; Azure DevOps non identifié ; pas de plan d’action canonique | **Partiel** | P0/P1 |
| **Mesurer** | Observer les conséquences réelles, comparer attendu/observé, détecter les effets secondaires | `Outcome` canonique + `/boucle/outcomes` ; worker D observations → Outcome ; note de passation + veille legacy ; calibration ; observations de Twins | `outcomes.py`, `mesure_auto.py`, `cognitif.py`, `cases.py` (veille), `moteur_veille`, `calibration_croyances.py` | Mesure automatique branchée sur observations, mais pas encore sur le chemin veille legacy complet ; dépend d’une Initiative canonique ; deux chemins de mesure non unifiés | **Partiel** | P1 |
| **Apprendre** | Mémoire de transformation : quelles recommandations ont marché, récurrences, effets secondaires, dépendances sous-estimées, valeur | Learning canonique, retrieval, réutilisation mesurée, calibration, consolidation mémoire, propositions depuis dossier | `outcomes.py`, `retrieval_memoire.py`, `apprentissage_raisonnement.py`, `consolidation_memoire.py`, `cognitif.py` | Pas de mémoire de transformation interrogeable ; pas de détection de patterns ; réutilisation non enregistrée automatiquement ; promotion humaine ; pas de lien veille legacy → Learning canonique | **Partiel / embryonnaire** | P1 |

---

## 4. Matrice des objets

| Objet | Modèle | Persistance | Création live | Statut |
|---|---|---|---|---|
| **Signal** | Nom de famille `emergence` uniquement | Aucune | Aucune | **Absent** |
| **Situation candidate** | `modele_entreprise.Situation` | `objet_entreprise` + backfill `migration_canonique` | `POST /boucle/situations` et bouton « Nouvelle situation » dans Boucle ; le live crée encore des `situations` Mongo | **Partiel** |
| **Expression** | Nom de famille `emergence` + `Situation.expression_id` | Aucune | Aucune | **Absent** |
| **Opportunity** | `modele_entreprise.Opportunity` | `objet_entreprise` possible | Aucune instanciation hors tests ; sous-document `opportunite` legacy | **Partiel / absent du live** |
| **Risk** | `modele_entreprise.Risk` | `objet_entreprise` possible | Aucune instanciation hors tests | **Partiel / absent du live** |
| **Investigation** | `modele_entreprise.Investigation` | `objet_entreprise` possible | Créée par `POST /boucle/situations/{id}/investigations` (UI) ou par le pont C2 | **Partiel** |
| **Hypothesis** | `dossier_raisonnement.Hypothese` + tableau `hypotheses` du case | Dossier / Mongo | Via raisonnement ou Travail, pas comme objet canonique | **Partiel** |
| **Expert** | `profils.Profil`, spécialistes cognitifs | Aucune | Aucune | **Partiel** |
| **ExpertContribution** | `Proposition`, contributions de mobilisation | Dossier de raisonnement / réponse | Pas d’objet canonique | **Partiel** |
| **Scenario** | `objets_exploitation.Scenario`, `construction_objets_exploitation.nouveau_scenario` | `objet_entreprise` + liens inverses `scenario_ids` / `scenario_id` | `POST /boucle/scenarios`, `GET /boucle/scenarios`, `POST /boucle/scenarios/comparer` et UI Boucle ; formulaire limité aux métriques principales, comparaison plafonnée à 50 | **Opérationnel, périmètre UI borné** |
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
| **Boucle** | Boucle opérationnelle complète | Lecture des objets canoniques et synthèse ; création d’une Situation racine ; transitions Investigation → Decision → Initiative → Outcome → Learning ; création et comparaison de Scénarios ; création d’Outcome et de Twin | Pas d’Opportunity/Risk opérationnels ; édition et suppression non exposées ; la décision ne sélectionne pas encore un scénario | **Opérationnelle hors Opportunity/Risk** |
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

`Signal`, `Expression`, `Hypothesis`, `Expert` et `ExpertContribution` n’existent pas comme
objets canoniques. `Scenario` est désormais canonique et comparable dans la Boucle.
`Opportunity` et `Risk` existent comme classes et sont testés, mais ne sont pas instanciés par
le chemin de production. La vision fait pourtant de l’Opportunité un objet majeur.

### 6.3 La boucle est opérable, mais pas encore complète

`/boucle/objets` est en lecture et l’UI Boucle expose désormais les écritures canoniques :

- créer une Situation racine (`POST /boucle/situations`, bouton « Nouvelle situation ») ;
- ouvrir une Investigation (`POST /boucle/situations/{id}/investigations`) ;
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

- créer une Expression canonique ;
- rattacher une Expertise.

### 6.4 La maturation et l’expression ne sont pas un pipeline

Les Claims ont une maturité et une calibration. Mais le passage **phénomène → hypothèse →
expression → opportunité/risque** n’est pas un pipeline canonique : il est soit dans le legacy
Mongo, soit dans le dossier de raisonnement. La « maturation » au sens de la vision reste à
construire au-dessus des Claims.

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
3. **Compléter les objets** : `Signal`, `Expression`, `Hypothesis`, `Expert`,
   `ExpertContribution` ; rendre `Opportunity` et `Risk` opérationnels.
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
