# ADR-0004 — Harness capacitaire avec registre d'outils dynamique

**Date :** 2026-10-30  
**Statut :** Accepté  
**Décideurs :** Produit, architecture, sécurité, exploitation  
**Complète :** ADR-0003  
**Amende :** ADR-0002

## Contexte

L'orchestrateur général a été livré avec une **boîte à trois outils** :

- `resoudre_application` ;
- `mobiliser_jumeaux` ;
- `concevoir_architecture`.

Cette boîte a corrigé le cas dating et évité la recherche systématique de jumeaux. Mais elle est **applicative et figée** :

- elle ne représente ni les processus, ni les capacités, ni les parcours, ni les situations, ni les décisions ;
- chaque nouvelle source ou capacité exige de modifier le code du noyau ;
- elle confond **outils** et **architecture** ;
- elle ne permet pas d'ajouter un outil à la volée, alors que Méridian doit intégrer des sources et des capacités hétérogènes ;
- elle ne porte ni manifeste, ni permissions, ni coût, ni preuve produite, ni découverte.

La question est donc : **une boîte scriptée est-elle la bonne pratique, ou faut-il un harness avec outils pluggables ?**

## Décision

Méridian adopte un **harness capacitaire** :

1. **Le noyau n'est pas la liste d'outils.** Le noyau est le modèle d'entreprise, le Mesh, les Claims/preuves/temporalité, la politique et la boucle cognitive.
2. **Les outils sont des adaptateurs** à des capacités d'entreprise.
3. **Chaque outil est déclaré par manifeste** :
   - nom, description, version ;
   - capacité (`situer`, `observer`, `prouver`, `relier`, `investiguer`, `décider`, `agir`, `mesurer`, `apprendre`, `concevoir`) ;
   - types d'objets lus/écrits ;
   - schéma d'entrée/sortie ;
   - portée tenant/persona/périmètre ;
   - permissions et effets de bord ;
   - coût, timeout, quotas ;
   - preuve produite et mode de résultat (`DECLARED`, `OBSERVED`, `INFERRED`, `PROPOSED`).
4. **Un registre** expose un catalogue filtré par politique.
5. **Le modèle découvre les outils à la demande** (`search_tools`, `describe_tool`) ; il ne reçoit pas tous les schémas dans le prompt.
6. **Un exécuteur** applique les limites, l'audit, la redaction, les timeouts et les retries.
7. **Un nouvel outil read-only** peut être ajouté par **manifeste/MCP** sans modifier le noyau.
8. **Aucun modèle n'installe, n'autorise ou ne code un outil à la volée.** Le plug-in est une action d'opérateur, signée/allowlistée, tenant-scoped.
9. **Les trois outils actuels restent** comme adaptateurs du noyau, pas comme architecture.

### Capacités minimales

| Capacité | Exemples d'outils |
|---|---|
| `situer` | domaines, capacités, processus, parcours, équipes |
| `observer` | sources, artefacts, traces, configurations |
| `prouver` | claims, preuves, fraîcheur, contradictions |
| `relier` | relations, propagation, domaines émergents |
| `maturer` | observation → hypothèse → claim |
| `investiguer` | hypothèses, experts, contributions |
| `décider` | scénarios, arbitrages, décisions |
| `agir` | initiatives, Travaux, livrables |
| `mesurer` | outcomes, indicateurs |
| `apprendre` | apprentissages, réutilisation |
| `concevoir` | architecture cible, transformation |
| `chercher_outil` | découverte du catalogue |

### Règles de sécurité

- Lecture seule par défaut.
- Écritures et actions sensibles soumises à approbation humaine.
- Manifeste signé ou source autoritative.
- Tenant et périmètre vérifiés côté plateforme, jamais côté prompt.
- Secrets par référence, jamais dans un manifeste, un prompt, un log ou une réponse.
- Audit append-only de chaque découverte, chargement et appel.

## Alternatives considérées

### Alternative 1 — Garder la boîte à trois outils
- **Avantages** : simple, testable, peu coûteuse.
- **Inconvénients** : app-first, non extensible, ignore les capacités d'entreprise.
- **Pourquoi rejetée** : acceptable comme amorce, pas comme architecture cible.

### Alternative 2 — Laisser le modèle créer/installer des outils
- **Avantages** : flexibilité maximale.
- **Inconvénients** : surface d'attaque majeure, permissions incontrôlées, supply chain, injection.
- **Pourquoi rejetée** : contredit la gouvernance et la sécurité.

### Alternative 3 — Un unique outil `call_tool(nom, args)`
- **Avantages** : catalogue compact.
- **Inconvénients** : schémas pauvres, validation faible, découverte opaque, erreurs difficiles à corriger.
- **Pourquoi rejetée** : les outils typés et découvrables sont plus sûrs et plus explicables.

### Alternative 4 — Tous les outils dans le prompt
- **Avantages** : le modèle voit tout.
- **Inconvénients** : explosion du contexte, bruit, coût, sélection dégradée.
- **Pourquoi rejetée** : la découverte filtrée est préférable.

### Alternative 5 — MCP uniquement
- **Avantages** : standard, écosystème.
- **Inconvénients** : tous les fournisseurs ne parlent pas MCP.
- **Pourquoi rejetée comme unique voie** : le registre accepte MCP, manifests internes et adaptateurs OpenAPI.

## Conséquences

### Positives

- Ajout d'une source ou d'un outil sans modifier le noyau.
- Découverte et sélection d'outils observables.
- Capacités d'entreprise explicites.
- Sécurité et audit centralisés.
- Les trois outils actuels deviennent des adaptateurs remplaçables.

### Négatives / coûts

- Complexité du registre, des manifests, de la politique et de l'exécuteur.
- Besoin de tests de sécurité, de contrat et d'évaluation de sélection.
- Risque de prolifération d'outils sans curation.
- Le modèle doit apprendre à chercher/charger un outil.

### Risques

- **Manifeste piégé** : signature/allowlist, validation stricte.
- **Outil qui ment** : preuve produite, mode, provenance, contradiction.
- **Sélection erronée** : jeu d'or, traces, budgets.
- **Coût** : quotas, cache, découverte compacte.

## Critères d'acceptation

1. Un outil read-only peut être ajouté par manifeste/MCP, découvert et appelé sans modification du code du noyau.
2. Le catalogue est filtré par tenant, persona, périmètre et risque.
3. Un outil sans permissions explicites n'est pas exposé.
4. Chaque appel est audité et chaque résultat porte sa provenance.
5. Le modèle peut lister les capacités, chercher un outil et charger son schéma à la demande.
6. Une action sensible est bloquée sans approbation.
7. Les trois outils actuels sont documentés comme adaptateurs, pas comme noyau.
8. Un test d'architecture échoue si un outil est ajouté en modifiant directement la liste du prompt.

## Références

- [PRD-001](../prd/PRD-001-enterprise-intelligence-mesh.md)
- [ADR-0003](0003-mesh-transversal-intelligence.md)
- [ADR-0005](0005-enterprise-object-model.md)
