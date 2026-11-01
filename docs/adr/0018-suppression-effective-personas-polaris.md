# ADR-0018: Suppression effective des personas et de Polaris

**Date**: 2026-10-31
**Status**: accepted
**Deciders**: Utilisateur

## Context

L'ADR-0017 gelait encore les champs persona historiques et laissait la démonstration Polaris.
L'utilisateur refuse cette dette : aucune persona de démonstration, aucun menu Polaris, aucun code
de compatibilité caché.

## Decision

- Supprimer `PERSONAS`, `X-Persona` et toute résolution de persona dans le backend.
- L'acteur est l'utilisateur authentifié, sinon `demo`.
- Les notifications, vues et espaces sont tenant-wide ; les cases et le journal sont actor-owned.
- Supprimer `/personas`, `/demo/reinitialiser`, `/demo/actes`, `DEMO_ACTES`, `COMMANDE_DEMO`.
- Supprimer la route frontend `/demo`, Polaris, le kiosque, le DemoProvider, le DemoTour et leurs fixtures.
- Supprimer la spécification Polaris et ses captures.
- Ne conserver aucune branche, constante ou import de compatibilité persona.
- Le seed de démonstration reste un jeu de données métier, pas un persona.

## Consequences

### Positive
- Plus de double modèle identité/persona.
- Plus de menu de démonstration ni de code Polaris.
- Le runtime et les routes produit utilisent `acteur`.
- Le code exécuté ne contient plus `persona`.

### Negative
- Les données historiques indexées par persona doivent être relues sans ce champ.
- Le mode `demo` partage l'acteur `demo`.
- Le seed est réinitialisé par la version de seed.

## Acceptance Criteria

1. `grep -RIn "persona\|PERSONAS\|X-Persona" backend frontend/src` ne retourne aucune occurrence exécutable.
2. `/api/demo/reinitialiser` et `/api/demo/actes` retournent 404.
3. La route `/demo` n'existe plus.
4. `pytest jumeau`, les tests frontend et le build passent.
5. Aucun code mort Polaris ou persona n'est conservé.
