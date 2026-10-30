# Architecture Decision Records

Index des décisions d'architecture de Méridian.

| ADR | Titre | Statut | Date |
|-----|-------|--------|------|
| [0001](0001-identite-typed-twin-discovery.md) | Identité typée : Application, Twin et découverte perpétuelle | accepted | 2026-10-30 |
| [0002](0002-orchestrateur-general.md) | Orchestrateur général : intention par le modèle, pas par routeur hardcodé | accepted — amendé par 0003 et 0004 | 2026-10-30 |
| [0003](0003-mesh-transversal-intelligence.md) | Le Mesh est la couche d'intelligence transversale, pas une source ni un outil | accepted | 2026-10-30 |
| [0004](0004-capability-first-harness.md) | Harness capacitaire avec registre d'outils dynamique | accepted | 2026-10-30 |
| [0005](0005-enterprise-object-model.md) | Modèle d'entreprise : huit familles d'objets et Twins non applicatifs | accepted | 2026-10-30 |

## Règles

- Un ADR accepté est **immuable** ; une évolution passe par un nouvel ADR qui l'amende ou le remplace.
- Le statut `superseded` référence toujours le remplaçant.
- Les ADR 0003 et 0004 amendent la formulation de 0002 ; le corps de 0002 reste l'historique.
- Le PRD de référence est [`docs/prd/PRD-001-enterprise-intelligence-mesh.md`](../prd/PRD-001-enterprise-intelligence-mesh.md).
