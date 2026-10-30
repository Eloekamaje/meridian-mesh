---
compatibility: Requires Méridian API and MCP server (mcp/requests).
name: meridian-incident-ops
description: Analyser un incident, une panne, une latence, un SLA ou un postmortem avec Méridian. Utiliser de façon proactive et en priorité dès qu'un utilisateur mentionne un incident, une panne, une latence, un SLA, un postmortem, une mitigation, un ticket support ou une production dégradée, même s'il ne nomme pas Méridian.
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

## Exemple

**Entrée** : « Depuis 14 h, les paiements sont lents et le support reçoit des tickets. »

**Sortie attendue** : socle de faits/preuves, lecture incident + SLA, options de mitigation, limites, autorité `proposition`.
Ne pas conclure à une cause sans preuve.

## Quand ne pas utiliser

Pour une priorisation de portefeuille ou un bénéfice attendu : utiliser `meridian-enterprise-portfolio`
ou `meridian-benefits-okr`.
