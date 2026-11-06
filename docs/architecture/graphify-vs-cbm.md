# Graphify vs CBM — comparaison sur Méridian

**Date :** 2026-11-03  
**Périmètre :** dépôt `meridian-mesh`  
**But :** comparer deux index, pas désigner un vainqueur universel.

## Versions

- Graphify : 0.9.61, graphe `graphify-out/graph.json`.
- CBM : binaire local `codebase-memory-mcp`, projet `home-majella-Documents-meridian-mesh`.

## Mesures Graphify

| Mesure | Valeur |
|---|---:|
| Nœuds | 21 093 |
| Arêtes | 39 975 |
| Communautés | 1 118 |
| Fichiers du corpus | 1 118 |
| Extraction | 96 % EXTRACTED, 4 % INFERRED |
| Fichiers non classés | 37 : XML 16, sans extension 10, `.service` 4 |
| Commit du graphe | `729706b8` |

Graphify contient du code, de la documentation, des ADR, des rapports et des images : ce n’est pas
un index de code pur.

## Mesures CBM

| Mesure | Valeur |
|---|---:|
| Nœuds | 18 437 |
| Arêtes | 23 528 |
| Statut | ready |
| Indexé le | 2026-10-27 |
| Fichiers parse partiel | 3 |
| Fichiers non indexés | 11 |
| Dossiers non indexés | 13 |
| Cross-repo | never_run |
| Watch | non surveillé (`cli_session`) |

`check_index_coverage` répond `no_recorded_issue`, mais avec `metadata_changed` / `not_tracked` :
**ce n’est pas une preuve de complétude**.

## Verdict

- **Graphify** : meilleur pour la carte d’architecture, les communautés, les docs et la navigation.
- **CBM** : meilleur pour les symboles, appels, routes et la précision de code.
- **Aucun des deux** : couverture framework Spring/EJB, JSP, COBOL copybooks, JCL.
- **Méridian** : doit rester la couche Claims/preuves/ACL.

## Règle

Le graphe Graphify et l’index CBM sont des **observations**.  
Une arête `INFERRED` n’est pas une preuve.  
Un `no_recorded_issue` CBM n’est pas une preuve de complétude.
