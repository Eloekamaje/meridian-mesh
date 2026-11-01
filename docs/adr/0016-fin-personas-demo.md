# ADR-0016: Fin des personas de démonstration

**Date**: 2026-10-31
**Status**: accepted
**Deciders**: Utilisateur + panel architecture

## Context

Les personas (`architecte`, `paiements`, `support`) ont été introduites pour la démonstration : elles
simulent une identité, un espace et un périmètre. Elles ne constituent ni une authentification réelle ni
un modèle d'autorisation. Le runtime durable et la cible AWS ne doivent pas en dépendre.

Le produit conserve une notion distincte : le **profil-lentille** (`architecte`, `ops`, `product_owner`),
qui change la lecture de la même vérité factuelle sans accorder d'autorité supplémentaire.

## Decision

- Supprimer les personas comme **identité et frontière d'autorisation**.
- Remplacer l'acteur par l'identité authentifiée (`utilisateur` OIDC/proxy) ou `demo` en mode démonstration.
- Conserver le tenant comme frontière de sécurité.
- Conserver les profils-lentilles comme choix explicite de lecture, plafonnés à `proposition`.
- Ne plus accepter `X-Persona` sur les nouvelles routes durables (`/api/runs`, `/api/boucle/analyser/runs`).
- Ne pas dériver l'acteur d'un payload client.
- Les partitions de données historiquement indexées par persona (notifications, vues, journal, cases,
  périmètres) seront migrées vers `tenant` ou `actor` dans un lot séparé, avec une décision explicite
  de propriété. Aucune suppression destructive n'est faite dans ce lot.

## Alternatives Considered

### Garder les personas comme RBAC de démo
- **Pros**: aucune migration.
- **Cons**: fausse frontière de sécurité, usurpation, couplage de la cible à la démo.
- **Why not**: les personas ne sont pas une authentification.

### Supprimer toutes les références persona en un seul lot
- **Pros**: propreté immédiate.
- **Cons**: 168 fichiers backend, 517 références, 23 fichiers frontend, partitions de données sans propriétaire cible.
- **Why not**: risque de casser la démo et de perdre l'audit ; migration par étranglement.

### Remplacer persona par un rôle RBAC complet
- **Pros**: modèle de sécurité riche.
- **Cons**: hors périmètre du pilote ; demande une politique d'entreprise.
- **Why not**: la cible actuelle est tenant + acteur authentifié + profils-lentilles.

## Consequences

### Positive
- Le runtime durable ne dépend plus d'un header de démo.
- Les bloquants d'usurpation de persona disparaissent sur les routes durables.
- L'audit conserve un acteur réel.
- Les profils restent une valeur produit, pas un droit.

### Negative
- Les routes produit ne lisent plus `X-Persona`.
- Les notifications, vues, journal et cases sont tenant-wide ou actor-owned.
- La démo est testée sans sélecteur de persona.

### Risks
- Confondre profil-lentille et persona.
- Laisser un header `X-Persona` réintroduire une identité.
- Migrer les notifications/vues vers le mauvais propriétaire.
- Croire que `demo` est une authentification de production.

## Acceptance Criteria

1. `/api/runs` et `/api/boucle/analyser/runs` ne lisent pas `X-Persona`.
2. L'acteur du run vient de `request.state.utilisateur` ou vaut `demo`, jamais du payload.
3. Le profil de lecture reste sélectionnable et plafonné à `proposition`.
4. Le tenant reste obligatoire et testé.
5. Un test prouve qu'un `X-Persona` usurpé ne change pas l'acteur du run.
6. Les partitions persona sont inventoriées avant toute migration destructive.
7. Aucun persona n'est requis pour créer, lire, annuler ou streamer un run durable.

## References

- [ADR-0010](0010-monolithe-modulaire-hexagonal.md), [ADR-0011](0011-runtime-durable-postgres.md)
- [ADR-0015](0015-frontiere-agent-workflow-outils.md)
- `backend/auth.py`, `backend/jumeau/execution/routes.py`, `backend/cognitif_routes.py`
