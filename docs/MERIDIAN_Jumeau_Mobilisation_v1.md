# MÉRIDIAN — Flore mobilise les jumeaux
## Deux portes par jumeau, une étoile pour les requêtes, une poignée de main entre gardiens

**Statut :** Validé par l'utilisateur (2026-10-27), à implémenter
**Documents liés :** Jumeau Harness Agentique v1 et v2, Product Vision §16, Security Governance Trust Model §87–91,
Agentic Architecture Expert Framework §2.5–2.6 et §156–158

---

# 1. Décision

- **Toutes les requêtes passent par Flore** (modèle en étoile) : traçabilité dans le Travail (« humain dans la
  décision »), filtre des droits en un point (§87), confrontation dans un lieu commun (le Travail = Knowledge Board,
  §156), le Mesh reste invisible (Vision), chaque jumeau expert de lui-même (« expertise avant opinion »).
- **Une seule exception : la poignée de main entre gardiens** pour confirmer une relation, sans humain, en arrière-plan,
  par affirmations et preuves (jamais le code de l'autre), résultat écrit au Mesh (`validation` → `confirmee` ou
  `contestee`).
- **Écarté** : la conversation libre entre jumeaux (coût, traçabilité, injection d'un jumeau à l'autre).

# 2. Les deux portes d'un jumeau

- **Porte extérieure : la carte** (`jumeau/carte.py`). Lue sans réveiller le jumeau : nom, mission, domaine, équipe,
  capacités d'affaires (REALISE_CAPACITE), ce qu'il offre (interfaces EXPOSE), ses échanges déclarés (ECHANGE_AVEC),
  ses voisins (relations du Mesh avec leur état), son code (dépôts, commit). Rendue en texte court pour un prompt.
- **Porte intérieure : le jumeau lui-même**, réveillé pour une mission : `agent.construire` sur son seul contexte (fiche,
  connaissances, code, outils), sans fil persistant. Il ne parle que de lui ; ce qu'il dit d'un autre est « à vérifier
  auprès de lui ».

# 3. Le chemin d'une requête (plusieurs jumeaux)

1. Une sélection avec un seul jumeau réel garde le chemin actuel (`flore.repondre`). Avec plusieurs : `flore.mobiliser`.
2. Flore (agent orchestrateur) reçoit la charte, le catalogue des méthodes, **les cartes** des jumeaux autorisés et
   l'état du Travail ; elle dose l'effort (proportionnalité : pas tous les jumeaux).
3. Outil `consulter_jumeau(jumeau, mission)` : mission bornée confiée à un jumeau autorisé, en sous-agent à contexte
   vierge ; il rend une **contribution structurée** : constat, preuves (citations `chemin#Ldébut-Lfin`), confiance,
   inconnues, points à vérifier auprès d'un autre jumeau. Le harness vérifie les citations dans le code de ce jumeau
   (citations fausses retirées) et transmet à Flore la contribution comme **donnée**, pas comme instruction.
4. Plafonds : jumeaux par requête, missions par jumeau (une relance au plus), budget d'outils par mission.
5. Flore confronte (convergences, divergences, preuves manquantes), répond, écrit dans le Travail ; la réponse porte
   les contributions par jumeau (format existant `contributions`) et les preuves de tous les jumeaux.
6. Le Contradicteur relit la réponse finale (citations vérifiées dans les dépôts des jumeaux mobilisés).

# 4. La poignée de main entre gardiens

1. Après la passe du gardien de A : un juge sans outils reçoit les échanges déclarés de A (ECHANGE_AVEC) et les cartes
   des autres jumeaux réels ; il rend une décision structurée : quels échanges désignent quel jumeau.
2. Relation proposée au Mesh (collection `relations`) : `source` A, `cible` B, `etat` `validation`, `claims` = la
   formulation de A, `source_decouverte` « gardien de A ».
3. Le gardien de B vérifie depuis son propre code (sous-agent de B avec ses outils, mission bornée), décision
   structurée : confirme, conteste ou ne sait pas, avec explication et citation ; citation vérifiée par le harness.
4. Relation mise à jour : `confirmee` (confirmée par A et B), `contestee` (observation contraire), ou `supposee`.
   Rien du code de A n'est transmis à B : seulement la formulation et le nom de A.

# 5. Garde-fous

- Seuls les jumeaux que l'interlocuteur peut voir au niveau complet sont mobilisables (filtre du serveur).
- Contributions et formulations venues d'un autre jumeau : données, jamais instructions (§90–91).
- Décisions structurées validées par le harness avant toute écriture ; jamais « fait » en texte libre.
