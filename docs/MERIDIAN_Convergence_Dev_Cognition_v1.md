# Méridian — Convergence Dev / Cognition v1

> **Date :** 2026-11. **Statut :** analyse de conciliation, non approuvée.
> **Avancement :** phase 1 faite (renommage `CONJECTURE`, migration 0006) ;
> phase 2 faite (unification `OPPORTUNITY` — détecteur en `DETECTED`,
> `signature`+`claim_ids` vaut trace, `RISK` ouvert dans `enregistrer_boucle`,
> `concentration_risque`/`dette_vs_usage` retypés `RISK.CONTINUITE`/`TECHNIQUE`,
> migration 0007) ; phase 3 faite (`journal_episodes` branché dans
> `enregistrer_objets_exploitation`, DECISION orpheline interdite — la chaîne
> d'épisode est créée, migration 0008, validateur B délégué pour
> OPPORTUNITY/RISK, `actions_canoniques` façade de `commandes_boucle`) ; phase 4
> faite (`POST /objets` restreint aux types épistémiques et SITUATION —
> `statut`/`mode`/`id` serveur refusés en 422, `_CLASSES` réduit au registre de
> création générique, transition générique sous verrou `FOR UPDATE` ; canal
> d'attention unifié — `domain/attention.score` lit `donnees.attention`,
> `GET /attention` fusionne les intentions échues, `PanneauActions` affiche le
> drapeau, les drapeaux transitoires sont effacés par les réécritures
> canoniques, migration 0009 indexe le store ; `revue_graduee` étendue aux
> propositions workflow — HYPOTHESIS/SCENARIO/EXPERT_CONTRIBUTION proposés,
> classés et marqués sans toucher `mode`/`statut`). Les 8 collisions basculent
> en XFAIL dans `test_collisions_monde` ; phase 5 faite (registre `SWEEPS`
> ordonné `{nom, flag, fn}` dans `gardien.veiller` — dépendance 4→5 via
> `ctx["poids_signatures"]`, isolation try/except et rapport par sweep
> conservés — migration 0009 index `attention`, migration 0010 index
> `signature`/`sujet_detection`).
> Reste différé : l'émission outbox de `decision_travail` est faite pour les
> cases liés (§6 — `_pont_apres_case` rend l'événement produit ; le miroir
> direct `_miroir_decision_canonique` n'écrit plus que pour les cases sans
> Situation liée, qu'ADR-0008 exclut de l'outbox : lever cette exclusion reste
> le chantier qui supprimera le second producteur). Le régime SCENARIO est
> fusionné : `enregistrer_boucle` délègue la validation à
> `objets_exploitation._valider_pour_persistance` (registre unique, `par_id`
> préserve les liens intra-lot) et contrôle `STATUTS_SCENARIO` à l'écriture —
> les deux chemins de persistance restent distincts par sémantique de lot, mais
> un seul validateur fait foi.
> **Périmètre :** l'arbre fusionné du commit `3c82f21` (branche `jumeau-p4-confort`),
> qui contient côte à côte le modèle d'exploitation canonique (« monde dev », ~146
> commits) et la couche épistémique du plan Cognition IA A→D (« monde cognition »,
> ~30 tâches). Chaque affirmation est adossée à `fichier:ligne`.
> **Vision de référence :** système d'intelligence vivante — *découvrir, mûrir,
> investiguer, décider, agir, mesurer, apprendre* — gouverné par la preuve et
> l'autorité humaine.

---

## 0. Synthèse exécutive

Les deux mondes écrivent dans **la même table** `objet_entreprise`
(`adapters/outbound/postgres/schema.sql:543-561`) avec **le même espace de
`type`**, mais selon **deux régimes d'invariants différents** et **deux chemins
de persistance distincts** (`postgres/boucle.enregistrer_boucle` vs
`postgres/objets_exploitation.enregistrer_objets_exploitation`). La coexistence
est viable aujourd'hui parce que les statuts sont portés par `donnees` (jsonb,
non contraint en SQL) et que les lectures HTTP passent en `as_dict=True` (lignes
brutes). Trois collisions sont déjà latentes :

1. **HYPOTHESIS désigne deux classes et deux cycles de vie incompatibles** dans
   le même `type` de la même table (§2.1) — avec une branche morte de fusion
   dans `_source_principale` (`postgres/boucle.py:1399-1403`).
2. **OPPORTUNITY** est écrite par deux producteurs dont les vocabulaires de
   statut et de type ne se recouvrent pas : les opportunités du détecteur
   (`statut="PROPOSED"`) sont **immuables et invisibles** pour le moteur de
   transitions typées (§2.2).
3. **Le journal d'épisodes D1 ne voit que `enregistrer_boucle`** : toutes les
   écritures des routes typées (Signal, Expression, Hypothesis workflow, Expert,
   Contribution, Scenario, Opportunity/Risk) sont absentes de `/episodes` (§5.4).

Aucune des deux moitiés n'est jetable : le monde dev apporte la gouvernance
transactionnelle, le contrat public et l'UI ; le monde cognition apporte
l'auto-évaluation (détecteurs, paris datés, calibration, érosion) qui réalise
« apprendre ». Le plan de conciliation (§7) est ordonné : renommage CONJECTURE →
unification OPPORTUNITY → unification des chemins d'écriture → modèle d'autorité
unique → canal d'attention unique → discipline de migrations.

---

## 1. Cartographie des deux mondes

### 1.1 Monde « dev » — modèle d'exploitation + industrialisation

| Couche | Fichier | Contenu |
|---|---|---|
| Domaine | `domain/objets_exploitation.py` (759 l.) | Signal, Expression, Hypothesis (workflow), Expert, ExpertContribution, Scenario + tables de statuts/transitions (`:97-207`) |
| Domaine | `domain/construction_objets_exploitation.py` (793 l.) | Fabriques `nouveau_*` / `muer_*` chargées paresseusement (`objets_exploitation.py:747-759`) |
| Application | `application/commandes_boucle.py` (1345 l.) | Orchestrateur transactionnel : source verrouillée (`FOR UPDATE`), transition pure, écriture create-only, liens inverses, relecture de chaîne (`_source` `:171-213`, `_persister` `:229-236`, `_relire` `:250-259`) |
| Port | `ports/boucle.py` (110 l.) | `BoucleStore` : boundary hexagonale injectée par HTTP |
| Persistance | `postgres/objets_exploitation.py` (1067 l.) | Validation des liens, dédup empreinte Signal (verrou consultatif `:318-327`), liens inverses set/append (`:504-540`), provenance `_pont` (`:75-95`, `:794-795`, `:823-840`), historique `_historique` plafonné à 50 (`:800-807`) |
| Persistance | `postgres/boucle.py` (1609 l.) | Dépôt « boucle » P1 : `enregistrer_boucle`, `lire_boucle`, `fusionner_donnees`, transitions canoniques, journal d'épisodes |
| Schéma | `postgres/migrations/0001-0005*.sql` | Index numérotés idempotents : liens situation/investigation/decision/expert/expression, unicité Expression↔Situation (0004), index hypothesis (0005) |
| Ponts | `application/pont_travail.py` (470 l.), `pont_canonique.py` (1641 l.), `pont_securite.py` (334 l.), `mapping_legacy.py` (205 l.), `tenant_context.py` (54 l.) | Outbox Mongo→PG signée HMAC, mapping legacy→canonique, contexte tenant |
| Mesures | `application/mesure_auto.py` (830 l.) + `mongo/mesure_auto.py` + `worker/mesure_auto_worker.py` | Observation → événement outbox → Outcome canonique, jamais de Learning |
| Initiatives | `application/initiatives_auto.py` (54 l.) | Proposition `en_attente` pour situation `priorite=haute` |
| HTTP | `adapters/inbound/http/boucle.py` (2054 l.) | ~40 routes typées + routes génériques + lecture cognition |
| UI | `frontend/src/components/boucle/` | `PanneauActions.jsx`, `ModaleTransition.jsx`, `ComparaisonScenarios.jsx`, `TraceCanonique.jsx`, `boucleUi.js` (tables de transitions dupliquées — risque assumé, cf. `objets_exploitation.py:134-135`, `:166-167`) |

**Invariants porteurs (« règles Bearer »)** — l'autorité humaine est codée en
dur dans le moteur de transitions :

- statut/mode/id initiaux **serveur** : refus 422 de tout champ client
  (`commandes_boucle.py:439-444`, `:780-792`, `:998-1046`, `:693-700`) ;
- `trancher_decision` exige `acteur` + `choix` + `decide_le`
  (`postgres/boucle.py:390-396`, `:1040-1043`) ;
- Opportunity/Risk exigent une **trace humaine** : `expression_id` ou
  `auteur + justification` (`postgres/objets_exploitation.py:276-284`) ;
- Learning n'accepte jamais `statut`/`mode` client (`_forcer_learning`,
  `commandes_boucle.py:358-362`) ;
- `Idempotency-Key` non accepté silencieusement : 501 tant que le stockage
  d'idempotence n'est pas branché (`http/boucle.py:14-16`).

### 1.2 Monde « cognition » — couche épistémique (plan A→D)

| Couche | Fichier | Contenu |
|---|---|---|
| Domaine | `domain/modele_entreprise.py` (1197 l.) | Socle `ObjetEntreprise` + Unknown (`:624-652`), Belief (`:656-718`), Need (`:863-944`), Hypothesis épistémique (`:980-1007`), Opportunity/Risk (`:751-848`), Decision/Initiative/Outcome/Learning (`:1010-1141`) |
| Domaine | `domain/epistemie.py` (283 l.) | QuestionFrame, Presupposition, BeliefRevision, EvidenceNeed, SourcePlan |
| Domaine | `domain/attention.py` (457 l.) | Scoring déterministe 0-100 explicable, empreinte SHA de dédup |
| Application | `sonde_evidence.py`, `contrat_question.py`, `groundedness.py`, `contrat_groundedness.py`, `beliefs.py`, `abduction.py`, `intention_action.py`, `pipeline_unifie.py`, `contrat_action.py`, `evaluation_gold.py` | Modules **purs** : sonde pré-raisonnement (trivial/clair/incertain), contrat de preuve, vérification de citations, érosion beliefs (demi-vie 90 j), hypothèses rivales, intentions d'action, machine unifiée /demander+/analyser, garde « proposer avant d'exécuter », jeu d'or |
| Persistance | `postgres/detecteurs_besoins.py` (614 l.) | 3 signatures : `question_non_tranchee` → UNKNOWN, `contournement` → 3 HYPOTHESIS rivales EMISE + NEED, `recurrence` → NEED ; quotas, dédup `signature+sujet_detection`, ids déterministes sha256 |
| Persistance | `postgres/detecteur_opportunites.py` (704 l.) | 3 signatures : `duplication`, `concentration_risque`, `dette_vs_usage` → OPPORTUNITY `statut=PROPOSED`, `type_opportunite` hors taxonomie dev |
| Persistance | `postgres/resolution_besoins.py` (637 l.) | Paris datés : à l'échéance de l'intention, ré-évalue le signal → corroboré/résolu ou `donnees.attention` ; écrit la prédiction `prediction_calibration` (C4) |
| Persistance | `postgres/signatures_besoins.py` (436 l.) | Taux de confirmation par signature + IC Wilson → poids `[POIDS_MIN, POIDS_MAX]` ; écrit des LEARNING via `entreprise_depot.enregistrer_objet` |
| Persistance | `postgres/calibration.py` (883 l.) | `prediction_calibration` : prédictions datées résolues, Brier + Wilson (`score_brier`), jamais de nombre sans `n` |
| Persistance | `postgres/decroissance_confiance.py` (445 l.) | Érosion beliefs → `donnees.attention` ; claims ACCEPTED périmés → intention ; réfutation postérieure → claim CONTESTED via `depot.reviser` |
| Persistance | `postgres/revue_graduee.py` (698 l.) | AUTO_VISIBLE (auto-accept révocable J+30) / ATTENTION / BLOQUANT, tracé dans `outil_audit` |
| Persistance | `postgres/discriminant.py` (321 l.) | Preuves discriminantes entre hypothèses rivales + question socratique (via `application/abduction`) |
| Persistance | `postgres/decision_travail.py` (246 l.) | Recopie B3 : décision Travail → DECISION canonique tranchée |
| Persistance | `postgres/actions_canoniques.py` (220 l.) | 5 callables Harness = transitions B1 (sans verrous ni orchestrateur) |
| Persistance | `postgres/journal_episodes.py` (142 l.), `evenements_requete.py` (159 l.), `memoire_unifiee.py` (420 l.), `projection_twin.py` (403 l.), `metriques_revue.py` (352 l.) | Journal append-only `evenement_episode`, épilogue de requête, façade mémoire 4 couches, twin = projection calculée, métriques de revue |
| Schéma | `schema.sql:593-627` | Triggers `need_exige_refutation` (NEED PROPOSED/CONFIRMED exige `refutable_par`, QUALIFIE/CORROBORE exige `porteur`) et `belief_exige_appui` (RAISONNEMENT exige ≥1 claim) ; `evenement_episode` immuable (`:665-683`) |

### 1.3 Le point de friction structurel : deux écrivains, une table

| | `enregistrer_boucle` (cognition + B1) | `enregistrer_objets_exploitation` (dev, « B ») |
|---|---|---|
| Fichier | `postgres/boucle.py:1251-1313` | `postgres/objets_exploitation.py:848-976` |
| Types acceptés | `TYPES_BOUCLE + TYPES_COMPLEMENTAIRES` = SITUATION, INVESTIGATION, DECISION, INITIATIVE, OUTCOME, LEARNING, SCENARIO, UNKNOWN, HYPOTHESIS, NEED, OPPORTUNITY, BELIEF (`:69-73`) | `TYPES_EXPLOITATION` = SIGNAL, EXPRESSION, HYPOTHESIS, EXPERT, EXPERT_CONTRIBUTION, SCENARIO, OPPORTUNITY, RISK (`domaine:97-106`) |
| Validation | `_valider_pour_persistance` `:984-1099` : chaîne source, décision tranchée, outcome mesuré, NEED `refutable_par`/porteur, HYPOTHESIS **rivale** (TESTEE/RETENUE), BELIEF appui | `_valider_pour_persistance` `:287-474` : résolution de liens typés, empreinte Signal, **trace humaine** Opportunity/Risk, contribution↔hypothèse↔investigation |
| Sémantique d'écriture | upsert avec merge de `donnees` + protection `_CHAMPS_INVERSES_LIES` (`:107-111`, `:1185-1206`) | upsert ordonné avec diff de liens inverses + verrouillage global trié (`:900-971`) |
| Journal D1 | oui (`_consigner_evenement` `:1224-1248`) | **non** — `journal_episodes` jamais importé |
| Provenance | aucune | `_pont.origine="exploitation"` posée sur objets **et** parents touchés (`:794-795`, `:835-838`) |

**Intersection des types écrits par les deux chemins :** SCENARIO, HYPOTHESIS,
OPPORTUNITY — exactement les trois objets à sémantique divergente.

---

## 2. Collisions sémantiques

### 2.1 HYPOTHESIS — deux classes, un seul `type`, deux cycles de vie

| | Épistémique (cognition) | Workflow (dev) |
|---|---|---|
| Classe | `modele_entreprise.Hypothesis` (`:980-1007`), sous-classée `postgres/boucle.Hypothesis` (`:499-514`) | `objets_exploitation.Hypothesis` (`:571-600`) |
| Statuts | `EMISE, TESTEE, RETENUE, REFUTEE` (`modele:109`) | `OPEN, STRENGTHENED, WEAKENED, REJECTED, CONFIRMED` (`objets_exploitation:123`) |
| Transitions | aucune table (transitions libres) | `TRANSITIONS_HYPOTHESIS` (`:124-130`) : OPEN→{S,W,R,C}, CONFIRMED/REJECTED terminaux |
| Champs clés | `rival_ids`, `preuve_discriminante`, `situation_id`, `need_id` — **une hypothèse sans rivale est une conclusion déguisée** : TESTEE/RETENUE exige ≥1 rivale (`:1004-1007`) | `investigation_id` **obligatoire** (`:590`), `conditions_test`, `claim_ids_soutenants/opposants`, `expert_id`, `motif` — CONFIRMED exige ≥1 preuve (`:599-600`) |
| Producteur | `detecteurs_besoins._detecter_contournement` (`:412-425`) — 3 rivales EMISE croisées, liées par `Need.hypothese_ids` ; `POST /objets` générique (`http/boucle.py:957-995` → `_CLASSES["HYPOTHESIS"]` épistémique, préfixe `hyp-`) | `commandes_boucle.creer_hypothese` (`:682-720`) — préfixe `hypothesis-`, investigation verrouillée et ouverte, statut `OPEN`/mode `PROPOSED` forcés |
| Validation à l'écriture | rivale exigée si TESTEE/RETENUE (`postgres/boucle.py:1079-1086`) ; `investigation_id` jamais exigé | `investigation_id` doit résoudre une INVESTIGATION (`postgres/objets_exploitation.py:339-346`) |
| Lecture | `_CLASSES["HYPOTHESIS"]=Hypothesis` (`postgres/boucle.py:589`) | `_CLASSES_LECTURE["HYPOTHESIS"]=HypothesisExploitation` (`postgres/boucle.py:603`) et `_CLASSES["HYPOTHESIS"]=domaine.Hypothesis` (`postgres/objets_exploitation.py:62`) |

**Conséquences concrètes du partage du `type` :**

- `lister_hypotheses` (`commandes_boucle.py:723-744`) filtre `type='HYPOTHESIS'`
  dans toute la table → les hypothèses épistémiques EMISE remontent dans
  `GET /boucle/hypotheses` (non filtré) avec des `donnees` hétérogènes.
- `changer_statut_hypothese` sur une hypothèse épistémique : `actuel="EMISE"` ∉
  `TRANSITIONS_HYPOTHESIS` → **409 permanent** (`:765-768`).
- `creer_contribution_hypothese` sur une épistémique : `investigation_id` absent
  → 409 « hypothèse incomplète » (`:936-939`).
- `creer_scenario` avec `hypothesis_ids` épistémiques : parent `None` ≠
  `investigation_reference` → 409 (`commandes_boucle.py:1272-1281`) ; même règle
  rejouée en persistance (`postgres/objets_exploitation.py:434-449`).
- **Lecture typée** : `_objet_depuis_ligne` construit la classe **workflow** pour
  tout `type='HYPOTHESIS'` (`postgres/boucle.py:1316-1340`,
  `postgres/objets_exploitation.py:753-777`). Une ligne épistémique (statut
  EMISE, sans `investigation_id`) lève `ObjetsExploitationInvalide` dès
  `as_dict=False` — `_CLASSES_LECTURE` se prétend « l'unique source de
  `TYPES_LECTURE` pour valider toute lecture canonique » (`:596-598`) mais ne
  peut pas reconstruire les objets qu'elle déclare lire.
- **Artefact de fusion** : `_source_principale` a **deux** branches
  `type_objet == "HYPOTHESIS"` — `:1363-1364` (`investigation_id`, sémantique
  dev) puis `:1399-1403` (`situation_id`/`need_id`, sémantique cognition)
  **inaccessible** : la seconde est du code mort. La chaîne canonique d'une
  hypothèse épistémique s'arrête donc à elle-même.

### 2.2 OPPORTUNITY — détecteur de graphe vs objet lié à une Expression

| | Détecteur (cognition) | Route typée (dev) |
|---|---|---|
| Écrit via | `boucle.Opportunity` → `enregistrer_boucle` (`detecteur_opportunites.py:488-495`, `:553-555`) | `creer_opportunite` → `enregistrer_objets` (`commandes_boucle.py:505-522`) |
| `statut` initial | `"PROPOSED"` — « une opportunité reste une proposition tant qu'aucun humain ne la qualifie » (`:19-22`, `:490`) | `"DETECTED"` forcé serveur (`:425`, `:520`) |
| `type_opportunite` | `DUPLICATION`, `CONCENTRATION_RISQUE`, `DETTE_CRITIQUE` (`:596`, `:632`, `:680`) | 10 valeurs : AUTOMATION…CONSOLIDATION (`domaine:147-151`) — **aucune commune** |
| Preuve | `claim_ids` cités + `signature` + `sujet_detection` | `expression_id` (lien obligatoire à une Expression qualifiable) |
| Mode | `INFERRED` (`postgres/boucle.py:95`) | `INFERRED` (`objets_exploitation.py:56`) — cohérent |

**Blocages effectifs :**

1. `STATUTS_OPPORTUNITE` (`domaine:152-155`) ne contient pas `PROPOSED` →
   `changer_statut_opportunite` répond 409 à toute cible (`TRANSITIONS_OPPORTUNITE.get("PROPOSED")=()`).
   Une opportunité de détecteur est **gelée** pour l'API typée.
2. `_exiger_trace_humaine` (`postgres/objets_exploitation.py:276-284`) exige
   `expression_id` ou `auteur+justification` : **réécrire** une opportunité de
   détecteur via le chemin B échouerait. Seul `enregistrer_boucle` — qui n'a
   aucune validation OPPORTUNITY — les accepte : deux régimes d'invariants pour
   le même type.
3. `lister_opportunites` (`commandes_boucle.py:555-562`) exige `expression_id` →
   les opportunités de détecteur sont invisibles à `GET
   /boucle/expressions/{id}/opportunities` ; elles n'apparaissent que dans
   `GET /boucle/objets?type=OPPORTUNITY` et `GET /boucle/objets/{id}`.
4. Asymétrie RISK : `detecteur_opportunites` note que `enregistrer_boucle`
   refuserait un type `RISK` (`:22-23` — RISK absent de `TYPES_COMPLEMENTAIRES`,
   `postgres/boucle.py:73`) : `concentration_risque` et `dette_vs_usage` sont
   donc stockés comme OPPORTUNITY alors que leur contenu est un risque.

### 2.3 Signal (dev) vs UNKNOWN (cognition) — recouvrement réel mais disjoint

- **Signal** (`domaine:485-529`) : *événement observé* rattaché à une `source`
  et à des `situation_ids`, dédup par empreinte SHA-256 serveur
  (`empreinte_signal` `:226-244`, verrou consultatif + requête
  `postgres/objets_exploitation.py:266-273`), cycle DETECTED→…→ARCHIVED.
- **UNKNOWN** (`modele:624-652`) : *question épistémique* qui bloque une
  conclusion — `question`, `bloque`, `tentatives`, `resolution_claim_id`, cycle
  OUVERT/EN_COURS/RESOLU/ABANDONNE, intention de résolution en
  `memoire_prospective` (`detecteurs_besoins.py:268-291`).

L'overlap est conceptuel, pas structural : un Signal dit « quelque chose a
changé/est anormal », un UNKNOWN dit « nous ne savons pas ». Le Signal peut
alimenter l'UNKNOWN (détecteur `question_non_tranchee` crée des UNKNOWN depuis
les réponses Flore non concluantes — `detecteurs_besoins.py:294-351`), mais ils
ne sont pas substituables : le Signal est un fait daté d'ingestion, l'UNKNOWN
porte une intention de résolution datée. **Pas de collision de type** — le
recouvrement se joue au niveau du fil d'attention (§5.5).

### 2.4 NEED vs Expression/Situation — frontière émergence, pas collision

`Need` (`modele:863-944`) : écart réel↔requis, `refutable_par` **obligatoire à
la construction** (`:893`) et renforcé par trigger `need_exige_refutation`
(`schema.sql:593-606`), cycle OUVERT→QUALIFIE→CORROBORE→ADRESSE (+REFUTE/PERIME,
réouverture motif+version `:919-944`). `transiter_need` est la seule action
épistémique exposée par `POST /objets/{id}/transition` (`http/boucle.py:941`).

Il n'y a pas de doublon fonctionnel : l'Expression dev est une formulation
humaine rattachée à une Situation ; le NEED est un écart détecté ou déclaré,
réfutable, jugeable à échéance. Les deux convergent dans `emergence` mais
n'occupent pas le même slot — le NEED est la *mûrisseuse* qui débouche en
OPPORTUNITY/RISK (`modele:867-870`), l'Expression est la *trace humaine* qui
justifie la création d'OPPORTUNITY/RISK côté dev.

---

## 3. Chevauchements fonctionnels

### 3.1 `POST /objets` + `/transition` génériques vs routes typées

Les endpoints génériques vivent **dans le même router** que les routes typées
(`http/boucle.py:76`, préfixe `/boucle`) :

- `POST /objets` (`:957-995`) : types créables = SITUATION, INVESTIGATION,
  DECISION, INITIATIVE, UNKNOWN, HYPOTHESIS, NEED (`:929-932`). Instanciation
  directe `_CLASSES[type]` + `enregistrer_boucle`, id serveur préfixé
  (`sit-`, `inv-`, `dec-`, `ini-`, `unk-`, `hyp-`, `need-` — `:924-928`).
- `POST /objets/{id}/transition` (`:998-1032`) : 6 actions
  (`_ACTIONS_TRANSITION` `:935-942`) — `transiter_need` est la seule action
  épistémique.

**Différences de gouvernance avec les routes typées :**

| | Générique | Typée |
|---|---|---|
| Verrou source | `lire_boucle` sans `for_update` (`:1025`) | `FOR UPDATE` systématique (`commandes_boucle._source` `:171-213`) |
| Statut initial | libre dans `donnees` (validation domaine seule) | forcé serveur, champ client refusé 422 |
| Transaction | `enregistrer_boucle` seul | `depot.transaction(conn)` + liens inverses + relecture `ResultatTransition{objet,chaine,historique}` |
| Idempotence | create-only implicite (id serveur aléatoire) | 409 explicites (`ObjetExistant`, `DoublonExploitation`, `DoublonEmpreinteSignal`) |
| Couverture | 7 types dont HYPOTHESIS épistémique | 8 types exploit + chaîne P1 complète |

**Chevauchement direct** : `POST /objets type=SITUATION` et `POST
/boucle/situations` créent le même type par deux chemins aux garanties
différentes ; `POST /objets type=HYPOTHESIS` crée l'épistémique `hyp-` pendant
que `POST /investigations/{id}/hypotheses` crée la workflow `hypothesis-` —
**même `type`, deux préfixes d'id, deux sémantiques** (§2.1).

`actions_canoniques.py` (D4) réutilise le même niveau d'abstraction que
`/objets` (`boucle.*` directs + `enregistrer_boucle`, avec contexte RLS
`:39-50`) — il expose donc la branche *faible* (sans verrous ni orchestrateur)
au Harness, alors que les routes typées incarnent la gouvernance.

### 3.2 `decision_travail` vs `pont_travail`/`pont_canonique` — double écriture de DECISION

Deux producteurs peuvent écrire une `DECISION` issue du même case Travail :

- **`decision_travail`** (cognition B3, appelé de `http/cases.py:353-361`) :
  synchrone, à la décision du case. Chaîne via `boucle.proposer_decision` +
  `trancher_decision` quand une INVESTIGATION canonique est trouvée
  (`:206-219`) ; **sinon écriture directe** `entreprise_depot.enregistrer_objet`
  d'une DECISION tranchée **sans `investigation_id`** (`:221-246`) —
  contournement assumé de `_valider_pour_persistance` (`postgres/boucle.py:996-999`
  exige la résolution du lien).
- **`pont_travail`/`pont_canonique`** (dev C1) : asynchrone, événements outbox
  Mongo signés HMAC (`application/pont_canonique.py`, `mongo/pont_canonique.py`),
  appliqués par `postgres/pont_canonique.appliquer` avec hash de contenu
  `donnees._pont.hash`, `source_maj_le` arbitre de rejeu, fusion champ par champ.

**Risque de doublon** : les identifiants divergent (`decision-*` aléatoire vs
ids déterministes du pont) → le même verdict humain peut exister deux fois dans
`objet_entreprise`. De plus la DECISION orpheline de `decision_travail` est
**empoisonnée en réécriture** : `modele.Decision` exige `investigation_id`
(`:1030-1032` — `_identifiant_lien` obligatoire), donc toute repasse par
`enregistrer_boucle` ou `_objet_depuis_ligne(as_dict=False)` échoue ; son
`investigation_id` « à renseigner plus tard » (`:14-15`) ne pourra jamais être
fusionné par le chemin canonique.

### 3.3 `mesure_auto` (dev) vs boucle Outcome/Learning (cognition)

- `mesure_auto` produit des **OUTCOME canoniques** via événement outbox signé —
  observation normalisée, cible `initiative_id`/`decision_id`, jamais de
  Learning automatique (`application/mesure_auto.py` docstring ; worker
  `mesure_auto_worker.py`).
- Cognition mesure autre chose : `calibration.resoudre` juge les prédictions
  datées contre les outcomes réels (Brier), `resolution_besoins` juge les paris
  datés, `signatures_besoins.capitaliser_mesures` écrit des **LEARNING**
  factuels directement via `entreprise_depot.enregistrer_objet` — en
  **contournant l'invariant domaine** « un Learning exige un Outcome ou une
  Investigation » (`modele:1138-1141`), assumé dans le docstring
  (`signatures_besoins.py:225-229`).

Recouvrement : deux notions d'« apprendre » — le Learning d'initiative (dev,
lié à outcome mesuré, promotion humaine forcée) et le Learning de signature
(cognition, mesure de détecteur, `donnees.origine` implicite). Même `type`,
deux provenances ; le second n'entre jamais dans la chaîne canonique.

### 3.4 Règles « Bearer » dev vs `contrat_action`/`intention_action`/`revue_graduee`

Deux étages complémentaires d'autorité :

- **Dev = invariants d'exécution** (serveur-side, au moment de l'écriture) :
  statuts forcés, `acteur`/`choix`/`decide_le` sur décision tranchée, trace
  humaine Opportunity/Risk, Learning non auto-promu (§1.1).
- **Cognition = gouverne d'exécution** (avant que l'action ne parte) :
  `contrat_action` — une action à effet de bord ne doit jamais être présentée
  comme exécutée sans confirmation (`application/contrat_action.py`) ;
  `intention_action` — manifeste approuvé exigé avant toute écriture
  (`application/intention_action.py`) ; `revue_graduee` — routage AUTO_VISIBLE /
  ATTENTION / BLOQUANT, auto-accept révocable J+30 audité (`postgres/revue_graduee.py`).

Pas de contradiction mais un **angle mort** : `revue_graduee` ne classe que les
claims PROPOSED et les « propositions » `objet_entreprise` portant
`donnees.type_claim` — les objets workflow dev (HYPOTHESIS mode=PROPOSED,
contributions PROPOSED, scénarios PROPOSED) ne passent pas par la revue graduée.

### 3.5 `gardien.py` — tous les sweeps des deux mondes

`veiller()` (`adapters/outbound/llm/gardien.py:478-669`) est devenu le
séquenceur de tout le système autonome. Ordre réel, chaque étape isolée par
try/except (fail-soft, rejouée à la passe suivante) :

| Ordre | Étape | Monde | Réf. |
|---|---|---|---|
| 1 | `_synchroniser_graphe` — upsert direct + planification outbox (`JUMEAU_GRAPH_PROJECTION`) | dev | `:488`, `:348-411` |
| 2 | Ingestion Git + `decouverte_interfaces.executer` + `impacts_situations` + `notifications_impacts` | dev | `:489-526` |
| 3 | `pulls_runtime.tirer_et_publier` (OTLP) | dev | `:529-534` |
| 4 | `signatures_besoins.mesurer` — poids C5, LEARNING par signature | cognition | `:536-547` |
| 5 | `detecteurs_besoins.detecter` — B7, avec `poids` de l'étape 4 | cognition | `:548-556` |
| 6 | `resolution_besoins.verifier_paris` — C6, jugement à échéance | cognition | `:557-565` |
| 7 | `calibration.resoudre` — C4, prédictions échues | cognition | `:566-574` |
| 8 | `decroissance_confiance.evaluer` — D2, érosion + réfutation | cognition | `:575-584` |
| 9 | `revue_graduee.appliquer` — D3, `JUMEAU_REVUE_GRADUEE=0` pour couper | cognition | `:585-594` |
| 10 | `detecteur_opportunites.detecter` — B2/D6 | cognition | `:595-602` |
| 11 | Ingestion, `comprendre.clore_sans_preuve`, situations, `registre.projeter`, fiche vivante Flore, `consolider`, `recoupement.verifier`, ancrage Jira, `poignee.serrer` | mixte | `:603-668` |
| — | `publier` → `initiatives_auto.proposer` (seuil `haute`) | dev | `:294-310` |
| — | `veiller_source` (Confluence/Jira/ServiceNow/Datadog) | dev | `:442-475` |

La dépendance 4→5 est explicite (`poids_signatures` injecté) : l'ordre est
signifiant. Le reste est indépendant — mais `veiller` est désormais une
god-function de ~200 lignes dont chaque insertion change le comportement système.

### 3.6 Provenance `_pont` — interaction subtile

Le chemin B estampille `donnees._pont = {"origine": "exploitation"}` sur chaque
création et, pire, **pose `exploitation` sur tout parent A touché qui n'a pas
déjà un `_pont` structuré** (`postgres/objets_exploitation.py:75-95`,
`:823-840`). Un parent créé par le pont C1 (`origine` autre) est préservé ; un
parent canonique « nu » devient marqué `exploitation` — la provenance C1 et la
provenance B partagent le même champ sans convention d'agrégation.

---

## 4. Ce qui n'existe que d'un côté — et pourquoi c'est précieux

**Uniquement dev :**

- **Moteur de transitions gouvernées** : verrous `FOR UPDATE`, ordre de
  verrouillage trié, `ResultatTransition` (objet+chaîne+historique), codes
  404/409/422/501 disciplinés — c'est l'incarnation « autorité humaine ».
- **Contrat public typé + UI** : `ReponseTransition`, `ModaleTransition`,
  `PanneauActions`, `ComparaisonScenarios` — le seul chemin où un humain mûrit
  réellement un objet.
- **Pont Mongo↔PG** : outbox HMAC + fencing token + idempotence par hash —
  l'industrialisation que la couche cognition n'a pas.
- **Migrations numérotées** 0001-0005 idempotentes (cognition a grossi
  `schema.sql` en ligne : triggers, `evenement_episode`, colonnes C4 — sans
  révision).
- **Signal** : ingestion dédupliquée par empreinte — rien d'équivalent côté
  cognition pour les faits d'observation.

**Uniquement cognition :**

- **NEED/UNKNOWN/BELIEF + invariants en base** (`refutable_par`, appui de
  claims) — le registre de ce que le système sait ne pas savoir.
- **Détecteurs déterministes** (besoins, opportunités) avec quotas, dédup
  `signature+sujet_detection`, ids stables — « découvrir » autonome et rejouable.
- **Boucle d'apprentissage fermée** : signatures→poids→confiance des besoins
  futurs→LEARNING ; paris datés→calibration Brier ; érosion de confiance→
  réfutation active — c'est « mesurer, apprendre ».
- **Épisodes & épilogue** (`evenement_episode`, `evenement_requete`) : la
  trace causale append-only.
- **Projection du twin** : l'état déduit des claims, pas une ligne divergente.
- **Groundedness / sonde / contrat_question / pipeline_unifie** : la
  vérification de citation et le routage d'effort avant raisonnement.
- **Revue graduée** : human-on-the-loop révocable, le seul mécanisme qui laisse
  passer la machine sans renoncer à l'autorité.

---

## 5. Risques cachés

1. **Double écriture, sémantiques divergentes** (§1.3) : `enregistrer_boucle`
   accepte HYPOTHESIS/OPPORTUNITY/SCENARIO avec les invariants épistémiques ;
   `enregistrer_objets_exploitation` impose les invariants workflow. Un même
   `type` peut donc exister dans la table sous deux formes incompatibles —
   aucune contrainte SQL ne le voit (`type` est texte libre,
   `schema.sql:549-552`).
2. **`_CLASSES_LECTURE` peut construire la mauvaise classe** : tout
   `type='HYPOTHESIS'` est reconstruit en workflow
   (`postgres/boucle.py:599-608`, `:1316-1340`) ; une ligne épistémique lève
   `ObjetsExploitationInvalide` en `as_dict=False`. Latent tant que toutes les
   lectures HTTP restent en `as_dict=True` — un piège pour tout futur lecteur
   typé.
3. **Branche morte `_source_principale`** (`postgres/boucle.py:1399-1403`) :
   la chaîne des hypothèses épistémiques ne remonte jamais à
   `situation_id`/`need_id` — symptôme du merge.
4. **`/episodes` aveugle aux écritures typées** : `journal_episodes` n'est
   appelé que par `enregistrer_boucle` (`:1224-1248`) — Signals, Expressions,
   Hypothesis workflow, contributions, scénarios créés par les routes typées
   sont invisibles au journal D1 présenté comme « la chaîne devient une vue
   sur les événements ».
5. **Deux canaux attention** : (a) `donnees.attention` `{raison, depuis}` +
   intentions `memoire_prospective` échues (cognition : `resolution_besoins:23`,
   `decroissance_confiance:55-80`) ; (b) fil Mongo `db.situations` + scoring
   `domain/attention.py` + `PanneauActions` (dev/legacy). Un besoin qui « remonte
   en attention » côté cognition n'apparaît pas dans le panneau d'actions de
   l'UI.
6. **DECISION orpheline** (§3.2) : écrite sans `investigation_id`, irréparable
   par le chemin canonique ; risque de doublon DECISION case↔canonique entre
   `decision_travail` (synchrone) et le pont C1 (outbox).
7. **Opportunités détectées gelées** (§2.2) : `statut=PROPOSED` hors cycle,
   invisibles aux listes typées, réécriture refusée par `_exiger_trace_humaine`.
8. **Provenance `_pont` partagée sans arbitrage** (§3.6) : B peut estampiller
   `exploitation` sur des parents A — deux producteurs de provenance, un champ.
9. **Revue graduée aveugle aux objets dev** (§3.4) : HYPOTHESIS/contributions
   PROPOSED échappent au routage AUTO_VISIBLE/ATTENTION/BLOQUANT.
10. **`POST /objets` accepte `mode` client** : un `mode=CONFIRMED` ou
    `statut=CONFIRMED` dans `donnees` traverse la validation domaine pour
    HYPOTHESIS épistémique (pas de table de transitions) — contourne la
    discipline « statut initial serveur » des routes typées.
11. **SCENARIO écrit par les deux chemins** : `enregistrer_boucle` (création
    canonique B1, validation `:1000-1039`) et `enregistrer_objets_exploitation`
    (validation `:404-449`) — règles quasi identiques mais divergentes
    (l'ordre des vérifications diffère ; `_verifier_conflits_liens` n'existe
    que côté B).
12. **LEARNING hors chaîne** (§3.3) : `signatures_besoins` écrit des LEARNING
    sans OUTCOME/INVESTIGATION lié — la chaîne `_source_principale`
    (`postgres/boucle.py:1387-1393`) les rend racines isolées.

---

## 6. Décisions de conciliation recommandées

Justification commune : la vision exige *un* cycle « découvrir → mûrir →
investiguer → décider → agir → mesurer → apprendre » ; deux objets qui portent
le même nom sans partager le cycle ne peuvent ni mûrir ni apprendre ensemble.

| Zone | Décision | Justification |
|---|---|---|
| HYPOTHESIS (§2.1) | **Renommer l'épistémique `CONJECTURE`** (garder `HYPOTHESIS` au workflow) | L'API publique, la migration 0005, l'UI (`boucleUi.js`) et le préfixe `hypothesis-` sont déjà livrés pour le workflow ; l'épistémique n'a que des producteurs internes (détecteur, `/objets`). « Une conjecture devient hypothèse quand l'investigation l'adopte » : EMISE→adoption→OPEN. Chemin de graduation documenté `CONJECTURE.(EMISE\|TESTEE\|RETENUE)` → `HYPOTHESIS.OPEN` |
| OPPORTUNITY (§2.2) | **Merger les cycles** : détecteur écrit `statut=DETECTED` + `signature`/`sujet_detection`/`claim_ids` ; `type_opportunite` étendu aux 3 valeurs détecteur ; `_exiger_trace_humaine` amendé — `signature+claim_ids` vaut trace | Un détecteur *détecte* : `DETECTED` est la vérité sémantique et remet l'objet dans `TRANSITIONS_OPPORTUNITE`. La qualification humaine (MATURING→QUALIFIED) reste le verrou d'autorité — cohérent avec « gouverné par la preuve et l'autorité humaine » |
| RISK détecteur | **Ouvrir l'écriture RISK dans `enregistrer_boucle`** (validation symétrique) et typer `concentration_risque`/`dette_vs_usage` comme RISK | L'asymétrie actuelle stocke des risques comme des opportunités (`detecteur_opportunites.py:22-23`) — la taxonomie doit dire la vérité sur la nature de l'objet |
| `POST /objets` vs typé (§3.1) | **Garder les deux, restreindre** : `/objets` = types épistémiques (UNKNOWN, NEED, CONJECTURE) + SITUATION ; INVESTIGATION/DECISION/INITIATIVE réservés aux routes typées | `/objets` est le canal bas-niveau de la couche cognitive ; les routes typées incarnent la gouvernance. Forcer `statut`/`mode` serveur aussi en générique |
| DECISION Travail (§3.2) | **Un seul producteur : l'outbox C1** ; `decision_travail` émet l'événement signé au lieu d'écrire ; interdire la DECISION orpheline (créer l'INVESTIGATION d'épisode ou différer via intention) | Idempotence par hash + id déterministe tuent le doublon ; une décision sans parent est un trou de causalité, pas une souplesse |
| mesure_auto vs cognition (§3.3) | **Garder les deux, relier** : `mesure_auto` reste le producteur d'OUTCOME ; LEARNING de signature porte `donnees.origine="signature"` + lien vers l'épisode | Deux natures d'apprentissage complémentaires ; l'invariant « Learning relié » est préservé en liant au besoin/à l'investigation de l'épisode |
| Autorité (§3.4) | **Unifier en « modèle d'autorité »** : `actions_canoniques` route via `commandes_boucle` (verrous + ReponseTransition + épisodes) ; `revue_graduee` étendue aux propositions `objet_entreprise` workflow | Aujourd'hui le Harness utilise le chemin *faible* ; l'autorité doit être unique, quel que soit l'appelant — humain, agent ou détecteur |
| gardien.py (§3.5) | **Extraire un registre de sweeps** `{nom, ordre, fn, feature_flag}` ; garder l'isolation try/except et le rapport par sweep | `veiller` agrège 11+ responsabilités ; un registre rend l'ordre explicite (4→5), permet le test unitaire et l'activation par tenant |
| Attention (§5.5) | **Un seul canal** : `donnees.attention` + intentions `memoire_prospective` = store canonique ; le fil Mongo `situations` et `PanneauActions` deviennent projections ; `domain/attention.py` fournit le scoring | Deux canaux = deux vérités sur « ce qui demande l'attention » ; la vision veut *un* fil gouverné |
| Épisodes (§5.4) | **Brancher `journal_episodes` dans `enregistrer_objets_exploitation`** | Un journal qui ne voit que la moitié des écritures n'est pas une source de vérité causale |
| Provenance `_pont` (§3.6) | **Convention unique** : `_pont.origine ∈ {legacy_pont, exploitation, detecteur, decision_travail}` + `writers[]` cumulatif | La provenance sert à arbitrer les fusions C1 ; deux auteurs non déclarés = arbitrage aveugle |
| Migrations | **Numéroter** les ajouts cognition (triggers, `evenement_episode`, colonnes C4, index `signature`/`sujet_detection`/`attention`) en 0006+ | La discipline dev est la seule qui rend le schéma rejouable en production |

---

## 7. Plan de migration ordonné

### Phase 0 — Caractérisation (préalable, ~1 semaine)

- Tests de caractérisation épinglant les deux sémantiques HYPOTHESIS
  (`test_hypotheses_boucle`, `test_detecteurs_besoins`, `test_modele_entreprise`)
  et le comportement actuel de `/objets` (`test_boucle_routes`).
- Inventaire des lignes existantes : compter `type='HYPOTHESIS'` par vocabulaire
  de statut (`donnees->>'statut'`), `type='OPPORTUNITY'` par `signature`.
- **Risque :** révéler des données hybrides déjà produites en démo.

### Phase 1 — Renommage CONJECTURE (~2 semaines) — risque moyen

Touchpoints exacts :

- `domain/modele_entreprise.py` : renommer classe + `STATUTS_HYPOTHESIS` →
  `STATUTS_CONJECTURE` (`:109`), type dans `TYPES_PAR_FAMILLE["investigation"]`
  (`:87`) ; docstring `Need.hypothese_ids` → accepter les deux espaces d'id.
- `postgres/boucle.py` : `_CLASSES`, `_CLASSES_LECTURE` (corriger le mapping
  croisé), `TYPES_COMPLEMENTAIRES`, `_valider_pour_persistance` (`:1079-1086`),
  supprimer la branche morte `_source_principale` (`:1399-1403`) et y router
  CONJECTURE, `_ORDRE`, `_MODE_DEFAUT`.
- `http/boucle.py` : `_TYPES_CREATION`, `_PREFIXES_ID` (`hyp-`→`conj-`),
  docstrings.
- Producteurs : `detecteurs_besoins` (classe `boucle.Hypothesis`→`Conjecture`,
  ids `hyp-`→`conj-`, `Need.hypothese_ids`), `abduction` (clés compatibles),
  `discriminant`, `resolution_besoins`.
- Trigger `need_exige_refutation` : **inchangé** (type NEED seul).
- Migration `0006` : `UPDATE objet_entreprise SET type='CONJECTURE' WHERE
  type='HYPOTHESIS' AND donnees->>'statut' IN ('EMISE','TESTEE','RETENUE','REFUTEE')`
  + mapping inverse jamais.
- Tests à renommer/adapter : `test_detecteurs_besoins`, `test_discriminant`,
  `test_resolution_besoins`, `test_modele_entreprise`, `test_abduction`,
  `test_boucle_*` (attendus `type`).
- **Risque :** tout consommateur externe de `type='HYPOTHESIS'` épistémique
  (fils, exports, Neo4j si projeté) ; les ids `hyp-*` existants restent valides
  (l'id n'est pas le type).

### Phase 2 — Unification OPPORTUNITY (~2 semaines) — risque moyen

- Étendre `TYPES_OPPORTUNITE` (+DUPLICATION, CONCENTRATION_RISQUE, DETTE_CRITIQUE
  — ou les renommer en valeurs canoniques) et admettre `signature`/`claim_ids`
  comme provenance dans `_exiger_trace_humaine`.
- Migration `0007` : `donnees.statut 'PROPOSED'→'DETECTED'` pour les OPPORTUNITY
  à `signature` ; ajouter RISK à `TYPES_COMPLEMENTAIRES` + validation symétrique.
- `detecteur_opportunites` écrit `DETECTED` et produit RISK pour ses signatures
  de risque.
- **Risque :** l'UI `boucleUi.js` doit apprendre à afficher la provenance
  `detecteur` sans `expression_id`.

### Phase 3 — Unification des chemins d'écriture (~3 semaines) — risque élevé

- `journal_episodes.consigner` dans `enregistrer_objets_exploitation` (même
  savepoint, jamais bloquant).
- `decision_travail` → émission d'événement outbox ; interdiction de DECISION
  orpheline (migration des existantes : rattacher à l'investigation d'épisode ou
  marquer `donnees.parent_manquant` et interdire leur mutation hors lien).
- Registre de validation unique : `enregistrer_boucle` délègue les types
  d'exploitation à la même `_valider_pour_persistance` — fin du double régime.
- `actions_canoniques` → façade sur `commandes_boucle` (verrous, codes).
- **Risque :** ordre de verrouillage différent entre les deux persisteurs —
  unifier sur le verrouillage global trié de B.

### Phase 4 — Autorité et attention unifiées (~2 semaines)

- `revue_graduee` étendue aux propositions workflow ; doc « modèle d'autorité »
  unique (règles Bearer + contrat_action + manifestes + revue).
- Canal attention unique : `PanneauActions` lit `donnees.attention` + intentions
  échues ; `domain/attention.py` fournit le score ; le fil Mongo `situations`
  reste une projection de compat.

### Phase 5 — Hygiène (~1 semaine, continu)

- Registre de sweeps du gardien ; migrations numérotées 0006+ pour tout ajout
  cognition ; index `(donnees->>'signature')`, `(donnees->>'sujet_detection')`,
  `(donnees->'attention')`.

---

## 8. Index des références critiques

| Collision | Preuve fichier:ligne |
|---|---|
| HYPOTHESIS épistémique | `domain/modele_entreprise.py:109`, `:980-1007` |
| HYPOTHESIS workflow | `domain/objets_exploitation.py:123-130`, `:571-600` |
| Mapping croisé lecture | `postgres/boucle.py:40`, `:581-609` |
| Branche morte | `postgres/boucle.py:1363-1364` vs `:1399-1403` |
| Deux validations HYPOTHESIS | `postgres/boucle.py:1079-1086` vs `postgres/objets_exploitation.py:339-346` |
| OPPORTUNITY statut PROPOSED | `postgres/detecteur_opportunites.py:488-491` vs `domain/objets_exploitation.py:152-155` |
| Trace humaine | `postgres/objets_exploitation.py:276-284` |
| RISK refusé en boucle | `postgres/detecteur_opportunites.py:22-23`, `postgres/boucle.py:73` |
| `/objets` générique | `http/boucle.py:924-1032` |
| Routes typées | `http/boucle.py:1311-2054`, `application/commandes_boucle.py` |
| DECISION orpheline | `postgres/decision_travail.py:221-246` |
| Épisodes partiels | `postgres/boucle.py:1224-1248` (absent de `postgres/objets_exploitation.py`) |
| Deux canaux attention | `postgres/resolution_besoins.py:23`, `postgres/decroissance_confiance.py:55-80` vs `domain/attention.py`, `application/initiatives_auto.py` |
| Sweeps du gardien | `adapters/outbound/llm/gardien.py:488-602` |
| Triggers cognition | `adapters/outbound/postgres/schema.sql:593-627` |
| `_pont` provenance | `postgres/objets_exploitation.py:75-95`, `:794-795`, `:823-840` |
| Migrations dev | `postgres/migrations/0001-0005*.sql` |
