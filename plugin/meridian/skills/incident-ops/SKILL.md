---
compatibility: Requires Méridian API and MCP server (mcp/requests).
name: meridian-incident-ops
description: Analyser un incident ou un SLA avec Méridian, sans écrire ni décider. Utiliser quand la question porte sur une panne, une latence, un incident, un SLA, une mitigation ou un postmortem.
---

# Incident / Opérations

## But
Transformer une situation opérationnelle en dossier vérifiable : impact, preuves, chronologie, options de mitigation et prochaines étapes. L'humain décide.

## Entrées
- question, situation_id, twin_ids ou application_id ;
- tenant et périmètre issus de l'identité, jamais du texte de l'utilisateur.

## Méthode
1. Appeler `meridian_analyser` avec `profil="ops"`, la situation et les Twins/application.
2. Lire le **socle** : faits, preuves, incertitudes, limites.
3. Construire la lecture ops : incident, SLA, mitigation, processus, risques.
4. Ne jamais inventer une chronologie ou une cause : une hypothèse reste une hypothèse.
5. Proposer au plus trois actions : ouvrir incident, vérifier SLA, préparer mitigation, postmortem.
6. Terminer par la décision humaine attendue.

## Garde-fous
- lecture seule ;
- aucune action exécutée ;
- si le socle est vide ou partiel, le dire ;
- rappeler que les preuves périmées ne sont pas des preuves courantes.

## Sortie
Respecter `contracts/reponse.json`. Les faits sont identiques à ceux du profil architecture ou produit ; seule la lentille change.

## Référence

Lire `references/response-contract.md` pour le contrat détaillé.
