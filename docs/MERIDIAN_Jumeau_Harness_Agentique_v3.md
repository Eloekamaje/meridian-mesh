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
| Demandes de permission | Revue humaine de **chaque** Claim | **Politique de revue** décidée par le propriétaire (§2) ; la revue unitaire reste pour ce qui est difficile à défaire |
| `CLAUDE.md` | La fiche vivante, régénérée à chaque commit | Deux objets : la **fiche** (générée, l'équivalent d'un index) et les **consignes du jumeau** (écrites par l'équipe, §5) |
| Où vit l'agent | Dans Méridian | Là où l'on travaille déjà : le jumeau s'expose aussi en **MCP**, en lecture seule (§3) |
| Mémoire « vraie quand elle a été écrite » | — | **Vérifier avant de citer**, y compris la fraîcheur des versions (§4) |
| Poser une question quand on est bloqué | — | Les inconnues deviennent des **questions adressées** à l'équipe (§7) |
| Évaluations | ❌ (v1 §4) | **Jeu de référence** tiré du jumeau lui-même, rejoué à chaque changement (§6) |

---

# 2. La permission : une politique, pas un clic par connaissance

**Ce que la v1 avait compris.** Les demandes de permission y correspondaient à la validation humaine de chaque
Claim (Architecture §1 : « l'équipe propriétaire valide ; aucun agent ne valide »).

**Ce que fait Claude Code.** Il a des modes et des autorisations durables (listes d'autorisations). Il ne demande
l'accord que pour ce qui est difficile à défaire ou tourné vers l'extérieur. Un accord donné dans un contexte ne
vaut pas pour un autre.

**Proposition.** L'`APPLICATION_OWNER` (Architecture §6.1) décide une **politique de revue** versionnée :

| Classe | Exemple | Traitement |
|---|---|---|
| Acceptée par la politique | dépendance lue dans un manifeste ; connaissance prouvée par deux systèmes (M3) | `ACCEPTED`, trace « acceptée par la politique v*n* de X » |
| Toujours revue | règle métier (`APPLIQUE_REGLE`), données détenues (`DETIENT`), relation du Mesh | revue unitaire par un `MAINTAINER` |
| Échantillon | tout le reste | *k* connaissances par semaine tirées au hasard ; un refus suspend l'acceptation automatique de la classe |

**Écart assumé avec l'Architecture §1.** Aucun agent ne valide toujours, et l'humain décide toujours. Il décide
une fois, au niveau de la politique, et elle reste révocable. La maturité M4 exige alors une validation **unitaire**,
et M3 + politique ne suffit pas. Les connaissances critiques gardent ainsi leur sens.

**Dépendance.** La politique suppose de savoir qui est propriétaire, c'est-à-dire l'identité, que l'utilisateur
a reportée (« sans acteur et profil, on y reviendra »). Elle n'est **pas implémentée** et attend ce sujet.

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
  borné (40 consignes, 6 000 caractères).
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
| 4 | §2 Politique de revue | à faire | identité |
| 5 | §7 Questions adressées | à faire | identité |
| 6 | §3 Le jumeau en MCP | document dédié, puis à faire | identité, document dédié |
| 7 | §8 Événements d'abord, veille longue | à faire | déploiement AWS |
