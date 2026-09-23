# MÉRIDIAN — Functional Architecture
## Capacités, domaines fonctionnels, responsabilités et interactions du produit

**Statut :** Architecture fonctionnelle de référence  
**Version :** 1.0  
**Produit :** MÉRIDIAN  
**Tagline :** **DÉCOUVRIR · COMPRENDRE · DÉCIDER**

---

# 0. Objet du document

Ce document traduit le **Product Blueprint** de Méridian en architecture fonctionnelle.

Il répond à la question :

> **Quelles capacités fonctionnelles Méridian doit-il posséder, comment sont-elles organisées, et comment collaborent-elles pour produire la boucle d’exploitation continue ?**

Il ne décrit pas encore les choix techniques d’implémentation détaillés.

Il définit :

- les domaines fonctionnels ;
- leurs responsabilités ;
- les objets manipulés ;
- les entrées et sorties ;
- les flux principaux ;
- les événements ;
- les frontières de responsabilité ;
- les interactions avec les utilisateurs ;
- les interactions entre jumeaux, Mesh, experts et Flore ;
- les règles de gouvernance ;
- les points où une décision humaine est requise.

La logique centrale demeure :

> **Découvrir → Maturer → Exprimer → Investiguer → Décider → Agir → Mesurer → Apprendre**

---

# 1. Positionnement de l’architecture fonctionnelle

Méridian doit être pensé en trois niveaux.

```text
┌──────────────────────────────────────────────────────────────┐
│  EXPÉRIENCE PRODUIT                                         │
│  Aujourd’hui · Atlas · Flore · Opportunités · Investigations│
├──────────────────────────────────────────────────────────────┤
│  CAPACITÉS FONCTIONNELLES                                   │
│  Découverte · Connaissance · Maturation · Expertise         │
│  Investigation · Décision · Suivi · Apprentissage           │
├──────────────────────────────────────────────────────────────┤
│  FONDATION TECHNIQUE                                        │
│  Agents · LLM · Graph · Stores · Events · Connecteurs       │
│  Sécurité · Observabilité · APIs · Orchestration            │
└──────────────────────────────────────────────────────────────┘
```

Le présent document décrit principalement le niveau intermédiaire.

---

# 2. Architecture fonctionnelle globale

Méridian est composé de neuf grands domaines fonctionnels.

1. **Acquisition & Sources**
2. **Twin Intelligence**
3. **Knowledge & Claims**
4. **Mesh Intelligence**
5. **Maturation & Emergence**
6. **Expertise & Investigation**
7. **Decision & Improvement**
8. **Experience & Interaction**
9. **Governance & Platform Control**

Représentation simplifiée :

```text
                               UTILISATEURS
                                   │
                     ┌─────────────┴─────────────┐
                     │                           │
                  FLORE                       SURFACES
                     │                Aujourd’hui / Atlas / etc.
                     └─────────────┬─────────────┘
                                   │
                        EXPERIENCE & INTERACTION
                                   │
        ┌──────────────────────────┼──────────────────────────┐
        │                          │                          │
 MATURATION &              EXPERTISE &               DECISION &
 EMERGENCE                 INVESTIGATION              IMPROVEMENT
        │                          │                          │
        └──────────────┬───────────┴──────────────┬───────────┘
                       │                          │
                MESH INTELLIGENCE          KNOWLEDGE & CLAIMS
                       │                          │
                       └──────────────┬───────────┘
                                      │
                              TWIN INTELLIGENCE
                                      │
                              ACQUISITION & SOURCES
                                      │
                             SYSTÈMES ENTREPRISE

                    GOVERNANCE & PLATFORM CONTROL
                         transverse à tous les domaines
```

---

# 3. Domaine 1 — Acquisition & Sources

## 3.1 Mission

Acquérir de manière continue les informations provenant des systèmes de l’entreprise et les transformer en observations exploitables par Méridian.

---

## 3.2 Responsabilités

Le domaine gère :

- catalogue de sources ;
- connexion aux sources ;
- authentification ;
- autorisations ;
- découverte initiale ;
- synchronisation ;
- ingestion événementielle ;
- extraction ;
- normalisation ;
- provenance ;
- fraîcheur ;
- qualité ;
- erreurs de synchronisation.

---

## 3.3 Types de sources

### Technique

- GitHub ;
- GitLab ;
- Bitbucket ;
- bases de données ;
- Kafka ;
- APIs ;
- CMDB ;
- Datadog ;
- Splunk ;
- logs ;
- traces ;
- métriques ;
- pipelines CI/CD.

### Gestion de travail

- Jira ;
- ServiceNow ;
- outils de projet ;
- gestion de changements.

### Documentation

- Confluence ;
- SharePoint ;
- documents ;
- wiki ;
- architecture.

### Métier

- systèmes transactionnels ;
- CRM ;
- données de processus ;
- données produit ;
- événements métier.

### Humain

- contributions validées ;
- commentaires ;
- décisions ;
- observations d’experts.

---

## 3.4 Objets fonctionnels

```text
Source
SourceConnection
SourceCredentialReference
SyncPolicy
SyncRun
SourceObservation
SourceArtifact
SourceHealth
SourcePermission
```

---

## 3.5 États d’une source

```text
Déclarée
→ Configuration
→ Validation
→ Connectée
→ Découverte initiale
→ Active
→ Dégradée
→ Suspendue
→ Retirée
```

---

## 3.6 Sorties fonctionnelles

Le domaine produit :

- artefacts bruts ;
- observations ;
- événements ;
- métadonnées ;
- preuves ;
- indicateurs de qualité ;
- changements détectés.

Il ne produit pas directement de conclusions métier.

---

# 4. Domaine 2 — Twin Intelligence

## 4.1 Mission

Construire et maintenir l’intelligence locale de chaque jumeau.

Le jumeau applicatif est responsable de ce qu’il sait sur son application.

---

## 4.2 Responsabilités

Chaque jumeau doit pouvoir comprendre progressivement :

- identité de l’application ;
- rôle ;
- capacités ;
- fonctionnalités ;
- architecture ;
- composants ;
- règles métier ;
- flux ;
- données ;
- dépendances ;
- API ;
- événements ;
- historique ;
- changements ;
- incidents ;
- voisins ;
- équipes ;
- zones inconnues.

---

## 4.3 Naissance du jumeau

Le processus de naissance comprend :

```text
Identification
↓
Connexion des sources
↓
Découverte initiale
↓
Extraction structurelle
↓
Graph de connaissance local
↓
Claims initiaux
↓
Résumé vivant
↓
Voisins potentiels
↓
Publication dans le Mesh
```

---

## 4.4 Capacités du jumeau

### Compréhension structurelle

- packages ;
- modules ;
- services ;
- tables ;
- endpoints ;
- dépendances.

### Compréhension comportementale

- flux ;
- séquences ;
- interactions ;
- appels ;
- déclencheurs.

### Compréhension métier

- règles ;
- capacités ;
- concepts ;
- événements métier ;
- responsabilités.

### Compréhension historique

- fonctionnalités ajoutées ;
- changements majeurs ;
- migrations ;
- incidents ;
- dettes.

---

## 4.5 Santé cognitive du jumeau

Chaque jumeau doit exposer :

- couverture ;
- fraîcheur ;
- confiance ;
- contradictions ;
- sources ;
- zones inconnues ;
- dette de connaissance.

---

# 5. Domaine 3 — Knowledge & Claims

## 5.1 Mission

Maintenir la connaissance explicite, traçable et versionnée de Méridian.

---

## 5.2 Claim

Un Claim est une affirmation vérifiable.

Exemple :

> « TBT consomme le service X pour valider une opération avant soumission. »

Un Claim n’est pas simplement une phrase générée par un LLM.

Il possède :

- sujet ;
- prédicat ;
- objet ;
- type ;
- provenance ;
- preuves ;
- confiance ;
- validité temporelle ;
- statut ;
- contradictions.

---

## 5.3 États d’un Claim

```text
Observé
→ Proposé
→ Supporté
→ Renforcé
→ Mature
→ Contesté
→ Invalidé
→ Historique
```

---

## 5.4 Capacités

- création ;
- enrichissement ;
- fusion ;
- versionnement ;
- validation ;
- contradiction ;
- invalidation ;
- traçabilité ;
- temporalité.

---

## 5.5 Relation Claim / preuve

```text
Claim
├── Evidence A
├── Evidence B
├── Evidence C
├── Contradiction X
└── Confidence
```

---

## 5.6 Knowledge Graph fonctionnel

Le graphe relie notamment :

- applications ;
- capacités ;
- processus ;
- équipes ;
- clients ;
- produits ;
- données ;
- événements ;
- règles ;
- domaines ;
- décisions ;
- investigations.

---

# 6. Domaine 4 — Mesh Intelligence

## 6.1 Mission

Construire la compréhension transversale qui dépasse chaque jumeau individuel.

---

## 6.2 Rôle

Le Mesh :

- relie les jumeaux ;
- découvre des relations ;
- confronte les Claims ;
- identifie les contradictions ;
- propose des regroupements ;
- construit des phénomènes transversaux ;
- détecte la propagation ;
- maintient la topologie vivante.

---

## 6.3 Relations

Les relations peuvent être :

- déclarées ;
- observées ;
- inférées ;
- confirmées ;
- contestées.

---

## 6.4 Contradiction

Le Mesh doit pouvoir détecter :

- deux Claims incompatibles ;
- divergence entre CMDB et comportement observé ;
- divergence entre documentation et code ;
- divergence entre modèle métier et flux réel ;
- divergence temporelle.

---

## 6.5 Domaine émergent

Le Mesh peut proposer :

> « Ces applications semblent former une capacité cohérente non représentée dans le modèle officiel. »

Cette proposition n’écrase pas le modèle humain.

Elle crée une divergence explicite à analyser.

---

# 7. Domaine 5 — Maturation & Emergence

## 7.1 Mission

Transformer des observations dispersées en phénomènes significatifs.

C’est l’un des domaines les plus importants de Méridian.

---

## 7.2 Pipeline

```text
Signal
↓
Situation candidate
↓
Qualification
↓
Maturation
↓
Expression
├── Opportunité
├── Risque
├── Investigation
└── Observation conservée
```

---

## 7.3 Signal

Un Signal représente un changement ou un fait pouvant devenir significatif.

Exemples :

- hausse de latence ;
- nouveau lien ;
- changement de code ;
- augmentation du travail manuel ;
- dégradation d’un parcours ;
- nouveau pattern d’incident.

---

## 7.4 Situation candidate

Plusieurs signaux peuvent être agrégés selon :

- proximité temporelle ;
- proximité topologique ;
- causalité probable ;
- même population affectée ;
- même processus ;
- même changement source.

---

## 7.5 Maturation

La maturation évalue :

- nombre de preuves ;
- diversité ;
- indépendance ;
- fraîcheur ;
- cohérence ;
- historique ;
- contradictions ;
- validation expert ;
- impact potentiel.

---

## 7.6 Expression

Une Expression est la formulation interprétée d’un phénomène.

Exemple :

> « Une friction progressive semble apparaître dans le parcours de renouvellement. »

---

## 7.7 Opportunité

Une Opportunité représente un potentiel de création de valeur.

Exemples :

- rationalisation ;
- automatisation ;
- simplification ;
- réduction de duplication ;
- modernisation ;
- amélioration client.

---

## 7.8 Risque

Un Risque représente une conséquence négative potentielle.

Il contient :

- probabilité ;
- impact ;
- exposition ;
- délai ;
- propagation ;
- contrôles existants.

---

# 8. Domaine 6 — Expertise & Investigation

## 8.1 Mission

Mobiliser les compétences nécessaires pour comprendre une situation suffisamment bien pour permettre une décision.

---

## 8.2 Expert

Un Expert est une capacité spécialisée.

Il possède :

```text
Expert
├── Domaine
├── Compétences
├── Méthodes
├── Sources autorisées
├── Outils
├── Critères de preuve
├── Mémoire spécialisée
├── Limites
└── Types de contribution
```

---

## 8.3 Familles d’experts

### TI

- architecture ;
- code ;
- base de données ;
- performance ;
- sécurité ;
- résilience ;
- données ;
- cloud ;
- modernisation.

### Métier

- paiements ;
- crédit ;
- hypothèque ;
- fraude ;
- conformité ;
- finance ;
- risque ;
- opérations.

### Transverses

- processus ;
- expérience client ;
- expérience employé ;
- transformation ;
- stratégie ;
- économie.

---

## 8.4 Orchestrateur d’expertise

L’orchestrateur détermine :

- quels experts appeler ;
- dans quel ordre ;
- quelles questions poser ;
- quelles preuves partager ;
- quand demander contradiction ;
- quand arrêter.

---

## 8.5 Investigation

L’investigation structure :

- question ;
- contexte ;
- hypothèses ;
- preuves ;
- contradictions ;
- experts ;
- timeline ;
- scénarios ;
- synthèse.

---

## 8.6 Cycle de l’investigation

```text
Ouverte
→ Cadrage
→ Collecte
→ Analyse
→ Contradiction
→ Synthèse
→ Scénarios
→ Prête à décider
→ Décision prise
→ Fermée
```

---

## 8.7 Hypothèse

Une hypothèse peut être :

- ouverte ;
- renforcée ;
- affaiblie ;
- rejetée ;
- confirmée.

---

# 9. Domaine 7 — Decision & Improvement

## 9.1 Mission

Transformer la compréhension en action gouvernée et mesurer les résultats.

---

## 9.2 Scénario

Un scénario représente une option.

Il contient :

- description ;
- coûts ;
- bénéfices ;
- risques ;
- dépendances ;
- impacts ;
- réversibilité ;
- confiance.

---

## 9.3 Décision

La décision capture :

- scénario retenu ;
- scénarios rejetés ;
- raisons ;
- décideurs ;
- date ;
- hypothèses ;
- critères de succès.

---

## 9.4 Initiative

Une décision peut créer une initiative.

Elle contient :

- objectifs ;
- responsables ;
- périmètre ;
- systèmes ;
- métriques ;
- échéances ;
- points de contrôle.

---

## 9.5 Mesure

Le système compare :

```text
Attendu
vs
Observé
```

---

## 9.6 Résultat

Un résultat peut être :

- conforme ;
- meilleur ;
- inférieur ;
- inattendu ;
- contradictoire.

---

## 9.7 Apprentissage

Un apprentissage peut créer :

- nouveau Claim ;
- nouveau Signal ;
- nouvelle Opportunité ;
- règle de décision ;
- pattern historique.

---

# 10. Domaine 8 — Experience & Interaction

## 10.1 Mission

Exposer l’intelligence de Méridian aux utilisateurs.

---

## 10.2 Surfaces

### Aujourd’hui

Priorisation de ce qui compte.

### Atlas

Géographie de l’entreprise.

### Flore

Interface conversationnelle.

### Radar

Phénomènes émergents.

### Opportunités

Portefeuille d’amélioration.

### Investigations

Analyse structurée.

### Jumeaux

Connaissance locale.

### Domaines

Vision organisationnelle et émergente.

### Décisions

Historique des arbitrages.

### Feed

Évolution de la connaissance.

---

# 11. Flore fonctionnellement

Flore est un orchestrateur conversationnel.

Elle doit :

1. comprendre l’intention ;
2. résoudre le contexte ;
3. déterminer la portée ;
4. identifier les capacités fonctionnelles nécessaires ;
5. exécuter ou déléguer ;
6. synthétiser ;
7. exposer les preuves.

---

## 11.1 Exemple

Question :

> « Quelles fonctionnalités ont été ajoutées à TBT depuis trois ans ? »

Flux :

```text
Intent
↓
Resolution TBT
↓
Time scope
↓
Twin Intelligence
↓
Source History
↓
Expert Code
↓
Expert Fonctionnel
↓
Knowledge Claims
↓
Synthesis
↓
Evidence references
```

---

# 12. Gouvernance & Platform Control

## 12.1 Mission

Garantir que Méridian reste contrôlable, explicable et sécurisé.

---

## 12.2 Capacités

- identité ;
- rôles ;
- permissions ;
- politiques ;
- accès aux sources ;
- cloisonnement ;
- audit ;
- provenance ;
- rétention ;
- gestion des coûts ;
- politiques IA ;
- validation humaine.

---

# 13. Modèle d’événements fonctionnels

Méridian doit être événementiel conceptuellement.

Exemples :

```text
SourceConnected
SourceSynced
ArtifactChanged
ObservationCreated
ClaimCreated
ClaimStrengthened
ClaimContradicted
RelationshipDiscovered
TwinUpdated
SignalDetected
SituationCreated
ExpressionCreated
OpportunityCreated
RiskCreated
InvestigationOpened
HypothesisCreated
ExpertRequested
ScenarioCreated
DecisionRecorded
InitiativeStarted
OutcomeMeasured
LearningCreated
```

---

# 14. Flux principal — découverte vers opportunité

```text
Source
↓
Observation
↓
Twin
↓
Claim
↓
Mesh relation
↓
Signal
↓
Situation candidate
↓
Maturation
↓
Expression
↓
Opportunity
```

---

# 15. Flux principal — opportunité vers décision

```text
Opportunity
↓
Investigation
↓
Expertise orchestration
↓
Hypotheses
↓
Contradiction
↓
Scenarios
↓
Human decision
↓
Initiative
```

---

# 16. Flux principal — décision vers apprentissage

```text
Initiative
↓
Observation after change
↓
Expected vs observed
↓
Outcome
↓
Learning
↓
Knowledge update
↓
Future detection improved
```

---

# 17. Frontières de responsabilité

## Acquisition

Ne doit pas interpréter profondément.

## Twin Intelligence

Ne doit pas prendre de décisions transversales.

## Knowledge

Ne doit pas décider si un phénomène mérite attention.

## Mesh

Ne doit pas transformer toute divergence en alerte.

## Maturation

Ne doit pas produire une décision.

## Experts

Ne doivent pas décider à la place de l’humain.

## Decision

Ne doit pas perdre les preuves de l’investigation.

## Experience

Ne doit pas inventer des informations absentes de la connaissance.

---

# 18. Objets métier principaux

```text
Source
Artifact
Observation
Twin
Claim
Evidence
Relationship
Domain
Signal
Situation
Expression
Opportunity
Risk
Investigation
Hypothesis
Expert
ExpertContribution
Scenario
Decision
Initiative
Outcome
Learning
```

---

# 19. Relations principales

```text
Source → Artifact
Artifact → Observation
Observation → Claim
Twin → Claim
Claim → Evidence
Twin → Relationship
Signal → Situation
Situation → Expression
Expression → Opportunity/Risk
Opportunity → Investigation
Investigation → Hypothesis
Investigation → ExpertContribution
Investigation → Scenario
Scenario → Decision
Decision → Initiative
Initiative → Outcome
Outcome → Learning
Learning → Claim/Signal
```

---

# 20. Temporalité fonctionnelle

Tous les objets critiques doivent supporter une dimension temporelle.

Exemples :

- validFrom ;
- validTo ;
- observedAt ;
- discoveredAt ;
- lastConfirmedAt ;
- supersededAt.

La temporalité permet :

- historique ;
- comparaison ;
- time travel ;
- analyse d’incident ;
- mesure d’évolution.

---

# 21. Niveaux de portée

Chaque capacité doit respecter :

- Perso ;
- Mon équipe ;
- Domaine ;
- Organisation ;
- Mesh global.

La portée est gouvernée par les droits.

---

# 22. Modèle de confiance

La confiance doit être calculée et explicable.

Dimensions possibles :

- diversité des sources ;
- qualité ;
- fraîcheur ;
- cohérence ;
- répétition ;
- validation ;
- contradiction ;
- historique.

---

# 23. Maturité vs confiance

Deux dimensions distinctes :

### Maturité

À quel point l’analyse est avancée.

### Confiance

À quel point la conclusion est crédible.

Exemple :

Une analyse peut être complète mais conserver une confiance moyenne.

---

# 24. Contradiction fonctionnelle

Chaque conclusion importante doit pouvoir exposer :

```text
Support
Contradictions
Unknowns
```

Exemple :

```text
Hypothèse : la règle X provoque la hausse de délais

Support :
+ corrélation temporelle
+ traces applicatives
+ tickets opérationnels

Contradictions :
- certains parcours non touchés

Unknowns :
? impact sur segment entreprise
```

---

# 25. Interaction humain / système

L’humain peut :

- confirmer ;
- contester ;
- commenter ;
- ajouter une preuve ;
- demander une expertise ;
- rejeter une opportunité ;
- accepter une investigation ;
- choisir un scénario ;
- enregistrer une décision.

Chaque intervention devient traçable.

---

# 26. Notifications fonctionnelles

Une notification doit être créée uniquement lorsqu’un événement mérite une action humaine.

Exemples :

- opportunité mature ;
- risque élevé ;
- décision attendue ;
- contradiction critique ;
- résultat inattendu ;
- expertise demandée.

---

# 27. États longs et traitements progressifs

Méridian doit fonctionner avec des traitements pouvant être longs.

Le produit doit supporter :

- progression ;
- résultats intermédiaires ;
- reprise ;
- échec partiel ;
- continuation ;
- publication incrémentale.

---

# 28. Exemple de progression d’investigation

```text
Investigation #INV-1024

✓ Contexte résolu
✓ 4 jumeaux identifiés
✓ 21 Claims récupérés
✓ Expert performance terminé
● Expert processus en cours
○ Contradiction
○ Synthèse
○ Scénarios
```

---

# 29. Cas d’usage fonctionnel — suppression de TBT

Question :

> « Que se passerait-il si nous retirions TBT dans 18 mois ? »

Étapes :

1. résoudre TBT ;
2. identifier dépendances ;
3. interroger voisins ;
4. récupérer capacités métier ;
5. identifier consommateurs ;
6. expert architecture ;
7. expert données ;
8. expert métier ;
9. expert opérations ;
10. expert risque ;
11. construire scénarios ;
12. exposer inconnues ;
13. produire synthèse.

Sortie :

- impact ;
- dépendances ;
- risques ;
- coûts ;
- migration ;
- inconnues ;
- scénarios.

---

# 30. Cas d’usage fonctionnel — opportunité processus

Méridian observe :

- tâches manuelles ;
- double saisie ;
- appels fréquents ;
- délais.

Flux :

```text
Observations
↓
Claims
↓
Situation
↓
Expression
↓
Opportunity
↓
Expert Processus
↓
Expert Employé
↓
Expert SI
↓
Investigation
↓
Scenario automation
```

---

# 31. Cas d’usage fonctionnel — incident

Flux :

```text
Signal monitoring
↓
Situation candidate
↓
Related changes
↓
Related twins
↓
Historical incidents
↓
Hypotheses
↓
Experts
↓
Root cause candidate
↓
Decision / remediation
↓
Outcome
↓
Learning
```

---

# 32. Capacités transversales

## Search

Recherche sémantique et structurée.

## Reporting

Export des synthèses et preuves.

## Timeline

Navigation temporelle.

## Provenance

Traçabilité complète.

## Audit

Historique des actions.

## Cost Awareness

Suivi des coûts d’analyse.

---

# 33. Priorisation fonctionnelle

## P0 — Fondation

- sources ;
- twins ;
- Claims ;
- relations ;
- Flore ;
- Atlas.

## P1 — Exploitation

- Signal ;
- Situation ;
- Expression ;
- Opportunité ;
- Investigation ;
- Expert orchestration.

## P2 — Décision

- Scénarios ;
- Décisions ;
- Initiatives ;
- Outcomes.

## P3 — Apprentissage

- mémoire ;
- pattern detection ;
- recommandations historiques.

---

# 34. MVP fonctionnel

Le MVP doit démontrer une boucle complète.

Minimum :

```text
Sources
↓
Twin
↓
Claims
↓
Signal
↓
Expression
↓
Investigation
↓
Experts
↓
Scenario
↓
Decision
↓
Outcome
```

Ce MVP vaut mieux que dix surfaces non reliées.

---

# 35. Critères de succès fonctionnels

Le produit doit permettre de démontrer :

### Compréhension

Une application peut expliquer ce qu’elle fait et pourquoi.

### Traversée

Une question peut traverser plusieurs jumeaux.

### Émergence

Méridian peut détecter quelque chose que personne n’a explicitement demandé.

### Investigation

Une situation peut être analysée avec plusieurs expertises.

### Décision

Une analyse peut aboutir à des scénarios comparables.

### Boucle

Le résultat d’une décision peut être mesuré et réinjecté.

---

# 36. Règles fonctionnelles critiques

1. Aucune conclusion majeure sans preuve.
2. Toute preuve doit conserver sa provenance.
3. Toute contradiction importante doit rester visible.
4. Toute décision importante doit rester humaine.
5. Toute connaissance doit être temporelle.
6. Une source ne doit pas devenir une vérité unique.
7. Un jumeau peut dire qu’il ne sait pas.
8. Le Mesh peut contredire un jumeau.
9. Un expert peut contredire le Mesh.
10. Une décision peut générer de nouveaux apprentissages.

---

# 37. Architecture fonctionnelle cible

Vision synthétique :

```text
┌──────────────────────────────────────────────────────────────────┐
│                        EXPERIENCE LAYER                          │
│ Aujourd’hui | Atlas | Flore | Opportunités | Investigations     │
└──────────────────────────────────────────────────────────────────┘
                               │
┌──────────────────────────────────────────────────────────────────┐
│                    EXPLOITATION INTELLIGENCE                     │
│ Maturation | Emergence | Expertise | Investigation | Decision   │
└──────────────────────────────────────────────────────────────────┘
                               │
┌──────────────────────────────────────────────────────────────────┐
│                       MESH INTELLIGENCE                          │
│ Relations | Contradictions | Propagation | Domains | Patterns   │
└──────────────────────────────────────────────────────────────────┘
                               │
┌──────────────────────────────────────────────────────────────────┐
│                         TWIN LAYER                               │
│ Twin Understanding | Claims | Local History | Local Context     │
└──────────────────────────────────────────────────────────────────┘
                               │
┌──────────────────────────────────────────────────────────────────┐
│                       ACQUISITION LAYER                          │
│ Sources | Sync | Normalization | Observation | Provenance       │
└──────────────────────────────────────────────────────────────────┘

            GOVERNANCE / SECURITY / TEMPORALITY / AUDIT
                     transverse à toutes les couches
```

---

# 38. Découpage en bounded contexts fonctionnels

Pour préparer l’architecture technique, les domaines peuvent être traités comme bounded contexts.

### Source Context

Responsable des connecteurs et observations.

### Twin Context

Responsable de la compréhension locale.

### Knowledge Context

Responsable des Claims et preuves.

### Mesh Context

Responsable des relations globales.

### Signal Context

Responsable des signaux et situations.

### Opportunity Context

Responsable des opportunités et risques.

### Investigation Context

Responsable des investigations et hypothèses.

### Expertise Context

Responsable des experts.

### Decision Context

Responsable des scénarios, décisions et initiatives.

### Learning Context

Responsable des outcomes et apprentissages.

### Experience Context

Responsable de Flore et des surfaces.

---

# 39. Contrats fonctionnels entre contextes

Exemple :

```text
Source Context
    publishes ObservationCreated

Twin Context
    consumes ObservationCreated
    publishes ClaimCreated

Knowledge Context
    validates ClaimCreated
    publishes ClaimStrengthened

Mesh Context
    consumes claims
    publishes RelationshipDiscovered

Signal Context
    consumes observations/relations
    publishes SituationCreated

Opportunity Context
    consumes mature situations
    publishes OpportunityCreated

Investigation Context
    consumes opportunities
    requests Expertise Context

Decision Context
    consumes investigation synthesis
    publishes DecisionRecorded

Learning Context
    consumes outcomes
    publishes LearningCreated
```

---

# 40. Questions ouvertes à résoudre dans l’architecture technique

Ce Blueprint fonctionnel laisse volontairement ouvertes plusieurs décisions techniques :

- stockage polyglotte ou unifié ;
- représentation des Claims ;
- event bus ;
- orchestration agentique ;
- mémoire des experts ;
- RAG global vs RAG local ;
- graph store ;
- temporal graph ;
- workflow engine ;
- vector stores ;
- isolation multi-tenant ;
- stratégie de cache ;
- coûts Bedrock ;
- modèle de sécurité ;
- observabilité des agents.

Ces choix doivent être traités dans le document suivant :

> **MÉRIDIAN — Technical Architecture**

---

# 41. Conclusion

L’architecture fonctionnelle de Méridian repose sur une séparation claire :

- les sources observent ;
- les jumeaux comprennent localement ;
- les Claims formalisent la connaissance ;
- le Mesh relie et confronte ;
- la maturation fait émerger ce qui compte ;
- les experts approfondissent ;
- les investigations structurent le raisonnement ;
- les décisions gouvernent l’action ;
- les outcomes mesurent ;
- les apprentissages enrichissent le système.

La boucle complète est :

> **Source → Observation → Claim → Mesh → Signal → Expression → Opportunité → Investigation → Décision → Résultat → Apprentissage**

C’est cette boucle qui doit guider l’architecture technique.

Le prochain document doit donc décrire comment ces capacités seront concrètement implémentées :

- services ;
- agents ;
- workflows ;
- stockages ;
- événements ;
- APIs ;
- sécurité ;
- observabilité ;
- coûts ;
- scalabilité ;
- résilience.

Ce document sera :

> **MÉRIDIAN — Technical Architecture**
