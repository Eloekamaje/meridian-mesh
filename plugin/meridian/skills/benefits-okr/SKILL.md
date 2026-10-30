---
compatibility: Requires Méridian API and MCP server (mcp/requests).
name: meridian-benefits-okr
description: Relier priorité, bénéfice, valeur, ROI, OKR, KPI, business case, outcome et learning avec Méridian. Utiliser de façon proactive dès qu'un utilisateur demande si une initiative vaut le coup, si un bénéfice est réalisé, ou ce qu'il faut mesurer, même s'il ne nomme pas Méridian.
---

# Bénéfices, OKR et apprentissage

## But
Aider à décider et à apprendre : bénéfice attendu, mesure, cible, outcome observé, learning réutilisable.

## Méthode
1. Appeler `meridian_analyser` avec `profil="product_owner"` et le contexte.
2. Appeler `meridian_valeurs` ou `meridian_valeur_resume` pour le Value Ledger.
3. Lire les learnings existants ; ne jamais fabriquer un learning sans enseignement explicite.
4. Distinguer bénéfice attendu, mesure observée, cible, baseline, attribution et écart.
5. Si la baseline ou l'outcome manque, déclarer une **dette de mesure**, pas une valeur réalisée.
6. Proposer une décision, une priorité ou une mesure d'outcome.
7. Capitaliser seulement si un humain fournit l'enseignement et les conditions de réutilisation.

## Garde-fous
- pas de bénéfice inventé ;
- pas de learning automatique ;
- les options restent des propositions ;
- la décision appartient au rôle humain autorisé.

## Sortie
Respecter `contracts/reponse.json`. Même socle que les autres profils, lecture produit.

## Référence

Lire `references/value-ledger.md` pour le contrat détaillé.

## Exemple

**Entrée** : « Cette initiative a-t-elle produit le bénéfice attendu ? »

**Sortie attendue** : baseline, cible, observé, écart, attribution et dette de mesure.
Si l'outcome n'existe pas, le dire ; ne pas inventer de learning.

## Quand ne pas utiliser

Pour une panne ou un SLA : utiliser `meridian-incident-ops`.
