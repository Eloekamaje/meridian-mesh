# Modèle de valeur Méridian

## Principe

Une connaissance n'a de valeur que si elle change une décision. Une décision n'a de valeur que si son outcome est
mesuré, attribué et réutilisé. Le Value Ledger conserve cette chaîne sans confondre mesure, bénéfice et causalité.

## Chaîne

`Source → Claim → Situation → Décision → Initiative → Outcome → Learning → Valeur`

## Types de valeur

| Type | Exemples | Unité |
|---|---|---|
| `revenu` | conversion, marge, revenu incrémental | devise |
| `cout_evite` | incident évité, perte évitée | devise |
| `cout_reduit` | run, licence, infrastructure | devise |
| `temps` | délai de décision, time-to-market | jours/heures |
| `qualite` | défauts, reprises, exactitude | %/nombre |
| `sla` | disponibilité, p95, MTTR | %/ms |
| `risque` | exposition, perte attendue, contrôle | devise/score |
| `conformite` | constat, CAPA, contrôle efficace | nombre/% |
| `client` | abandon, satisfaction, effort | %/score |
| `connaissance` | réutilisation, couverture, contradiction tranchée | nombre/% |
| `strategie` | optionalité, résilience, capacité | score |
| `autre` | valeur non classée | libre |

## Champs du ledger

`id, tenant_id, type, libelle, proprietaire, beneficiaire, domaine, objet_source_type, objet_source_id, baseline,
cible, observe, unite, devise, periode, attribution, confiance, preuves, fraicheur, cout, risque, statut,
date_revue, donnees`.

## Statuts

`hypothese → mesuree → validee → realisee` ; branches `deplacee`, `detruite`, `abandonnee`.

- **hypothese** : valeur attendue, non observée.
- **mesuree** : observation disponible, attribution pas encore validée.
- **validee** : observation et attribution revues.
- **realisee** : bénéfice constaté sur la période.
- **deplacee** : valeur transférée ailleurs.
- **detruite** : valeur annulée ou négative.
- **abandonnee** : hypothèse fermée sans réalisation.

## Attribution

- `directe` : lien causal étroit et documenté ;
- `contribution` : contribution plausible avec d'autres facteurs ;
- `activation` : la valeur existait, Méridian l'a révélée ;
- `inconnue` : pas d'attribution défendable.

## Règles

1. Pas de baseline, pas de valeur réalisée.
2. Pas d'unité/devise, pas d'agrégat monétaire.
3. Pas de preuve, pas de validation.
4. Pas de contre-factuel, pas d'attribution directe.
5. Une valeur déplacée n'est pas une valeur créée.
6. Une valeur négative est une valeur.
7. Une valeur observée sans cible reste une mesure.
8. Un agent peut proposer ; l'humain valide.

## Anti-patterns

- compter les Claims, Twins ou situations comme valeur ;
- additionner des euros et des jours ;
- confondre activité, output, outcome et impact ;
- déclarer un ROI sans baseline ni période ;
- attribuer tout le bénéfice à Méridian ;
- cacher la dette de mesure ;
- ignorer le coût du délai et le coût de la mesure.
