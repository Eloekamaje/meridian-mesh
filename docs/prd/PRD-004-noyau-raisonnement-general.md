# PRD-004 — Noyau de raisonnement général

**Statut :** accepted — implémentation initiale
**Version :** 1.0
**Date :** 2026-11-02
**Complète :** [PRD-001](PRD-001-enterprise-intelligence-mesh.md), [PRD-002](PRD-002-memoire-contexte-raisonnement.md), [PRD-003](PRD-003-capacite-charge-prevision-budget.md)
**Décisions liées :** [ADR-0002](../adr/0002-orchestrateur-general.md), [ADR-0004](../adr/0004-capability-first-harness.md), [ADR-0015](../adr/0015-frontiere-agent-workflow-outils.md), [ADR-0020](../adr/0020-roles-projet-lentilles.md)
**Portée :** raisonnement d'entreprise, pas intelligence générale

## 0. Règle de lecture

Ce PRD décrit le **produit cible**. Il ne remplace pas PRD-002 : il en complète la section
« Raisonnement » par le **chaînon de contrôle** qui manque entre la question, les preuves, les
spécialistes et la réponse.

PRD-002 définit déjà des exigences de raisonnement (`RSN-001` à `RSN-014`). Une partie est implémentée :
trace de raisonnement, composition de plan, spécialistes, decision support, contexte borné. Le présent
PRD ne réécrit pas ces briques. Il définit ce qui manque pour qu'elles fonctionnent comme un **noyau de
raisonnement complet**, applicable à toute question et pas seulement à la conception.

Le langage normatif suit RFC 2119 : **DOIT**, **NE DOIT PAS**, **DEVRAIT**, **PEUT**.

---

## 1. Objet

Méridian doit pouvoir traiter **toute question d'entreprise** avec le bon niveau de raisonnement :

- une question factuelle ;
- une question ambiguë ;
- une investigation ;
- un diagnostic ;
- une conception ;
- une décision ;
- un plan ;
- une action ;
- une vérification ;
- une explication ;
- une comparaison ;
- une question sensible ou réglementée.

« N'importe quelle question » ne veut pas dire « même cérémonie pour toutes les questions ».
Cela veut dire que le noyau possède les opérations nécessaires et choisit une **profondeur proportionnée**.

Le noyau doit produire non seulement une réponse, mais un **dossier de raisonnement** :

```text
Demande → Cadre → Plan → Exécution → Critique → Décision → Livraison → Capitalisation
```

La conception n'est qu'un des modes d'application de ce noyau.

---

## 2. Problème observé

### 2.1 Cas révélateur

Dans le Travail `qui-es-tu`, Flore répond correctement à « Qui es-tu ? », puis reçoit :

> « peux-tu dessiner une architecture pour une application de dating ? »

Elle produit immédiatement une architecture cible de 12 composants et 20 liens, avec des hypothèses et
un hors-périmètre. La proposition est étiquetée comme non prouvée, ce qui est correct. Mais :

- aucune question n'est posée avant de concevoir ;
- le besoin réel n'est pas distingué de la demande littérale « dessiner » ;
- une seule option est proposée ;
- les risques d'âge, de sécurité des personnes, de données sensibles et de modération sont sous-traités ;
- la revue critique n'existe pas dans le processus ;
- le schéma dépasse les budgets du design system ;
- les hypothèses ne deviennent pas des hypothèses à valider ;
- aucun ADR, aucune alternative, aucun plan de validation n'est produit.

Le problème n'est pas que Flore ne sait pas produire une architecture. Le problème est qu'elle **n'a pas
reçu de processus** pour la concevoir.

### 2.2 Diagnostic

Le système actuel est principalement :

- **mono-tour** : l'agent choisit des outils et rend une réponse ;
- **orienté production** : la valeur est dans le livrable, pas dans la qualité de la décision ;
- **post-hoc** : la trace de raisonnement est construite après la réponse ;
- **non interruptible** : un outil ne peut pas rendre « clarification requise » ;
- **sans critique indépendante** : rien n'oblige à challenger le livrable ;
- **sans contrat de sortie** : le schéma de `concevoir_architecture` ne peut pas porter d'options, de
  risques, de questions ou de décisions ;
- **sans apprentissage** : une critique ou une correction utilisateur ne devient pas une règle, un test
  ou un learning.

Autrement dit, Méridian sait **produire**, mais pas encore **conduire un raisonnement jusqu'à une
décision défendable**.

---

## 3. État actuel et écart

| Brique existante | Ce qu'elle fait | Limite pour le noyau |
|---|---|---|
| `domain/raisonnement.py` — `TraceRaisonnement` | Trace auditable : plan, spécialistes, preuves, alternatives, incertitudes | Construite après coup ; ne pilote pas le tour |
| `application/composition.py` — `PlanComposition` | Compose méthodes, compétences et spécialistes | Sélection bornée, mais pas de boucle, de clarification ni de re-planification |
| `domain/specialistes.py` — `OrchestrateurSpecialistes` | Exécute des spécialistes en parallèle et produit des propositions | Cinq spécialistes seulement ; pas de critique ni de risque |
| `domain/methodes_cognitives.py` | Catalogue de méthodes : ADR, PMBOK, postmortem, A3, etc. | `adr` documente une décision ; il ne provoque pas la conception |
| `domain/competences_cognitives.py` | Catalogue de compétences et spécialités | `SPECIALISTES` figé : `decouverte`, `preuve`, `impact`, `outcome`, `outil` |
| `application/reponse_cognitive.py` | Assemble une réponse située avec decision support | Suppose des faits existants ; ne traite pas la conception greenfield |
| `analyse_service.py` | Produit la trace et la réponse cognitive | Chaîne d'analyse, pas noyau général de traitement |
| `capacites.py` — `concevoir_architecture` | Produit une proposition d'architecture | Entrée : `question` seule ; sortie : titre, résumé, hypothèses, composants, liens, hors-scope |
| `orchestrateur.py` | Agent + politique + outils, budget de 6 appels | Un seul tour ; une réponse d'outil peut devenir la réponse finale sans critique |
| Travail / cases | Conserve conversation, options, décisions, livrables | Pas de dossier de raisonnement structuré ni de reprise de phase |

**Conclusion :** les composants existent, mais ils ne sont pas reliés par un **contrat de traitement**.
C'est ce contrat que PRD-004 définit.

---

## 4. Principes

- **P-01 — Le noyau est un workflow, pas un agent.** Le workflow possède les états, les gates et les
  budgets ; le modèle propose ; le ToolGateway agit ; l'humain décide.
- **P-02 — La profondeur est proportionnée.** Une question simple ne doit pas déclencher un dossier lourd.
- **P-03 — Une proposition n'est pas un fait.** Le noyau sépare observation, claim, inférence, hypothèse,
  proposition, décision et action.
- **P-04 — La clarification est un acte de raisonnement, pas un échec.** Elle n'est demandée que si la
  réponse change réellement.
- **P-05 — La critique est indépendante.** Le producteur ne se certifie pas lui-même.
- **P-06 — Les options sont obligatoires pour les décisions conséquentes.** Une recommandation sans
  alternative est une opinion.
- **P-07 — La trace est vérifiable, pas une chaîne de pensée privée.** On conserve les étapes, preuves,
  hypothèses et décisions, jamais les tokens internes.
- **P-08 — L'humain gouverne.** Le noyau peut proposer, jamais décider seul d'une action sensible.
- **P-09 — Le noyau est indépendant du fournisseur de modèle.** DeepSeek, Bedrock ou modèle local sont des
  adapters.
- **P-10 — L'apprentissage est un effet du raisonnement.** Une critique, une correction ou un outcome doit
  pouvoir devenir un test, une règle ou un learning.
- **P-11 — Pas de prompt géant.** La discipline est portée par les états, les artefacts, les schémas et
  les gates, pas par un texte de 10 000 lignes.
- **P-12 — La conception est une capacité parmi d'autres.** Le noyau ne doit pas être modelé autour d'un
  seul type de livrable.

---

## 5. Définitions

| Terme | Définition |
|---|---|
| **Demande** | Question, mission ou action exprimée par l'utilisateur, avec son contexte et son enjeu |
| **Niveau de rigueur** | Profondeur de traitement requise : direct, étayé, cadré, décisionnel, critique |
| **Cadre** | Objectif, périmètre, contraintes, critères de succès, hypothèses, inconnues, risques |
| **Plan de raisonnement** | Opérations, méthodes, outils, seuil de preuve, niveau de critique, budgets |
| **Dossier de raisonnement** | Agrégat persistant qui porte toutes les phases et tous les artefacts |
| **Constat** | Observation ou fait relié à une source et à une date |
| **Hypothèse** | Proposition non encore validée, avec test et critère de réfutation |
| **Option** | Solution ou décision candidate, avec avantages, inconvénients, risques et conséquences |
| **Critique** | Revue indépendante avec findings, sévérité et dissensus |
| **Décision** | Choix explicite avec justification, alternatives écartées, conséquences et propriétaire |
| **Validation** | Plan qui transforme les hypothèses en tests, mesures ou expériences |
| **Action** | Effet externe soumis à autorisation, idempotence, audit et rollback |
| **Capitalisation** | Transformation d'une expérience en learning, test ou règle réutilisable |
| **Tour** | Unité d'interaction entre l'utilisateur et le noyau ; peut contenir plusieurs passes internes |

---

## 6. Niveaux de rigueur

Le noyau DOIT choisir un niveau avant de produire. Le niveau PEUT être relevé par la politique, jamais
abaissé sous le seuil de sécurité.

| Niveau | Nom | Déclencheurs | Sortie minimale |
|---|---|---|---|
| `N0` | Direct | Fait stable, faible impact, aucune donnée sensible | Réponse concise |
| `N1` | Étayé | Fait à vérifier, incertitude ou source nécessaire | Réponse + provenance + limite |
| `N2` | Cadré | Ambiguïté forte, plusieurs contraintes, exploration | Questions utiles + cadre |
| `N3` | Décisionnel | Impact élevé, conception, arbitrage, plan | Brief + options + critique + décision |
| `N4` | Critique | Irréversible, données sensibles, sécurité, juridique, mineurs, production | `N3` + revue indépendante + approbation humaine |

### 6.1 Règles de proportionnalité

- `N0` NE DOIT PAS créer un dossier lourd ni poser de question.
- `N1` PEUT citer une source sans produire d'artefact Canvas.
- `N2` DOIT limiter les questions aux informations qui changent la réponse.
- `N3` DOIT produire un cadre, au moins deux options réelles et une critique.
- `N4` DOIT ajouter une revue indépendante et une autorisation humaine avant toute action.

### 6.2 Clarification

- Le noyau DOIT demander une clarification si une information manquante change la réponse.
- Le noyau NE DOIT PAS demander une clarification si la réponse est la même dans tous les cas.
- Le noyau DOIT poser au plus **cinq questions** par tour de clarification.
- Le noyau DOIT pouvoir poursuivre avec des hypothèses explicites si l'utilisateur refuse de répondre.
- Une question DOIT avoir un effet identifiable sur le traitement ; sinon elle est supprimée.

---

## 7. Modèle canonique

### 7.1 `Demande`

- `id`
- `texte`
- `objet` : application, décision, incident, document, etc.
- `but` : comprendre, expliquer, concevoir, décider, agir, vérifier
- `enjeu` : faible, modéré, élevé, critique
- `ambiguite` : 0–1, avec raisons
- `reversibilite` : réversible, coûteuse, irréversible
- `sensibilite` : aucune, personnelle, financière, sécurité, juridique, mineurs
- `autorite` : lecture, proposition, approbation, décision, action
- `echeance`
- `niveau` : `N0` à `N4`

### 7.2 `Cadre`

- `objectif`
- `perimetre`
- `contraintes`
- `criteres_succes`
- `parties_prenantes`
- `hypotheses` : chacune avec `texte`, `impact`, `test`
- `inconnues`
- `risques`
- `questions_bloquantes`
- `questions_non_bloquantes`

### 7.3 `PlanRaisonnement`

- `niveau`
- `operations`
- `methode_ids`
- `competence_ids`
- `specialistes`
- `outils_prevus`
- `seuil_preuve`
- `niveau_critique`
- `budget` : appels, temps, tokens
- `conditions_arret`
- `justification`

### 7.4 `Constat`

- `id`
- `type` : observation, claim, inférence
- `texte`
- `provenance`
- `fraicheur`
- `confiance`
- `contradictions`
- `limites`

### 7.5 `Option`

- `id`
- `titre`
- `description`
- `avantages`
- `inconvenients`
- `risques`
- `cout`
- `reversible`
- `conditions_de_validite`
- `source` : proposée, observée, importée

### 7.6 `Critique`

- `id`
- `cible`
- `rubrique`
- `findings` : `severite`, `constat`, `preuve`, `remediation`
- `dissensus`
- `verdict` : pass, conditional, fail
- `reviewer` : modèle, humain, paire
- `independance` : séparée, croisée, humaine

### 7.7 `Décision`

- `id`
- `choix`
- `justification`
- `options_ecartees`
- `consequences`
- `proprietaire`
- `autorite`
- `date`
- `conditions_de_retournement`
- `plan_validation`

### 7.8 `Validation`

- `hypothese_id`
- `methode` : test, expérience, mesure, revue
- `critere`
- `echeance`
- `proprietaire`
- `resultat`

### 7.9 `DossierRaisonnement`

- `id`
- `tenant`
- `travail_id`
- `demande`
- `cadre`
- `plan`
- `constats`
- `options`
- `critiques`
- `decision`
- `validation`
- `trace`
- `statut`
- `cout`
- `created_at`
- `updated_at`

Le dossier DOIT être persistant, rejouable et inspectable.

---

## 8. Modes et opérations

### 8.1 Opérations universelles

Le noyau NE DOIT PAS être une liste de types de questions codés en dur. Il compose des opérations :

`qualifier`, `cadrer`, `planifier`, `observer`, `chercher`, `vérifier`, `inférer`, `comparer`, `simuler`,
`générer`, `critiquer`, `décider`, `planifier_action`, `agir`, `mesurer`, `expliquer`, `capitaliser`.

Les méthodes existantes sont des **recettes** qui composent ces opérations. Les outils sont des
**capacités d'exécution**. Les spécialistes sont des **lentilles**.

### 8.2 Modes

| Mode | Opérations dominantes | Sortie |
|---|---|---|
| Répondre | qualifier, vérifier, expliquer | Réponse sourcée |
| Explorer | qualifier, chercher, comparer | Constats, lacunes, questions |
| Diagnostiquer | observer, inférer, vérifier | Causes, preuves, actions |
| Concevoir | cadrer, générer, comparer, critiquer | Brief, options, ADR |
| Décider | cadrer, comparer, critiquer, décider | Recommandation, conditions, validation |
| Planifier | cadrer, décomposer, planifier | Plan, dépendances, risques |
| Agir | planifier_action, agir, vérifier | Action, preuve, rollback |
| Vérifier | observer, vérifier, critiquer | Findings, sévérité, remédiation |
| Enseigner | expliquer, illustrer, vérifier | Explication adaptée |

Un mode PEUT en appeler un autre. Le mode n'est pas une catégorie rigide ; c'est une composition
d'opérations.

---

## 9. Exigences fonctionnelles

### 9.1 Qualification et cadrage

- **KRN-001** — Tout tour DOIT créer ou mettre à jour un `DossierRaisonnement`.
- **KRN-002** — Le noyau DOIT qualifier la demande avant de générer : objet, but, enjeu, ambiguïté,
  réversibilité, sensibilité, autorité.
- **KRN-003** — La qualification NE DOIT PAS reposer sur une liste de mots-clés fermée ; elle PEUT combiner
  règles, modèle et politique.
- **KRN-004** — Le noyau DOIT choisir un niveau de rigueur et exposer sa justification.
- **KRN-005** — Le noyau DOIT produire un cadre pour tout traitement `N2`, `N3` ou `N4`.
- **KRN-006** — Le cadre DOIT distinguer questions bloquantes et non bloquantes.
- **KRN-007** — Une hypothèse non validée DOIT avoir un test ou une raison explicite de ne pas en avoir.

### 9.2 Planification

- **KRN-010** — Le noyau DOIT produire un plan borné : opérations, méthodes, spécialistes, outils,
  budgets, conditions d'arrêt.
- **KRN-011** — Le plan DOIT être révisable après une clarification, une critique ou un nouvel élément.
- **KRN-012** — Le plan NE DOIT PAS dépasser l'autorité de l'acteur.
- **KRN-013** — Le noyau DOIT pouvoir s'arrêter sur incertitude résiduelle et déclarer pourquoi.

### 9.3 Clarification

- **KRN-020** — Un outil ou un agent DOIT pouvoir retourner `clarification_requise` avec des questions
  structurées.
- **KRN-021** — Le noyau DOIT interrompre la production si une question bloquante n'est pas résolue.
- **KRN-022** — Le noyau DOIT limiter les questions et expliquer leur effet attendu.
- **KRN-023** — Le noyau DOIT permettre un mode « sans questions » avec hypothèses explicites et livrable
  marqué provisoire.
- **KRN-024** — Une question de clarification NE DOIT PAS être posée si la réponse ne change pas.

### 9.4 Preuves et connaissance

- **KRN-030** — Toute affirmation factuelle importante DOIT être reliée à une source, un claim ou une
  hypothèse explicite.
- **KRN-031** — Le noyau DOIT distinguer « non observé », « non recherché » et « inexistant ».
- **KRN-032** — Le noyau DOIT conserver les contradictions au lieu de les fusionner silencieusement.
- **KRN-033** — Le noyau DOIT exposer fraîcheur, couverture, confiance et limites.
- **KRN-034** — Un chiffre sans source DOIT être marqué comme hypothèse ou retiré.

### 9.5 Options et décision

- **KRN-040** — Toute décision conséquente DOIT exposer au moins deux options réelles, dont l'option
  « ne rien faire » lorsque pertinente.
- **KRN-041** — Chaque option DOIT porter avantages, inconvénients, risques et conséquences.
- **KRN-042** — Une recommandation DOIT être séparée des faits qui la soutiennent.
- **KRN-043** — Toute décision DOIT porter un propriétaire, une autorité et des conditions de retournement.
- **KRN-044** — Une conception `N3` DOIT produire un ADR ou une décision équivalente.
- **KRN-045** — Une décision sans plan de validation DOIT être marquée comme non validée.

### 9.6 Critique

- **KRN-050** — Tout livrable `N3` DOIT passer une critique avant livraison.
- **KRN-051** — Tout livrable `N4` DOIT passer une critique indépendante et une approbation humaine.
- **KRN-052** — La critique DOIT être produite dans un contexte séparé de l'auteur.
- **KRN-053** — La critique DOIT produire des findings avec sévérité et remédiation.
- **KRN-054** — La critique NE DOIT PAS réécrire le livrable ; elle le juge.
- **KRN-055** — Un finding critique non résolu DOIT bloquer la livraison.
- **KRN-056** — Le dissensus DOIT être conservé et exposé.
- **KRN-057** — Le noyau DOIT borner les boucles de correction et escalader au-delà.

### 9.7 Action

- **KRN-060** — Toute action DOIT passer par le ToolGateway.
- **KRN-061** — Toute action irréversible DOIT exiger une approbation humaine.
- **KRN-062** — Toute action DOIT déclarer idempotence, audit et rollback.
- **KRN-063** — Le noyau NE DOIT PAS confondre une proposition avec une action.
- **KRN-064** — Un échec d'action DOIT produire un constat, pas une réponse inventée.

### 9.8 Livraison

- **KRN-070** — La réponse DOIT exposer son niveau, sa confiance, ses hypothèses, ses questions ouvertes
  et ses limites.
- **KRN-071** — La réponse DOIT rester concise pour `N0` et `N1`.
- **KRN-072** — La réponse DOIT produire des artefacts Canvas pour `N3` et `N4`.
- **KRN-073** — Le noyau NE DOIT PAS exposer de chaîne de pensée privée ; il expose une rationale
  vérifiable.
- **KRN-074** — Le noyau DOIT permettre à l'utilisateur de demander plus de profondeur ou une critique.

### 9.9 Persistance et apprentissage

- **KRN-080** — Le dossier DOIT être persisté et reprenable.
- **KRN-081** — Le dossier DOIT être rejouable sans rappeler le modèle lorsque les artefacts sont
  persistés.
- **KRN-082** — Chaque critique et correction DOIT pouvoir devenir un test de non-régression.
- **KRN-083** — Chaque décision DOIT pouvoir être reliée à un outcome.
- **KRN-084** — Le noyau DOIT mesurer la qualité du raisonnement, pas seulement la satisfaction.

### 9.10 Sensibilité et domaines

- **KRN-090** — Le noyau DOIT détecter les domaines sensibles et relever le niveau de rigueur.
- **KRN-091** — Un pack de domaine PEUT ajouter des contrôles, jamais retirer un gate de sécurité.
- **KRN-092** — Les données personnelles, secrets et identifiants NE DOIVENT PAS entrer dans un prompt,
  une trace ou un artefact non autorisé.
- **KRN-093** — Une question hors périmètre ou dangereuse DOIT produire un refus explicite et une
  alternative sûre.

---

## 10. Critique et gates

### 10.1 Rubriques de critique

La critique de base couvre :

- cadrage ;
- pertinence des questions ;
- qualité des preuves ;
- contradictions ;
- couverture des options ;
- risques ;
- sécurité ;
- vie privée ;
- conformité ;
- opérabilité ;
- coût ;
- simplicité ;
- validation ;
- clarté.

Les rubriques spécifiques sont ajoutées par le mode ou le pack de domaine.

### 10.2 Gates

| Gate | Condition | Effet |
|---|---|---|
| `G-KRN-01` | Question bloquante non résolue | Interrompre et demander |
| `G-KRN-02` | `N3` sans cadre | Refuser la livraison |
| `G-KRN-03` | `N3` avec moins de deux options | Refuser la livraison |
| `G-KRN-04` | `N3` sans critique | Refuser la livraison |
| `G-KRN-05` | `N4` sans revue indépendante | Refuser la livraison |
| `G-KRN-06` | Finding critique non résolu | Refuser la livraison |
| `G-KRN-07` | Action irréversible sans approbation | Refuser l'action |
| `G-KRN-08` | Chiffre sans source ni hypothèse | Retirer ou requalifier |
| `G-KRN-09` | Schéma au-delà des budgets | Scinder ou refuser |
| `G-KRN-10` | Hypothèse sans test en `N3` | Requalifier ou bloquer |
| `G-KRN-11` | Boucle de correction dépassée | Escalader |
| `G-KRN-12` | Contexte vide ou partiel | Réduire la confiance et l'exposer |

### 10.3 Indépendance de la critique

- `N3` : critique séparée, même modèle accepté.
- `N4` : critique croisée ou humaine.
- Une critique humaine DOIT pouvoir contredire le modèle et être conservée.
- Le critique NE DOIT PAS recevoir les tokens internes de l'auteur ; il reçoit le livrable, le cadre,
  les preuves et la rubrique.

---

## 11. Contrat de tour et orchestration

### 11.1 Statuts

Un tour ou un outil DOIT pouvoir retourner :

- `reponse` : réponse directe ;
- `clarification_requise` : questions bloquantes ;
- `proposition` : livrable à critiquer ;
- `decision` : choix proposé ;
- `action_requise` : approbation ou exécution ;
- `partiel` : résultat incomplet ;
- `refus` : hors périmètre ou dangereux ;
- `echec` : erreur technique.

### 11.2 Boucle

```text
qualifier
  ↓
cadrer
  ↓
planifier
  ↓
exécuter ←──────────────┐
  ↓                     │
critiquer               │
  ↓                     │
décider ── re-planifier ┘
  ↓
livrer
  ↓
capitaliser
```

### 11.3 Budgets et arrêt

- maximum de tours de clarification ;
- maximum de boucles de critique ;
- maximum d'appels d'outils ;
- budget de temps et de tokens ;
- arrêt sur incertitude résiduelle ;
- escalade humaine au-delà des seuils.

Le noyau DOIT préférer un résultat partiel honnête à une réponse inventée.

---

## 12. Expérience utilisateur

- Le chat DOIT afficher la phase courante : cadrage, recherche, critique, décision.
- Les questions DOIT être posées dans le fil, avec leur effet attendu.
- Les artefacts `Brief`, `Options`, `Critique`, `Décision` et `Validation` DOIVENT être consultables dans
  le Canvas.
- L'utilisateur DOIT pouvoir choisir : « réponse rapide », « approfondis », « critique ».
- Le mode rapide NE DOIT PAS désactiver les gates de sécurité.
- Un livrable provisoire DOIT être clairement marqué.
- L'utilisateur DOIT pouvoir contester une décision et rouvrir le dossier.

---

## 13. Architecture et implémentation

### 13.1 Domaine

Étendre `backend/meridian/domain/raisonnement.py` sans casser `TraceRaisonnement`, et ajouter les objets
du dossier :

- `demande.py` ;
- `dossier_raisonnement.py` ;
- `critique.py` ;
- `decision.py` ;
- `validation.py`.

`TraceRaisonnement` devient une vue du dossier, pas le dossier lui-même.

### 13.2 Application

Nouveau service : `backend/meridian/application/noyau_raisonnement.py`.

Responsabilités :

- `qualifier` ;
- `cadrer` ;
- `planifier` ;
- `executer` ;
- `critiquer` ;
- `decider` ;
- `livrer` ;
- `capitaliser`.

Il réutilise :

- `composition.planifier` ;
- `specialistes.OrchestrateurSpecialistes` ;
- `reponse_cognitive.composer` ;
- `contexte` et `resolveur_contexte` ;
- `methodes_cognitives` et `competences_cognitives` ;
- `executeur` et `ToolGateway`.

Il ne réimplémente pas les preuves, les Claims, les Twins ni les outils.

### 13.3 Orchestrateur

`backend/meridian/adapters/outbound/llm/orchestrateur.py` devient un **workflow multi-passes**.

- Le workflow possède l'état et les gates.
- L'agent propose des opérations et des contenus.
- Un outil ne remplace plus directement la réponse finale.
- Un outil peut retourner `clarification_requise`.
- Une réponse finale passe par `critiquer` puis `livrer`.

### 13.4 Contrat des outils

`concevoir_architecture` DOIT évoluer :

- entrée : `question`, `cadre`, `contraintes`, `niveau`, `options_attendues` ;
- sortie : `statut`, `questions`, `hypotheses`, `options`, `risques`, `composants`, `liens`,
  `plan_validation`.

Le schéma actuel, limité à `titre`, `resume`, `hypotheses`, `composants`, `liens` et `hors_scope`, est
insuffisant pour un traitement `N3`.

### 13.5 Spécialistes

Ajouter :

- `specialiste_critique.py` ;
- `specialiste_risque.py`.

Étendre `SPECIALISTES` de `decouverte`, `preuve`, `impact`, `outcome`, `outil` à une liste incluant
`critique` et `risque`.

Le spécialiste critique :

- ne réécrit pas ;
- produit des findings ;
- conserve le dissensus ;
- est exécuté dans un contexte séparé.

### 13.6 Méthodes et compétences

Ajouter une méthode `conception` qui couvre :

- cadrage ;
- options ;
- critique ;
- décision ;
- validation.

`adr` reste la méthode de **documentation** d'une décision déjà construite. Elle ne doit pas être le
seul mécanisme de conception.

Ajouter les compétences :

- `formuler_probleme` ;
- `comparer_options` ;
- `critiquer_conception` ;
- `planifier_validation` ;
- `qualifier_demande`.

### 13.7 Persistance

Le dossier de raisonnement est attaché au Travail. Il PEUT être stocké :

- dans `cases` pour le MVP ;
- dans une table `dossier_raisonnement` pour la version durable.

Le stockage DOIT respecter le tenant, les permissions, la rétention et l'audit.

### 13.8 Interface

- questions dans le chat ;
- artefacts dans le Canvas ;
- statut de phase ;
- bouton « contester » ;
- bouton « approfondir » ;
- bouton « mode rapide » ;
- export du dossier.

---

## 14. Données, sécurité et audit

- Le dossier DOIT être tenant-scoped.
- Les secrets et identifiants NE DOIVENT PAS être persistés dans le dossier.
- Les données personnelles DOIVENT être minimisées et soumises à la politique de rétention.
- La trace DOIT être altérable uniquement par une procédure auditée.
- Un dossier DOIT pouvoir être exporté et supprimé selon les droits.
- Les appels de critique DOIVENT être tracés : modèle, version, rubrique, durée, coût.
- Un dossier `N4` DOIT conserver l'identité du relecteur humain.

---

## 15. Évaluation et métriques

### 15.1 Jeux d'évaluation

- questions factuelles ;
- questions ambiguës ;
- questions de conception ;
- décisions à fort enjeu ;
- diagnostics ;
- actions irréversibles ;
- sujets sensibles ;
- preuves contradictoires ;
- schémas trop denses ;
- questions pièges.

### 15.2 Métriques

- taux de questions utiles ;
- taux de sur-questionnement ;
- taux de risques détectés avant l'utilisateur ;
- taux d'options réelles par décision ;
- taux de findings critiques détectés ;
- taux de livrables acceptés sans correction ;
- taux de décisions avec plan de validation ;
- taux d'actions avec rollback ;
- latence et coût par niveau ;
- taux de réponses trop longues ;
- calibration de la confiance.

### 15.3 Non-régression

- Une question simple NE DOIT PAS devenir un dossier `N3`.
- Une conception `N3` NE DOIT PAS être livrée sans critique.
- Un schéma trop dense NE DOIT PAS passer.
- Une question de dating NE DOIT PAS reproduire l'absence de cadrage du cas `qui-es-tu`.
- Une réponse sans preuve NE DOIT PAS être présentée comme certaine.

---

## 16. Critères d'acceptation

- **AC-01** — Le même cas `qui-es-tu` produit soit une clarification, soit un brief explicite avant
  l'architecture.
- **AC-02** — Une conception `N3` expose au moins deux options et une critique.
- **AC-03** — Une décision expose ses conditions de retournement et son plan de validation.
- **AC-04** — Une question `N0` reste concise et ne déclenche pas de dossier lourd.
- **AC-05** — Un outil peut retourner une clarification et le tour reprend après réponse.
- **AC-06** — Un finding critique non résolu bloque la livraison.
- **AC-07** — Un schéma au-delà des budgets est scindé ou refusé.
- **AC-08** — Un chiffre non sourcé est retiré ou requalifié.
- **AC-09** — Le dossier est persistant et rejouable.
- **AC-10** — Une action irréversible exige une approbation humaine.
- **AC-11** — Une critique indépendante est conservée avec son dissensus.
- **AC-12** — Le noyau fonctionne avec DeepSeek, Bedrock ou un modèle local via adapter.

---

## 17. Hors périmètre

- Intelligence générale hors questions d'entreprise.
- Remplacement des Claims, Twins, preuves et spécialistes existants.
- Décision automatique sans humain sur les sujets sensibles.
- Entraînement d'un modèle maison.
- Vérification formelle de toutes les architectures.
- RLS et OIDC de production.
- Voix temps réel.
- Évaluation exhaustive de tous les domaines métier.

---

## 18. Déploiement par lots

### Lot 1 — Socle

- dossier de raisonnement ;
- qualification ;
- routeur de niveaux ;
- cadrage ;
- gates ;
- persistance ;
- trace.

### Lot 2 — Critique

- spécialiste critique ;
- rubriques ;
- boucle de correction ;
- artefacts Canvas ;
- mode « contester ».

### Lot 3 — Décision et action

- options ;
- ADR ;
- validation ;
- approbations ;
- rollback ;
- spécialiste risque.

### Lot 4 — Apprentissage

- jeux d'évaluation ;
- calibration ;
- corrections utilisateur ;
- learnings ;
- revue croisée multi-modèles.

---

## 19. Questions ouvertes

1. Le dossier doit-il vivre dans `cases` ou dans une table dédiée dès le MVP ?
2. Quel seuil d'ambiguïté déclenche `N2` sans créer de sur-questionnement ?
3. Critique same-model ou cross-model par défaut pour `N3` ?
4. Combien de tours de clarification maximum ?
5. Quel niveau de détail exposer dans le dossier sans exposer de raisonnement privé ?
6. Quel propriétaire humain pour les décisions `N4` ?
7. Comment mesurer la qualité d'une critique sans la réduire à un score ?
8. Faut-il un ADR dédié pour le contrat de tour et les statuts ?

---

## 20. Références

- [PRD-001 — Enterprise Intelligence Mesh](PRD-001-enterprise-intelligence-mesh.md)
- [PRD-002 — Mémoire, contexte et raisonnement](PRD-002-memoire-contexte-raisonnement.md)
- [PRD-003 — Capacité, charge, prévision et budget](PRD-003-capacite-charge-prevision-budget.md)
- [ADR-0002 — Orchestrateur général](../adr/0002-orchestrateur-general.md)
- [ADR-0004 — Harness capacitaire](../adr/0004-capability-first-harness.md)
- [ADR-0015 — Frontière agent, workflow et outils](../adr/0015-frontiere-agent-workflow-outils.md)
- [ADR-0020 — Rôles projet et lentilles](../adr/0020-roles-projet-lentilles.md)
- `backend/meridian/domain/raisonnement.py`
- `backend/meridian/application/composition.py`
- `backend/meridian/domain/specialistes.py`
- `backend/meridian/application/reponse_cognitive.py`
- `backend/meridian/domain/capacites.py`
- `backend/meridian/adapters/outbound/llm/orchestrateur.py`

---

## 21. État d'implémentation

| Capacité | État | Où |
|---|---|---|
| Dossier et niveaux | implémenté | `domain/dossier_raisonnement.py` |
| Qualification, cadrage, plan | implémenté | `application/noyau_raisonnement.py` |
| Clarification avant génération | implémenté | noyau + `cases.py` (`raisonnement_en_attente`) |
| Critique structurelle | implémenté | `noyau_raisonnement.critiquer_reponse` |
| Spécialiste critique | implémenté | `application/specialiste_critique.py` |
| Spécialiste risque | implémenté | `application/specialiste_risque.py` |
| Options et décision | implémenté | schémas du noyau + `conception.py` |
| Gates et statuts de tour | implémenté | `noyau_raisonnement.evaluer_gates` |
| QuestionFrame / présupposés | implémenté | `domain/epistemie.py`, `application/epistemie.py` |
| Croyances / révisions | implémenté | `Belief`, `BeliefRevision`, révision persistée |
| Plan de sources | implémenté | `SourcePlan` dans le dossier |
| Exécution du SourcePlan | implémenté | `recherche_refutation.py` : claims, preuves CONTRE, contradictions |
| Calibration des croyances | implémenté | `belief_calibration`, résolution par outcome, Brier |
| Outcome → croyance | implémenté | `CreationOutcome.dossier_id` + `belief_ids`, révisions retournées |
| Continuité des croyances | implémenté | reprises depuis le Travail au tour suivant |
| Gate de prémisse | implémenté | `G-PREM-01`, `G-PREM-02` |
| Contexte → dossier | implémenté | `application/contexte_raisonnement.py` |
| PlanComposition → PlanRaisonnement | implémenté | `noyau_raisonnement.planifier(plan_composition=...)` |
| Dossier sur `/analyser` | implémenté | `analyse_service.py` (`dossier_raisonnement`) |
| Trace reliée au dossier | partiel | `trace_id` repris ; deux vues coexistent |
| Persistance du dossier | implémenté | Mongo + table Postgres `dossier_raisonnement` + API de lecture |
| API de raisonnement | implémenté | `/api/raisonnement/qualifier`, `/analyser`, `/evaluer` |
| Affichage du dossier | implémenté | `RaisonnementFlore.jsx` |
| Authoring design-diagram | implémenté | `design_diagram.py`, cache par hash, budget 9/12 |
| Viewport SVG interactif | implémenté | `DiagrammeCompile.jsx` : zoom, pan, clic, plein écran |
| Évaluation déterministe | implémenté | `application/evaluation_raisonnement.py` |
| Action gouvernée | implémenté | `action_raisonnement.py` + `POST /api/raisonnement/actions` + ToolGateway |
| Apprentissage | implémenté | proposition persistée `PROPOSED`, promotion humaine via `/apprentissage/{id}/promouvoir` |
| Critique croisée multi-modèle | implémenté | `JUMEAU_CRITIQUE_CROISEE=1` et modèle juge séparé |
| Rollback d'action | implémenté comme opération compensatoire explicite | `executer_rollback`, toujours via ToolGateway |
| RLS du dossier | implémenté et prouvé | table dans RLS, `scripts/rls-verify-local.sh` passe |
| Outils d'action configurés | à déployer | `EXECUTION_TOOLS` + `EXECUTION_ALLOWLIST` |

Les éléments partiels sont des chantiers explicites, pas des exceptions silencieuses.

## 22. Références d'implémentation

- `backend/meridian/domain/dossier_raisonnement.py`
- `backend/meridian/application/noyau_raisonnement.py`
- `backend/meridian/application/epistemie.py`
- `backend/meridian/domain/epistemie.py`
- `backend/meridian/adapters/outbound/postgres/recherche_refutation.py`
- `backend/meridian/application/calibration_croyances.py`
- `backend/meridian/adapters/outbound/postgres/calibration_croyances.py`
- `backend/meridian/domain/epistemie.py`
- `backend/meridian/application/contexte_raisonnement.py`
- `backend/meridian/application/action_raisonnement.py`
- `backend/meridian/application/apprentissage_raisonnement.py`
- `backend/meridian/adapters/outbound/postgres/apprentissage_raisonnement.py`
- `backend/meridian/adapters/outbound/llm/critique_raisonnement.py`
- `backend/meridian/application/evaluation_raisonnement.py`
- `backend/meridian/adapters/outbound/postgres/dossiers_raisonnement.py`
- `backend/meridian/application/specialiste_critique.py`
- `backend/meridian/application/specialiste_risque.py`
- `backend/meridian/adapters/inbound/http/raisonnement.py`
- `backend/meridian/adapters/outbound/llm/orchestrateur.py` — `executer_raisonne`
- `backend/meridian/adapters/outbound/llm/conception.py`
- `frontend/src/components/RaisonnementFlore.jsx`
- `frontend/src/components/DiagrammeCompile.jsx`
- `backend/meridian/adapters/outbound/llm/design_diagram.py`
- `backend/meridian/application/diagrammes.py`
- `docs/diagrammes/raisonnement-contexte-jumeaux.html` — état et manques
- `backend/meridian/tests/test_noyau_raisonnement.py`
- `backend/meridian/tests/test_evaluation_raisonnement.py`
- `backend/meridian/tests/test_specialiste_critique_risque.py`
