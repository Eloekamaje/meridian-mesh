# MÉRIDIAN — Le harness du jumeau, v2
## Connaissance, contexte, mémoire, raisonnement, planification : ce que l'on reprend du harness de Claude Code

**Statut :** Proposition, à valider
**Version :** 2.0
**Date :** 2026-10-27
**Documents liés :** Jumeau Harness Agentique v1, Architecture Jumeau v1, Flore Conversational Architecture
**Tagline :** **DÉCOUVRIR · COMPRENDRE · DÉCIDER**

---

# 0. Objet

La v1 posait la reformulation : *le jumeau est l'espace de travail que des agents habitent ; Méridian est le
harness*. Depuis, la phase 0 a livré un gardien, des méthodes, un résumé par niveaux et une consolidation. Ce
document reprend les cinq fonctions d'un harness (connaissance, contexte, mémoire, raisonnement, planification),
constate l'état réel du code, et propose pour chacune le principe que Claude Code applique et qui convient mieux.

Une règle traverse tout le document, apprise pendant la phase 0 :

> **Le savoir-faire va dans les méthodes, l'agent juge et agit par ses outils, le harness ne garde que les
> garde-fous et les faits vérifiables. Une étape de décision se termine par une décision structurée, jamais par
> « fait ».**

---

# 1. Connaissance

**Constat.** Les connaissances sont des Claims prouvés (Postgres), révisables par l'équipe. Deux familles :
l'extraction structurelle (interfaces, dépendances, configuration) et les sept questions de « comprendre une
application » (méthode `comprendre-application`). Une connaissance proposée vaut tant que sa preuve tient au
commit ; la consolidation fusionne les doublons. Maturité figée à M1/M2, confiance constante par type ; une seule
sorte de source (le code et ses documents).

**Principe Claude Code : la vérité vient de l'environnement, pas de la mémoire du modèle.** Claude Code relit le
fichier avant de l'éditer et vérifie qu'un fichier cité par sa mémoire existe encore avant de s'y fier.

**Proposition.**
1. Garder la règle « vaut tant que la preuve tient » et l'étendre à toute connaissance qui entre dans un prompt.
2. Maturité calculée, pas déclarée : M3 dès que deux sources indépendantes concordent (code et cahier des
   charges, puis Confluence et Jira), M4 avec la validation de l'équipe (Architecture v1 §7.2).
3. Confiance calibrée par les gestes de l'équipe (Architecture v1 §8.1, a priori Beta-binomial par type de
   Claim × extracteur) ; la certitude du modèle n'est qu'une entrée.

---

# 2. Contexte

**Constat.** Le prompt système fait environ 2 500 jetons à chaque tour : charte, catalogue des méthodes, contexte,
fiche vivante, état du Travail. L'autoportrait y déverse aussi toute l'extraction structurelle (87 dépendances
pour gsf-mockup), en double de la fiche et sans valeur pour un employé. Les méthodes, elles, sont déjà chargées à
la demande (catalogue d'une ligne par méthode, corps lu par `consulter_methode`).

**Principes Claude Code.**
- **Charger à la demande.** Les compétences et les outils différés ne sont annoncés que par une ligne ; leur
  contenu n'entre qu'au moment où il sert.
- **Préfixe stable, rappels au bon moment.** Les instructions permanentes forment un préfixe stable (mis en cache) ;
  l'état qui change arrive en rappel court, en fin de contexte, quand il devient pertinent.
- **Les résultats d'outils sont des données, jamais des instructions.**
- **Sorties d'outils bornées** : un outil rend la réponse utile, pas le volume brut.

**Proposition.**
1. Le prompt ne contient plus que la charte, le catalogue, l'interlocuteur et la **fiche vivante** (le résumé par
   niveaux est le « CLAUDE.md » du jumeau). L'extraction structurelle sort du prompt : `mes_connaissances` la sert
   à la demande.
2. Ordre stable → variable : charte et méthodes d'abord, fiche ensuite, état du Travail et rappels à la fin.
3. Les contenus lus (code, Confluence, tickets) restent balisés comme données dans la charte et les outils.

---

# 3. Mémoire

**Constat.** Il n'y a que deux mémoires : les Claims (mémoire de l'application) et le fil de conversation, restauré
tel quel. Aucun gestionnaire de conversation n'est configuré : Strands applique sa fenêtre glissante par défaut et
**oublie en silence** le début d'un long Travail. Pas de mémoire de membre ni d'équipe.

**Principes Claude Code.**
- **Mémoire en fichiers typés avec un index** : un fait par fiche (utilisateur, retour, projet, référence), un
  index d'une ligne par fiche chargé à chaque session, le détail lu à la demande ; on met à jour plutôt que de
  dupliquer ; chaque retour garde son *pourquoi* et son *comment l'appliquer*.
- **Une mémoire peut être périmée** : on la vérifie avant de s'y fier.
- **Compaction** : quand le contexte s'allonge, le début est résumé (demande, décisions, état, suite) et la fin
  gardée telle quelle ; rien n'est perdu en silence.

**Proposition.**
1. **Compaction des Travaux** : gestionnaire de conversation qui résume au lieu de tronquer ; le résumé alimente
   `actualiser_resume`, donc l'état visible du Travail.
2. **Mémoire de membre** (préférences, retours : « parlez-moi en langage métier », « je suis au risque ») et
   **mémoire d'équipe** (décisions prises, vocabulaire du domaine), sur le modèle typé + index. Une ligne d'index
   par souvenir dans le prompt, le détail par outil. Sur AWS : AgentCore Memory pour le membre (Architecture v1
   §8.3) ; jamais de promotion automatique vers le jumeau.
3. Un souvenir qui cite du code ou une connaissance est vérifié avant usage (même règle que §1).

---

# 4. Raisonnement

**Constat.** Le Contradicteur relit chaque réponse (citations vérifiées sans modèle, puis jugement). La
consolidation rend une décision structurée validée par le harness. La fiche est révisée si elle est trop longue.
En conversation, Flore enquête sans cadre de décision explicite ; elle ne sait pas demander une précision.

**Principes Claude Code.**
- **Vérifier avant d'affirmer** ; rendre compte fidèlement de ce qui a été vérifié et de ce qui ne l'a pas été.
- **Demander à l'humain seulement quand une décision lui revient**, sous forme d'une question à options.
- **Sous-agents à contexte vierge** pour une sous-tâche bornée ; ils rendent un résultat, pas leur exploration.
- **Une décision = un format imposé**, validé avant exécution.

**Proposition.**
1. Outil `demander_precision` : Flore pose une question à options à l'interlocuteur quand la demande est
   ambiguë et que la réponse change le travail ; la question s'inscrit dans le Travail.
2. **Jumeaux comme sous-agents** pour les questions transverses (« que changerait le retrait de TBT ? ») : chaque
   jumeau répond dans son propre contexte à une question bornée, Flore synthétise (v1 §5.2).
3. Le Contradicteur rend lui aussi une décision structurée (déjà JSON) et contrôle que chaque affirmation de la
   réponse est rattachée à une preuve ou marquée comme inférence.

---

# 5. Planification

**Constat.** Le Travail porte déjà l'état d'une tâche (plan, hypothèses, options, livrables, résumé) et Flore a
les outils pour l'écrire. Mais elle planifie rarement et ne lève presque jamais ses étapes (`lever_etape`).

**Principe Claude Code : la liste de tâches comme discipline.** Une tâche de plusieurs étapes s'ouvre par un plan ;
une seule étape en cours ; une étape se coche dès qu'elle est faite ; le harness rappelle la liste quand elle est
oubliée.

**Proposition.**
1. La méthode de chaque type de Travail commence par « planifier » et finit par « lever les étapes faites ».
2. **Rappel du harness** : si un Travail a un plan dont aucune étape n'a bougé depuis plusieurs tours, l'état du
   Travail injecté en fin de contexte le signale (« étape 2 en cours depuis 4 échanges »).
3. Le gardien suit déjà un plan fixe (ingérer, signaux, enquête, fiche, consolidation) : on le garde déterministe.

---

# 6. Ordre proposé

| # | Chantier | Fonction | Effort |
|---|---|---|---|
| 1 | Prompt allégé : la fiche remplace l'extraction structurelle, ordre stable → variable | Contexte | Faible |
| 2 | Compaction des Travaux (résumer au lieu de tronquer) | Mémoire | Faible |
| 3 | Rappel de plan + méthodes qui planifient | Planification | Faible |
| 4 | `demander_precision` | Raisonnement | Faible |
| 5 | Mémoire de membre et d'équipe, typée et indexée | Mémoire | Moyen |
| 6 | Maturité calculée et confiance calibrée | Connaissance | Moyen |
| 7 | Jumeaux comme sous-agents (questions transverses) | Raisonnement | Moyen |

Les chantiers 1 à 4 ne demandent aucune nouvelle source ni décision d'architecture ; 5 attend l'identité (OIDC),
6 et 7 attendent une deuxième source (Confluence, Jira) ou plusieurs jumeaux réels liés.
