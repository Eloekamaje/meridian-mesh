# Couverture du code legacy

**Date :** 2026-11-03  
**Objet :** distinguer indexation syntaxique, preuve et connaissance métier.

## Quatre niveaux de couverture

| Niveau | Ce que cela veut dire |
|---|---|
| 1. Indexé | le code est parsé et présent dans le graphe |
| 2. Citable | une ligne peut être lue et citée avec un locator |
| 3. Claim | Meridian extrait une connaissance typée et la prouve |
| 4. Impact | les relations sont utilisées dans les parcours d’impact |

## Matrice

| Technologie | Indexation CBM | Claims Meridian | Verdict |
|---|---|---|---|
| Java | oui, Hybrid LSP | routes/config/classes selon extracteurs | bon index, Claims partiels |
| JEE / Spring | oui côté Java | sidecar Java + packs | routes, composants, injections, mapping JPA |
| JSP | sidecar JSP | interfaces utilisateur localisées | indexé et lié aux Servlets/Spring |
| Python | oui, Hybrid LSP | routes, variables, dépendances | bon |
| TypeScript/JS | oui, Hybrid LSP | routes, variables, dépendances | bon |
| C#/.NET | oui, Hybrid LSP | partiel | à tester |
| Go | oui, Hybrid LSP | partiel | à tester |
| C/C++ | oui, Hybrid LSP | partiel | à tester |
| Kotlin | oui, Hybrid LSP | partiel | à tester |
| Rust | oui, Hybrid LSP | faible | à adapter |
| PHP | oui, Hybrid LSP | faible | à adapter |
| Ruby | oui, tree-sitter | faible | à adapter |
| **COBOL** | **oui, tree-sitter + sidecar** | **CALL/COPY/EXECUTE/LIT_DATASET** | indexé et promouvable |
| **XML** | **oui, tree-sitter** | **WSDL/OpenAPI/config seulement** | partiel |
| **JSP** | **sidecar** | **INTERFACE_UTILISATEUR** | couvert structurellement |
| JCL | sidecar | EXECUTE/LIT_DATASET | couvert structurellement |
| PL/I | sidecar | candidats | inventaire structurel |
| RPG | sidecar | candidats | inventaire structurel |
| ABAP | sidecar | candidats | inventaire structurel |
| Oracle Forms | sidecar XML | candidats | inventaire structurel |
| PowerBuilder | sidecar texte | candidats | PBL binaire partiel |
| Ada | non | non | Gap |
| Fortran | oui, tree-sitter | non | indexé seulement |

## Ce que CBM ne fait pas pour le legacy

- il ne comprend pas nécessairement les dialectes : COBOL CICS, DB2, VSAM, copybooks ;
- il ne crée pas de Claims métier ;
- il ne modélise pas les transactions mainframe ;
- il ne résout pas JSP/EL/taglibs ;
- il ne remplace pas un analyseur de flux ou un parseur JCL.

## Plan legacy

Le socle fédéré est décrit dans [legacy-index-federation.md](legacy-index-federation.md).

1. **COBOL** : PROGRAM-ID, COPY, CALL, paragraphes, CICS/DB2, copybooks, JCL.
2. **JSP** : JSP/EL, taglibs, formulaires, routes Servlet, liens vers Java.
3. **XML** : WSDL/OpenAPI déjà, puis XSD et configurations.
4. **Mainframe** : JCL, CICS, DB2, VSAM ; hors CBM.
5. **Tests** : corpus publics, citations versionnées, claims prouvés.

## Règle produit

Ne jamais dire « on couvre le COBOL » parce que CBM le parse. La couverture réelle se mesure au
niveau **Claim + preuve + impact**, pas au niveau de l’index.
