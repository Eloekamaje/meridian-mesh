# MÉRIDIAN — Plan de remédiation
## Rendre vraies les étiquettes, puis les mécanismes, puis la démonstration

**Statut :** Proposition, à valider
**Version :** 1.6 — lots 0 à 2 exécutés, deux points clos par un constat ; état en §0bis
**Date :** 2026-10-28
**Documents liés :** Écarts Intelligence v1, Jumeau Harness Agentique v3, Architecture Jumeau v1, Jumeau Sources v1
**Origine :** trois audits adversariaux du code et des données (Postgres `meridian`, Mongo `meridian_db`, cache
d'index, sessions persistées), chacun avec ses preuves `fichier:ligne` ou ses `SELECT`. Les constats marqués
**vérifié** ont été reproduits à la main sur cette machine ; un constat de l'audit a été **corrigé** (§9).

**Tagline :** **DÉCOUVRIR · COMPRENDRE · DÉCIDER**

---

# 0. Le diagnostic en trois phrases

Les mécanismes existent et travaillent ; ce sont les **étiquettes** qui sont en avance sur eux. Chaque mot fort du
produit — *vérifié*, *recoupé*, *relu*, *schéma vérifié flèche par flèche*, *2 s* — désigne aujourd'hui un mécanisme
réel qui garantit **moins** que ce que le mot promet. Pour un produit qui vend la discipline de ne pas surestimer ce
qu'on sait, c'est le défaut le plus grave possible, et c'est aussi le moins coûteux à corriger.

Deux règles gouvernent tout ce plan :

1. **Une correction n'existe que si un test échoue avant et passe après.** Le dépôt a 442 tests verts ; la
   discipline est déjà là, il suffit de l'appliquer aux promesses.
2. **On n'ajoute aucune capacité avant la fin du lot 1.** Pas de MCP, pas de sous-agents parallèles, pas de nouvelle
   interface, pas de nouveau prédicat. Chaque capacité ajoutée multiplie la surface non vérifiée.

---

# 0bis. État d'avancement (2026-10-28)

| Lot | État | Preuve |
|---|---|---|
| **0 — Honnêteté** | **fait** | `jumeau/tests/test_honnetete.py` (10 tests) + `frontend/src/lib/marqueRelecture.test.js` et `origineFlore.test.js` (5 tests) ; suite `jumeau` : **457 passés, 0 échec** |
| L0.1 `relu` conditionnel | fait | `ETATS_RELECTURE` ; une relecture en panne s'affiche « non relu » |
| L0.2 `corrige` = texte changé | fait | `reviser()` rend `corrige` faux si la révision échoue ou ne change rien |
| L0.3 « non relu » à l'écran | fait | `MarqueRelecture` lit `relecture_etat` |
| L0.4 plus d'étape inventée | fait | `FloreActivite` n'affiche plus de libellés fabriqués ; une activité sans étape dit « Aucune étape enregistrée » |
| L0.5 réponses de démonstration marquées | fait | `jumeau/origine.py` + `MarqueOrigine` ; les indicateurs écrits à la main ne sont plus affichés |
| L0.6 premier mot horodaté | fait | `durees.premier_texte` posé par `flux.en_flux` ; « 2 s » retiré des Écarts |
| **0bis — L'index** | **fait, un point ouvert** | |
| L0bis.1 preuve = ligne d'appel | fait | `appels.ligne_d_appel` exige une construction d'appel ; sur Conduit, **56 des 176 lignes** que l'ancienne règle retenait ne contenaient aucun appel |
| L0bis.2 JSON + résolution | fait | `search_graph` et `trace_path` en `format="json"` ; l'arête porte `resolution` (lsp/heuristic) et `confiance` |
| L0bis.3 index reconstructible | **partiel** | l'ingestion réindexe déjà à chaque passe, et une relecture impossible dit maintenant quoi faire (`ingerer.py`) ; **reste ouvert** : versionner l'index avec le commit plutôt que de le laisser dans un cache indexé par chemin absolu |
| L0bis.4 index absent signalé | fait | `cbm.indexe()` ; Flore dit « index de code de ce dépôt non disponible, il se reconstruit à la prochaine ingestion » au lieu d'« Outil indisponible » |
| **1 — Épistémologie** | **fait** (un point clos par un constat) | suite `jumeau` avec Postgres : **552 passés, 0 échec** |
| L1.1 recette non circulaire | fait | `adaptateur` n'appelle plus `recettes` ; la preuve vient de l'index (`start_line`) ou d'une règle de déclaration propre, la recette juge ensuite — elle peut donc le contredire |
| L1.2 le déterministe ne s'efface plus | fait | la recette s'exécute même avec plusieurs systèmes ; deux systèmes dont l'extrait passe donnent `recoupe` **déterministe** |
| L1.3 M3 hors du dépôt | fait | `systeme_de_preuve` = type de la source, au Python **et** en SQL ; **les 9 M3 sont tombées à M2** (vérifié sur la base réelle : 546 M2, 0 M3) |
| L1.4 concordance déterministe | **clos avec un constat** | `copie` est calculée (recouvrement de mots ≥ 0,85) et ne peut que retirer le recoupement. Au-delà, la comparaison lexicale **ne peut pas** servir de veto : une ligne de code ne répète pas les mots d'une phrase métier, et deux tests de recoupement légitime sont tombés quand je l'ai essayé. L'observation (« tel système ne nomme pas l'énoncé ») est enregistrée avec le verdict, jamais utilisée comme condition |
| L1.5 preuves remplacées | fait | une preuve du même fichier remplace l'ancienne ; `recouper` refuse dès qu'un système est déjà représenté (plus d'empilement) |
| L1.6 aucun état manquant | fait | état `en_attente` posé à la naissance (trigger), maturité recalculée à la clôture : **0 connaissance sans état** (557 rattrapées), **0 M3 close** |
| L1.7 juge distinct | fait | `JUMEAU_MODELE_JUGE` sépare le modèle du juge ; une décision manquante est comptée (`pannes`) dans le bilan de la passe et journalisée en avertissement |
| **1bis — La compréhension** | **fait, un point refusé** | `jumeau/tests/test_prouvables.py` (4 tests) |
| L1bis.1 extracteur `cross_service` | **non fait, mesuré** | voir §2bis : **aucun** appel HTTP sortant vers une application nommée dans les quatre dépôts ; le mode `cross_service` de l'index rend la même liste que `calls` |
| L1bis.2 prédicats non prouvables | fait | règle d'autorité : une phrase sur le métier prouvée **uniquement par du code** reste M1. Base réelle : **398 faits établis, 148 hypothèses** (APPLIQUE_REGLE 45, REALISE_CAPACITE 33, DETIENT 28, SERT_ACTEUR 26, ECHANGE_AVEC 15, RISQUE 1) |
| **2 — Démonstration** | **fait, un point partiel** | suite `jumeau` avec Postgres : **552 passés, 0 échec** |
| L2.1 deux univers distincts | fait | l'API porte `origine: reel \| demonstration` ; l'Atlas cercle en pointillé les jumeaux de démonstration ; la page Jumeaux a la vue « Nés d'une vraie source » |
| L2.2 vérité de référence | fait | `jumeau/references/<jumeau>.json` ; 5 couples pour Conduit, écrits à la main. L'exactitude n'est plus `null` dès qu'un jumeau a ses références |
| L2.3 chiffres inventés | fait | aucun indicateur d'un chemin non calculé n'est affiché (`origine.ORIGINES_SANS_MESURE`) ; la couverture de situation du gardien ne ment plus |
| L2.4 banc publié | fait | le banc passe par le chemin de l'écran et chronomètre le premier mot ; relevé daté dans `MERIDIAN_Latence_2026-10-28.md` (1 question sur 4 tient l'objectif, aucune réponse complète sous 5 s) |
| L2.5 connecteurs | fait | 6 branchés, 6 refusés explicitement (`non_branche`) ; le catalogue expose `branche` |
| L2.6 découverte des sources | fait | la liste écrite d'avance est retirée : la découverte se déclare `non_branchee` |
| L2.7 couverture calculée | fait | part de ce qui est **établi** : Conduit 49 %, Gestion des articles 83 %, Méridian 76 % — au lieu de 32 % pour tous |

---

# 1. Lot 0 — Honnêteté immédiate (1 jour, risque nul, aucun appel de modèle)

Objectif : **aucune étiquette affichée ne dépasse ce que le mécanisme garantit.** Tout est réversible, rien ne change
de comportement fonctionnel.

| # | Correction | Fichier | Critère |
|---|---|---|---|
| L0.1 | `relu` n'est plus posé en dur. Introduire `relecture_etat ∈ {ok, objections, indisponible, non_executee}` ; `relu = (etat in {ok, objections})` | `jumeau/flore.py:279` | test : relecteur qui lève → `relu = False`, `relecture_etat = "indisponible"` |
| L0.2 | `corrige` seulement si le texte a réellement changé (comparaison avant/après) ; une révision qui échoue ne produit pas « corrigé à la relecture » | `jumeau/flore.py:258-266` | test : révision qui lève → texte inchangé, `corrige = False` |
| L0.3 | Le panneau de Flore n'annonce plus d'étape qui n'a pas eu lieu : plus de `relire_sans_risque` silencieux, plus d'étape inventée | `jumeau/flore.py:97-103`, `jumeau/contradicteur.py:109-118` | une relecture sautée est dite « non relue » à l'écran |
| L0.4 | L'interface ne fabrique plus d'activité terminée : sans étape réelle, « aucune étape enregistrée » | `frontend/.../OngletTravail.jsx:698-700`, `components/FloreActivite.jsx:6-14` | test : `etapes.length === 0` → aucun libellé coché |
| L0.5 | Les réponses scriptées sont **marquées** : `origine: "scenario"` + badge « réponse de démonstration » ; les indicateurs inventés sont retirés ou calculés | `server.py:1356-1362`, `seed_data.py:502`, `components/FlorePanel.jsx:416` | test : une réponse de `AURORA_SCRIPTS` porte `origine = "scenario"` |
| L0.6 | Les latences ne sont plus affirmées : horodater le premier delta `texte` dans `flux.en_flux`, et retirer « 2 s » des documents tant qu'aucun banc ne le produit | `jumeau/flux.py`, `docs/MERIDIAN_Ecarts_Intelligence_v1.md:42,67` | un champ `premier_texte` existe dans `durees` et est renseigné |

**Ce que ça coûte :** rien de fonctionnel. **Ce que ça rapporte :** le produit cesse de mentir à l'écran, ce qui est
la seule chose qu'un comité d'architecture vérifie en premier.

---

# 1bis. Lot 0bis — L'index doit être reconstructible et son absence visible (2 à 3 jours)

**Diagnostic corrigé (2026-10-28, vérifié deux fois).** L'audit du moteur concluait que l'index de code était en panne
et que les outils de lecture étaient muets. **C'est faux, et la cause de l'erreur est instructive** : le binaire
ouvre ses bases SQLite en écriture (verrous, WAL) même pour une simple lecture. Sous un montage en lecture seule
hors du dépôt, il échoue sur `could not load saved runtime settings` ; exécuté avec un accès normal, il répond :

```bash
$ codebase-memory-mcp cli --quiet list_projects        # 6 projets
$ cbm.interroger("…copies-conduit")                    # {'routes': 27, 'paquets': 0, 'variables': 2, 'images': 1}
```

Le cache de configuration avait d'ailleurs **zéro ligne** : il n'était pas corrompu, il était illisible faute de
droits d'écriture. Il n'y a donc **pas de P0 « moteur cassé »**. Restent quatre défauts réels, dont un grave.

| # | Correction | Critère |
|---|---|---|
| L0bis.1 | **La preuve d'une flèche doit être la ligne d'appel, pas la première ligne qui nomme la fonction.** `appels.py:49-55` retient la première occurrence du nom et n'écarte que les lignes commençant par `#`, `//`, `"""`, `'''` : une chaîne de caractères ou un commentaire bloc (`/* */`, `<!-- -->`) devient le « fondement » d'une arête | une flèche dont la ligne citée ne contient pas de construction d'appel est rejetée |
| L0bis.2 | **Consommer `--format json` et `--include-evidence`** : `appels.py` parse aujourd'hui la sortie **texte** en regex et jette la confiance du résolveur | aucune citation de preuve issue d'un découpage de chaînes |
| L0bis.3 | **Rendre l'index reconstructible** : il vit dans un cache opaque indexé par **chemin absolu** (`index_code = home-majella-…-meridian-mesh`) ; un déménagement de répertoire le rend introuvable. Réindexer depuis le commit, ou versionner l'index avec le dépôt | `python -m jumeau.ingerer --depot <un des 4>` réussit sur une machine neuve |
| L0bis.4 | **Dire quand l'index manque** au lieu de laisser les outils répondre « Outil indisponible » (`agent.py:211-213`) | la fiche du jumeau, et Flore, signalent un index absent |

**Constat annexe, à verser au lot 1bis.** `cbm.interroger` rend `paquets: 0` sur un dépôt qui en a douze : le binaire
ne relie pas les dépendances de `pyproject.toml`. Les 243 `DEPEND_DE` de la base viennent donc de `manifestes.py`, le
contournement de 53 lignes — c'est-à-dire que **la seule famille de connaissances « vérifiée » par recette est produite
hors de l'index**. Cela renforce L1bis.1 plutôt que L0bis.

---

# 2. Lot 1 — L'épistémologie (8 à 10 jours) — le cœur

Objectif : **« vérifié » et « recoupé » deviennent vrais.** C'est le lot qui décide si Méridian est un produit de
confiance ou un pipeline annoté.

## L1.1 — La vérification n'est plus circulaire

**Constat.** `adaptateur.py:92` filtre l'extraction par la recette elle-même :

```python
"variables": _jeton("LIT_VARIABLE", "variable",
                    filtre=lambda l, v: recettes.recette("LIT_VARIABLE", v, [l]) == "verifie"),
```

La recette ne peut donc jamais échouer sur ces connaissances : elle rejoue la règle qui a fabriqué la preuve. Les 394
connaissances « vérifiées » ne portent aucune information de confiance.

**Correction.** L'extracteur choisit sa preuve selon l'index de code (cbm), sans appeler `recettes`. La recette
vérifie ensuite, indépendamment. Les trois autres prédicats passent par `localiser()` (`adaptateur.py:15`), qui
choisit la ligne contenant le jeton : même défaut de principe, à corriger de la même façon.

**Critère.** `test_recettes.py` contient des cas **négatifs** — des énoncés faux, correctement cités, qui doivent
échouer. Aujourd'hui il n'en contient aucun.

## L1.2 — Le déterministe ne s'efface plus

**Constat.** `recoupement.py:119` n'exécute les recettes que si `systemes == {"git"}` **exactement**. Dès qu'une
connaissance a une preuve « documentation », elle saute la recette et part au juge LLM. Le déterministe s'efface
précisément sur les connaissances qui portent la promesse de recoupement.

**Correction.** La recette s'exécute toujours qu'elle s'applique ; son verdict prime sur celui du juge pour les
prédicats couverts. Le juge ne tranche que là où aucune recette ne peut s'exécuter — c'est ce que la v3 §2 dit déjà.

**Critère.** une connaissance de prédicat couvert, avec deux systèmes, est vérifiée par recette et non par le juge.

## L1.3 — L'indépendance devient une propriété, pas une extension de fichier

**Constat.** `recoupement.py:28` et la fonction SQL `systeme_de_preuve` déclarent « documentation » tout `.md` du
dépôt. Les **9 connaissances M3** de la base sont toutes sur le jumeau `meridian`, et leur « second système
indépendant » est **le README ou le fichier de méthode du même dépôt, au même commit**. Exemple : connaissance 9332,
`MOTS_FICHE = 300` dans `gardien.py` face à « 300 mots au plus » dans `methodes/comprendre-application.md`.

**Correction.** L'indépendance exige deux `source.id` distincts, de `source.type` distincts, et **hors du même
dépôt**. La documentation interne au dépôt reste une preuve (elle appuie l'énoncé) mais n'est plus un système :
elle ne peut plus fonder M3.

**Critère.** la fonction SQL et son jumeau Python disent la même chose ; un test prouve qu'un `.md` du dépôt ne crée
pas de second système ; **les 9 M3 tombent à M2** — et c'est le résultat attendu, pas une régression.

## L1.4 — La concordance est calculée, la copie n'est plus une opinion

**Constat.** `juge.py` fait décider dans un même appel `appui`, `concordance` **et** `copie`, tous trois par
`deepseek-chat` — le modèle de l'auteur, avec sa clé (`gardien.py:361` transmet `agent.modele()`). Aucune ligne du
dépôt ne compare deux texte. Pire, le prompt **instruit** le juge que « deux systèmes différents sont indépendants,
sauf recopie » (`juge.py:32`), c'est-à-dire lui souffle la réponse.

**Correction.** Un contrôle déterministe minimal compare les extraits (recouvrement de tokens normalisés, passages
littéralement partagés). Recouvrement au-delà d'un seuil → `copie = true` → état `selon`, jamais `recoupe`, **sans
voix au chapitre du modèle**. Le juge garde le jugement sémantique d'appui, pas l'indépendance.

**Critère.** `copie` est forcé par le déterministe ; un test sur deux extraits identiques rend `selon`, même si le
juge répond « concordantes ».

## L1.5 — Les preuves se remplacent, elles ne s'empilent plus

**Constat.** `a_verifier` construit l'empreinte de **toutes** les preuves de soutien, tous commits confondus.
**225 connaissances courantes** portent des preuves de plusieurs commits ; une en porte **859**
(`REACT_APP_BACKEND_URL`). Conséquences : M3 peut s'obtenir en appariant une ligne du commit A avec un document du
commit B ; la fraîcheur des preuves perd son sens ; le juge reçoit des dizaines de versions historiques du même
fichier ; et la boucle re-vérifie sans fin (3 504 lignes de vérification pour 394 connaissances, ≈ 9 passes chacune).

**Correction.** Une preuve nouvelle sur le même `(claim, source, chemin)` **remplace** l'ancienne (colonne
`remplace_par`, ou clôture de l'ancienne) ; l'empreinte ne porte que sur les preuves courantes. Migration des 225
connaissances concernées.

**Critère.** une connaissance n'a qu'une preuve courante par couple `(source, chemin)` ; le nombre de re-vérifications
par passe devient stable ; une requête `SELECT` le prouve.

## L1.6 — Aucune connaissance sans état, aucune maturité orpheline

**Constat.** 50 des 546 connaissances courantes n'ont **aucune** ligne `verification`, alors que le document affirme
que chacune a un état explicite. Et 16 connaissances **clôturées** portent encore M3 : la fermeture ne recalcule pas
la maturité.

**Correction.** Une ligne `verification` en `etat = 'en_attente'` est créée à la naissance de la connaissance
(contrainte NOT NULL) ; `recalculer_maturite` est déclenché aussi sur la clôture.

**Critère.** `SELECT count(*) FROM claim WHERE NOT EXISTS (… verification …)` rend 0 ; aucune connaissance clôturée
n'est M3.

## L1.7 — Le juge n'est plus l'auteur, et une panne ne disparaît plus

**Constat.** Même modèle, même fournisseur, même clé pour l'auteur et le juge. Et un lot en panne abandonne
**12 connaissances en silence** : un `warning`, un `en_attente`, aucune remontée.

**Correction.** Le juge tourne sur un modèle d'une autre famille (ou d'un autre fournisseur) ; l'échec d'un lot est
compté dans le bilan de la passe et remonté dans la revue. `juge.py:72` explicite `tools=[]` comme
`contradicteur.py:122`.

**Critère.** une panne forcée du juge apparaît dans le bilan de la passe ; le modèle du juge diffère de
`JUMEAU_MODELE`.

---

# 2bis. Lot 1bis — La compréhension n'est pas encore dans le code (5 à 8 jours) — **P1 vérifié**

**L1bis.1 — l'extracteur d'échanges n'a pas été écrit, et voici pourquoi (mesuré le 2026-10-28).** Le mode
`cross_service` de l'index rend, sur Conduit, **exactement la même liste que `calls`** : il ne détecte aucune frontière
de service. Et un extracteur fondé sur les appels sortants à URL littérale ne trouverait rien : dans les quatre
dépôts, `requests|httpx|axios|fetch(...)` avec une URL `http(s)://` **rend zéro ligne**. Les deux seuls clients HTTP
existent, mais leur cible vient d'une variable d'environnement (`import.meta.env.VITE_API_URL`, `REACT_APP_BACKEND_URL`)
— ce n'est pas une application nommée. Écrire l'extracteur maintenant produirait soit rien, soit « échange avec une
variable de configuration » : ce serait exactement le genre de connaissance creuse que ce plan corrige.

**Constat, mesuré en base.** L'ingestion ne produit que **quatre familles** : routes, paquets, variables, images
(`cbm.py:8-14`). Toute la couche qui ressemble à de la compréhension est **écrite par le modèle**, jamais extraite :

| Prédicat | Origine | Nb (courantes) |
|---|---|---|
| `DEPEND_DE`, `EXPOSE`, `LIT_VARIABLE`, `EXECUTE_IMAGE` | `INGESTION` | **398** |
| `APPLIQUE_REGLE`, `REALISE_CAPACITE`, `DETIENT`, `SERT_ACTEUR`, `ECHANGE_AVEC`, `RISQUE` | **`CONVERSATION`** | **148** |

Autrement dit : « le jumeau sait ce que l'application fait pour le métier » signifie aujourd'hui « le modèle l'a
écrit, et une ligne quelconque a été citée ». C'est le constat le plus structurant des trois audits, parce qu'il
explique tout le reste : ces 148 connaissances ne peuvent pas être vérifiées par une recette, donc elles finissent
chez le juge, donc M3 s'obtient par opinion. Et l'outil qui pourrait les fonder **existe déjà et n'est pas utilisé** :
le binaire expose `mode="cross_service"` et `data_flow`, que `appels.py:37` n'appelle jamais.

| # | Correction | Critère |
|---|---|---|
| L1bis.1 | Un extracteur de **flux inter-applications** (`cross_service`) et un extracteur d'**appels sortants** (URL littérale dans `requests`/`fetch`/`RestTemplate`) | `ECHANGE_AVEC` a une origine `INGESTION` et une preuve d'appel |
| L1bis.2 | Les prédicats que le code ne peut pas prouver (`SERT_ACTEUR`, `APPLIQUE_REGLE`, `DETIENT`) sortent du jumeau et deviennent des **hypothèses** dans le Travail, pas des connaissances | aucun prédicat non prouvable n'est compté dans la maturité |
| L1bis.2 bis | Exception, Sources v1 §2 (« les règles qu'elle applique : code d'abord » ; « les informations qu'elle détient : données, code ») : `APPLIQUE_REGLE` et `DETIENT` passent M2 si une recette de **forme** (décision / déclaration de donnée dans les lignes citées, chaînes et commentaires ignorés) ET le juge d'appui (« oui ») concordent ; la forme prouve la forme, le juge le sens, aucun des deux seul. `SERT_ACTEUR`, `REALISE_CAPACITE`, `ECHANGE_AVEC`, `RISQUE` restent M1 sans source documentaire | forme échouée = M1, dite dans l'état de vérification |
| L1bis.3 | Les trous connus de l'extracteur sont traités, pas contournés : injection de dépendances (`Depends`), SQL externalisé, imports dynamiques | au moins un cas test par trou |
| L1bis.4 | Lever le plafond dur de volumétrie : `LIMITE = 10000` fait **échouer toute l'ingestion** d'un dépôt d'entreprise (`cbm.py:75`), au lieu de dégrader | un dépôt à 20 000 routes s'ingère, tronqué et signalé |

---

# 3. Lot 2 — La démonstration (3 à 5 jours)

Objectif : **le spectateur peut distinguer une réponse calculée d'une réponse récitée, et deux jumeaux réels de
quarante-deux jumeaux inventés.**

| # | Correction | Critère |
|---|---|---|
| L2.1 | Séparer visiblement les deux univers : démonstration (Mongo, 42 jumeaux de seed) et réel (Postgres, 4 jumeaux). Aucune vue ne les mélange sans le dire | l'Atlas affiche son origine ; un jumeau de démonstration porte un badge |
| L2.2 | Une vérité de référence pour l'évaluation : faute de connaissances validées (il y en a **une**), le jeu d'exactitude ne peut pas se déduire du jumeau. Écrire les questions/réponses attendues à la main, 5 par jumeau | `evaluation.scores.exactitude` n'est plus `null` |
| L2.3 | Supprimer ou calculer les indicateurs inventés (`confiance: 84, couverture: 76, fraicheur: "il y a 3 min"`) | aucun chiffre affiché sans requête qui le produit |
| L2.4 | Publier le banc : premier texte et total, p50/p95, relevé daté et versionné dans le dépôt | plus aucun chiffre de performance cité hors du banc |
| L2.5 | Les **12 connecteurs** de l'interface : 5 ont une implémentation, et `_simuler_test` (`server.py:1063-1074`) rend `{"statut": "prete"}` sans le moindre paquet réseau — il peut donc déclarer prête une source PostgreSQL qui n'existe pas | un connecteur non implémenté est dit « non branché » |
| L2.6 | La « découverte automatique des sources » est une **liste codée en dur** (`server.py:1240-1255` : « PostgreSQL Settlement », « Oracle Clearing »…) | la découverte rend ce que les sources déclarent, ou rien |
| L2.7 | `registre.couverture` est une formule (`min(20 + 12*nb_sources, 88)`) appliquée avec `couverture(1)` : **tout jumeau réel affiche 32 %** quel que soit son contenu | la couverture est calculée sur les connaissances vérifiées |

---

# 4. Lot 3 — Ce qui manque pour que ce soit un produit (à discuter, pas à coder)

Ces points ne s'ouvrent **qu'après** le lot 1. Brancher une vraie source avant de réparer M3 reviendrait à alimenter
la même machine défaillante, mais à l'échelle d'un vrai Confluence.

1. **La première source réelle** (Confluence, Jira), avec le critère des Écarts : ≥ 50 connaissances recoupées entre
   deux systèmes **réellement distincts**, et ≥ 1 contradiction tranchée par l'équipe.
2. **Le positionnement.** Le document d'écarts mise sur la compréhension et le Mesh ; l'actif réel est la **trace de
   ce que l'entreprise croit sur son SI, qui l'a confirmé, et quand la croyance a vieilli**. C'est un produit de
   conformité et d'audit (E-23, B-13, journal d'audit) — vendable plus tôt, et cohérent avec la contrainte bancaire.
3. **Le ratio de gouvernance.** 546 connaissances, **1 validation**. Le bon indicateur n'est pas « combien produites »
   mais « combien exigent une attention humaine ». Tant que ce ratio n'est pas d'un ordre de grandeur soutenable, le
   produit crée le travail qu'il prétend supprimer.
4. **Les plafonds silencieux.** `MAX_ESPACES = 250` (Confluence), `MAX_PROJETS = 250` (Jira), `MAX_CI = 250`
   (ServiceNow), `MAX_SERVICES = 100` (Datadog), `_memo` qui vide tout le cache à 500 entrées et
   `MAX_APPELS_MINUTE = 30` par jeton : une banque a des milliers d'espaces, et le dépassement **n'est pas dit à
   l'agent**. Le lecteur voit 250 pages et croit avoir tout vu. La dégradation doit être visible dans la réponse.
5. **L'authentification et les droits.** Trois schémas Basic, aucun OAuth 2.0 ni mTLS ni SSO ; `tenant_id` en dur à
   `"local"` (`naissance.py:290`), **aucune politique RLS, aucun `GRANT`** — la colonne est un filtre, pas une
   frontière ; et surtout `chercher_dans` rend à l'agent le contenu d'une page Confluence **sans vérifier que
   l'interlocuteur aurait le droit de la lire dans Confluence**. En banque, ce n'est pas une lacune d'architecture,
   c'est le point qui bloque le déploiement.
6. **La minimisation.** `masquer` (`lecteurs.py:33-41`) ne connaît ni IBAN, ni numéro de compte, ni nom de personne,
   alors que tout ce qui est lu part vers un modèle externe. À traiter avant toute source réelle, pas après.

---

# 5. Ce qu'on ne fait pas

- Pas de MCP, pas de sous-agents parallèles, pas de mémoire de décision, pas de nouveaux experts : ce sont les
  mécaniques d'un autre produit (le lot 1 change la nature du produit ; le reste attend).
- Pas de nouveau prédicat tant que les quatre existants ne sont pas vérifiables par un test négatif.
- Pas de nouveau connecteur avant que M3 ne puisse plus être obtenu sans source externe.
- Pas de chiffre dans un document qui ne vienne d'une requête ou d'un banc.

---

# 6. Ce qu'on garde absolument

Le plan détruit une partie du récit ; il ne touche pas à ce qui fait la valeur :

- les **citations vérifiées au commit** contre la source réelle (`contradicteur.py:64-87`) — c'est déjà rare ;
- « **validé par l'équipe** » contrôlé **sans modèle** (`contradicteur.py:98-106`) — c'est exactement la bonne idée ;
- la **charte** et son honnêteté (« confirmé par l'équipe seulement pour une connaissance validée ») ;
- les **invariants en base** (trigger `claim_accepte_exige_revue`, immuabilité des preuves) — la confiance est portée
  par le schéma, pas par la bonne volonté ;
- la **recherche agentique** plutôt que les embeddings — le choix est juste et défendu ;
- les **lecteurs réels** (HTTP authentifié, refus d'hôte non public, version de document) — il ne leur manque qu'un
  vrai compte ;
- les **442 tests verts** — c'est l'infrastructure qui rend ce plan exécutable.

---

# 7. Critères de sortie du plan

Le plan est terminé quand ces sept phrases sont vraies, chacune vérifiable par une commande :

1. Aucune étiquette affichée ne promet plus que son mécanisme — et un test le dit.
2. Aucune connaissance ne peut être `recoupée` sans **deux sources de types distincts, hors du même dépôt**.
3. Une affirmation **fausse mais correctement citée** est refusée par un test.
4. Un spectateur distingue à l'écran une réponse calculée d'une réponse récitée, et un jumeau réel d'un jumeau de
   démonstration.
5. **Le jumeau est reconstructible** : l'index se refait depuis le commit, sur une machine neuve, sans cache opaque.
6. **Aucune connaissance n'est comptée comme compréhension si seule la conversation l'a produite** : la maturité ne
   s'applique qu'à ce que le code prouve ; le reste est hypothèse, et se dit tel quel.
7. Le document d'écarts peut être défendu ligne par ligne devant un comité, sans qu'aucune de ses phrases ne soit
   contredite par son propre code.

---

# 8. Ce que l'audit du moteur a changé au plan

Trois conséquences, dans l'ordre d'importance :

1. **Un P0 est apparu, que les deux premiers audits ne voyaient pas** : le socle d'index ne sait plus réingérer.
   `naissance` et la réingestion du gardien sont mortes ; les outils de lecture de Flore vivent encore, sur un index
   périmé et non reconstructible. Sans le lot 0bis, les lots 1 et 1bis répareraient la vérification d'un moteur qui
   ne peut plus apprendre.
2. **Le lot 1bis devient aussi important que le lot 1.** On savait que la vérification était faible ; on sait
   maintenant **pourquoi** : 148 des 546 connaissances courantes ne viennent pas du code mais du modèle. Réparer le
   juge sans réparer l'extraction reviendrait à mieux noter des affirmations que personne n'a extraites.
3. **Le lot 3 s'alourdit avant la première source réelle.** Droits par lecteur, minimisation (IBAN, noms), plafonds
   silencieux et multi-tenant ne sont pas des finitions : ce sont des conditions d'entrée chez un client bancaire.

---

# 9. Correction apportée à un constat d'audit

L'audit du moteur concluait que l'index était en panne, que les cinq outils de code étaient muets et que le cache de
configuration était illisible. **La vérification montre que c'était un artefact d'environnement, pas un défaut du
produit** : le binaire ouvre ses bases SQLite en écriture même pour lire, donc un montage en lecture seule le fait
échouer sur `could not load saved runtime settings`. Hors de ce montage, `list_projects` rend 6 projets et
`cbm.interroger` rend 27 routes pour Conduit. Le cache n'était pas corrompu (table `config` vide, ce qui est l'état
normal).

Conséquence sur le plan : le « P0 moteur cassé » **disparaît**, et le lot 0bis se réduit aux quatre défauts réels
(preuve de flèche, JSON du résolveur, index reconstructible, absence d'index signalée). Deux enseignements en
tirent :

1. **Un audit mené sous contrainte de sandbox doit le déclarer.** La leçon vaut pour ce document : toute mesure
   d'exécution produite ici est suspecte si elle touche un chemin hors du dépôt.
2. **Un cache opaque qui échoue sans dire pourquoi reste un vrai défaut de produit** — non parce qu'il est cassé,
   mais parce que sa panne ressemble à une panne de modèle (« Outil indisponible pour ce dépôt »). L0bis.4 le
   corrige.

Second point laissé ouvert, faute de compte réel : la validité actuelle des endpoints Atlassian
(`/wiki/rest/api/search` en CQL v1) et Datadog (`/api/v1/service_dependencies`, historique) n'est pas confirmée. Ce
sont des **risques signalés**, pas des faits établis.

