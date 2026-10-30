# ADR-0002 — Orchestrateur général : intention par le modèle, pas par routeur hardcodé

- **Statut :** Accepté — **amendé par ADR-0003 et ADR-0004**
- **Date :** 2026-10-30
- **Portée :** routage Flore, conception greenfield, mobilisation des jumeaux
- **Complète :** ADR-0001

> **Amendement du 2026-10-30.** La formulation « le Mesh est une source » et l'idée que les trois outils constituent le noyau sont remplacées par [ADR-0003](0003-mesh-transversal-intelligence.md) (le Mesh est la couche d'intelligence transversale, ni source ni outil) et [ADR-0004](0004-capability-first-harness.md) (harness capacitaire, outils adaptateurs). Le corps ci-dessous reste l'historique de la décision ; il ne doit pas être utilisé comme politique courante.

## Contexte

Le premier correctif du cas « architecture d'une application de dating » a introduit un routeur d'intention déterministe (`intentions.py`). Ce routeur reconnaissait des verbes et des noms, puis choisissait une branche. Il corrigeait le cas testé, mais il ne reproduisait pas le mécanisme d'un agent général : la décision restait une liste de règles, et le prochain cas non prévu aurait demandé une nouvelle règle.

Le défaut réel était **mesh-first** : Flore commençait par chercher des jumeaux, montrait l'Atlas, puis tentait de faire rentrer la demande dans le registre. Une question de conception greenfield n'a pourtant aucun jumeau à consulter.

## Décision

Flore utilise un **orchestrateur général** :

- un seul modèle ;
- une politique système ;
- trois outils bornés :
  - `resoudre_application` ;
  - `mobiliser_jumeaux` ;
  - `concevoir_architecture` ;
- une boucle outil → résultat → réponse.

Aucun routeur d'intention par expression régulière n'est consulté. Le routeur `intentions.py` a été retiré du chemin principal et supprimé, pour éviter de recréer une seconde autorité de décision.

### Politique

- Le Mesh est une **source**, pas le point de départ.
- Application existante nommée ou sélectionnée → résolution puis mobilisation ciblée.
- Application absente / conception / architecture cible → `concevoir_architecture`, sans jumeau ni Atlas.
- Question générale → réponse directe, sans inventer de fait d'entreprise.
- Ambiguïté → clarification.
- Une proposition n'est jamais présentée comme un fait observé.
- Si un outil a produit une réponse complète, le serveur utilise cette réponse ; le modèle ne la réécrit pas.

### Conception greenfield

`conception.py` produit une `ArchitectureCible` structurée :

- composants et liens ;
- hypothèses et hors-périmètre explicites ;
- schéma `mode="proposition"`, flèches `etat="propose"` ;
- aucune preuve, aucun jumeau, aucun claim.

### Sélection explicite

Une sélection d'applications reste un chemin direct borné : elle n'est pas réinterprétée par l'orchestrateur. Le cas greenfield sans sélection utilise l'orchestrateur.

### Panne

Si le modèle ou l'orchestrateur est indisponible, Flore renvoie un **signal d'indisponibilité** :

- aucun jumeau n'est mobilisé ;
- aucune conclusion n'est tirée ;
- aucune absence n'est affirmée.

## Alternatives rejetées

| Alternative | Raison du rejet |
|---|---|
| Routeur regex | Ne généralise pas ; recrée une autorité de décision cachée ; le cas suivant demande une nouvelle règle. |
| Toujours mobiliser tous les jumeaux | Coût, latence, biais mesh-first, questions de conception hors sujet. |
| Mode dating dédié | Pansement : le problème est l'intention, pas le domaine. |
| Laisser le modèle sans outils | Il ne peut ni résoudre une app ni produire un schéma structuré ; risque de fait inventé. |
| Faire décider l'UI | Déplace le problème et retire la traçabilité côté serveur. |

## Conséquences

- Le choix d'outil est **observable** dans `orchestration.outils`.
- La conception est **traçable** : `proposition=true`, `mode=proposition`, hypothèses.
- Le coût augmente d'un appel d'orchestration ; la conception ajoute un appel de modèle dédié.
- La qualité dépend du modèle et doit être mesurée par un jeu d'or (dating, app existante, comparaison, ambigu, question générale).
- Un routeur heuristique ne doit pas redevenir primaire sans nouvelle ADR.

## Cas d'acceptation

1. « architecture d'une application de dating » → outil `concevoir_architecture` seulement ; aucun participant ; schéma proposition.
2. « décris l'architecture de Conduit » → `resoudre_application` puis `mobiliser_jumeaux` ; participant Conduit.
3. « bonjour » → réponse directe ou clarification, aucun outil imposé.
4. Modèle indisponible → signal, aucun jumeau.
5. Aucun `Conduit` ne doit apparaître dans le schéma d'une question de conception greenfield.

## Limites connues

- Le modèle peut choisir un outil non optimal ; le jeu d'or et les traces sont la garde.
- Pas de timeout/retry par outil dans l'orchestrateur.
- La conception est une proposition non vérifiée par construction.
- Le chemin de sélection explicite reste distinct et doit être testé séparément.
