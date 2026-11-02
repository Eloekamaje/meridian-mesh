# PRD-003 — Pilotage de la capacité, de la charge et de la prévision

**Statut :** accepted — implémentation initiale
**Version :** 1.2
**Date :** 2026-11-01
**Complète :** [PRD-001](PRD-001-enterprise-intelligence-mesh.md), [PRD-002](PRD-002-memoire-contexte-raisonnement.md)
**Décisions d'architecture :** [ADR-0019](../adr/0019-source-travail-generique-planification.md), [ADR-0020](../adr/0020-roles-projet-lentilles.md)

## 1. Objet

Donner aux acteurs d'un projet — Product Owner, manager d'équipe, Scrum Master, PMO, Finance, membre
d'équipe, architecte, sponsor — une réponse fiable à quatre questions :

1. **Capacité** — combien l'équipe peut-elle absorber sur une période ?
2. **Charge** — qu'est-ce qui est engagé, planifié et non planifié ?
3. **Prévision** — avec quelle probabilité tiendra-t-on un périmètre ou une date ?
4. **Budget et valeur** — combien cela coûte, et pour quel bénéfice attendu ou observé ?

La fonctionnalité est **indépendante de l'outil de gestion du travail**. Jira, Azure DevOps, Linear,
GitHub Issues, Asana, Monday, ClickUp, Trello ou un fichier CSV sont des **sources**. Aucun ne définit le
modèle, l'interface ou le moteur de prévision.

## 2. Problème

Aujourd'hui, les réponses sont dispersées :

- le tracker contient le backlog, les estimations et parfois les sprints ;
- les absences, astreintes et compétences sont dans des fichiers ou des outils RH ;
- les incidents et le support sont dans un ITSM ;
- le budget est dans Finance, Tempo ou un tableur ;
- la valeur est dans le Value Ledger ou une revue de portefeuille ;
- les dépendances inter-équipes sont dans les têtes, les tickets et les réunions.

Chaque outil pris isolément produit une vue partielle. Un PO ne peut pas répondre simplement à :

- « Peut-on prendre cet épic dans le prochain trimestre ? »
- « Quelle est la probabilité de tenir la release ? »
- « Où est la surcharge réelle, une fois le support et les incidents comptés ? »
- « Cette initiative consomme-t-elle du budget pour la valeur attendue ? »
- « Quelle compétence est le goulot ? »

## 3. Principes

- **Source-agnostique** : le domaine ne connaît ni Jira ni ses champs.
- **Un fait, plusieurs lentilles** : les mêmes données canoniques servent tous les rôles ; seuls le
  détail, les filtres et les actions changent.
- **Rôle ≠ persona** : un rôle projet est une autorisation réelle, pas une persona de démonstration.
- **Équipe d'abord** : la vue est agrégée par équipe et par horizon ; pas de classement individuel.
- **Capacité ≠ compétence** : la capacité est quantitative ; les compétences sont qualitatives.
- **Prévision probabiliste** : P50/P85/P95, hypothèses et abstention, jamais une date certaine.
- **Prédiction étiquetée** : un modèle peut estimer un risque ou un effort ; il ne devient pas une vérité.
- **Budget séparé** : le budget est un objet financier ; les story points ne se convertissent pas en euros.
- **Preuve et fraîcheur** : chaque chiffre porte sa source, sa date et sa couverture.
- **Non observé ≠ zéro** : une source absente ou un champ vide n'est pas une absence de charge.
- **Lecture seule** : Méridian observe et propose ; il n'écrit pas dans les outils de gestion.
- **Abstention** : sans historique ou sans données suffisantes, la prévision s'abstient.

## 4. Acteurs, rôles et tâches

### 4.1 Quatre notions distinctes

| Notion | Rôle |
|---|---|
| **Identité** | Qui est authentifié : acteur, tenant, périmètre |
| **Rôle projet** | PO, Scrum Master, Engineering Manager, PMO, Finance, membre d'équipe, architecte, sponsor, ops, audit |
| **Lentille** | Comment le système explique et hiérarchise pour cette personne : produit, flux, technique, finance |
| **Autorité** | Ce que la personne peut lire, proposer, approuver ou décider |

Un rôle projet **n'est pas** une persona de démonstration. Il est attribué explicitement à un acteur,
pour un périmètre et une période. Un rôle inconnu obtient la lecture minimale.

### 4.2 Acteurs

| Acteur | Question principale | Décision | Visibilité |
|---|---|---|---|
| **PO / Product Manager** | Que faire, quand, pour quelle valeur ? | priorité, scope, arbitrage valeur | équipe/portefeuille agrégé |
| **Scrum Master / Agile coach** | Pourquoi le flux bloque-t-il ? | animation, amélioration | équipe, flux, impediments |
| **Engineering Manager** | Qui est disponible, avec quelles compétences ? | staffing, réallocation | équipe agrégée, compétences |
| **Membre d'équipe** | Que dois-je faire, qu'est-ce qui me bloque ? | estimation, engagement de son travail | son travail + agrégat équipe |
| **Tech lead / Architecte** | Quelles dépendances et quels impacts ? | faisabilité technique | interfaces, dépendances, Twins |
| **PMO / Chef de projet** | Le plan tient-il ? | plan, jalons, coordination | multi-équipes, dépendances |
| **Finance / Controlling** | Budget, forecast, réel, variance ? | enveloppe, imputation | financier agrégé |
| **Sponsor / Direction** | Combien, pour quelle valeur, avec quelle confiance ? | financement, go/no-go | synthèse, valeur, risque |
| **Ops / Support** | Quelle charge non planifiée ? | priorité incident, capacité | incidents, charge d'exploitation |
| **Audit / Conformité** | Qui a décidé quoi, avec quelle preuve ? | conformité | décisions, preuves, audit |

### 4.3 Droits de décision

| Décision | Responsable | Méridian |
|---|---|---|
| Priorité / scope | PO | propose, ne décide pas |
| Staffing / capacité | Engineering Manager | propose, ne réaffecte pas |
| Plan / jalons | PMO | consolide, ne valide pas seul |
| Budget | Finance | calcule, ne vote pas |
| Financement / go-no-go | Sponsor | éclaire, ne décide pas |
| Estimation | Équipe | agrège, ne force pas |

Une lentille ne donne jamais un droit. Les permissions sont vérifiées avant l'agrégation et avant
l'appel d'un outil.

### 4.4 Confidentialité par rôle

- **Membre d'équipe** : son travail et l'agrégat de son équipe ; pas le travail individuel des autres.
- **Manager** : agrégat équipe ; pas de classement individuel de performance.
- **Finance** : budget, coût, forecast ; pas les commentaires de tickets.
- **Sponsor** : synthèse, valeur, risque, confiance ; pas le détail opérationnel.
- **Auditeur** : décisions, preuves, audit ; pas les données personnelles inutiles.
- **Rôle inconnu** : lecture minimale, aucune action.

## 5. Définitions

| Terme | Définition |
|---|---|
| **Capacité** | Disponibilité d'une équipe sur une période : FTE, jours, heures, ou capacité exprimée en points par l'équipe |
| **Compétence** | Savoir-faire nécessaire pour réaliser un travail ; distincte de la capacité |
| **Charge** | Demande de travail : engagée, planifiée, non planifiée |
| **Engagé** | Périmètre déjà commité (sprint, release, engagement) |
| **Planifié** | Travail prévu mais non encore engagé |
| **Non planifié** | Incidents, support, BAU, réunions, interruptions |
| **Marge** | Capacité moins charge, avec intervalle d'incertitude |
| **Cycle** | Sprint, itération ou période de flux |
| **Prévision** | Projection probabiliste à partir de l'historique et des hypothèses |
| **Prédiction** | Estimation modelée d'un effort, d'un risque ou d'un délai, étiquetée comme telle |
| **Budget** | Enveloppe financière autorisée |
| **Forecast financier** | Dépense attendue à terminaison |
| **Réel** | Dépense ou temps constaté |
| **Valeur** | Bénéfice attendu ou observé, séparé du coût |

## 6. Modèle canonique

Le domaine manipule les objets suivants. Aucun champ spécifique à un éditeur n'y entre.

### 6.1 Équipe et capacité

- `Équipe` : id, nom, domaine, parent, source, statut.
- `Membre` : identité pseudonymisée, rôle, FTE, période, source.
- `Compétence` : référentiel, niveau, preuve, source.
- `Disponibilité` : jours ouvrés, absences, astreinte, support, capacité déclarée.
- `Capacité` : équipe, période, unité, valeur, confiance, fraîcheur, source.

### 6.2 Travail

- `ÉlémentDeTravail` : id externe, source, type, titre, statut normalisé, priorité, parent, équipe.
- `Estimation` : valeur, unité (`points`, `heures`, `jours`, `items`), méthode, auteur, date.
- `TempsPassé` : valeur, unité, période, agrégation équipe.
- `Cycle` : id, équipe, début, fin, capacité, engagement.
- `Release` : id, nom, date cible, statut, périmètre.
- `Dépendance` : source, cible, type (`bloque`, `dépend`, `lie`), statut.
- `Plan` : horizon, équipe, allocation, scénario, version, auteur.

### 6.3 Finance et valeur

- `LigneBudget` : enveloppe, devise, centre de coût, période, source.
- `TauxCoût` : rôle ou équipe, coût chargé, période, source.
- `Coût` : prévu, engagé, réel, forecast at completion.
- `Valeur` : baseline, cible, observé, unité, source, confiance, lien Value Ledger.

### 6.4 Prévision

- `Prévision` : périmètre, horizon, méthode, P50/P85/P95, hypothèses, exclusions, confiance, date de calcul.
- `Scénario` : capacité, scope, dépendances, budget, résultat comparé.

### 6.5 Rôles et autorisations

- `RoleProjet` : identifiant, libellé, famille, description.
- `AffectationRole` : acteur, rôle, périmètre (équipe, programme, portefeuille, Twin), début, fin, source.
- `Lentille` : préférence d'explication et de priorisation ; ne donne aucun droit.
- `DroitDecision` : rôle, décision, périmètre, niveau (`lecture`, `proposition`, `approbation`, `decision`).
- `VueRole` : configuration des métriques, filtres et actions visibles pour un rôle et un périmètre.

## 7. Sources et ports

### 7.1 Port `SourceTravail`

Chaque outil de gestion du travail expose, selon ses capacités :

```text
capacites() -> {sprints, points, heures, worklogs, dépendances, releases, historique, équipes}
lister_equipes()
lister_elements(depuis, périmètre)
lister_cycles()
lister_releases()
lister_dependances()
lister_temps()
```

L'adapter **déclare** ce qu'il sait faire. L'UI et la prévision s'adaptent ; elles ne fabriquent pas une
donnée absente.

### 7.2 Autres ports

- `SourcePeople` : équipes, membres, FTE, absences, compétences.
- `SourceFinance` : budget, taux, coûts, devises.
- `SourceValeur` : Value Ledger Méridian.
- `SourceIncidents` : ITSM / support / incidents.
- `SourceCalendrier` : jours ouvrés, fermetures, astreintes.

### 7.3 Adapters pressentis

| Famille | Exemples | Apport |
|---|---|---|
| Tracker agile | Jira, Azure DevOps, Linear, Asana, Monday, ClickUp | travail, estimations, cycles, dépendances |
| Issues / projets | GitHub Issues/Projects, GitLab | travail, labels, jalons |
| Kanban simple | Trello | items, listes, échéances ; peu d'estimations |
| ITSM | ServiceNow, JSM | incidents, support, changements |
| Finance | ERP, Tempo, Jira Align | budget, coûts |
| People | HR, annuaire, calendrier | FTE, absences, compétences |
| Fichier | CSV/Excel | secours, migration, petites équipes |

## 8. Normalisation

- **Statuts** : `à_faire`, `en_cours`, `terminé`, `annulé`, `inconnu`. Jamais le libellé brut comme clé.
- **Hiérarchie** : épic/parent/enfant quand disponible ; sinon `non structuré`.
- **Équipes** : mapping explicite vers une équipe Méridian ; une équipe non mappée est visible.
- **Estimations** : unité et méthode conservées ; aucune conversion silencieuse points ↔ heures.
- **Cycles** : sprint ou période de flux ; un outil sans sprint ne devient pas un faux sprint.
- **Releases** : version, jalon ou release ; sinon absent.
- **Dépendances** : uniquement les liens explicites ; pas d'inférence depuis le texte.
- **Temps** : worklogs agrégés par équipe et période ; jamais un classement individuel.
- **Sources multiples** : une source primaire par équipe/élément ; déduplication et couverture explicites.

## 9. Exigences

### 9.1 Sources

- **SRC-001** — Toute fonctionnalité de capacité, charge, prévision ou budget DOIT passer par un port
  générique ; aucun nom d'éditeur NE DOIT apparaître dans le domaine ou l'UI produit.
- **SRC-002** — Chaque adapter DOIT déclarer ses capacités et ses limites.
- **SRC-003** — Chaque donnée DOIT porter sa source, sa date d'observation et sa fraîcheur.
- **SRC-004** — Une source absente, vide ou en erreur DOIT rester `non observée` ; elle NE DOIT PAS être
  interprétée comme zéro.
- **SRC-005** — Les adapters DOIVENT être en lecture seule et ne jamais modifier le tracker.
- **SRC-006** — La synchronisation DOIT être incrémentale et idempotente ; les suppressions DOIVENT être
  représentées par un tombstone ou une réconciliation.
- **SRC-007** — Les sources multiples DOIVENT être dédupliquées ; une source primaire DOIT être déclarée
  par équipe et par élément.
- **SRC-008** — Le mapping équipe/compétence DOIT être explicite ; une équipe non mappée DOIT être
  signalée, jamais inventée.
- **SRC-009** — Les données personnelles DOIVENT être masquées ou agrégées ; l'UI NE DOIT PAS exposer un
  classement individuel.
- **SRC-010** — Un adapter PEUT exposer des champs supplémentaires, mais le domaine ne doit dépendre que
  des champs canoniques.
- **SRC-011** — Pour Jira, l'authentification reste un **PAT e-mail:jeton** (`secret_ref` Vault/env) pour
  le moment ; OAuth 2.0 3LO n'est pas requis dans ce lot. Aucun jeton n'est persisté dans la source ou
  dans les preuves.

### 9.2 Capacité et compétences

- **CAP-001** — L'UI DOIT afficher la capacité par équipe et par horizon.
- **CAP-002** — La capacité DOIT distinguer disponibilité théorique, absences, support/astreinte et
  allocation.
- **CAP-003** — La capacité DOIT porter une unité et une confiance.
- **CAP-004** — Les story points NE DOIVENT PAS être additionnés entre équipes.
- **CAP-005** — La couverture par compétence DOIT être visible pour identifier un goulot.
- **CAP-006** — Les compétences DOIVENT venir d'une source déclarée ; elles NE DOIVENT PAS être déduites
  du texte d'un ticket.
- **CAP-007** — Un scénario de capacité DOIT permettre d'ajouter, retirer ou réallouer une ressource.

### 9.3 Charge et planification

- **WLOAD-001** — La charge DOIT distinguer engagée, planifiée, non planifiée et inconnue.
- **WLOAD-002** — La charge non planifiée PEUT venir d'un ITSM ou d'une source déclarée.
- **WLOAD-003** — Le taux d'éléments non estimés DOIT être visible.
- **WLOAD-004** — Une dépendance bloquante DOIT être visible dans le plan.
- **WLOAD-005** — La marge DOIT être calculée avec une incertitude, pas comme un seul chiffre.
- **PLAN-001** — Le plan DOIT versionner horizon, périmètre, capacité, hypothèses et auteur.
- **PLAN-002** — Le plan DOIT comparer engagé, planifié et capacité.
- **PLAN-003** — Un scénario NE DOIT PAS modifier les sources ni le plan officiel.
- **PLAN-004** — Un écart plan/réel DOIT être explicable par scope, capacité, dépendance ou qualité
  d'estimation.

### 9.4 Prévision et prédiction

- **FORE-001** — La prévision DOIT produire P50, P85 et P95, avec hypothèses et exclusions.
- **FORE-002** — La méthode DOIT être choisie selon les données disponibles : vélocité, débit/cycle time,
  nombre d'items, ou abstention.
- **FORE-003** — Sans historique suffisant, le système DOIT s'abstenir explicitement.
- **FORE-004** — Une prévision NE DOIT PAS être présentée comme une date certaine.
- **FORE-005** — Le calcul DOIT être déterministe et reproductible ; le LLM NE DOIT PAS faire l'arithmétique.
- **FORE-006** — Chaque prévision DOIT être calibrée a posteriori (P85 réellement couvert ~85 %).
- **FORE-007** — Une prédiction de risque ou d'effort DOIT être étiquetée comme hypothèse, avec intervalle.
- **FORE-008** — Les scénarios DOIVENT montrer l'effet d'un changement de capacité, de scope ou de
  dépendance.
- **FORE-009** — La prévision DOIT exposer ce qui la ferait changer (hypothèses, conditions de retournement).

### 9.5 Budget et valeur

- **BUDG-001** — Le budget, le forecast et le réel DOIVENT être trois objets distincts.
- **BUDG-002** — Un story point NE DOIT JAMAIS être converti en devise.
- **BUDG-003** — Le coût de capacité DOIT être calculé à partir de FTE/temps et d'un taux déclaré.
- **BUDG-004** — Le budget DOIT venir d'une source Finance ou d'un Value Ledger, jamais d'une inférence
  depuis le tracker.
- **BUDG-005** — Le système DOIT afficher budget, forecast at completion, réel et variance.
- **BUDG-006** — La valeur DOIT rester séparée du coût et suivre le Value Ledger.
- **BUDG-007** — Les devises et unités NE DOIVENT PAS être additionnées sans conversion explicite.
- **BUDG-008** — Une ligne budgétaire DOIT pouvoir être reliée à une initiative, un épic ou un Twin.

### 9.6 Expérience

- **UX-001** — Une seule fonctionnalité « Capacité & charge » quel que soit le fournisseur.
- **UX-002** — Le fournisseur est un réglage de source, pas une variante de produit.
- **UX-003** — Chaque chiffre DOIT être cliquable jusqu'à sa source et sa fraîcheur.
- **UX-004** — L'UI DOIT montrer les données manquantes et les équipes non mappées.
- **UX-005** — L'UI NE DOIT PAS produire de classement individuel de performance.
- **UX-006** — Un export DOIT permettre de retrouver les hypothèses et la version du calcul.
- **UX-007** — Le pilotage DOIT être accessible dans le chat via les outils du Harness et rendu dans le
  chat ou le Canvas (tableaux, graphiques, documents Markdown, Mermaid, JSON). Aucun menu de pilotage
  dédié n'est requis ; le fournisseur reste un réglage de source.

### 9.7 Gouvernance

- **ROLE-001** — Un rôle projet DOIT être explicite, tenant-scopé et attribué à un acteur pour un
  périmètre et une période.
- **ROLE-002** — Un rôle projet N'EST PAS une persona de démonstration ; aucune persona ne DOIT être
  réintroduite.
- **ROLE-003** — Les rôles DOIVENT partager un seul jeu de faits canoniques ; aucun rôle NE DOIT avoir
  son propre modèle de capacité, de charge ou de budget.
- **ROLE-004** — Une lentille NE DOIT PAS élargir les droits d'un acteur.
- **ROLE-005** — Les permissions DOIVENT être appliquées avant l'agrégation et avant tout appel d'outil.
- **ROLE-006** — Un membre d'équipe NE DOIT PAS voir le travail individuel des autres ; un manager NE
  DOIT PAS obtenir un classement individuel de performance.
- **ROLE-007** — Un rôle inconnu DOIT obtenir la lecture minimale et aucune action.
- **ROLE-008** — Une décision (priorité, staffing, budget, financement) DOIT rester humaine ; Méridian
  propose et trace.
- **ROLE-009** — Chaque rôle DOIT avoir des vues et des options adaptées, sans duplication de modèle.
- **ROLE-010** — Les attributions de rôle et les décisions DOIVENT être auditables (acteur, rôle,
  périmètre, date, preuve).
- **GOV-001** — Toute donnée DOIT être tenant-scopée.
- **GOV-002** — Les permissions de lecture DOIVENT s'appliquer avant l'agrégation.
- **GOV-003** — Les secrets de source NE DOIVENT PAS être persistés en clair.
- **GOV-004** — Les données individuelles DOIVENT avoir une politique de rétention et d'agrégation.
- **GOV-005** — Un calcul de prévision DOIT être auditable : méthode, données, hypothèses, version.
- **GOV-006** — Une source en panne DOIT être visible dans la santé de la source.

## 10. Scénarios d'acceptation

### A. Un PO avec Jira

- capacité de l'équipe sur le prochain sprint ;
- charge engagée et planifiée ;
- part non planifiée visible ;
- prévision P50/P85/P95 de l'épic ;
- source et fraîcheur affichées.

### B. La même fonctionnalité avec un deuxième outil

- un adapter Azure DevOps ou Linear remplace Jira ;
- le domaine, l'UI et le moteur de prévision ne changent pas ;
- les capacités absentes sont affichées comme telles.

### C. Un outil sans story points

- la charge s'exprime en items ou en heures ;
- la prévision utilise le débit ou s'abstient ;
- aucun faux points n'est inventé.

### D. Un outil sans historique

- l'UI affiche « prévision indisponible : historique insuffisant » ;
- aucune date n'est inventée.

### E. Budget et valeur

- budget et coût viennent d'une source Finance ;
- la valeur vient du Value Ledger ;
- le forecast et la variance sont calculés ;
- aucun point n'est converti en euro.

### F. Goulot de compétence

- la capacité est disponible ;
- la compétence requise ne l'est pas ;
- le goulot est visible et le scénario propose une réallocation.

### G. Sources multiples

- Jira et un ITSM alimentent la charge ;
- aucun double comptage ;
- la source primaire et la couverture sont explicites.

### H. Un Scrum Master

- voit le flux, le WIP, les impediments et la capacité du sprint ;
- ne voit ni le budget ni un classement individuel ;
- peut comparer deux sprints et expliquer une dérive de flux.

### I. Un Engineering Manager

- voit la capacité, les absences, les compétences et les goulots de son équipe ;
- ne voit pas les commentaires de tickets ;
- peut simuler une réallocation sans modifier le tracker.

### J. Finance et sponsor

- Finance voit budget, forecast, réel et variance ;
- le sponsor voit une synthèse avec valeur, risque et confiance ;
- aucun des deux ne voit le détail individuel des tickets.

### K. Un membre d'équipe

- voit son travail et l'agrégat de son équipe ;
- ne voit pas le travail individuel des autres ;
- peut signaler un blocage ou une surcharge.

### L. Un rôle inconnu

- obtient la lecture minimale ;
- aucune action, aucun budget, aucun détail individuel ;
- la raison de la restriction est explicite.

## 11. Métriques de succès

- **Couverture** : % d'équipes mappées, % d'éléments estimés, % de sources fraîches.
- **Calibration** : taux de couverture réel du P85, erreur absolue de la prévision.
- **Adoption** : PO, managers, PMO et Finance actifs ; décisions documentées avec une prévision.
- **Couverture des rôles** : % d'acteurs avec un rôle et un périmètre explicites.
- **Conformité d'accès** : aucune vue ne dépasse le périmètre autorisé.
- **Délai** : temps pour répondre à « peut-on prendre cet épic ? ».
- **Budget** : écart forecast/réel détecté avant la clôture.
- **Qualité** : équipes non mappées, unités inconnues, sources en erreur.
- **Garde-fou** : aucune vue de classement individuel.

## 12. Phasage

| Phase | Contenu | Critère de sortie |
|---|---|---|
| P0 — Socle | modèle canonique, rôles/périmètres, port `SourceTravail`, adapter Jira + un deuxième, mapping équipes | même vue avec deux sources et droits corrects |
| P1 — Capacité/charge | capacité, charge, non planifié, dépendances, marge | un PO répond à « peut-on prendre ? » |
| P2 — Prévision | P50/P85/P95, scénarios, calibration | prévision reproductible et étiquetée |
| P3 — Compétences | matrice, couverture, goulots | goulot identifié et simulé |
| P4 — Budget/valeur | budget, coût, forecast, variance, Value Ledger | budget et valeur reliés |
| P5 — Portefeuille | comparaison équipes/initiatives, scénarios | arbitrage de portefeuille explicite |

## 13. Hors périmètre

- Remplacer Jira, Azure DevOps ou un autre tracker.
- Notation individuelle, surveillance des personnes, timesheet.
- Affectation automatique des personnes.
- Facturation, comptabilité, paie.
- Promesse d'une date exacte.
- Modification automatique du backlog ou des priorités.
- Optimisation budgétaire automatique sans décision humaine.
- Fusion de story points entre équipes.

## 14. Questions ouvertes

1. L'unité primaire du PO est-elle l'équipe, le programme ou le portefeuille ?
2. Utilise-t-on les story points pour la prévision d'équipe et les heures/FTE pour le transverse ?
3. Qui maintient le mapping équipe et la matrice de compétences ?
4. Quelle source Finance fait autorité : ERP, Tempo, Jira Align, Value Ledger ?
5. Quels seuils de confiance et horizons affiche-t-on par défaut ?
6. Quelle politique de rétention pour les worklogs et données individuelles ?
7. Quels deux adapters valident la généricité : Azure DevOps, Linear, GitHub Projects ?
8. Le budget est-il suivi par initiative, par épic ou par équipe ?
9. Qui attribue les rôles projet et les périmètres : annuaire, manager, admin Méridian ?
10. Quelles vues sont partagées entre PO, PMO et Finance, et lesquelles sont strictement privées ?
11. Le rôle de Scrum Master et celui d'Engineering Manager sont-ils distincts dans toutes les équipes ?

## 15. Risques

| Risque | Mitigation |
|---|---|
| Données de tracker incomplètes | couverture visible, non observé, pas de faux zéro |
| Story points comparés entre équipes | unité par équipe, pas d'agrégation |
| Fausse précision de la prévision | P50/P85/P95, calibration, abstention |
| LLM qui invente une date | calcul déterministe, LLM narratif seulement |
| Double comptage multi-sources | source primaire, déduplication, couverture |
| Surveillance individuelle | agrégation équipe, pas de classement |
| Budget confondu avec effort | objets distincts, source Finance |
| Dépendance à un éditeur | port générique, deux adapters |
| Explosion des dashboards par rôle | un jeu de faits, des lentilles configurables |
| Confusion rôle / persona | rôle = autorisation réelle, pas de persona de démo |
| Rôle qui élargit les droits | matrice d'autorité, permissions avant agrégation |
| Surveillance individuelle | agrégat équipe, pas de classement |

## 16. Références

- [ADR-0019](../adr/0019-source-travail-generique-planification.md)
- [ADR-0020](../adr/0020-roles-projet-lentilles.md)
- [PRD-001](PRD-001-enterprise-intelligence-mesh.md)
- [PRD-002](PRD-002-memoire-contexte-raisonnement.md)
- [ADR-0009](../adr/0009-value-ledger.md)
- [Jira REST API v3](https://developer.atlassian.com/cloud/jira/platform/rest/v3/intro/)
- [Jira velocity chart](https://support.atlassian.com/jira-software-cloud/docs/view-and-understand-the-velocity-chart/)
- [Jira capacity planning](https://support.atlassian.com/jira-software-cloud/docs/plan-individual-capacity-for-your-team/)
- [Jira story points](https://support.atlassian.com/jira-software-cloud/docs/what-are-story-points/)
