---
name: meridian-benefits-okr
description: Relier une initiative, un outcome et un learning avec Méridian. Utiliser pour une priorité, un bénéfice, un OKR, une décision ou une capitalisation.
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
