# ADR-0030 — Écosystème tiers et identité des ressources

**Date :** 2026-11-04
**Statut :** accepted
**Décideurs :** Architecture, Données, Sécurité, Produit
**Amende :** ADR-0001, ADR-0005

## Contexte

Une équipe peut être responsable de ressources fournies par un tiers sans être responsable de
tous les logiciels hébergés. Certaines équipes n'ont pas d'`application_id`. La commande de
jumeau actuelle exige pourtant un `application_id` et l'utilise comme identifiant du Twin, ce
qui empêche les cas non applicatifs.

## Décision

### Identité

- `twin_id` est l'identifiant interne stable et universel d'un Twin.
- `application_id` est une identité applicative **optionnelle**.
- `resource_id`, `supplier_id`, `team_id` sont des identités métier externes, stockées dans
  les identifiants du Twin.
- Aucun `application_id` n'est généré artificiellement.
- Le nom affiché n'est jamais une identité.

### Types de Twin

Ajouter :

- `RESOURCE` : ressource fournie par un tiers ;
- `SUPPLIER` : fournisseur ou opérateur ;
- `TEAM` : équipe interne ;
- `ECOSYSTEM` : périmètre d’équipe regroupant ressources, applications, fournisseurs et
  responsabilités.

`APPLICATION` reste le type des applications. `RESOURCE` n'est pas une Application déguisée.

### Application sans App ID

Une application sans `application_id` peut exister comme :

- `APPLICATION CANDIDATE` ;
- `UNRESOLVED` ;
- cible d’un Claim `RESOURCE_SUPPORTE_APPLICATION`.

Elle n'est jamais promue automatiquement et son nom n'est pas utilisé comme identifiant.

### Commande

La commande de jumeau devient typée :

```text
type : APPLICATION | TEAM | RESOURCE | SUPPLIER | ECOSYSTEM
twin_id : généré ou fourni
application_id : optionnel
ressource / fournisseur / équipe : identifiants selon le type
nom, propriétaire, périmètre
sources
```

Règles :

- `APPLICATION` : `application_id` requis ou mode candidat explicite ;
- `TEAM` / `ECOSYSTEM` : aucun `application_id` requis ;
- `RESOURCE` / `SUPPLIER` : identifiant externe ou `twin_id` généré ;
- `twin_id` est unique ; `application_id` est unique seulement quand il existe.

### Sources

- Ajouter `TEAMS` aux types de source.
- Un Twins `TEAM` / `ECOSYSTEM` peut naître avec des sources documentaires et ITSM, sans
  GitHub.
- Un Twins `RESOURCE` / `SUPPLIER` peut naître depuis CMDB, ServiceNow, contrat ou export
  fournisseur.
- Les ACL de source restent appliquées ; Teams n'est jamais ingéré globalement.

### Responsabilités

Les responsabilités sont des Claims, jamais des champs libres :

```text
FOURNISSEUR_FOURNIT
EQUIPE_EST_ACCOUNTABLE_DE
EQUIPE_EST_RESPONSABLE_DE
CONTRAT_COUVRE
RESOURCE_SUPPORTE_APPLICATION
APPLICATION_DEPEND_DE_RESSOURCE
RESPONSABILITE_LIMITEE_A
```

Chaque Claim porte une preuve localisée, une autorité de source et une temporalité.

### Fédération

Une vue transverse est une **projection autorisée** de plusieurs Twins. Ce n'est pas un Twin
supplémentaire et elle ne copie pas les Claims.

## Conséquences

- La commande peut créer des Twins non applicatifs.
- Les ressources partagées ont un `twin_id`/identifiant canonique commun.
- Les anciens Twins restent lisibles : migration par défaut `type = APPLICATION`,
  `application_id = id`.
- Les Claims continuent de pointer vers un `twin_id`, pas vers un `application_id`.
- Les règles de naissance dépendent du type.
- L’UI n’affiche qu’un identifiant métier selon le type ; le `twin_id` reste généré et rangé
  dans « Avancé ».
- L’écosystème se lit par une lentille dans l’Atlas existant, pas par une nouvelle page.

## Migration

1. Ajouter `jumeau.type`, `jumeau.application_id` nullable, `jumeau.perimetre`,
   `jumeau.identifiants jsonb`.
2. Backfill : `type = 'APPLICATION'`, `application_id = id`.
3. Ajouter `TEAMS` à la contrainte de type de source.
4. Adapter la commande et la naissance.
5. Aucun jumeau existant n'est supprimé.

## Critères d'acceptation

1. Créer un Twin `TEAM` sans App ID.
2. Créer un Twin `ECOSYSTEM` avec Confluence et ServiceNow.
3. Créer un Twin `APPLICATION` avec App ID.
4. Créer un Twin `APPLICATION` candidat sans App ID.
5. Lancer une naissance non applicative sans GitHub.
6. Relier une ressource à une application candidate.
7. Une vue transverse ne fuit aucune source interdite.
8. Les anciens Twins restent lisibles après migration.
