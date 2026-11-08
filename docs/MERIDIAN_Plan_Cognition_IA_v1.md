# Méridian — Plan Cognition IA v1

> **Avancement (session 2026-11)** : `A1–A6` ✅ · `B1–B9` ✅ · `C1–C8` ✅ · `D1–D9` ✅ — **plan complet**.
> Livrables : `application/groundedness.py`, `contrat_groundedness.py`, `contrat_question.py`, `sonde_evidence.py`, `beliefs.py`, `abduction.py`, `intention_action.py`, `pipeline_unifie.py` — `postgres/detecteurs_besoins.py`, `detecteur_opportunites.py` (3 signatures), `resolution_besoins.py`, `signatures_besoins.py`, `decision_travail.py`, `journal_episodes.py`, `evenements_requete.py`, `calibration.py`, `metriques_revue.py`, `decroissance_confiance.py`, `revue_graduee.py`, `memoire_unifiee.py`, `projection_twin.py`, `discriminant.py`, `actions_canoniques.py` — objets NEED/UNKNOWN/HYPOTHESIS/Opportunity/BELIEF — endpoints boucle (objets, transition, episodes, calibration, revue/metriques+niveaux, twins/projection) — UI `Boucle.jsx` + carte Revue `Administration.jsx` — `.github/workflows/evals.yml`.
> **Arbitrages tranchés (vision)** : attention = marqueur dict `{raison, depuis}` sur l'objet (claim ou objet_entreprise), action = intention `memoire_prospective` ; `verifier_paris` attache `question_socratique` (discriminant D7) au NEED quand l'attention se pose ; `revue_graduee.appliquer` tourne dans le Gardien (`JUMEAU_REVUE_GRADUEE=0` pour couper) ; `claim.donnees` canonisé pour le marqueur.

> **Date :** 2026-11-07. **Statut :** proposition consolidée, non approuvée.
> **Sources :** revue multi-experts de la couche cognitive/IA (orchestration, connaissance,
> mémoire/retrieval, évaluation, produit/gouvernance), confrontée à
> [etat-actuel.md](architecture/etat-actuel.md), [ecarts-vision.md](architecture/ecarts-vision.md),
> [GAP-ANALYSIS.md](cognitive/GAP-ANALYSIS.md) et au code `backend/meridian/`.
>
> Ce plan répond à une question : **comment faire passer le jumeau de constatateur
> à apprenant** — apprendre les besoins ouverts, raisonner sur preuves, et fermer
> les boucles que la vision promet.

## 0. Verdict de la revue (synthèse)

Le socle épistémique est réel et rare : invariants en SQL, preuve exigée pour `ACCEPTED`,
contradictions conservées, budgets et autorité dans le code, honnêteté documentaire
exceptionnelle. Mais trois écarts structurent tout le reste :

1. **Mécanique réelle en périphérie, discipline de forme au centre.** Le dossier de
   raisonnement vérifie la forme d'un livrable, pas sa validité ; les beliefs sont
   fabriqués par heuristiques avec confiance hardcodée ; les 6 spécialistes sont des
   lentilles déterministes, pas les experts de la vision ; le « harness capacitaire »
   ne gouverne que 6 outils d'orchestration.
2. **Les mesures mesurent la cohérence interne, pas la justesse.** Pilote 2-scénarios
   quasi tautologique (le contrat déterministe satisfait seul la plupart des critères),
   gold set auto-noté par défaut, groundedness des citations jamais vérifiée,
   calibration jamais alimentée par un vrai outcome.
3. **La boucle n'est refermée nulle part.** Learnings mesurés mais non scorés, décisions
   live non canoniques, outcomes `observe=null`, beliefs sans échéance déclenchée,
   mémoires `user` lisibles cross-utilisateur, requêtes utilisateurs qui meurent
   sans laisser de signal.

**Principe du plan** : d'abord ce qui peut nuire, ensuite ce qui mesure la vérité,
ensuite ce qui produit la valeur. Un parcours réel avant la complétude du modèle.

---

## Phase A — Sécurité des données & honnêteté de la mesure

| ID | Tâche | Fichiers clés | Effort | Dépend | Critère de sortie |
|---|---|---|---|---|---|
| A1 | ACL lecture mémoires `user` : `acteur` obligatoire dans `recuperer()`, filtre `scope/scope_id` dans `lister()` ; `consommateur` propagé dans `retrieval_chat` | `postgres/retrieval_memoire.py:348-496`, `application/retrieval_chat.py`, `postgres/memoire_durable.py` | M | — | Test : user A du tenant T ne lit aucune entrée `scope=user` de B |
| A2 | Échapper `<`/`>` dans `_contexte_pour_prompt` ; purger les tool results injectés avant persistence session | `llm/orchestrateur.py:450-472` (pattern `agent.py:729-732`) | S | — | Injection `</donnee>` ne casse pas le délimiteur ni ne survit au tour suivant |
| A3 | Allowlist domaines `lire_page` + politique d'égress LLM explicite | `deepseek.py:83-93`, `.env.*.example` | S | — | `JUMEAU_DOMAINES_WEB` appliqué ; données envoyées au provider documentées |
| A4 | **Groundedness** : extraire les citations (`RE_CITATION`, `RE_CITATION_SOURCE`, `RE_CITATION_PIECE`) et vérifier existence + tenant + statut en base | `connaissance.py`, `agent.py:567-669`, sortie `flore.py`/`orchestrateur.py` | M | — | Test négatif : `#L999` inexistant est flagué, jamais silencieux |
| A5 | Gold branché sur le vrai planificateur + contrôle négatif + gate CI | `evaluation_gold.py:585` (supprimer défaut `cas.attendu()`), `.github/workflows/evals.yml` | M | — | Gold échoue sur plan incorrect volontaire ; CI bloque régression ≥2 cas |
| A6 | Scoring pilote sur la sortie modèle seule | `evals/run_deepseek.py:420`, `run_benchmark.py:673-699` | S | — | PASS impossible via les seules clés du contrat |

**Gate A** : A1–A5 en CI.

## Phase B — Parcours canonique + registre des besoins

Parcours choisi : *duplication/redondance applicative* — détectable sur le graphe
existant (claims `REALISE_CAPACITE` partagés), aucune donnée nouvelle requise.

| ID | Tâche | Effort | Dépend | Critère de sortie |
|---|---|---|---|---|
| B1 | API écriture canonique : `POST /boucle/objets` (Situation, Investigation, Decision, Initiative) + `POST /objets/{id}/transition` | M | — | Chaîne complète via API, tenant-scopée, transitions invalides refusées |
| B2 | Détecteur `duplication` → `Opportunity` (PROPOSED, claims cités) | M | B1 | Fixture : 2 apps / 1 capacité → 1 Opportunity prouvée |
| B3 | Décision Travail → `Decision` canonique (dual-write via `JUMEAU_TRAVAIL_*`) | M | B1 | Même identifiant d'épisode Mongo↔Postgres |
| B4 | Outils jumeau sous `Harness` : `proposer_connaissance` + écritures Travail `lecture_seule=False` + `approuves` exercé | L | — | `OutilNonApprouve` sur écriture non approuvée, audit tracé |
| B5 | UI Boucle : création/transition des 4 objets + Opportunity | M | B1, B2 | Parcours complet en UI |
| **B6** | **Objets NEED / UNKNOWN / HYPOTHESIS** : types enregistrés, dataclasses, transitions, triggers (`refutable_par` obligatoire, `rival_ids ≥ 1`) | M | B1 | NEED sans `refutable_par` rejeté en base ; HYPOTHESIS sans rivale rejetée |
| **B7** | **3 détecteurs de besoins** : `question_non_tranchee` (→ UNKNOWN + Intention), `contournement` (→ HYPOTHESIS×n → NEED), `recurrence` (→ NEED) — déterministes, branchés Gardien | M | B6 | Toute non-réponse Flore laisse un UNKNOWN vivant ; un contournement produit ≥2 rivales |
| **B8** | **Sonde de preuve pré-raisonnement** : lexical+graphe+mémoire borné (~200 ms) avant `executer_raisonne`, verdict trivial/clair/incertain ; court-circuit déterministe des triviales | M | B1 | Une question lookup ne consomme aucun token LLM ; la sonde alimente le contrat de preuve |
| **B9** | **Contrat de preuve de question** : remplacer `qualifier` (mots-clés FR) par « quel artefact trancherait », calculé depuis la sonde | M | B8 | Une question en anglais/avec faute n'est plus classée muette |

**Gate B** : démo reproductible — Opportunity-doublon → Investigation → Decision (depuis
Travail) → Initiative → Outcome, un seul identifiant ; ET un NEED né d'une vraie
question Flore non tranchée.

## Phase C — Refermer les boucles

| ID | Tâche | Effort | Dépend | Critère de sortie |
|---|---|---|---|---|
| C1 | `taux_succes` learnings dans le score retrieval ; PROPOSED < ACCEPTED | S | — | Test de ranking |
| C2 | `Validation.echeance` → résolution réelle ; Beliefs persistés `claim_id` + audit | M | — | Croyance expirée → demande de résolution |
| C3 | Instrumentation revue humaine (taux, délai, divergence relecteurs) | M | — | `/boucle/revue/metriques` en Administration |
| C4 | Premier outcome réel → calibration + IC binomial | M | B, C2 | Rapport refuse n<10 |
| **C5** | **Poids de signatures** : `signature_besoin` — taux confirmé/réfuté par signature module la confiance des NEED suivants | M | B7, C1 | « contournement+récurrence » a un taux mesuré appliqué au score |
| **C6** | **Intentions ↔ besoins bouclés** : Intention de vérification résolue → NEED `QUALIFIE→CORROBORE` ; expirée → remonte en attention | M | B7 | Un NEED se corrobore ou se dégrade seul à l'échéance |
| **C7** | **Post-vérification de réponse** : la réponse est un brouillon jusqu'à groundedness (consomme A4) ; faits non vérifiables marqués incertains | S-M | A4 | Réponse avec fait non vérifiable publiée `confiance_marquee` |
| **C8** | **Épilogue de requête** : chaque requête écrit l'événement (sondes, preuves, confiance, non-résolu) → UNKNOWN / NEED / calibration | M | B7 | Le registre des besoins épistémiques se remplit sans intervention |

## Phase D — Refontes conceptuelles (progressives)

| ID | Refonte | Effort | Dépend |
|---|---|---|---|
| D1 | Journal d'épisodes append-only (`evenement`) — la chaîne devient une vue | L | B1 |
| D2 | Érosion de confiance + réfutation active des ACCEPTED | M | — |
| D3 | Revue graduée par risque (human-on-the-loop), révocable | M | C3 |
| D4 | Flore opérateur : intentions action → objets canoniques via Harness | L | B1, B4 |
| D5 | Mémoire 4 couches (Connaissance / Épisodes / Recettes / Documents) | M | D1 |
| D6 | Opportunités graphe étendues (concentration risque, dette vs usage) | M | B2 |
| D7 | Abduction + preuve discriminante : spécialiste `abduction`, retrieval `discriminant`, question socratique à valeur maximale | L | B6, B7 |
| D8 | Twin comme projection des claims | L | D1 |
| D9 | Fusion `/demander` + `/analyser` : une machine, deux profils d'effort | L | B8, C7 |

## Chemin critique

```
A4 → B1 → B6 → B7 → C6     (le jumeau devient apprenant)
A5/B8 en parallèle          (la mesure devient honnête, le coût chute)
```

## Exclusions assumées

- `SIGNAL`/`EXPRESSION`/`SCENARIO` canoniques : créés quand un parcours les appelle.
- pgvector/ANN : seulement quand >400 chunks/tenant est la norme.
- Spécialistes LLM : via D7 seulement, si les templates B7 montrent leurs limites mesurées.
- Migration Mongo big-bang : dual-write B3 rend la migration progressive.
- Experts métier/processus/client de la vision : impossible tant que les sources
  correspondantes n'existent pas — un expert sans données est un prompt sans fondement.

## Risques

| Risque | Mitigation |
|---|---|
| A4 flague trop → bruit | Mode `shadow` (compte sans afficher) avant activation |
| B3 dual-write diverge | Étendre `parite_mongo.py` aux objets boucle |
| D1 journal + `objet_entreprise` = deux vérités | Journal = source, objet = projection ; pas de coexistence |
| Détecteurs B7 → avalanches de NEED | Seuil + dédup par signature/sujet ; quota hebdo par détecteur |
| B9 casse la classification existante | `qualifier` reste en observateur 1 release : comparer, pas remplacer à froid |

---

# Annexe 1 — Objets NEED / UNKNOWN / HYPOTHESIS

## NEED — besoin ouvert (famille `emergence`, nouveau type)

Un besoin ouvert = un écart observé entre un état réel et un état requis, non encore
satisfait ni expliqué. Distinct de `CLAIM` (« ceci est vrai »), `UNKNOWN` (« on ne sait
pas »), `OPPORTUNITY` (« ceci pourrait être mieux »). Un NEED mûrit en OPPORTUNITY ou
RISK — jamais directement en décision.

```python
@dataclass
class Need(ObjetEntreprise):
    famille: str = "emergence"
    type: str = "NEED"
    titre: str = ""
    porteur: str = ""            # twin_id / equipe / parcours / profil — qui manque
    exigence: str = ""           # ce qui est requis (capacité, info, délai, fiabilité)
    ecart: str = ""              # l'écart observé, formulé
    statut: str = "OUVERT"
    signature: str = ""          # patron de détection (contournement, recurrence…)
    refutable_par: str = ""      # OBLIGATOIRE : observation qui tuerait ce besoin
    situation_id: str | None = None
    hypothese_ids: list[str] = field(default_factory=list)
    unknown_id: str | None = None
    opportunity_id: str | None = None
    risk_id: str | None = None
    intention_id: str | None = None   # vérification datée (mémoire prospective)
    twin_ids: list[str] = field(default_factory=list)
    claim_ids: list[str] = field(default_factory=list)
```

**Transitions** (`TRANSITIONS_NEED`, validées Python + trigger) :

```
OUVERT    → QUALIFIE   (porteur + exigence + ecart + refutable_par + ≥1 claim)
QUALIFIE  → CORROBORE  (Intention résolue succès | revue humaine | 2 sources indépendantes)
CORROBORE → ADRESSE    (Decision/Initiative liée)
OUVERT|QUALIFIE → REFUTE (observation refutable_par | verdict humain)
*         → PERIME     (valide_jusqua dépassée sans transition)
REFUTE|PERIME → OUVERT (version+1, motif obligatoire ; historique via journal D1)
```

**Trigger** (pattern `claim_accepte_exige_preuve`) :

```sql
CREATE OR REPLACE FUNCTION need_exige_refutation() RETURNS trigger AS $$
BEGIN
    IF NEW.type = 'NEED' AND NEW.mode IN ('PROPOSED','CONFIRMED')
       AND NULLIF(TRIM(NEW.donnees->>'refutable_par'), '') IS NULL THEN
        RAISE EXCEPTION 'NEED % : PROPOSED/CONFIRMED sans refutable_par', NEW.id;
    END IF;
    IF NEW.type = 'NEED' AND NEW.donnees->>'statut' IN ('QUALIFIE','CORROBORE')
       AND NULLIF(TRIM(NEW.donnees->>'porteur'), '') IS NULL THEN
        RAISE EXCEPTION 'NEED % : statut avancé sans porteur', NEW.id;
    END IF;
    RETURN NEW;
END $$ LANGUAGE plpgsql;
```

## UNKNOWN — besoin épistémique (famille `connaissance`, type déjà réservé)

```python
@dataclass
class Unknown(ObjetEntreprise):
    famille: str = "connaissance"
    type: str = "UNKNOWN"
    question: str = ""           # ce qu'on ne sait pas
    bloque: str = ""             # ce que ça empêche de conclure
    statut: str = "OUVERT"       # OUVERT | EN_COURS | RESOLU | ABANDONNE
    origine: str = ""            # flore | revue | investigation | gardien
    tentatives: list[str] = field(default_factory=list)
    resolution_claim_id: str | None = None
```

Règle de vie : tout UNKNOWN est créé **avec une Intention de résolution**
(`memoire_prospective`, scope `tenant`). Échéance passée sans résolution → remonte
dans le fil d'attention, jamais enfoui.

## HYPOTHESIS — rivale (famille `investigation`, type déjà réservé)

```python
@dataclass
class Hypothesis(ObjetEntreprise):
    famille: str = "investigation"
    type: str = "HYPOTHESIS"
    enonce: str = ""
    statut: str = "EMISE"        # EMISE | TESTEE | RETENUE | REFUTEE
    rival_ids: list[str]         # ≥1 obligatoire pour TESTEE/RETENUE
    preuve_discriminante: str = ""   # observation qui sépare des rivales
    situation_id: str | None = None
    need_id: str | None = None
```

Une hypothèse sans rivale n'est pas une hypothèse, c'est une conclusion déguisée.

## Détecteurs de besoins (déterministes — B7)

| Signature | Déclencheur | Produit |
|---|---|---|
| `question_non_tranchee` | réponse Flore « non observé » / non concluante | UNKNOWN + Intention |
| `contournement` | `observed` ≠ `declared` sur même interface | HYPOTHESIS×n → NEED |
| `recurrence` | ≥3 situations même entité / fenêtre | NEED signature=recurrence |
| `intention_expiree` | Intention passée `expire`/`annule` | NEED (engagement échoué) |
| `contradiction_ouverte` | contradiction sans verdict > N jours | UNKNOWN |
| `capacite_inutilisee` | `REALISE_CAPACITE` confirmé sans usage observé | NEED bidirectionnel |
| `echec_recette` | Learning `echec` réutilisé | NEED (besoin mal compris) |

Chaque NEED porte sa `signature` : le taux confirmé/réfuté par signature devient un
Learning qui module la confiance des NEED suivants (C5) — **le jumeau apprend quels
signaux annoncent un vrai besoin.**

---

# Annexe 2 — Pipeline cognitif de requête repensé

## Le pipeline actuel (tracé dans `legacy.py:generer_reponse_flore`)

```
question → contrat_securite (regex) → question_pedagogique → enveloppe
 → rate limit → hors-périmètre (nom twin en substring)
 → orchestrateur.executer_raisonne (Strands, 6 outils)
      └─ noyau_raisonnement : qualifier/cadrer/planifier par mots-clés FR,
         injecté en texte dans le prompt, jamais révisé
      └─ mobiliser_jumeaux → agent jumeau (~25 outils)
 → repli : intention_selection (regex) → scénarios → AURORA_FALLBACK
 → contrat_action → contrat_preuve (≥3 puces → disclaimer regex)
```

**Failles** : raisonne avant de regarder ; qualification par mots-clés fragile ;
routeur d'intention caché dans le repli ; refus périmètre par substring ; contrat de
preuve qui mesure la forme ; `confiance=0.6` hardcodée dans le dossier ; la requête
meurt après la réponse (aucun signal); coût uniforme quelle que soit l'incertitude ;
deux pipelines cognitifs (`/demander` vs `/analyser`) non confrontés.

## Le pipeline cible — même boucle que l'agentique de référence, rebranchée

```
RECEVOIR   injection couche 1/2 (garder ; jamais seule défense)
SONDER     sonde bornée AVANT raisonnement : lexical + graphe + mémoire (~200 ms)
           → verdict : trivial | clair | incertain              [B8]
ROUTER     par incertitude, pas par intention :
             trivial   → réponse déterministe, 0 token LLM
             clair     → boucle agent bornée
             incertain → interprétations rivales → question discriminante | sonde
CONTRAT    « quel artefact trancherait cette question » calculé depuis la sonde,
           pas depuis les mots de la phrase                      [B9]
BOUCLER    état explicite {connu, manquant, prochaine_sonde_moins_chère}
           replanifié à chaque observation ; arrêt gain marginal < coût
VÉRIFIER   réponse = brouillon → groundedness → faits non vérifiables marqués [C7]
APPRENDRE  événement complet : question, sondes, preuves, confiance, non-résolu
           → UNKNOWN si non tranché, NEED si récurrence, prédiction datée     [C8]
```

## Mapping sur les briques existantes

| Brique agentique | Existant Méridian | Écart |
|---|---|---|
| Sonde pré-raisonnement | `enrichir_pack` (retrieval borné) | Arrive trop tard / pas pour toutes les requêtes |
| État externe vivant | `dossier_raisonnement` | Contient des croyances synthétiques, pas des faits vérifiés + état de sonde |
| Parallélisme | `OrchestrateurSpecialistes` | Orphelin (aucun appelant frontend) ; pas branché dans le chemin requête |
| Replanning | boucle outils Strands | Le plan `planifier` n'est jamais révisé par les observations |
| Vérification avant publication | `contrat_preuve` | Compte les puces (forme), ne vérifie pas les faits (A4) |
| Trace qui réalimente | `outil_audit`, épisodique | Append-only passif ; rien ne le relit pour apprendre |
| Épilogue apprenant | — | **Absent** : la requête s'évapore |

Le pipeline cible n'invente presque rien : il **rebranche des briques existantes dans
le bon ordre avec les bons contenus**.

## Métriques du nouveau pipeline

- % requêtes triviales servies sans token LLM (coût, latence)
- taux de citations vérifiées par réponse (groundedness réel)
- UNKNOWN créés par semaine / résolus (besoins épistémiques captés)
- NEED par signature et taux de confirmation (apprentissage mesurable)
- questions discriminantes posées vs clarifications génériques
