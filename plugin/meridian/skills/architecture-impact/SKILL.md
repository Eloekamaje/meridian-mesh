---
name: meridian-architecture-impact
description: Analyser un changement d'architecture, d'API ou d'interface avec Méridian. Utiliser pour un impact technique, un ADR, une dépendance, une interface ou un plan de changement.
---

# Architecture et impact

## But
Évaluer l'impact d'un changement sur les applications, interfaces, processus et parcours, avec preuves et limites.

## Méthode
1. Appeler `meridian_analyser` avec `profil="architecte"`, `application_id`, `twin_ids` et la question.
2. Vérifier les opérations exposées/consommées et leur posture observer/agir.
3. Lire l'impact amont/aval et les chemins ; ne pas déduire une relation absente.
4. Séparer clairement : impact prouvé, impact inféré, impact inconnu.
5. Proposer un ADR, un test de rollback ou une vérification d'interface, sans exécuter.
6. Signaler les écritures comme « approbation requise ».

## Garde-fous
- aucune modification de contrat ;
- aucune relation inventée ;
- une opération non trouvée n'est pas une preuve d'absence ;
- les actions restent des propositions.

## Sortie
Respecter `contracts/reponse.json`. Même socle que les autres profils, lecture architecture.
