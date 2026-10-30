---
compatibility: Requires Méridian API and MCP server (mcp/requests).
name: meridian-architecture-impact
description: Analyser un changement d'API, d'interface, de dépendance, d'architecture, d'ADR, de migration ou de rollback avec Méridian. Utiliser de façon proactive dès qu'un utilisateur demande l'impact technique d'un changement, même s'il ne nomme pas Méridian.
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

## Référence

Lire `references/output-contract.md` pour le contrat détaillé.

## Exemple

**Entrée** : « Si je change GET /status, quelles applications et interfaces sont impactées ? »

**Sortie attendue** : impact prouvé/inféré/inconnu, opérations `observer`/`agir`, vérifications et ADR proposé.
Aucune relation déduite d'un nom.

## Quand ne pas utiliser

Pour un incident de production sans changement : utiliser `meridian-incident-ops`.
