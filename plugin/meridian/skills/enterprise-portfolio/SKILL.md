---
compatibility: Requires Méridian API and MCP server (mcp/requests).
name: meridian-enterprise-portfolio
description: Lire un portefeuille ou un domaine entier avec Méridian et produire une lecture business. Utiliser pour une question globale, un portefeuille, un domaine, une priorisation ou une valeur métier.
---

# Portefeuille et valeur business

## But
Répondre à une question d'entreprise, pas seulement d'application : que se passe-t-il dans le portefeuille, quelles situations comptent, quelles décisions sont ouvertes, quels outcomes et learnings existent.

## Méthode
1. Appeler `meridian_portefeuille` avec le domaine demandé ou sans domaine pour l'entreprise.
2. Lire `valeur` et `valeur_ledger` : situations, décisions, initiatives, outcomes, valeurs attendues/observées, dette de mesure, valeur à risque par devise.
3. Lire `attention` et les propositions, sans conclure à une causalité.
4. Si une application précise est mentionnée, appeler ensuite `meridian_analyser` pour le détail.
5. Produire une lecture business : exposition, priorités, bénéfices, décisions attendues, risques.
6. Ne jamais généraliser un cas applicatif à tout le portefeuille.

## Garde-fous
- agrégat borné au tenant et au domaine ;
- aucun objet sans domaine rattaché automatiquement ;
- aucune causalité inventée entre situation, décision et outcome ;
- lecture seule, décisions humaines.

## Sortie
Utiliser `valeur`, `attention`, `propositions` et `limites`. Le socle reste traçable ; la lentille business ne change pas les faits.

## Référence

Lire `references/portfolio-contract.md` pour le contrat détaillé.
