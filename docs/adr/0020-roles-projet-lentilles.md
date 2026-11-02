# ADR-0020: Rôles projet et lentilles, pas de modèles ni de personas par rôle

**Date**: 2026-11-01
**Status**: accepted
**Deciders**: Utilisateur

## Context

Le cadrage capacité/charge/prévision/budget a d'abord été écrit autour du Product Owner. Or les outils de
projet réunissent des acteurs qui n'ont ni les mêmes questions, ni les mêmes droits : PO, Scrum Master,
Engineering Manager, membre d'équipe, architecte, PMO, Finance, sponsor, ops, audit.

Le risque est double :

- dupliquer un modèle ou un dashboard par rôle, ce qui crée des vérités divergentes ;
- réintroduire des personas de démonstration, alors que l'ADR-0018 les a supprimées.

Un rôle projet n'est pas une persona. C'est une **autorisation réelle** liée à une identité, un périmètre
et une période. Une lentille est une manière d'expliquer et de prioriser ; elle ne donne aucun droit.

## Decision

- Séparer explicitement **identité**, **rôle projet**, **périmètre**, **lentille** et **autorité**.
- Conserver **un seul jeu de faits canoniques** pour la capacité, la charge, la prévision, le budget et la
  valeur. Les rôles partagent les mêmes faits ; seuls le détail, les filtres, les options et les droits
  changent.
- Ajouter les objets `RoleProjet`, `AffectationRole`, `Lentille`, `DroitDecision` et `VueRole`.
- Attribuer les rôles explicitement, par acteur et par périmètre ; un rôle inconnu obtient la lecture
  minimale.
- Appliquer les permissions avant l'agrégation et avant tout appel d'outil. Aucune lentille ne peut
  élargir l'autorité.
- Interdire le classement individuel de performance. Un membre d'équipe voit son travail et l'agrégat de
  son équipe, pas le travail individuel des autres.
- Garder les décisions humaines : PO pour la priorité, Engineering Manager pour le staffing, PMO pour le
  plan, Finance pour l'enveloppe, sponsor pour le financement. Méridian propose et trace.
- Le Harness expose des capacités génériques ; `composition` et le contexte filtrent selon le rôle, le
  périmètre et la question. Aucun outil spécifique à un rôle n'est nécessaire.

## Alternatives Considered

### Alternative 1: Un modèle ou un module par rôle
- **Pros** : réponse apparemment simple à chaque besoin.
- **Cons** : duplication des faits, incohérences, maintenance multipliée, dashboards divergents.
- **Why not** : contredit le principe d'un fait unique et d'une lecture multiple.

### Alternative 2: Réintroduire des personas de démonstration
- **Pros** : démonstrations faciles.
- **Cons** : retour d'une dette supprimée par l'ADR-0018 ; faux acteurs, fausses permissions.
- **Why not** : les rôles doivent être réels, attribués et auditables.

### Alternative 3: Un dashboard unique pour tous
- **Pros** : simplicité.
- **Cons** : surcharge pour les uns, détail insuffisant pour les autres ; risque de divulguer des données.
- **Why not** : les mêmes faits ne se lisent pas au même niveau de détail.

### Alternative 4: Faire du rôle une lentille cognitive
- **Pros** : réutilise `profils` et `composition`.
- **Cons** : confond autorisation et explication ; un profil inconnu pourrait hériter de droits.
- **Why not** : l'autorité doit rester indépendante de la manière de répondre.

## Consequences

### Positive
- Un seul modèle de capacité, charge, prévision et budget.
- Des vues adaptées sans duplication.
- Des droits et des décisions explicites, auditables.
- Une base saine pour PO, SM, EM, PMO, Finance, sponsor et membre d'équipe.

### Negative
- Il faut maintenir un mapping acteur ↔ rôle ↔ périmètre.
- Les rôles varient selon les organisations ; le paramétrage est nécessaire.
- Certaines vues demandent des règles de confidentialité fines.

### Risks
- **Explosion des rôles** : limiter à des rôles projet stables, les variantes sont des lentilles.
- **Élargissement des droits** : tester chaque combinaison rôle/périmètre.
- **Surveillance individuelle** : agrégation stricte, pas de classement.
- **Confusion rôle/persona** : documenter et tester l'absence de persona.

## Acceptance Criteria

1. Un PO, un Scrum Master, un Engineering Manager, un PMO et Finance voient les mêmes faits à des
   niveaux de détail différents.
2. Aucun modèle de données ou dashboard n'est dupliqué par rôle.
3. Un rôle inconnu obtient la lecture minimale.
4. Un membre d'équipe ne peut pas lire le travail individuel d'un autre.
5. Une lentille ne modifie jamais l'autorité.
6. Les décisions de priorité, staffing, plan, budget et financement restent humaines.
7. Les attributions de rôle et les décisions sont auditables.

## References

- [PRD-003](../prd/PRD-003-capacite-charge-prevision-budget.md)
- [ADR-0018](0018-suppression-effective-personas-polaris.md)
- [ADR-0019](0019-source-travail-generique-planification.md)
