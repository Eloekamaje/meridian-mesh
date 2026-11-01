# ADR-0017: Choix de clôture du pilote Méridian

**Date**: 2026-10-31
**Status**: superseded by ADR-0018
**Deciders**: Utilisateur + panel architecture

## Context

Le runtime durable, l'analyse asynchrone et l'interface sans personas sont opérationnels. Plusieurs
sujets restent ouverts mais ne peuvent pas être traités comme de simples correctifs : migration des
champs persona historiques, activation RLS, producer outbox/graphe, worker supervisé, boucle asyncio
persistante et suppression de `demo.echo`. Chacun engage soit des données, soit l'exploitation.

## Decision

Pour le pilote actuel, les choix suivants sont retenus.

1. **Personas backend : gelés, non migrés.**
   - L'interface et le runtime n'exposent plus de personas.
   - Les routes legacy conservent `x_persona` avec le défaut `architecte` pour compatibilité.
   - Aucun nouveau code ne doit dépendre d'une persona ; l'acteur de référence est `actor`/`utilisateur`.
   - La migration des notifications, vues, journal, cases et périmètres vers `actor` est un lot séparé,
     avec migration de données et tests d'intégration.

2. **RLS : opt-in, non activée sur le pilote.**
   - Les tables `execution_*` restent protégées par les filtres tenant applicatifs.
   - L'activation exige deux rôles DB distincts : `meridian_app` (RLS) et `meridian_worker`
     (BYPASSRLS ou accès global contrôlé).
   - Aucune policy ne sera activée sans ces rôles et un test de reprise worker sous RLS.

3. **Graphe : synchronisation directe conservée.**
   - `outbox.py` et `projecteur_graphe.py` restent disponibles et testés.
   - Le producer `graph.synchroniser` n'est pas branché sur le gardien tant que le dispatcher n'est pas
     supervisé ; la synchronisation directe reste la vérité opérationnelle du pilote.
   - Le passage outbox-only est un lot séparé avec projecteur en service et métrique de retard.

4. **Worker : processus manuel supervisé hors Compose.**
   - `python -m jumeau.execution.worker` et `outbox_worker` sont les points d'entrée.
   - L'intégration Compose/AWS attend une image backend et une politique de santé/redémarrage.

5. **Exécuteur agent : `asyncio.run` accepté pour le pilote.**
   - Le worker est synchrone ; un run à la fois.
   - La boucle persistante et l'annulation fine seront traitées avec la concurrence bornée.

6. **`demo.echo` est supprimé du registre de production.**
   - Les tests utilisent des exécuteurs injectés ou des types de file sans exécution.
   - Aucun exécuteur de démonstration n'est exposé.
7. **Inbox et effet idempotent ne sont pas conservés sans consommateur.**
   - Les tables `execution_inbox` et `execution_effet` sont retirées.
   - La prédiction de calibration reste déterministe par `run_id` + `decision_id`.

## Consequences

### Positive
- Pas de migration destructive sans décision de propriété.
- Le pilote reste démontrable et testé.
- Les limites sont explicites et ne sont pas masquées par un faux persona.

### Negative
- Les champs `persona` historiques restent dans le backend.
- RLS, outbox-only, worker Compose et boucle persistante ne sont pas opérationnels.
- `demo.echo` existe encore dans le registre.

### Risks
- Un futur contributeur réintroduit une persona comme frontière de sécurité.
- Le graphe reste couplé à la synchronisation directe.
- Le worker manuel n'est pas redémarré automatiquement.

## Acceptance Criteria

1. Aucun nouveau chemin utilisateur ne dépend de `X-Persona`.
2. Les routes durables utilisent `actor`, jamais une persona de payload.
3. La synchronisation graphe directe reste testée.
4. Les tests du runtime et de l'outbox restent verts.
5. Toute activation RLS ou outbox-only fait l'objet d'un nouvel ADR.

## References

- [ADR-0010](0010-monolithe-modulaire-hexagonal.md), [ADR-0011](0011-runtime-durable-postgres.md)
- [ADR-0013](0013-projection-graphe.md), [ADR-0016](0016-fin-personas-demo.md)
- `backend/jumeau/execution/`, `backend/jumeau/gardien.py`, `backend/jumeau/rls.py`
