# ADR-0028 — Analyseurs sémantiques legacy externes

**Date :** 2026-11-03
**Statut :** accepted
**Décideurs :** Architecture, Ingestion legacy

## Contexte

Les sidecars regex donnaient une couverture structurelle, mais pas un AST fiable. Pour ABAP,
RPGLE, PL/I et les sources PowerBuilder extraites, un parseur complet ne peut pas être maintenu
sérieusement dans Méridian : les grammaires sont grandes, évolutives et parfois peu documentées.

## Décision

Méridian **orchestre des moteurs externes** et normalise leurs sorties en `Observation` :

| Technologie | Moteur | Licence | Sortie |
|---|---|---|---|
| ABAP | `@abaplint/core` via Node | MIT | AST/statements |
| RPGLE | `rpgleparser` ANTLR via Java | LGPL 2.1 | parse tree |
| PL/I | `grammars-v4/pl1` ANTLR | BSD | parse tree |
| PowerBuilder | extraction PBL MIT + parseur texte | MIT | sources et AST local |
| Oracle Forms | export XML | — | modèle Forms |

Le sidecar structurel reste le **fallback** si le moteur n'est pas installé ou si le fichier
n'est pas supporté. Le rapport expose toujours `parser` et `provider`, et la couverture dit
`partiel` ou `non_supporte` quand le moteur manque.

Les moteurs sont installés par les scripts de `tools/` ; jars, classes, parseurs générés et
`node_modules` ne sont pas versionnés.

## Conséquences

### Positives

- AST/parse tree réels pour ABAP, RPGLE et PL/I ;
- extraction complète des sources d'un `.pbl` (objets `.sra/.srd/.srs/.srw/.sru/.srf/.srm/...`) ;
- Oracle Forms XML garde un modèle sémantique exploitable ;
- les sidecars regex restent disponibles pour les environnements sans moteur.

### Limites

- ABAP/RPG/PLI : le moteur fournit une syntaxe/AST, pas une analyse de flux de données ou de
  typage inter-programmes complète.
- Oracle Forms `.fmb` reste binaire non décodé ; seul l'export XML est sémantique.
- PowerBuilder `.pbl` est **extrait** complètement, mais l'analyse PowerScript/DataWindow reste
  structurelle ; une sémantique complète exigerait un parseur PowerScript dédié.
- Les moteurs ajoutent Node, Java et ANTLR au poste d'indexation.
