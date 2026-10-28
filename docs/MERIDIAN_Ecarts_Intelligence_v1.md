# MÉRIDIAN — Ce qui manque pour être aussi intelligent que sa vision
## Écarts avec Claude Code et les produits de l'industrie, constatés dans le code et mesurés

**Statut :** Analyse, à discuter — **amendée le 2026-10-28** après exécution du plan de remédiation
**Version :** 1.0
**Date :** 2026-10-28
**Documents liés :** Product Vision & Operating Model (§4, §7, §9, §14, §15), Non-Functional Requirements (§5, §8),
Architecture Jumeau v1, Jumeau Harness Agentique v1–v3, Jumeau Sources v1, Investigation & Decision Engine,
Continuous Improvement & Learning Model, Security Governance Trust Model
**Tagline :** **DÉCOUVRIR · COMPRENDRE · DÉCIDER**

---

# 0. Objet et méthode

La vision de Méridian (§3) est un « système d'exploitation cognitif de l'entreprise ». Elle avance en trois
générations : **comprendre**, **exploiter**, puis une troisième (§14). Sa différence tient dans une boucle continue :
**observer → comprendre → faire émerger → investiguer → décider → apprendre** (§15).

Ce document mesure la distance entre cette vision et ce qui tourne réellement aujourd'hui. Il compare Méridian à deux
références : Claude Code, l'agent qui a construit une bonne partie de ce code, et les produits de l'industrie qui
visent des promesses voisines. Chaque constat s'appuie sur le code (fichier cité), sur une mesure, ou sur une source
publique (§8). Une affirmation sur un produit tiers que nous n'avons pas pu confirmer est signalée comme telle.

---

# 1. Où en est Méridian, en une page

**Ce qui existe et fonctionne** (branche `jumeau-phase0`, 552 tests) :

- Des **jumeaux nés du code** (4 réels). Chacun porte des connaissances prouvées ligne par ligne, une fiche vivante
  et un gardien qui suit les commits.
- Des **sources branchées** selon un même contrat (Confluence, Jira, ServiceNow, Datadog). Elles sont écrites et
  testées, **mais aucune n'a tourné sur un vrai compte**.
- **Vérifier comme on teste** (v3 §2) : recettes déterministes, juge d'appui, recoupement entre systèmes. Une
  connaissance n'atteint M3 que si deux systèmes **de types distincts** concordent — et un fichier Markdown du dépôt
  n'est plus un système à part (voir « État après remédiation » ci-dessous).
- **Des garde-fous avant l'envoi** : citations vérifiées, fraîcheur des preuves, confirmations inventées
  refusées, échappement HTML.
- **Des schémas fondés sur le code** : l'enchaînement d'une fonctionnalité est lu dans le graphe d'appels, chaque
  flèche est prouvée par sa ligne, et le harness dessine le Mermaid.
- **Une réponse au fil de l'eau** : vraies étapes, brouillon « en relecture », puis l'état réel de la relecture
  (`relu`, `corrigé — non relu`, `non relu`). La latence du premier mot est désormais **mesurée** (`durees.premier_texte`) ;
  aucun chiffre n'est publié tant qu'un relevé de banc daté n'est pas joint.
- **Flore** répond seule ou orchestre plusieurs jumeaux. Elle montre sur l'Atlas, travaille dans un Travail
  (plan, hypothèses, livrables) et route d'elle-même vers l'application nommée.

**État après remédiation (2026-10-28, mesuré sur la base réelle).** Le 28 octobre, les défauts d'honnêteté et de
méthode listés dans le plan de remédiation ont été corrigés (`MERIDIAN_Plan_Remediation_v1.md`). Les chiffres publiés plus haut ont changé en
conséquence, et il faut lire ceux-ci :

| Mesure | Avant | Après |
|---|---|---|
| Connaissances recoupées (M3) | 9 | **0** — les 9 reposaient sur « le README du même commit approuve le code » |
| Faits établis par une source | — | **398** (`DEPEND_DE`, `EXPOSE`, `LIT_VARIABLE`, `EXECUTE_IMAGE`) |
| Hypothèses (phrase métier, preuve = ligne de code) | comptées comme M2 | **148**, ramenées à M1 |
| Connaissances sans état de vérification | 50 | **0** (état `en_attente` posé à la naissance) |
| « Vérifié » par recette | circulaire (l'extraction était filtrée par la recette) | **non circulaire** : la preuve vient de l'index, la recette la juge |
| Recoupement | un mot du juge | **déterministe** quand une recette s'applique ; sinon l'observation « tel système ne nomme pas l'énoncé » accompagne le verdict |
| Couverture d'un jumeau | 32 % pour tous | **49 % / 83 % / 76 %** (part de ce qui est établi) |
| Connecteurs réellement branchés | 12 affichés, 7 simulés | **6 branchés**, 6 déclarés non branchés |
| Latence du premier mot | citée à 2 s, jamais mesurée | **mesurée** partout (`durees.premier_texte`), aucun chiffre publié sans relevé |

Une phrase du présent document était donc trop optimiste : « 5 connaissances sont recoupées pour de vrai ». Il n'y
en a plus aucune : le seul chemin vers M3 est désormais une source **d'un autre type**, et aucune n'est branchée.
C'est la mesure de ce qui reste à faire, et non une régression.

**Où cela se situe dans la vision.** Nous sommes au milieu de **Méridian 1 — Comprendre**, pour une poignée
d'applications sans données d'entreprise réelles. Les étapes **faire émerger**, **investiguer**, **décider** et
**apprendre** de la boucle (§15) existent dans les documents, et presque pas dans le code.

---

# 2. La grille : dix capacités d'un système intelligent

Légende de l'écart : 🔴 bloque la vision · 🟠 limite fortement · 🟢 en bonne voie.

| # | Capacité | Ce que font les meilleurs | Méridian aujourd'hui | Écart |
|---|---|---|---|---|
| 1 | **Contexte d'entreprise réel** | Glean indexe chaque application connectée (Slack, Drive, Jira, Confluence…) dans un graphe qui respecte les droits [G1] ; Rovo relie Jira, Confluence, JSM, Slack et e-mail dans le Teamwork Graph [R1] | Les lecteurs existent, mais aucun n'est branché sur un vrai compte ; le contexte, ce sont 4 dépôts de démonstration | 🔴 |
| 2 | **Identité et droits à chaque réponse** | Glean et Rovo ne montrent à chacun que ce qu'il pourrait voir dans la source d'origine [G2][R2] | `X-Persona` déclaratif, non authentifié ; OIDC reporté ; les droits de revue et de consigne ne sont pas appliqués | 🔴 |
| 3 | **Comprendre le code** | Analyse statique d'abord, le modèle nomme ensuite (CodeBoarding, Swimm, CodeWiki) [C1–C3] | Index de code et graphe d'appels (`appels.py`) ; ne voit ni l'injection de dépendances (`Depends`), ni les requêtes SQL externalisées, ni les appels entre applications | 🟠 |
| 4 | **Vérifier ce qu'il affirme** | Claude Code teste et relit ; Google *Check Grounding* note l'ancrage de chaque phrase [V1] ; l'API Citations d'Anthropic rend les passages exacts [V2] | **Point fort du mécanisme, résultat vide.** Les recettes sont déterministes et ne fabriquent plus leur propre preuve, la copie entre deux sources est calculée, et M3 exige deux sources de **types distincts**. Conséquence assumée : **0 connaissance recoupée**, 398 faits établis, 148 hypothèses, 1 validation humaine sur 546 | 🟢 |
| 5 | **Raisonner en plusieurs étapes** | Claude Code planifie, délègue à des sous-agents au contexte isolé, recueille leurs résultats [A1] ; Glean annonce une planification adaptative et des sous-agents parallèles (rapporté) [G1] | Plan et étapes dans un Travail ; mobilisation en étoile ; **pas de moteur d'investigation** (hypothèses mises à l'épreuve, options comparées) | 🟠 |
| 6 | **Experts spécialisés** (Vision §7) | Des capacités définies par leur domaine, leurs outils, leurs critères de preuve et leurs limites | Flore, les jumeaux, le juge d'appui et le relecteur ; **aucun expert métier** (risque, données, sécurité, architecture) | 🔴 |
| 7 | **Faire émerger, sans qu'on demande** | Glean et Rovo poussent des réponses et des agents dans le flux de travail (rapporté) [G1][R1] | Le gardien publie des situations sur un changement de code ; pas d'opportunité, pas d'anomalie d'exploitation réelle (Datadog non branché) | 🔴 |
| 8 | **Mémoire et apprentissage** | Claude Code : `CLAUDE.md` et mémoire relus à chaque session, compétences chargées à la demande [A1] | Connaissances et consignes d'équipe (sans interface) ; **ni retour d'usage qui améliore les réponses, ni mémoire des décisions et de leurs effets** (Learning Model) | 🔴 |
| 9 | **Rendu riche** | Artifacts de Claude dans un cadre isolé sur une autre origine [D1] ; Google Code Wiki régénère ses diagrammes à chaque changement [C4] | Schémas Mermaid prouvés, scènes sur l'Atlas ; ni page libre isolée, ni schéma préparé d'avance | 🟢 |
| 10 | **Vitesse perçue** | Réponse diffusée au fil de l'eau, outils visibles en direct | Diffusion réelle, mais **aucune mesure fiable** : le premier mot est horodaté depuis le 2026-10-28, et la seule mesure persistée donne 17,4 s de moyenne (objectif NFR < 5 s) | 🟠 |

Quatre capacités transversales complètent la grille :

| Capacité | Méridian aujourd'hui | Écart |
|---|---|---|
| **Évaluation continue** | `evaluation.py` et banc de latence, lancés à la main ; pas de jeu de référence validé, pas d'exécution à chaque changement | 🟠 |
| **Exposition** (MCP, là où l'on travaille) | Glean est rapporté à la fois serveur et client MCP [G1] ; Méridian n'est accessible que par son interface (v3 §3, non fait) | 🟠 |
| **Choix du modèle** | Un seul modèle, DeepSeek, réservé au code non bancaire ; Bedrock prévu mais non branché. **Le code bancaire ne peut donc pas être analysé aujourd'hui.** Glean est rapporté compatible avec plus de 15 modèles [G1] | 🔴 |
| **Agir** | Lecture et propositions seulement (livrables dans un Travail) ; Rovo agit dans Jira (rapporté) [R1]. C'est un choix de gouvernance, mais il manque au moins le brouillon d'action (ticket, ADR) que l'équipe valide | 🟠 |

---

# 3. Ce que Claude Code fait et que Méridian ne fait pas encore

| Mécanisme de Claude Code | Équivalent dans Méridian | Ce qui manque |
|---|---|---|
| Mémoire projet relue à chaque session (`CLAUDE.md`) [A1] | Fiche vivante, consignes d'équipe | Interface des consignes ; consignes alimentées par les contestations motivées |
| Mémoire automatique (retours de l'utilisateur, avec leur pourquoi) | — | Apprendre d'un « réponse fausse » ou d'un « utile », sans modifier les règles critiques sans gouvernance (Discovery §90) |
| Compétences chargées à la demande | Méthodes (7) | Des méthodes par métier et par expert ; des méthodes propres à une équipe |
| Contrôles déterministes autour des outils (hooks) | Garde-fous du harness | Des contrôles configurables par l'équipe (« toute connaissance sur des données personnelles passe en revue ») |
| Sous-agents au contexte isolé, lancés en parallèle | Mobilisation des jumeaux, l'un après l'autre | Consultation en parallèle ; experts comme sous-agents |
| Index du code préparé d'avance | Index cbm, connaissances | Enchaînements et schémas préparés par le gardien à chaque commit |
| Tâches longues en arrière-plan, avec notification | Gardien ; Travail | Une analyse lourde devenue tâche, avec accusé de réception immédiat et notification de fin (NFR §8) |
| Vérifier en agissant (tests, `grep`) | Recettes, juge d'appui | Tester une affirmation contre l'exploitation réelle (Datadog, incidents) |
| Interruption et réorientation en cours de route | — | Arrêter ou réorienter Flore pendant qu'elle travaille |
| Rendre compte en « testé / non testé » | « vérifié / selon / recoupé / non appuyé » | Rien d'essentiel : c'est fait |

---

# 4. Les trois écarts qui bloquent la vision

**4.1 Pas de données d'entreprise réelles.** Toute l'intelligence de Méridian repose sur le croisement des sources
(Sources v1 §1 : le code dit ce qu'elle fait, la documentation ce qu'elle doit faire, l'exploitation comment elle
échoue). Aujourd'hui, une seule nature de source tourne : le code de 4 dépôts de démonstration. Sans un vrai
Confluence, un vrai Jira et un vrai ServiceNow :
- pas de recoupement à grande échelle ;
- pas de contradictions réelles ;
- pas d'émergence ;
- pas d'impact entre applications.

C'est le premier verrou. Il n'est pas technique : il faut des comptes, des périmètres et un accord de la banque.

**4.2 Pas d'identité ni de modèle souverain.** Sans identité (OIDC, rôles de l'Architecture §6.1), on ne peut ni
montrer à chacun ce qu'il a le droit de voir, comme Glean et Rovo, ni faire valider par la bonne personne. Sans
modèle hébergé au Canada (Bedrock), aucun code bancaire ne peut être lu. Ces deux points conditionnent tout
déploiement réel.

**4.3 La boucle s'arrête à « comprendre ».** La boucle de la Vision §15 se poursuit par *faire émerger, investiguer,
décider, apprendre*. Les documents de conception sont riches (Investigation & Decision Engine, Learning Model),
mais le code n'a ni investigation outillée (hypothèses mises à l'épreuve, options comparées avec leurs preuves), ni
mémoire de décision (ce qu'on a décidé, ce qu'on attendait, ce qui s'est passé). Le cas d'usage phare de la Vision
(§9 : « Qu'est-ce qui changerait si nous retirions TBT ? ») n'est donc pas encore possible de bout en bout.

---

# 5. Ce que Méridian fait déjà mieux que l'industrie

Les recherches menées pour ce document et pour la v3 n'ont trouvé **aucun produit qui revendique** ces garanties.
Elles sont la base de la différence de Méridian, et il faut les garder :

1. **Chaque flèche d'un schéma est prouvée par sa ligne de code**, et une flèche non prouvée n'est pas dessinée.
2. **Chaque connaissance a un état de vérification explicite** : vérifié, d'après une seule source, recoupé,
   contesté, en partie, non appuyé. Elle n'est jamais simplement « vraie ».
3. **M3 exige une concordance réelle entre deux systèmes indépendants**, pas leur simple présence.
4. **Une confirmation de l'équipe ne peut pas être inventée** : un contrôle déterministe le refuse.
5. **Ce que l'on ignore est dit**, et ce que sa preuve n'appuie pas sort de la présentation.

Ce sont des propriétés de **confiance**. Dans une banque, elles valent plus qu'une réponse plus rapide ou plus
éloquente.

**Depuis le 2026-10-28, la garantie 3 est vraie au sens strict — et c'est exactement pourquoi il n'y a plus aucune
connaissance recoupée.** Un fichier Markdown du dépôt n'est plus un système indépendant ; le seul chemin vers M3
exige donc une source d'un autre type, et aucune n'est branchée. Le mécanisme est désormais plus honnête que
flatteur, ce qui est le but, mais il ne produit rien tant que Confluence ou Jira ne sont pas connectés.

---

# 6. Feuille de route proposée

Chaque étape a un critère vérifiable. On ne la déclare pas « faite » sans le critère.

**Horizon 1 — rendre réel (0 à 1 mois)**

| Étape | Critère |
|---|---|
| Brancher **un** vrai Confluence et **un** vrai Jira sur une application pilote | ≥ 50 connaissances recoupées entre deux systèmes ; ≥ 1 contradiction réelle tranchée par l'équipe |
| Identité OIDC et rôles (Architecture §6.1) ; consignes, revues et contradictions réservées aux bons rôles | Un test prouve qu'un `VIEWER` ne peut ni valider ni poser de consigne |
| Bedrock (ca-central-1) comme modèle pour le code bancaire ; routage par sensibilité du dépôt | Une application bancaire pilote analysée sans appel à DeepSeek (journal à l'appui) |
| Évaluation et banc de latence à chaque changement de méthode ou de modèle | Tendance publiée ; une régression bloque la fusion |

**Horizon 2 — exploiter (1 à 3 mois)**

| Étape | Critère |
|---|---|
| Investigation outillée : impact entre applications à partir des relations du Mesh et du graphe d'appels | « Que se passe-t-il si X tombe ? » rend une note d'impact où chaque effet a sa preuve |
| Analyse lourde transformée en tâche : accusé immédiat, étapes en direct, notification de fin | NFR §8 tenu : accusé < 2 s, progression < 3 s |
| Gardien qui prépare enchaînements et schémas à chaque commit | « Illustre la fonctionnalité X » en < 3 s pour les routes préparées |
| Premiers experts (architecture, données, sécurité), selon la Vision §7 : domaine, outils, critères de preuve, limites | Un expert sécurité signale au moins un risque réel prouvé sur une application pilote |
| Consignes d'équipe dans l'interface ; une contestation motivée devient une consigne confirmée | ≥ 1 consigne par application pilote, chacune avec son pourquoi |

**Horizon 3 — apprendre et faire émerger (3 à 6 mois)**

| Étape | Critère |
|---|---|
| Retour d'usage sur chaque réponse (utile, faux, déjà su) qui alimente l'évaluation et les méthodes, sous gouvernance | Taux de « faux » en baisse, mesuré |
| Mémoire de décision : options, preuves, effet attendu, effet observé (Learning Model) | Une décision relue 30 jours après, avec son effet observé |
| Émergence : anomalies et opportunités tirées de l'exploitation réelle (Datadog, ServiceNow) | ≥ 1 situation utile par semaine qu'aucun humain n'avait signalée |
| Méridian en MCP, en lecture seule, avec les droits de l'appelant (v3 §3) | Un agent de code reçoit, avec ses preuves, la règle validée qui s'applique à la ligne qu'il modifie |
| Questions adressées : une inconnue importante devient une question à la bonne personne (v3 §7) | Indicateur *Unknown Reduction* (Stratégie §163) en baisse |

---

# 7. Ce qu'il ne faut pas copier

- **Le RAG par embeddings comme colonne vertébrale.** Pour comprendre le code, les trois expertises consultées
  (recherche, RAG, architecture) ont convergé : la structure doit venir de l'analyse statique, et l'équipe de Claude
  Code est rapportée avoir abandonné la base vectorielle au profit de la recherche agentique [C5].
- **Le juge LLM comme seule vérification.** Ses notes varient selon le modèle juge [V3]. Chez Méridian, le
  déterministe passe d'abord, et le juge ne sert que pour le sens.
- **« Zéro hallucination » comme slogan.** Aucun chiffre publié ne l'étaye chez ceux qui l'affichent [C2]. Méridian
  doit afficher ses mesures (évaluation, part de connaissances recoupées), pas une promesse.
- **Agir sans gouvernance.** La Vision (§16) et l'Architecture (§1) le refusent. L'action viendra sous forme de
  brouillon validé par l'équipe.

---

# 8. Sources

Mesures et constats internes : `backend/jumeau/` (evaluation.py, latence.py, recoupement.py, appels.py,
schemas.py, flux.py), commits de la branche `jumeau-phase0` du 2026-10-28.

- [G1] Futurum Group, *Glean Doubles ARR to $200M. Can Its Knowledge Graph Beat Copilot?* — https://futurumgroup.com/insights/glean-doubles-arr-to-200m-can-its-knowledge-graph-beat-copilot/ (analyste, avril 2026)
- [G2] *Glean review 2026* — https://aiagentrank.io/blog/glean-review-2026 (revue secondaire)
- [R1] Atlassian, *Rovo* — https://wac-cdn.atlassian.com/software/rovo ; *Team '26* — https://www.atlassian.com/blog/company-news/rovo-team-26 (sources commerciales)
- [R2] Atlassian Community, *Getting started with Rovo* — https://community.atlassian.com/forums/Training-Certification-articles/Q-amp-A-from-Getting-started-with-Rovo-and-Find-and-use-AI/ba-p/3264233
- [C1] CodeBoarding — https://dev.to/brovatten/codeboarding-interactive-diagrams-of-code-2bbe
- [C2] Swimm, analyse statique — https://swimm.io/blog/how-swimm-uses-static-analysis-to-generate-quality-code-documentation ; https://swimm.io/how-it-works
- [C3] CodeWiki (arXiv 2510.24428) — https://arxiv.org/html/2510.24428v5 ; DocAgent (Meta) — https://arxiv.org/html/2504.08725v2
- [C4] InfoQ, *Google Code Wiki* — https://www.infoq.com/news/2025/11/google-code-wiki
- [C5] *Why coding agents still use grep* — https://yage.ai/share/why-coding-agents-still-use-grep-en-20260327.html
- [V1] Google Cloud, *Check grounding* — https://cloud.google.com/generative-ai-app-builder/docs/check-grounding
- [V2] Anthropic, *Introducing Citations on the Anthropic API* — https://claude.com/blog/introducing-citations-api
- [V3] MermaidSeqBench — https://arxiv.org/html/2511.14967v1
- [A1] Anthropic, glossaire Claude Code — https://code.claude.com/docs/en/glossary ; architecture du harness (secondaire) — https://mer.vin/linkedin/claude-code-architecture-explained-six-harness-layers-beyond-the-llm-linkedin/
- [D1] Pluto Security, *Inside Claude Artifacts* — https://pluto.security/blog/inside-claude-artifacts-how-your-agent-publishes-to-the-web/

Les descriptions de Glean et de Rovo viennent de sources secondaires ou commerciales. Elles sont données comme
« rapportées » et restent à confirmer dans leur documentation technique.
