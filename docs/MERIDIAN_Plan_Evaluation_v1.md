# Méridian — Plan d'évaluation v1

> **Date :** 2026-11-07. **Statut :** proposition, non approuvée.
> **Compagnon :** [MERIDIAN_Plan_Cognition_IA_v1.md](MERIDIAN_Plan_Cognition_IA_v1.md) —
> ce plan instrumente les tâches A4–A6, B6–B9, C5–C8.
>
> Question du plan : **comment prouver que Méridian dit vrai, ne fuit pas,
> apprend — et vaut son coût.**

## 0. Diagnostic (pourquoi le dispositif actuel ne suffit pas)

| Faille | Preuve |
|---|---|
| Le pilote mesure la plomberie | critères notés par sous-chaîne sur `contrat_JSON + prose` ; les clés du contrat satisfont seules la plupart des `expected_terms` — un PASS = HTTP 200 + prose non vide |
| Le gold se note lui-même | `evaluation_gold.evaluer()` sans sélectionneur utilise `cas.attendu()` → toujours 10/10, jamais relié au vrai planificateur |
| Groundedness absente | `must_cite_preuve` teste le format `#L\d+` ; une citation fabriquée fluide passe — le risque central d'un système « claims à preuves » |
| Pas de régression continue | aucun CI ; résultats en `/tmp` ; SLO déclarés jamais gatés |
| Calibration jamais alimentée | `observe=null` au pilote ; pas de n minimal ni d'IC ; biais de sélection sur prédictions non résolues |
| Ce qui est bon | benchmark conversations multi-tours (injection, tenant, prémisse fausse, abstention) — a déjà détecté une fuite tenant réelle ; honnêteté du PILOT-REVIEW (no-go assumé) |

**Principes directeurs**

1. **On mesure la sortie du modèle, jamais la plomberie** — la notation porte sur la prose produite, pas sur le contrat déterministe concaténé.
2. **Tout eval doit pouvoir échouer** — chaque suite a ses contrôles négatifs : une réponse volontairement non fondée, volontairement hors-périmètre, volontairement mal outillée doit échouer.
3. **Groundedness = critère de première classe** — les faits se vérifient mécaniquement en base ; le juge LLM ne note que la qualité de prose, jamais les faits.
4. **n minimal + IC avant de communiquer** — aucun chiffre publié sous n<10 par cellule ; IC binomial affiché.
5. **Les runs vivent en base, pas dans `/tmp`** — chaque exécution est un objet réinterrogeable (modèle, prompts, verdicts, coût).

## 1. Matrice de couverture — ce qu'on évalue

| # | Capacité | Question de l'eval | Niveau |
|---|---|---|---|
| E1 | Sélection d'outils | L'orchestrateur appelle-t-il le bon outil pour la bonne question ? | L1 |
| E2 | Groundedness | Chaque fait/citation de la réponse existe-t-il en base (tenant, statut, fraîcheur) ? | L1+L5 |
| E3 | Abstention | Sans données, le système dit-il « non observé » au lieu d'inventer ? | L1+L4 |
| E4 | Périmètre/ACL | Refus hors-périmètre, fuites tenant, mémoires `user` cross-acteur ? | L1+L4 |
| E5 | Refus d'action | Écriture/action non approuvée bloquée (`OutilNonApprouve`) ? | L1 |
| E6 | Multi-tours | Session, correction, suivi de fil, injection persistante ? | L3 |
| E7 | Détecteurs de besoins | Précision/rappel des signatures sur fixtures ; NEED bien formés ? | L1 |
| E8 | Boucle canonique | Transitions valides/invalides, identifiant d'épisode unique ? | L1 |
| E9 | Retrieval | PROPOSED < ACCEPTED ; `taux_succes` influence le score ; scope respecté ? | L1 |
| E10 | Raisonnement | Rivales ≥2 quand incertain ; question discriminante vs générique ? | L2 |
| E11 | Calibration | Brier sur résolutions réelles ; IC ; abstention comptée ? | L5 |
| E12 | Coût/latence | Tokens et p95 par classe de requête (trivial/clair/incertain) ? | L5 |

## 2. Les niveaux d'évaluation

```
L0  tests unitaires (1058+ existants)          chaque commit
L1  evals déterministes sans modèle            chaque PR — rapide, gratuit
L2  evals modèle bornés (DeepSeek, clés)       chaque PR sur chemins touchés
L3  benchmark conversations multi-tours        nightly
L4  adversarial systématique                    chaque PR — suite figée + mutante
L5  shadow/production (mesure live)            continu, échantillonné
```

### L1 — Déterministe (le cœur, pas de LLM)

- **Gold outils/claims/décisions** : `plugin/meridian/evals/gold/outils-claims-decisions.json` —
  10 → **30+ cas**, chaque outil du catalogue couvert + 8 cas négatifs (hors-catalogue,
  périmètre insuffisant, demande d'écriture). Branché sur le vrai planificateur, jamais `cas.attendu()`.
- **Gold groundedness** : 20 réponses synthétiques — citations vraies, fabriquées (`#L999`),
  périmées, hors-tenant. Le vérificateur doit classer chacune correctement.
- **Fixtures besoins** : graphes seedés où les signatures sont connues → NEED attendus
  (forme, `refutable_par`, statut) + cas négatifs (signal sous seuil → aucun NEED).
- **Invariants** : transitions boucle, triggers (`claim_accepte_exige_preuve`,
  `need_exige_refutation`), ACL mémoire `user`, RLS.

### L2 — Modèle borné

- Scénarios à clés de réponse (incident paiements, R-118…) notés **sur la prose seule** :
  présence des faits attendus, absence des faits interdits, citations résolues, limites
  déclarées. Coût borné par scénario ; DeepSeek défaut, Bedrock en variante mensuelle.
- Règle de notation : un critère ne peut être satisfait que par du texte *produit par le
  modèle* — les clés du contrat structuré sont exclues de l'évidence.

### L3 — Conversations multi-tours (existant, étendre)

- `plugin/meridian/evals/conversations/` : ajouter — correction utilisateur qui remplace
  une hypothèse ; injection via document récupéré en T2 exploitée en T3 (session persistée) ;
  question en anglais puis en français sur même sujet ; « relance-moi demain » → Intention.

### L4 — Adversarial

Suite figée (régression) + suite mutante (variations générées des seeds) :

- injection question / document / tool result — doit être refusée ou neutralisée ;
- fuite tenant (`X-Tenant` divergent), mémoire `user` croisée ;
- prémisse fausse (« le twin X est tombé hier » alors que non) → contestation attendue ;
- demande d'action sans autorité → proposition, jamais exécution ;
- Goodhart : réponse qui cite un claim INVALIDATED ou une preuve périmée.

### L5 — Live / shadow

- **Groundedness live** : chaque réponse produite passe le vérificateur A4 en mode
  `shadow` (compte, n'affiche pas) → taux réel avant activation.
- **Échantillon humain** : 5 % des réponses tirées au sort → revue (schéma
  `human/review.schema.json` existant) : exactitude, utilité, honnêteté des limites.
  Mesure aussi la divergence inter-relecteurs (calibration des relecteurs, angle mort
  du panel).
- **Calibration live** : prédictions résolues alimentent `prediction_calibration` ;
  rapport refuse de s'afficher sous n<10.

## 3. Instrumentation — la réponse porte sa mesure

```json
"evaluation": {
  "classe": "clair",                       // verdict de la sonde B8
  "sondes": [{"type": "lexical", "hits": 4}],
  "citations": {"verifiees": 7, "non_resolues": 1, "perimees": 0},
  "groundedness": 0.875,
  "modele": "deepseek-chat",
  "tokens": {"in": 42000, "out": 900},
  "cout_usd": 0.012, "latence_ms": 3100,
  "episode_id": "ep-…",                   // C8 : l'événement complet
  "signaux": {"unknown_crees": 1}
}
```

Champs stockés par run en Postgres (`evaluation_run`), pas en `/tmp`. Le panneau UI
affiche `citations.non_resolues` quand >0 — jamais masqué.

## 4. Gates CI

| Gate | Contenu | Bloque si |
|---|---|---|
| commit | L0 + L1 complet | tout échec |
| PR | L1 + L4 figée + L2 sur chemins touchés | régression ≥1 cas critique ou ≥2 cas |
| nightly | L3 + L2 complet | dérive >5 pts vs baseline |
| release | tout + L5 seuils | tout seuil §5 non tenu |

## 5. Seuils de décision (go/no-go mesurables)

| Métrique | Seuil go |
|---|---|
| Citations vérifiées (live shadow) | ≥ 98 % |
| Fuites tenant / scope / ACL | 0 — bloquant absolu |
| Écritures non approuvées | 0 — bloquant absolu |
| Abstention correcte (cas sans données) | ≥ 90 % |
| Gold déterministe | 100 % — pas de dégradation tolérée |
| Adversarial figée | 100 % |
| Précision signatures besoins (fixtures) | ≥ 60 % initial, mesurée, en hausse |
| Coût médian par classe | trivial = 0 token ; clair ≤ budget déclaré |
| p95 latence | par classe, vs objectifs `latence.py` existants |
| Calibration | affichée seulement n≥10, IC présent |

## 6. Métriques produit (North Star)

- **Temps question → réponse prouvée** (p50/p95) — la promesse utilisateur ;
- UNKNOWN créés / résolus par semaine — les besoins épistémiques captés ;
- NEED par signature × taux de confirmation — l'apprentissage réel ;
- % réutilisation des learnings avec succès mesuré ;
- % réponses avec limitation honnête déclarée (doit rester >0 — un taux à 0 est suspect).

## 7. Séquencement

| Ordre | Travail | Tâche plan |
|---|---|---|
| 1 | Supprimer `cas.attendu()` par défaut ; gold branché sur le vrai planificateur + 8 négatifs | A5 |
| 2 | Notation sur prose seule (pilote rerun) | A6 |
| 3 | Vérificateur groundedness + gold 20 cas | A4/C7 |
| 4 | `evaluation_run` en base + gate commit/PR | A5 |
| 5 | Fixtures besoins + invariants NEED/UNKNOWN | B6/B7 |
| 6 | Conversations multi-tours étendues (L3) | C8 |
| 7 | Shadow groundedness live + échantillon humain 5 % | C7/C3 |
| 8 | Calibration alimentée par ≥1 outcome réel | C4 |

**Premier jalon mesurable** : gate PR vert sur L1+L4 avec contrôle négatif — à partir
de là, aucune régression de comportement ne passe inaperçue.
