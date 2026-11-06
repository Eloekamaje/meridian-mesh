# ADR-0021 — Retrieval unifié et preuve documentaire

**Date :** 2026-11-03  
**Statut :** proposed — décision de revue  
**Décideurs :** Architecture, Sécurité, Produit, Retrieval

## Décision

Un seul service de retrieval alimente les raisonnements. Le chat et `/analyser` ne peuvent plus
avoir deux politiques de contexte concurrentes.

```text
Question
→ RetrievalService
→ candidats (Claims, preuves, mémoire, documents, communautés)
→ filtrage tenant/ACL/version
→ classement unifié
→ ContextePack
→ modèle
```

- Un chunk documentaire reste un **candidat** ; il devient une preuve citée avec source, version et locator.
- Le ContextePack porte l'empreinte, les inconnues, les limites et les scores.
- Aucun prompt ne reçoit directement un chunk sans passer par ce contrat.
- Les classements `retrieval_hybride`, `contexte.py` et `pg_recherche.py` convergent vers une
  politique unique ou des politiques explicitement étagées par type de source.

## Conséquences

- Le code de `cases.py` doit déléguer au service, pas appeler les stores directement.
- Le retrieval devient testable sans FastAPI.
- Un score de retrieval non nul ne vaut pas preuve : les gates restent.
