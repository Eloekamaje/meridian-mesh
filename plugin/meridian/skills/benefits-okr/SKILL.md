---
name: meridian-benefits-okr
description: Relier une initiative, un outcome et un learning avec Méridian. Utiliser pour une priorité, un bénéfice, un OKR, une décision ou une capitalisation.
---

# Bénéfices, OKR et apprentissage

## But
Aider à décider et à apprendre : bénéfice attendu, mesure, cible, outcome observé, learning réutilisable.

## Méthode
1. Appeler `meridian_analyser` avec `profil="product_owner"` et le contexte.
2. Lire les learnings existants ; ne jamais fabriquer un learning sans enseignement explicite.
3. Distinguer bénéfice attendu, mesure observée, cible et écart.
4. Proposer une décision, une priorité ou une mesure d'outcome.
5. Si aucun outcome n'existe, le dire et proposer de mesurer.
6. Capitaliser seulement si un humain fournit l'enseignement et les conditions de réutilisation.

## Garde-fous
- pas de bénéfice inventé ;
- pas de learning automatique ;
- les options restent des propositions ;
- la décision appartient au rôle humain autorisé.

## Sortie
Respecter `contracts/reponse.json`. Même socle que les autres profils, lecture produit.
