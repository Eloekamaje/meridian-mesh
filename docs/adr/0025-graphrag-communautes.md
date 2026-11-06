# ADR-0025 — GraphRAG local par défaut, global conditionnel

**Date :** 2026-11-03  
**Statut :** proposed  
**Décideurs :** Produit, Architecture, Retrieval

## Décision

- **Local** : retrieval autour des Twins actifs, profondeur bornée, toujours disponible.
- **Global** : rapports de communautés précompilés, jamais calculés à la volée dans le chat.
- Les communautés sont un index dérivé versionné, filtré par tenant/ACL.
- Le mode global n'est activé que si des questions de synthèse sont mesurées.
- Aucun rapport de communauté ne devient un Claim sans preuve et promotion humaine.

## Conséquences

- Worker de calcul des communautés planifié.
- `graph_community` porte version, fraîcheur et ACL.
- Le mode `global` dégrade explicitement si l'index est absent.
