# ADR-0009 — Value Ledger séparé des objets d'entreprise

- **Statut :** accepted
- **Date :** 2026-10-30
- **Amende :** ADR-0005 (ne force pas la valeur dans les 8 familles), ADR-0008 (le Travail reste distinct)

## Contexte

La valeur business n'est ni un objet d'entreprise comme un Twin, ni une simple mesure dans `Outcome`. Elle relie :
une hypothèse, un propriétaire, un bénéficiaire, une baseline, une cible, une observation, une attribution, des preuves,
un coût, un risque, une période et une revue. La forcer dans `objet_entreprise` mélangerait connaissance et comptabilité
de valeur, et rendrait les agrégats multi-devises faux.

## Décision

1. Créer un **Value Ledger** Postgres dédié (`valeur`), borné au tenant.
2. Une ligne peut pointer vers une décision, une initiative ou un outcome par `objet_source_type`/`objet_source_id`.
3. Ne jamais additionner des devises ou unités différentes ; les agrégats sont séparés par devise/unité.
4. Ne jamais calculer une causalité : `attribution ∈ {directe, contribution, activation, inconnue}` est déclarée.
5. Un outcome observé sans baseline reste une **mesure**, pas une valeur réalisée.
6. Une valeur non mesurée ou sans observation est une **dette de mesure**.
7. L'écriture du ledger est humaine via l'API ; le MCP ne l'expose qu'en lecture.
8. Les agents proposent des valeurs ; ils ne les déclarent pas réalisées.

## Conséquences

- Le ledger est un bounded context, pas une 9e famille d'entreprise.
- Le portefeuille expose les compteurs et le résumé de valeur, séparés par devise/unité.
- Le plugin `benefits-okr` et `enterprise-portfolio` lisent le ledger.
- La valeur reste auditable : preuve, confiance, attribution, date de revue.
