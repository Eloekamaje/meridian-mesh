# ADR-0015: Frontière agent, workflow et outils

**Date**: 2026-10-31
**Status**: accepted
**Deciders**: Panel architecture (Principal Architect, Runtime, IA, Staff) + utilisateur

## Context

Le LLM et les agents sont probabilistes ; les décisions d'entreprise, les approbations, les politiques et les
effets externes ne le sont pas. Aujourd'hui, Flore choisit ses outils et peut enchaîner des lectures dans un
tour. Les écritures sont encore limitées, mais la cible doit distinguer clairement ce qui raisonne de ce qui
décide et de ce qui agit.

## Decision

Séparer trois responsabilités :

1. **Workflow déterministe** : états, gates, approbations, retries, deadlines, compensation. Il possède le run.
2. **AgentRuntime** : propose une réponse structurée, des citations, une confiance, un usage et une liste
   d'outils demandés. Il ne décide pas, n'écrit pas et ne persiste pas.
3. **ToolGateway** : seule voie d'effet. Il applique manifeste, policy, autorisation, approbation, timeout,
   audit, idempotence et allowlist.

Règles :

- Un événement ne déclenche jamais implicitement une décision métier ; il déclenche un workflow explicite.
- L'agent ne reçoit jamais un identifiant d'écriture direct ; il propose, le workflow dispose.
- Le contexte est assemblé par un port `Evidence/Context`, pas par l'agent.
- Les citations, schémas, budgets et policies sont validés avant toute réponse ou effet.
- SSE est un transport d'interface ; le bus d'événements métier est l'outbox. Ce sont deux choses distinctes.
- MCP est une source/outil read-only derrière un port ; il ne devient pas le cœur.
- Le raisonnement interne n'est pas persisté ; on conserve les faits, les sources, les décisions, les
  propositions et les traces d'outils.

## Alternatives Considered

### Alternative 1: L'agent comme orchestrateur
- **Pros**: flexibilité, moins de code déterministe.
- **Cons**: non-déterminisme, rejeu difficile, policy dans le prompt, effets imprévisibles.
- **Why not**: le workflow doit rester explicite et testable.

### Alternative 2: L'agent écrit directement
- **Pros**: moins de cérémonie.
- **Cons**: pas d'approbation, pas d'idempotence, risque de fuite et d'effet non voulu.
- **Why not**: toute écriture passe par ToolGateway.

### Alternative 3: Les événements déclenchent des décisions
- **Pros**: automatisation.
- **Cons**: décision sans humain, boucles d'effets, responsabilité floue.
- **Why not**: l'humain gouverne ; un événement ne fait qu'ouvrir un workflow.

### Alternative 4: Un port AgentRuntime très générique
- **Pros**: indépendance fournisseur.
- **Cons**: plus petit dénominateur, fuite des capacités, appauvrissement.
- **Why not**: contrat étroit centré sur proposition structurée, citations, budget et streaming.

## Consequences

### Positive
- Les décisions et effets sont auditables et rejouables.
- Le modèle est remplaçable (Strands, Bedrock, local).
- Le cœur et les tests tournent sans modèle.
- Les outils ont un contrat et une policy uniques.

### Negative
- Plus de code déterministe autour de l'agent.
- Les prompts et gates doivent être maintenus ensemble.
- Le port agent doit rester assez riche pour le streaming et les citations.

### Risks
- Un port trop générique qui fuit les spécificités du fournisseur.
- Une policy dupliquée entre prompt et ToolGateway.
- Un streaming confondu avec le bus d'événements.
- Une approbation humaine contournée par un outil.

## Acceptance Criteria

1. Un agent ne peut pas persister ni appeler un connecteur d'écriture directement.
2. Toute proposition passe par validation de schéma, citations, budget et policy.
3. Toute écriture passe par ToolGateway avec audit et idempotence.
4. Un run peut être rejoué sans rappeler le modèle si la proposition est persistée.
5. SSE ne transporte que l'interface ; l'outbox porte les événements métier.
6. Les tests du cœur tournent sans LLM ni MCP.
7. Une décision humaine est explicite et persistée ; aucun événement ne la remplace.

## References

- [ADR-0002](0002-orchestrateur-general.md), [ADR-0004](0004-capability-first-harness.md)
- [ADR-0011](0011-runtime-durable-postgres.md), [ADR-0012](0012-outbox-idempotence.md)
- `backend/jumeau/orchestrateur.py`, `backend/jumeau/executeur.py`, `backend/jumeau/harness.py`
- `backend/jumeau/protocole.py`, `plugin/meridian/mcp/server.py`
