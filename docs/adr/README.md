# Architecture Decision Records

Index des décisions d'architecture de Méridian.

| ADR | Titre | Statut | Date |
|-----|-------|--------|------|
| [0001](0001-identite-typed-twin-discovery.md) | Identité typée : Application, Twin et découverte perpétuelle | accepted | 2026-10-30 |
| [0002](0002-orchestrateur-general.md) | Orchestrateur général : intention par le modèle, pas par routeur hardcodé | accepted — amendé par 0003 et 0004 | 2026-10-30 |
| [0003](0003-mesh-transversal-intelligence.md) | Le Mesh est la couche d'intelligence transversale, pas une source ni un outil | accepted | 2026-10-30 |
| [0004](0004-capability-first-harness.md) | Harness capacitaire avec registre d'outils dynamique | accepted | 2026-10-30 |
| [0005](0005-enterprise-object-model.md) | Modèle d'entreprise : huit familles d'objets et Twins non applicatifs | accepted | 2026-10-30 |
| [0006](0006-postgres-unique-sans-projection.md) | Postgres unique, sans projection ni read model séparé | superseded by 0007 | 2026-10-30 |
| [0007](0007-polyglot-postgres-graph.md) | Architecture polyglotte : Postgres pour la connaissance, graph store pour le Mesh | accepted | 2026-10-30 |
| [0008](0008-travail-work-store.md) | Le Travail est un store de travail, pas un objet d'entreprise | accepted | 2026-10-30 |
| [0009](0009-value-ledger.md) | Value Ledger séparé des objets d'entreprise | accepted | 2026-10-30 |
| [0010](0010-monolithe-modulaire-hexagonal.md) | Monolithe modulaire hexagonal, ports et adapters | accepted | 2026-10-31 |
| [0011](0011-runtime-durable-postgres.md) | Runtime durable adossé à PostgreSQL | accepted | 2026-10-31 |
| [0012](0012-outbox-idempotence.md) | Outbox, inbox, idempotence et concurrence | accepted | 2026-10-31 |
| [0013](0013-projection-graphe.md) | Projection graphe et cohérence éventuelle | accepted | 2026-10-31 |
| [0014](0014-adapters-aws-sans-lock-in.md) | Adapters AWS sans lock-in | accepted | 2026-10-31 |
| [0015](0015-frontiere-agent-workflow-outils.md) | Frontière agent, workflow et outils | accepted | 2026-10-31 |
| [0016](0016-fin-personas-demo.md) | Fin des personas de démonstration | accepted | 2026-10-31 |
| [0017](0017-cloture-pilote.md) | Choix de clôture du pilote | superseded by 0018 | 2026-10-31 |
| [0018](0018-suppression-effective-personas-polaris.md) | Suppression effective des personas et de Polaris | accepted | 2026-10-31 |

## Règles

- Un ADR accepté est **immuable** ; une évolution passe par un nouvel ADR qui l'amende ou le remplace.
- Le statut `superseded` référence toujours le remplaçant.
- Les ADR 0003 et 0004 amendent la formulation de 0002 ; le corps de 0002 reste l'historique.
- Le PRD de référence est [`docs/prd/PRD-001-enterprise-intelligence-mesh.md`](../prd/PRD-001-enterprise-intelligence-mesh.md).
