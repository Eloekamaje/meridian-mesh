# Analyseurs sémantiques legacy

**Date :** 2026-11-03
**Statut :** moteurs branchés, limites de profondeur documentées

## Principe

```text
source
→ analyseur dédié
→ AST / parse tree
→ Observation normalisée
→ liens
→ Findings
→ Claims si la recette et la preuve localisée passent
```

Un sidecar regex reste un **fallback**, jamais une prétendue analyse sémantique.

## Moteurs

| Technologie | Moteur | Commande de préparation |
|---|---|---|
| ABAP | `@abaplint/core` | `npm install --prefix tools/abaplint` |
| RPGLE | `rpgleparser` + ANTLR | voir `tools/rpgle/README.md` |
| PL/I | `grammars-v4/pl1` + ANTLR | `bash tools/pli/generate.sh` |
| PowerBuilder | extraction PBL MIT | aucune dépendance |
| Oracle Forms | export XML | aucune dépendance |

## Installation

```bash
# ABAP
npm install --prefix tools/abaplint
# RPGLE : voir tools/rpgle/README.md
# PL/I
cd tools/pli && ./generate.sh
```

## Comportement

- Si le moteur est présent : `provider` reste `abap`, `rpg`, `pli` ; `parser` indique le moteur.
- Si le moteur manque : fallback structurel, couverture `partiel` ou `non_supporte` selon le cas.
- Les erreurs de parse ne lèvent jamais : elles deviennent une couverture partielle.
- Les objets `.pbl` sont éclatés en sources `pbl://<fichier>/<objet>`.
- Aucun Claim n'est produit directement par un analyseur : la promotion reste dans `legacy_packs`.

## Limites assumées

- ABAP/RPG/PLI : AST/parse tree, pas typage inter-programmes ni flux de données complet.
- Oracle Forms `.fmb` : binaire non décodé ; l'export XML est la source sémantique.
- PowerBuilder : extraction complète des sources PBL, analyse PowerScript/DataWindow encore
  structurelle.
- Les dépendances Node/Java/ANTLR doivent être présentes sur le poste d'indexation.

## Résultats de validation

- ABAP : parse abaplint réel, statements AST indexés ; runner Node testé.
- RPGLE : parse tree ANTLR réel (`Analyze` Java), 72 tokens / 137 nœuds sur le fixture.
- PL/I : grammaire ANTLR générée, procédures/variables/appels/SQL indexés.
- PowerBuilder : `wiz_setup.pbl` → **3 objets source** extraits, dont `.sru` et `.srw`.
- Oracle Forms : triggers XML → tables SQL et appels de formulaire.
- Corpus versionné : **20 Claims** vérifiés ; les moteurs sémantiques alimentent les mêmes Observations.
