# Revue du pilote — 2026-10-30

## Décision

**No-go pour la production et le passage à l'échelle.**

**Go conditionnel pour une seconde itération contrôlée** après correction et revue humaine.

## Résultats automatisés

- Incident Paiements, 5 runs : `skill+mcp` **5/5**, `checklist+mcp` **0/5**, `data-only` **0/5**.
- Changement R-118, 5 runs : `skill+mcp` **5/5** avec budget 2,00 USD ; `checklist+mcp` **1/5** ;
  `data-only` **1/5** à 1,25 USD.
- Le format imposé par la skill explique une partie de l'avantage ; ce n'est pas une preuve de
  meilleure décision business.

## Revue aveugle

- 16 échantillons, 8 reviewers **agents**, pas des humains.
- 13 approbations sur 16.
- 3 rejets, tous sur des sorties skill :
  - incohérence du nombre d'identifiants d'impact ;
  - inversion amont/aval dans une phrase ;
  - action `ouvrir_incident` présentée comme issue du socle.
- Corrections appliquées : listes amont/aval cohérentes avec la troncature, suppression du fallback
  d'action non sourcée, consigne explicite sur le sens amont/aval. **À re-revoir.**

## Value Ledger

- Deux hypothèses, aucune valeur réalisée.
- `observe` reste `null` : pas de baseline, pas d'outcome.
- La dette de mesure est visible et ne doit pas être présentée comme un ROI.

## Gates

- **G1 automatique** : passé sur les deux scénarios, avec un budget hétérogène.
- **G2 humain** : non passé — aucune revue humaine, seulement des agents.
- **G3 valeur** : non passé — aucune baseline/outcome réel.
- **G4 sécurité** : lecture seule, pas d'écriture constatée ; RLS/OIDC non activés.

## Seconde itération autorisée

1. Rejouer les sorties corrigées et refaire la revue humaine (6-8 personnes).
2. Conserver le budget 2,00 USD pour R-118 et le documenter.
3. Remplir baseline/outcome sur les deux valeurs.
4. Revoir la direction amont/aval et l'ancrage des actions.
5. Décider scale/no-scale après G2 et G3.
