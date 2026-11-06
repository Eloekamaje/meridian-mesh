# ADR-0023 — ACL de retrieval fail-closed

**Date :** 2026-11-03  
**Statut :** proposed  
**Décideurs :** Sécurité, Architecture, Produit

## Décision

Toute récupération est filtrée **avant** le prompt et **fail-closed**.

- Une ACL absente n'est pas « public » en production : elle est refusée ou dérivée de la source.
- ACL par document, pas seulement par source, dès que la source l'expose.
- Le tenant vient de la requête authentifiée, jamais d'un en-tête client ni d'un défaut d'environnement.
- Le filtre s'applique aux documents live, aux chunks, aux communautés et à la mémoire.
- Les tests couvrent : hors espace, ACL vide, document live restreint, fuite inter-tenant.

## Mode pilote

`ACL_STRICT=0` peut conserver le comportement permissif pour une démonstration. La production
exige `ACL_STRICT=1`.
