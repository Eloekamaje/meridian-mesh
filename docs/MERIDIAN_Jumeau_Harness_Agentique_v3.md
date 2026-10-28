# MÉRIDIAN — Le harness du jumeau, v3
## Ce que la correspondance avec Claude Code avait mal compris, et ce qu'elle avait oublié

**Statut :** Proposition, à valider. Les §4, §5 et §6 sont implémentés sur la branche `jumeau-phase0`
**Version :** 3.0
**Date :** 2026-10-28
**Documents liés :** Jumeau Harness Agentique v1 (§5 correspondance) et v2, Architecture Jumeau v1 (§1, §6),
Jumeau Sources v1, Product Strategy v2 (§64, §162–165), Discovery Maturation Engine (§89–90), Domain Model (§5, §6.3)
**Tagline :** **DÉCOUVRIR · COMPRENDRE · DÉCIDER**

---

# 0. Objet

La v1 (§5) a posé une formule qui tient toujours : *le jumeau n'est pas un agent ; c'est l'espace de travail que des
agents habitent, et Méridian est le harness*. La v2 a repris les cinq fonctions d'un harness. Ce document met
la **correspondance** elle-même à l'épreuve, ligne par ligne. Trois lignes ont mal compris le mécanisme de
Claude Code. Trois mécanismes manquent.

La règle de la v2 reste en vigueur : *le savoir-faire va dans les méthodes, l'agent juge et agit par ses outils,
le harness ne garde que les garde-fous ; une décision se rend structurée, jamais par « fait ».*

Un fait mesuré motive ce document. Sur les 525 connaissances courantes de la base locale, **une seule est
validée**, et toutes les autres sont M2. La propriété « Gouvernance » de l'Architecture §1 n'a donc, en
pratique, aucun effet.

---

# 1. Correspondance corrigée

| Claude Code | v1 (§5.1) | v3 |
|---|---|---|
| Demandes de permission | Revue humaine de **chaque** Claim | **Vérifier comme on teste** (§2) : recettes, juge d'appui, recoupement ; l'humain ne garde que les décisions |
| `CLAUDE.md` | La fiche vivante, régénérée à chaque commit | Deux objets : la **fiche** (générée, l'équivalent d'un index) et les **consignes du jumeau** (écrites par l'équipe, §5) |
| Où vit l'agent | Dans Méridian | Là où l'on travaille déjà : le jumeau s'expose aussi en **MCP**, en lecture seule (§3) |
| Mémoire « vraie quand elle a été écrite » | — | **Vérifier avant de citer**, y compris la fraîcheur des versions (§4) |
| Poser une question quand on est bloqué | — | Les inconnues deviennent des **questions adressées** à l'équipe (§7) |
| Évaluations | ❌ (v1 §4) | **Jeu de référence** tiré du jumeau lui-même, rejoué à chaque changement (§6) |

---

# 2. Vérifier comme on teste : recettes, juge d'appui, recoupement

**Ce que la v1 avait compris.** Les demandes de permission y correspondaient à la validation humaine de chaque
Claim (Architecture §1 : « l'équipe propriétaire valide ; aucun agent ne valide »).

**Ce que fait Claude Code.** Il ne demande pas à l'utilisateur de valider un fait. Il le vérifie lui-même, et il
préfère l'exécution à l'opinion : un `grep` plutôt qu'un souvenir, un test plutôt qu'un avis. L'auteur n'est
jamais son propre juge : un relecteur au contexte neuf relit le travail. Un rapport reste une affirmation et non
un fait : Claude relance les tests après la fusion. Il rend compte en « testé / non testé » et revérifie en
continu. L'humain décide ; il ne vérifie pas.

**Constat (code et données, 2026-10-28).** La maturité M3 compte les **systèmes** des preuves. Rien ne vérifie
que deux preuves disent **la même chose**, alors que l'Architecture Jumeau définit M3 comme « deux sources
indépendantes **concordantes** ». Rien ne vérifie non plus qu'une ligne citée appuie bien l'énoncé : le gardien
(`clore_sans_preuve`) vérifie seulement que la ligne existe. Les 10 343 preuves sont toutes du code, et 397 des
525 connaissances viennent de l'ingestion.

**Règle.** Chaque connaissance est vérifiée comme on teste, à la manière d'un journaliste qui recoupe ses sources :

1. **Recettes déterministes**, sans modèle : la ligne citée contient-elle bien l'objet de la connaissance, au
   commit ? Elles s'appliquent aux dépendances, aux interfaces exposées, aux variables lues et aux images. Le
   résultat est **vérifié** ou **non appuyé**.
2. **Juge d'appui**, uniquement là où aucune recette ne s'exécute (règles, acteurs, capacités, échanges, données
   détenues). Un agent sans outils, sur un fil vierge et distinct de l'auteur, lit l'énoncé et les extraits cités.
   Il rend une décision structurée : la preuve l'appuie, l'appuie en partie, ou ne l'appuie pas. Une seule source
   qui l'appuie donne **selon le code** (ou selon Confluence…).
3. **Recoupement** : deux systèmes **indépendants** qui appuient chacun l'énoncé, et qui se concordent, donnent
   **recoupé**, et c'est **le seul chemin vers M3**. Une source qui recopie l'autre ne compte qu'une fois
   (Knowledge Claims §11–15). Deux sources discordantes passent par une **contradiction**. Celle-ci est tranchée
   par la règle d'autorité (Sources §2) quand elle s'applique ; sinon, par l'équipe.
4. **Rejouer** : à chaque passe, le gardien rejoue les vérifications dont la preuve a changé. Une connaissance
   qui ne tient plus redescend, et la fiche le dit.
5. **Rendre compte** : la fiche et la revue affichent *vérifié*, *selon X*, *recoupé*, *contesté* ou
   *non appuyé*, jamais « vrai ».

**Implémenté (2026-10-28).**
- Recettes (`recettes.py`), juge d'appui (`juge.py`, lots de 12, 24 par passe), orchestration (`recoupement.py`,
  table `verification`, gardien). M3 exige le recoupement.
- État `en_partie`, distinct de « selon » : comme le Check Grounding de Google, une phrase appuyée en partie n'est
  pas appuyée.
- La documentation du dépôt (.md, .mdx, .rst, .adoc) est un système à part, distinct du code.
- L'outil `recouper_connaissance` ajoute une seconde source à une connaissance existante (refusée si elle vient du
  même système), et la méthode explique comment recouper.
- La fiche affiche les compteurs et l'état de chaque connaissance. Ce que sa preuve n'appuie pas sort de la
  présentation et passe dans « ce que j'ignore ».
- L'extracteur ne prouve plus une variable par un commentaire qui la nomme.

**Premiers résultats réels (meridian).**
- Première passe : 175 connaissances vérifiées, 21 selon le code, 12 non appuyées. Huit des non appuyées venaient
  de l'extracteur : des variables « lues » dans des commentaires.
- Après correction de l'extracteur : 182 vérifiées, 3 non appuyées.
- Recoupement par l'agent dans la documentation du dépôt : **5 connaissances recoupées, M3**. Le juge a refusé
  une seconde source qui ne disait pas la même chose (« selon »), et en a jugé une autre seulement « en partie ».

**Limites.**
- Les fichiers de méthode (`methodes/*.md`) comptent comme documentation. Ce sont aussi des consignes pour
  l'agent : ils prouvent l'intention, pas un comportement observé.
- Aucune source externe n'est encore branchée sur un vrai compte (Confluence, Jira…).

**L'humain** ne voit plus que les vraies décisions : les contradictions qu'aucune règle d'autorité ne tranche,
et la validation (M4) des connaissances qui comptent. « Recoupé » n'est pas « validé » : la propriété
« Gouvernance » de l'Architecture §1 reste entière.

**Remplace** la « politique de revue » d'une première version de ce paragraphe. Une politique décidée par le
propriétaire supposait l'identité. La vérification, elle, n'en a pas besoin.

---

# 3. Vivre là où l'on travaille : le jumeau en MCP

**Ce que la v1 avait compris.** Les agents qui habitent l'espace sont ceux de Méridian.

**Ce que fait Claude Code.** Il est dans le terminal et l'éditeur du développeur ; le contexte vient à lui.

**Proposition.** Le jumeau devient un **serveur MCP en lecture seule**, servi par Méridian. Il offre :
`carte(jumeau)`, `connaissances(jumeau, question)` avec leurs preuves, `voisins(jumeau)` et `inconnues(jumeau)`. Il
respecte les niveaux de projection (`existence` … `complet`, Architecture §6.1). Un agent de code qui modifie TBT
apprend alors que la ligne applique la règle R12, validée, et que l'application Fraude consomme ce flux. Plus tard,
le gardien pourra commenter une pull request qui touche une connaissance validée. Ce serait une action tournée
vers l'extérieur, à décider séparément.

**Dépendance.** Sans identité, un serveur MCP exposerait tout à quiconque s'y connecte. Il faut d'abord
l'authentification OIDC et les niveaux par appelant. Ce point mérite son propre document (périmètre,
authentification, audit, coût), puis une implémentation. Il n'est **pas implémenté**.

---

# 4. Vérifier avant de citer, y compris la fraîcheur

**Constat (code).** C'est déjà largement en place. `contradicteur.citations_invalides` contrôle chaque citation de
la réponse avant l'envoi (code au commit, sources par `lecteur.verifier`), et les citations introuvables sortent du
volet des preuves.

**Ce qui manque.** Une citation de source est **versionnée** (`confluence://TBT/123@7#L4-L9`). Elle reste vraie
pour la version 7 alors que la page en est peut-être à la version 9. C'est exactement le statut d'une mémoire chez
Claude Code : « vraie quand elle a été écrite ».

**Règle (implémentée).** Avant l'envoi, Flore compare la version citée à la version courante du document, en
lecture bornée et sans modèle. Une preuve dépassée reste dans le volet avec la mention « a changé depuis
(v7 → v9) ». Le texte de la réponse n'est pas modifié. Une source injoignable ne bloque pas la réponse : la
preuve est alors marquée « non revérifiée ». Les jours de Datadog sont exclus de ce contrôle, puisqu'une
journée passée ne change pas.

---

# 5. Les consignes du jumeau

**Ce que la v1 avait compris.** `CLAUDE.md` correspondait à la fiche générée.

**Ce que fait Claude Code.** `CLAUDE.md` est court, écrit par des humains, et contient des consignes. Les
fichiers se superposent du plus général au plus particulier (utilisateur, règles, projet). Le plus particulier
l'emporte en cas de conflit. Ce qu'on régénère automatiquement est un index (CodeGraph, graphify), pas `CLAUDE.md`.

**Règle (implémentée).**
- Une **consigne** est un texte court (≤ 500 caractères) écrit par un humain. Son **pourquoi** est obligatoire,
  sur le modèle des mémoires `feedback`. Exemples : du vocabulaire (« ici, un "dossier" est une demande de
  crédit, pas un dossier client »), une source qui fait autorité, un hors-périmètre, une zone sensible.
- **Portée** : `domaine`, `equipe` ou `jumeau`, chacune résolue à partir du jumeau (son domaine, son équipe,
  son identifiant). Elles sont chargées dans le prompt de tout agent qui travaille sur ce jumeau (réponse,
  gardien, mobilisation), du plus général au plus particulier, et la plus particulière l'emporte. Le volume est
  borné (40 consignes, 6 000 caractères), avec **une part par portée** (13 consignes, 2 000 caractères), à
  l'écriture comme à la lecture. Ainsi des consignes de jumeau ne font jamais sauter celles du domaine.
- On ne retire qu'une consigne qui s'applique au jumeau désigné, dans son tenant
  (`POST /api/v2/jumeaux/{id}/consignes/{n}/retrait`).
- **Limite connue, en attente de l'identité.** Quiconque écrit sur un jumeau peut aujourd'hui poser une consigne
  de portée domaine ou équipe, qui s'applique alors à tous les jumeaux de ce domaine ou de cette équipe. Ces
  deux portées exigeront un droit propre (Architecture §6.1). L'auteur est l'en-tête `X-Persona`, qui n'est pas
  authentifié.
- Une consigne est une **instruction de l'équipe**. Elle se distingue des sources, qui restent des données.
  C'est la seule entrée d'instructions humaines dans le prompt, ce qui exige d'en tracer l'auteur et la date
  et de pouvoir la retirer sans la supprimer (historique).
- **Contester avec un motif** propose une consigne. Elle n'est jamais créée seule : le harness la présente dans
  la revue, et un humain la confirme. C'est conforme au Discovery §90 : « les règles critiques ne doivent pas
  s'auto-modifier sans gouvernance ».
- **Interface** : la maquette passe par le compagnon visuel avant l'implémentation (règle du projet). En
  attendant, l'API existe.

---

# 6. Évaluer : un jeu de référence tiré du jumeau

**Ce que la v1 constatait.** « Évaluations et observabilité : ❌ ». C'est toujours vrai. Pourtant les méthodes, les
prompts et le modèle changent souvent.

**Ce que fait Claude Code.** On rejoue un jeu de cas à chaque changement de prompt ou de modèle (pass@k), et
une régression se voit avant d'atteindre les utilisateurs.

**Règle (implémentée).** `python -m jumeau.evaluation --jumeau <id>` construit puis rejoue un jeu à deux étages :

1. **Exactitude**, à partir des connaissances **validées** : la connaissance validée est la réponse attendue
   (« Avec qui TBT échange-t-elle ? » → la relation prouvée). Un juge sans outils rend une décision structurée :
   la réponse contient-elle l'attendu, le contredit-elle ?
2. **Ancrage**, sur les sept questions de la méthode `comprendre-application`, pour tout jumeau même sans
   validation. On mesure la part de citations valides, la part d'affirmations appuyées par une citation (même
   juge) et le temps de réponse.

Chaque passe est enregistrée (table `evaluation` : jumeau, date, version des méthodes et de la charte, modèle,
scores, détails) pour suivre la tendance. Le coût est borné : au plus 10 questions par passe, une réponse et un
jugement par question. Le jeu fournit directement deux indicateurs de la Stratégie : *Time to understand
application* (§64) et, avec la validation, la part de connaissances validées qui restent bien restituées.

---

# 7. Les inconnues deviennent des questions adressées

**Constat.** L'Architecture §1 demande au jumeau d'*exposer* ses inconnues. C'est passif.

**Ce que fait Claude Code.** Quand il est bloqué sur une décision qui revient à l'utilisateur, il la pose, et
seulement celle-là.

**Proposition.** Une inconnue importante (une question sans réponse prouvée, une contradiction ouverte depuis plus
de *n* jours) devient une **question adressée** à un rôle de l'équipe (`MAINTAINER` du périmètre). Elle est
asynchrone, et l'on ne pose qu'une question à la fois par personne. La réponse entre comme preuve `HUMAN`
(Architecture §6.3). Ce mécanisme fait baisser l'indicateur *Unknown Reduction* (Stratégie §163). Il réutilise
`demander_precision`, mais adressé à l'équipe plutôt qu'à l'interlocuteur du moment.

**Dépendance.** Il faut savoir à qui l'adresser, donc l'identité. Ce point n'est **pas implémenté**.

---

# 8. Ce qui reste juste dans la v1

Plusieurs correspondances de la v1 tiennent :
- les méthodes correspondent aux skills ;
- les jumeaux mobilisés correspondent aux sous-agents (contrat : Flore recueille, elle ne délègue pas pour
  oublier) ;
- le gardien correspond aux agents d'arrière-plan ;
- le Travail correspond à l'état de tâche ;
- le Contradicteur correspond aux hooks de vérification ;
- les sources sont des données, jamais des instructions.

Le déclenchement du gardien gagnerait toutefois à suivre la règle de Claude Code : « ne pas sonder ; un événement
d'abord, une veille de secours longue ». Aujourd'hui, le gardien sonde toutes les 120 s. Les événements (GitHub
Actions, versions de page) deviennent le signal principal, et la veille passe à 30 min (AWS v1, décision
GitHub Actions).

---

# 9. Ordre

| # | Objet | État | Dépend de |
|---|---|---|---|
| 1 | §4 Fraîcheur des preuves à la lecture | implémenté | — |
| 2 | §6 Évaluations | implémenté | — |
| 3 | §5 Consignes du jumeau (API et prompt) | implémenté ; l'interface attend sa maquette | — |
| 4 | §2 Vérifier comme on teste | implémenté | — |
| 5 | §7 Questions adressées | à faire | identité |
| 6 | §3 Le jumeau en MCP | document dédié, puis à faire | identité, document dédié |
| 7 | §8 Événements d'abord, veille longue | à faire | déploiement AWS |
