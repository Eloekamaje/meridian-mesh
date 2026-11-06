# Écosystème de ressources tierces

**Date :** 2026-11-04  
**Statut :** proposition d’architecture ; domaine, schéma et migration d’identité implémentés par ADR-0030
**Objet :** reconstruire, vérifier et maintenir une compréhension partagée des ressources fournies par un tiers.

## 1. Problème

Une équipe est responsable d’un ensemble de ressources fournies par un tiers, sans être
responsable de tous les logiciels hébergés dessus. Elle doit pourtant comprendre :

- l’usage réel des ressources ;
- leurs dépendances ;
- les applications qu’elles supportent ;
- les responsabilités de chaque intervenant ;
- ce qui a changé, ce qui n’est plus vrai, ce qui est supposé ou inconnu.

La connaissance est dispersée entre :

- documents fournisseur ;
- schémas d’architecture de différentes époques ;
- Confluence ;
- SharePoint ;
- incidents et changements ServiceNow ;
- décisions prises dans Teams.

Avec le temps, ces sources divergent. Le problème n’est donc pas de chercher un document :
c’est de maintenir un **modèle partagé, temporel et prouvable** d’un écosystème dont l’équipe
ne contrôle qu’une partie.

## 2. Décision proposée

Méridian traite cet écosystème comme un **jumeau de preuve temporel** :

```text
Sources
  → preuves localisées
  → Claims typés
  → entités et relations
  → timeline
  → contradictions / inconnues
  → agents d’analyse
  → revue humaine
  → carte partagée
```

Règle :

> Le modèle propose. Le graphe enregistre. La preuve établit. L’humain valide.

Ce n’est pas un RAG documentaire. Le RAG fournit des **candidats** ; il ne crée ni Claim, ni
preuve, ni responsabilité.

## 3. Modèle de connaissance

### Entités

- `RESOURCE` : ressource fournie par un tiers (infrastructure, plateforme, service managé,
  base, réseau, certificat, intégration, appliance…).
- `SUPPLIER` : fournisseur ou opérateur de la ressource.
- `APPLICATION` : application supportée ou consommatrice.
- `TEAM` : équipe interne, propriétaire ou utilisatrice.
- `CONTRACT` : contrat, engagement de service, annexe de responsabilité.
- `SERVICE` : service rendu par la ressource.
- `INCIDENT` : incident ServiceNow.
- `CHANGE` : changement ServiceNow.
- `DECISION` : décision tracée dans Teams ou un compte rendu.
- `CONSTRAINT` : contrainte contractuelle, technique ou réglementaire.
- `EVIDENCE` : preuve localisée.

### Claims

```text
RESOURCE_SUPPORTE_APPLICATION
APPLICATION_DEPEND_DE_RESSOURCE
FOURNISSEUR_FOURNIT
EQUIPE_EST_ACCOUNTABLE_DE
EQUIPE_EST_RESPONSABLE_DE
CONTRAT_COUVRE
SERVICE_RENDU_PAR
INCIDENT_AFFECTE
CHANGEMENT_IMPACTE
DECISION_PRISE
CONTRAINTE_S_APPLIQUE
RESPONSABILITE_LIMITEE_A
```

Chaque Claim porte :

```text
sujet, prédicat, objet
statut : établi | historique | supposé | contesté | inconnu
confiance
source + locator exact
valid_from / valid_to
observed_at
autorité de la source
périmètre
```

### Preuve

Une preuve doit pointer vers :

- un document fournisseur, page/paragraphe ;
- un schéma, version et date ;
- une page Confluence ;
- un ticket ServiceNow ;
- un change ;
- un timestamp de réunion Teams ;
- une ligne de CMDB ou d’observabilité.

Une réponse doit distinguer explicitement :

```text
Établi : la ressource X supporte l’application Y.
Preuve : contrat §4.2 + CMDB CI-123.
Historique : le schéma 2022 la rattachait à Z.
Supposé : le flux A→B, non confirmé.
Inconnu : le propriétaire du certificat.
Contesté : deux documents donnent deux dates de fin.
```

## 3 bis. Identité sans AppID

Toutes les équipes ni toutes les ressources n’ont pas d’`app_id`. Ce n’est pas une erreur :
l’`app_id` est une identité d’application, pas l’identité universelle de Méridian.

Hiérarchie d’identité :

```text
twin_id interne stable            (toujours)
  └── identité du type
        RESOURCE  : resource_id / identifiant CMDB / asset fournisseur
        SUPPLIER  : supplier_id / code fournisseur
        TEAM      : team_id / identifiant organisation
        APPLICATION : app_id si disponible
  └── identifiants externes
        CI ServiceNow, contrat, asset ID, URL, code fournisseur
  └── clé locale de source
        espace Confluence + page, ticket, chemin, message Teams
```

Règles :

- une ressource, un fournisseur ou une équipe **n’exige jamais un app_id** ;
- une application sans `app_id` devient `APPLICATION CANDIDATE` ou `UNRESOLVED`, jamais une
  application inventée ;
- un `app_id` absent n’autorise pas à utiliser le nom comme identifiant canonique ;
- l’identité interne (`twin_id` / `entity_id`) reste stable même si l’`app_id` arrive plus tard ;
- une ressource peut supporter une application sans `app_id` : le lien est un Claim
  `RESOURCE_SUPPORTE_APPLICATION` avec une cible `CANDIDATE` ou `UNKNOWN` ;
- un espace Confluence d’équipe est une **source**, pas une identité d’application ;
- une équipe sans application peut avoir un Twin de type `TEAM` ou `ECOSYSTEM`.

Conséquence pour le modèle :

```text
Application : app_id optionnel
Resource    : resource_id ou identifiants externes
Supplier    : supplier_id ou code fournisseur
Team        : team_id
Twin        : twin_id interne, toujours
```

Le résolveur doit donc avoir deux chemins :

```text
ApplicationResolver  → app_id / alias / registre applicatif
EntityResolver       → identifiants de ressource, fournisseur, équipe, source
```

Ne pas avoir d’`app_id` ne doit jamais bloquer l’ingestion, la preuve ou le Claim.

## 4. Responsabilités

Il faut un modèle explicite, pas une liste de contacts :

```text
Ressource
  Fournisseur : responsable de l’infrastructure
  Équipe interne : accountable de l’usage
  Application A : consommatrice
  Application B : consommatrice
  Équipe B : responsable de B, pas de la ressource
```

C’est ce qui évite de confondre :

- « hébergé sur » et « responsable de » ;
- « supporté par » et « maintenu par » ;
- « fourni par le tiers » et « exploité par l’équipe ».

La matrice de responsabilité doit être un Claim, pas un champ libre.

## 5. Sources et autorité

| Sujet | Source d’autorité principale | Sources de recoupement |
|---|---|---|
| Responsabilité contractuelle | contrat / SoW | décision, ticket |
| Usage réel | CMDB, observabilité | incidents, architecture |
| Dépendance | architecture, CMDB | Confluence, changes |
| Historique | versions datées | décisions, incidents |
| Décision | compte rendu validé | Teams, Confluence |
| Contrainte | contrat, réglementation | audit |

Une source ancienne n’est pas supprimée : elle devient **historique**.
Une absence n’est pas une preuve d’absence : elle devient **inconnue**.
Deux sources contradictoires ne sont pas fusionnées : elles créent une **contradiction** à trancher.

## 6. Intégration dans Méridian

### 6.1 Sources et connecteurs

Déjà présents :

- Confluence ;
- SharePoint ;
- ServiceNow ;
- Git / code ;
- documentation ;
- Jira, Datadog, OTLP.

À ajouter :

- **Teams** via Microsoft Graph, sur des canaux et réunions explicitement autorisés ;
- documents fournisseur, souvent PDF/Office ;
- schémas d’architecture, avec OCR/vision ;
- CMDB ou export d’inventaire.

Chaque source reste une `Source` avec ACL, curseur, secret, et preuve localisée.

### 6.2 Ingestion

Le pipeline existant reste :

```text
Source → observation → Claim → preuve
```

Ajouts :

- extraction des ressources et fournisseurs ;
- extraction des responsabilités et limites de périmètre ;
- extraction des décisions dans Teams ;
- extraction des changements et incidents ;
- résolution d’entités entre « la même ressource » nommée différemment.

### 6.3 Domaine

`TYPES_TWIN` contient désormais `APPLICATION`, `PROCESS`, `CAPABILITY`, `JOURNEY`,
`ORGANIZATION`, `PRODUCT`, `DATA_DOMAIN`, `RESOURCE`, `SUPPLIER`, `TEAM` et `ECOSYSTEM`
(ADR-0030). Le schéma `jumeau` porte `type`, `application_id` optionnel, `perimetre` et
`identifiants` jsonb ; `TEAMS` est ajouté aux types de source. La migration des anciens Twins
pose `type = APPLICATION` et `application_id = id`.

### 6.4 Graphe

Le graphe existant reçoit les nouveaux nœuds et relations :

```text
SUPPLIER → FOURNIT → RESOURCE
RESOURCE → SUPPORTE → APPLICATION
APPLICATION → DEPEND_DE → RESOURCE
TEAM → ACCOUNTABLE_DE → RESOURCE
CONTRACT → COUVRE → RESOURCE
INCIDENT → AFFECTE → RESOURCE
CHANGE → IMPACTE → APPLICATION
DECISION → PORTE_SUR → RESPONSABILITE
```

La carte doit rester une **projection** du modèle, pas une seconde vérité.

### 6.5 Retrieval

Le retrieval existant reste un fournisseur de candidats :

- chunks documentaires ;
- communautés GraphRAG ;
- Claims et preuves ;
- mémoire du Travail.

Il ne décide pas qu’une responsabilité est vraie. Il fournit des preuves à examiner.

### 6.6 Raisonnement et dialogue

Le `ConducteurTour` et le noyau existants peuvent traiter :

- « Que supporte cette ressource ? »
- « Qui est responsable de quoi ? »
- « Que savait-on au 1er janvier 2025 ? »
- « Qu’est-ce qui a changé depuis six mois ? »
- « Quel est l’impact de ce changement ? »
- « Qu’est-ce qui est supposé ou inconnu ? »

La réponse doit exposer :

```text
établi / historique / supposé / contesté / inconnu
```

et les preuves correspondantes.

### 6.7 UI

L’écosystème n’a pas de page dédiée. Il se lit dans l’Atlas existant :

1. **Lentille Atlas** : `Tous`, `Applications`, `Écosystème tiers` — ressources, fournisseurs,
   équipes et dépendances, sans seconde vérité ni seconde carte.
2. **Dossier de compréhension** : le panneau du Twin expose usage, contrats, historique,
   incidents, décisions et inconnues.
3. **File de vérité** : contradictions, Claims à revoir, sources périmées, questions ouvertes.

Dans le formulaire de commande, un seul identifiant métier est visible selon le type
(`App ID`, `Team ID`, `Resource ID`, `Supplier ID`) ; le `twin_id` technique est généré
automatiquement et rangé dans « Avancé ».

### 6.8 ACL et gouvernance

- ACL serveur, tenant/espace, filtrage avant prompt.
- Teams : canaux autorisés uniquement, jamais tout le tenant.
- Documents fournisseur : classification et droits.
- Revue humaine obligatoire pour les Claims de responsabilité.
- Audit des lectures, des Claims proposés et des décisions.

## 7. Agents AI

- **Collecteur** : lit les sources autorisées.
- **Extracteur** : documents, PDF, schémas, tickets, transcriptions.
- **Résolveur d’entités** : évite les doublons de ressources.
- **Historien** : replace chaque information dans le temps.
- **Sceptique** : cherche contradictions et affirmations non prouvées.
- **Impact analyst** : parcourt le graphe pour un incident ou un changement.
- **Intervieweur** : pose les questions ciblées qui manquent.
- **Curateur** : propose les mises à jour, sans valider.

Tous restent bornés par le `Harness`, les ACL, les budgets et les gates.

## 8. Périmètre de démarrage

1. Une famille de ressources, trois applications.
2. Quatre sources : SharePoint, Confluence, ServiceNow, Teams ciblé.
3. Dix prédicats, preuve localisée.
4. Trois vues : carte, dossier, contradictions/inconnues.
5. Un agent sceptique et un agent intervieweur.
6. Vingt questions de référence.
7. Revue humaine hebdomadaire.

## 9. Critères de succès

- 100 % des Claims ont une preuve localisée.
- 0 Claim inventé.
- Taux de contradictions détectées.
- Taux d’inconnues résolues.
- Temps pour répondre à « qui dépend de quoi ? ».
- Temps pour évaluer un changement.
- Fraîcheur des sources.
- Accord entre la carte et la réalité opérationnelle.

## 10. ADR existants et écart

Les invariants sont déjà couverts :

| ADR | Ce qu’il couvre | Ce qu’il ne couvre pas |
|---|---|---|
| ADR-0001 | Application, Twin, artefact, identité, promotion humaine | les types `RESOURCE` / `SUPPLIER` |
| ADR-0004 | registre capacitaire, manifestes, usages, portée | les capacités du domaine tiers |
| ADR-0005 | huit familles, Twins non applicatifs | `RESOURCE` / `SUPPLIER` / identité canonique de ressource |
| ADR-0013 / 0022 | graphe = projection reconstructible | la vue transverse comme capacité de fédération |
| ADR-0023 | ACL fail-closed | ACL au niveau source Teams |
| ADR-0029 | conducteur de tour unique | le pack métier écosystème tiers |

ADR-0030 tranche les types `RESOURCE`, `SUPPLIER`, `TEAM` et `ECOSYSTEM`, ainsi que
l’identité `twin_id` / `application_id` optionnel. Restent à formaliser :

- l’identifiant canonique d’une ressource partagée entre plusieurs jumeaux ;
- la source `TEAMS` et son périmètre ;
- l’autorité des sources par prédicat ;
- les prédicats de responsabilité.

## 11. Tension tranchée

ADR-0030 retient que `RESOURCE`, `SUPPLIER`, `TEAM` et `ECOSYSTEM` sont des Twins non
applicatifs : `APPLICATION` reste le type des applications, et `RESOURCE` n’est pas une
Application déguisée. L’identité universelle reste `twin_id` ; `application_id` est optionnel.

## 12. ADR

1. **ADR-0030 — Écosystème tiers et identité des ressources** : accepté (types, identité,
   frontière ressource/application).
2. **ADR-0031 — Autorité des sources par prédicat**.
3. **ADR-0032 — Source Teams, périmètre et ACL**.
4. **ADR-0033 — Décisions à prendre** sur la revue humaine des responsabilités.
