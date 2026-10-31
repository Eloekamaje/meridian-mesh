---
compatibility: Requires Méridian API and MCP server (mcp/requests).
name: meridian-enterprise-portfolio
description: Lire un portefeuille, un domaine ou l'entreprise entière avec Méridian et produire une lecture business. Utiliser de façon proactive dès qu'un utilisateur demande une vue globale, une priorisation de portefeuille, une concentration de valeur/risque ou un impact transverse, pas une seule application.
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

## Exemple

**Entrée** : « Où la valeur et le risque sont-ils concentrés dans Paiement ? »

**Sortie attendue** : situations, situations hautes, décisions, initiatives, Value Ledger par devise/unité,
limites de rattachement et absence de causalité.

## Quand ne pas utiliser

Pour une seule application sans question de portefeuille : utiliser `meridian-architecture-impact`.

## Format de sortie obligatoire

Toujours inclure :

1. `## Socle de faits`
2. `## Valeur`
3. `## Risque`
4. `## Actions proposées`
5. `## Autorité`
6. `## Prochaines étapes`
7. `## Limites`
