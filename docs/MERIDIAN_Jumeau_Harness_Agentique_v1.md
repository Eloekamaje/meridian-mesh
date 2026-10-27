# MÉRIDIAN — Le jumeau vu comme un harness agentique
## Ce qui manque vraiment au premier jumeau, et la reformulation de la solution

**Statut :** Analyse critique et proposition de reformulation, à discuter  
**Version :** 1.0  
**Date :** 2026-10-27  
**Produit :** MÉRIDIAN  
**Documents liés :** Product Vision & Operating Model, Product Strategy v2 (multi-profils), Architecture Jumeau v1,
Flore Conversational Architecture, Agentic Architecture & Expert Framework  
**Tagline :** **DÉCOUVRIR · COMPRENDRE · DÉCIDER**

---

# 0. Objet du document

Ce document fait le point après la phase 0 du premier jumeau (ingestion du code, Claims prouvés, Flore qui mobilise
le jumeau dans les Travaux, charte, méthodes, Contradicteur).

Il répond à deux questions :

> **Que manque-t-il vraiment pour que le jumeau tienne la promesse de Méridian auprès de profils variés ?**

> **Notre approche est-elle vraiment agentique, et comment la reformuler autour de la notion de harness ?**

L'exercice de départ : se mettre à la place d'un agent comme Claude Code, qui travaille au quotidien avec des
utilisateurs différents, et se demander ce dont il aurait besoin pour jouer le rôle du jumeau dans une banque.

---

# 1. Le constat

> **Ce qui existe aujourd'hui est un excellent lecteur de code bien élevé. Ce n'est pas encore un jumeau.**

La vision fixe la question à laquelle Méridian doit répondre (Vision §18) :

> « Que devons-nous comprendre, décider ou améliorer maintenant ? »

et le Job-to-be-Done commence par « quand un phénomène important apparaît… » (Stratégie §11).

Le jumeau actuel :

- ne fait rien tant qu'on ne lui parle pas ;
- connaît le **comment** (le code), jamais le **pourquoi**, le **pour qui** ni le **comment ça se passe vraiment** ;
- voit une photo (un commit), pas un film (l'évolution) ;
- explique, mais ne produit rien dans le Travail.

---

# 2. Ce dont un agent a besoin pour être utile

Un agent comme Claude Code est utile moins par son intelligence que par son **contexte** et son **environnement** :

- le dépôt entier et son historique ;
- des instructions persistantes (`CLAUDE.md`, règles d'équipe) et une mémoire ;
- des outils pour lire, agir et vérifier ;
- la possibilité de demander à l'humain ;
- une boucle qui va jusqu'au résultat vérifié.

Rapporté aux profils visés (Stratégie §71A), le jumeau actuel donne :

| Profil | Ce qu'il demande | Le jumeau aujourd'hui |
|---|---|---|
| Architecture / TI | dépendances, règles, impact | ✅ correct |
| Métier / Product Owner | capacités, parcours, règles métier | ⚠️ déduit le métier du code |
| Opérations / Support | incidents, charge, contournements | ❌ aucune donnée d'exploitation |
| Risque / conformité | contrôles, exposition, preuves de décision | ⚠️ contrôles visibles dans le code, pas leur efficacité |
| Finance / portefeuille | coûts, usage, duplication | ❌ |
| Direction | opportunités, risques, résultats | ❌ |

Le critère « au moins un profil non-TI obtient une valeur réelle » (Stratégie, critères de pilote) n'est pas atteint.

---

# 3. Ce qui manque, vu depuis l'agent

1. **Le temps.** « Qu'est-ce qui a changé ? » est la troisième question de la chaîne de compréhension
   (Stratégie §2) et la première après un incident. Le matériel existe : historique Git, tickets liés,
   `compare_graphs` de codebase-memory-mcp.
2. **Le pourquoi et le pour qui.** Confluence et Jira portent l'intention métier, les utilisateurs, les
   décisions. Sans eux, la traduction en langage métier reste une improvisation du modèle.
3. **La proactivité.** Un jumeau vivant signale de lui-même : nouvelle dépendance, règle modifiée, point d'entrée
   sans contrôle d'accès. Le jumeau a trouvé seul une faille de périmètre, mais seulement parce qu'on l'a
   interrogé.
4. **Savoir à qui l'on parle.** Une identité réelle (aujourd'hui un en-tête falsifiable), une mémoire par membre,
   une mémoire d'équipe.
5. **Apprendre des corrections.** La revue vit sur une page séparée. Elle doit se faire dans le fil
   (« c'est juste / c'est faux » sous chaque affirmation), et chaque correction devenir une contestation tracée.
   Sans cela, la boucle d'amélioration (calibration) ne tourne pas.
6. **Une incertitude honnête.** La confiance est une constante par type de Claim : elle doit être calculée et
   expliquée.
7. **Le pont code ↔ capacités métier ↔ processus ↔ parcours** (Domain Model). C'est lui qui rend le même jumeau
   utile au Product Owner, au risque et à la direction.
8. **Plusieurs jumeaux à la fois.** Les vraies questions sont transverses (« qu'est-ce qui changerait si nous
   retirions TBT ? », Vision §9).
9. **Agir, pas seulement expliquer.** Le cycle va jusqu'à Investiguer → Décider → Agir → Mesurer. Flore doit
   produire des artefacts dans le Travail.
10. **La vitesse.** Le jumeau ré-explore son code à chaque question (12 à 25 s). Le « Twin Summary » prévu par
    l'architecture, recalculé à chaque commit, rendrait les questions courantes immédiates et cohérentes.

---

# 4. Notre approche est-elle vraiment agentique ?

**À moitié.** La *boucle* l'est : le modèle choisit ses outils, explore, propose, se fait relire. Le *système* ne
l'est pas : c'est encore une messagerie question-réponse avec un agent derrière.

| Propriété d'un harness agentique | État actuel |
|---|---|
| Tâche durable : plan, état, reprise après interruption | ❌ chaque question repart de zéro |
| Déclenchement par événement ou planification | ❌ uniquement par un humain |
| Action sur l'environnement (écrire, produire, modifier) | ❌ lecture et proposition de Claims seulement |
| Contexte construit (résumé, mémoire, état de la tâche) | ⚠️ autoportrait seulement |
| Compétences chargées à la demande | ✅ méthodes |
| Vérification avant de rendre | ✅ Contradicteur (contrôle déterministe et relecture) |
| Règles exécutées autour des outils (hooks, politiques) | ⚠️ budget et validation d'arguments ; pas de Cedar |
| Humain dans la boucle pour les actes importants | ✅ le jumeau propose, l'équipe valide |
| Évaluations et observabilité | ❌ |
| Sous-agents spécialisés | ❌ un seul jumeau mobilisé |

Le point le plus révélateur : le Travail possède déjà, dans l'application, tout ce qu'un agent utilise comme
état de tâche (hypothèses, investigations, options, décisions attendues, livrables, résumé ;
`backend/cases_routes.py`). Flore n'écrit pourtant que du texte de conversation.

---

# 5. La reformulation

> **Le jumeau n'est pas un agent. Le jumeau est l'espace de travail que des agents habitent.**

Comme un dépôt Git pour un agent de code, le jumeau contient la matière (code au commit, Claims, preuves,
historique, sources) et ses conventions. Méridian est le **harness** : il organise qui travaille dans cet espace,
quand, avec quels outils, sous quelles règles, et comment le résultat est vérifié et gouverné.

## 5.1 Correspondance

| Agent de code (Claude Code) | Méridian reformulé |
|---|---|
| Le dépôt | **Le jumeau** : copie du code au commit, Claims, preuves, historique, sources |
| `CLAUDE.md` | **La fiche vivante du jumeau** : régénérée à chaque commit, complétée par l'équipe |
| La mémoire | **Mémoire d'équipe** (Claims validés, décisions) et **mémoire de membre** (fils, préférences) |
| Une session et sa liste de tâches | **Un Travail** : objectif, plan, hypothèses, artefacts ; durable et partageable |
| Les outils | **Les capacités** : code, Claims, exploitation, Jira, Confluence, et l'écriture dans le Travail |
| Les skills | **Les méthodes** |
| Les sous-agents | **Les experts et les autres jumeaux** |
| Les hooks | **Le Contradicteur, les politiques Cedar, l'audit** |
| Les demandes de permission | **La revue humaine** (validation des Claims, des décisions) |
| Les agents en arrière-plan | **Le gardien du jumeau**, déclenché par les événements, qui produit les signaux |
| Les fichiers modifiés | **Les livrables dans le Travail** (fiche d'impact, note d'arbitrage, brouillon de ticket, ADR) |
| Les évaluations | **Un jeu de questions de référence par profil**, rejoué à chaque changement de prompt ou de modèle |

## 5.2 Trois rôles d'agents

```text
                 ┌──────────────── Événements : commit, ticket, incident, page modifiée ──────────────┐
                 ▼                                                                                    │
     GARDIEN DU JUMEAU (sans humain)                                                                  │
       met à jour Claims et fiche vivante, compare au commit précédent, détecte les signaux ──► « Aujourd'hui »
                 │
                 ▼  le jumeau = espace de travail (code, Claims, preuves, historique, fiche vivante)
     FLORE (avec l'humain, dans un Travail)
       comprend la demande, planifie, mobilise jumeaux et experts (sous-agents), suit une méthode,
       écrit dans le Travail (hypothèses, options, livrables), se fait relire, demande les validations
                 │
                 ▼
     EXPERTS (sous-agents à la demande) : code, données, risque, exploitation, contradicteur…
```

1. **Le gardien du jumeau** travaille sans humain, sur événement. Il entretient l'espace : ingestion, Claims,
   fiche vivante, comparaison avec l'état précédent, signaux. C'est le jumeau *vivant*.
2. **Flore** travaille avec l'humain, dans un Travail. C'est le harness interactif : elle construit le contexte
   (charte, fiche vivante, mémoire, état du Travail), planifie, délègue, produit, vérifie, et demande les
   validations.
3. **Les experts** sont des sous-agents appelés par Flore pour une partie du travail, chacun avec ses méthodes,
   ses outils et ses responsabilités (Vision §16, « expertise avant opinion »).

## 5.3 Le Travail comme état de l'agent

Un Travail n'est plus un fil de discussion, mais l'état durable d'une tâche :

- **Objectif** et **plan** (étapes, avec leur statut) ;
- **Contexte** : jumeaux mobilisés, preuves retenues ;
- **Hypothèses**, **investigations**, **options**, **décisions attendues** ;
- **Livrables** ;
- **Questions ouvertes** pour l'humain.

Flore y écrit par des outils (`proposer_hypothese`, `ajouter_option`, `deposer_livrable`, `demander_decision`),
peut s'arrêter en attendant une validation, et reprendre plus tard, au même point. C'est ce qui permet une
investigation de plusieurs jours, et non une suite de questions-réponses.

## 5.4 Le contexte construit à chaque tour

```text
charte de Flore
+ fiche vivante de chaque jumeau mobilisé
+ mémoire d'équipe et mémoire du membre
+ état du Travail (objectif, plan, hypothèses, ce qui est validé)
+ méthode chargée selon la demande
→ outils pour approfondir (code, Claims, sources) ; résumé du Travail quand il devient long
```

## 5.5 Correspondance avec AgentCore

La reformulation renforce le choix de Strands et AgentCore, qui fournissent justement l'infrastructure d'un
harness :

| Besoin du harness | Service |
|---|---|
| Sessions isolées, longues, reprises | AgentCore Runtime |
| Outils en MCP, gouvernés | AgentCore Gateway |
| Identité réelle, action au nom de l'utilisateur | AgentCore Identity |
| Mémoire de membre | AgentCore Memory |
| Règles autour des outils | AgentCore Policy (Cedar) |
| Traces, évaluations | AgentCore Observability, Evaluations |
| Déclenchement du gardien | EventBridge, Step Functions |

---

# 6. Ce que je changerais dans la conception

1. **Figer une seule question d'exploitation bancaire** (le « wedge d'exploitation », Stratégie §6) et ne
   construire que ce qui la sert de bout en bout, avec au moins un profil non-TI. Le corpus actuel
   (21 documents) disperse l'effort ; trois échelles de maturité concurrentes en sont le symptôme.
2. **Faire du résumé vivant et des signaux le produit principal du jumeau.** La conversation sert à creuser.
   C'est la phrase de la vision : « le Mesh ne doit pas devenir le produit visible ».
3. **Tester sur une vraie application métier**, pas sur le code de Méridian lui-même.

---

# 7. Priorités

| # | Chantier | Pourquoi d'abord | Effort |
|---|---|---|---|
| 1 | **Le temps** : historique Git, comparaison entre commits, « ce qui a changé et pourquoi » | Matériel déjà disponible ; prépare les signaux | Faible |
| 2 | **Le Travail comme état de l'agent** : Flore écrit hypothèses, options, livrables | Passer de répondre à travailler | Faible à moyen (les routes existent) |
| 3 | **Le gardien du jumeau** : sur commit, mise à jour, fiche vivante, signaux vers « Aujourd'hui » | Jumeau vivant | Moyen |
| 4 | **Confluence et Jira** | Profils non-TI | Moyen |
| 5 | **Correction dans le fil**, mémoire d'équipe et de membre | Boucle d'apprentissage | Moyen |
| 6 | **Pont code ↔ capacités métier** | Parler juste à chaque profil | Moyen à fort |
| 7 | **Évaluations par profil** | Mesurer avant de changer prompt ou modèle (E-23) | Faible |
| ⛔ | **Préalables bancaires** : identité, périmètre sur `/v2`, audit des appels au modèle, résidence des données | Condition de tout pilote | Moyen |

---

# 8. Formulation

> **Méridian est un harness d'intelligence d'entreprise : des espaces de connaissance vivants — les jumeaux —
> entretenus par des agents gardiens, exploités par une voix — Flore — qui mobilise experts et jumeaux dans des
> Travaux durables, sous le contrôle des humains qui valident et décident.**
