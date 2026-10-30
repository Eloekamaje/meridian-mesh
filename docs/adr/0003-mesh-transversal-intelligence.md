# ADR-0003 — Le Mesh est la couche d'intelligence transversale, pas une source ni un outil

**Date :** 2026-10-30  
**Statut :** Accepté  
**Décideurs :** Produit, architecture d'entreprise, données, sécurité  
**Complète :** ADR-0001  
**Amende :** ADR-0002

## Contexte

Une formulation de l'orchestrateur général disait : « Le Mesh (les jumeaux, leurs dépôts et leurs connaissances) est une source, pas le point de départ obligatoire. » Cette phrase a été reprise dans ADR-0002. Elle est fausse à plusieurs titres :

- elle réduit le Mesh à un **outil de vérification** ;
- elle traite les **dépôts Git** comme une source centrale ;
- elle confond **sources, observations, connaissance et Mesh** ;
- elle laisse croire que le Mesh est un catalogue que l'on consulte après coup ;
- elle ne représente ni les **processus**, ni les **capacités**, ni les **parcours**, ni les **décisions**, ni les **apprentissages**.

Les documents fondateurs disent l'inverse :

- Méridian est un **Enterprise Intelligence Mesh**, un **système d'exploitation cognitif de l'entreprise** ;
- les **sources observent** ; les **jumeaux comprennent localement** ; les **Claims formalisent** ; le **Mesh relie et confronte** ; la **maturation fait émerger** ; l'humain décide ; les outcomes mesurent ; les apprentissages enrichissent ;
- le Mesh est le **système nerveux** : indispensable, rarement le sujet principal de l'expérience ;
- le Mesh est la **connaissance qui dépasse un Twin** ;
- le Mesh est le **point de rencontre des projections** : architecture, business, client, employé, opérations, risque, finance, data, transformation.

## Décision

Le Mesh est la **couche d'intelligence transversale de l'entreprise**. Il n'est :

- ni une **source** (les sources produisent des observations) ;
- ni un **outil de vérification** (la vérification est une propriété des Claims et des preuves) ;
- ni un **produit visible** (l'utilisateur voit des situations, des questions, des décisions et des actions) ;
- ni un **catalogue d'applications** (l'application est un point d'amorçage, pas l'ontologie).

Le Mesh est le **substrat cognitif partagé** qui relie, confronte, fait émerger et conserve la mémoire temporelle de l'entreprise.

### Séparations normatives

1. **Sources vs connaissance** : les sources produisent des observations ; les Claims formalisent la connaissance.
2. **Twin vs Mesh** : le Twin comprend localement ; le Mesh comprend transversalement.
3. **Connaissance vs agents** : les stores conservent ; les agents raisonnent.
4. **Agents vs workflows** : les agents exécutent des tâches cognitives ; les workflows portent la durabilité.
5. **Compréhension vs décision** : Méridian construit des scénarios ; l'humain conserve la gouvernance.

### Boucle de référence

> **Source → Observation → Claim → Mesh → Signal → Expression → Opportunité → Investigation → Décision → Initiative → Outcome → Apprentissage**

### Rôle des Twins

Un Twin est une représentation vivante d'une entité d'entreprise. Il n'est **pas limité à l'application** : `APPLICATION`, `PROCESS`, `CAPABILITY`, `JOURNEY`, `ORGANIZATION`, `PRODUCT`, `DATA_DOMAIN`. L'application est le premier type implémenté, pas le type universel.

### Rôle de Flore

Flore est un agent d'entreprise **situé dans le Mesh**, pas un routeur d'applications. Elle peut :

- situer une demande dans les domaines, capacités, processus et parcours ;
- lire des Claims, des preuves et des contradictions ;
- relier des Twins et confronter des sources ;
- faire émerger une situation ;
- investiguer, proposer une décision, agir, mesurer et apprendre ;
- concevoir une cible greenfield quand l'application n'existe pas.

## Alternatives considérées

### Alternative 1 — Le Mesh comme base de vérification
- **Avantages** : cadre simple, facile à exposer comme outil.
- **Inconvénients** : réduit le produit à un moteur de réponse ; ignore l'émergence, l'investigation, la décision et l'apprentissage.
- **Pourquoi rejetée** : contredit la vision et la finalité du produit.

### Alternative 2 — Le Mesh comme source
- **Avantages** : unification naïve de la lecture.
- **Inconvénients** : confond observations et connaissance ; efface la provenance, la temporalité et la maturation.
- **Pourquoi rejetée** : les sources observent ; le Mesh relie et confronte.

### Alternative 3 — Le Mesh comme produit visible
- **Avantages** : démonstration spectaculaire de la carte.
- **Inconvénients** : l'utilisateur voit un graphe technique au lieu d'une situation, d'une décision ou d'une action.
- **Pourquoi rejetée** : « le Mesh ne doit pas devenir le produit visible ».

### Alternative 4 — Le catalogue d'applications comme noyau
- **Avantages** : simplicité, proximité avec le code et les jumeaux existants.
- **Inconvénients** : app-only, ignore processus, capacités, parcours, organisations, produits et domaines de données.
- **Pourquoi rejetée** : l'application est le point d'amorçage, pas la finalité.

## Conséquences

### Positives

- Le produit est aligné sur l'**Enterprise Intelligence Mesh**.
- Les sources, les Twins, les Claims, le Mesh, les situations et les décisions ont des rôles distincts.
- Les outils deviennent des **adaptateurs** à des capacités, pas le noyau.
- Les conceptions greenfield peuvent être produites sans faux jumeau et sans fausse preuve.
- La boucle décision → outcome → apprentissage devient représentable.

### Négatives / coûts

- Le modèle d'objets est plus riche : huit familles, plusieurs types de Twin, temporalité.
- Les écrans et APIs doivent exposer des situations et des décisions, pas seulement des applications.
- Les agents doivent être évalués sur la sélection de capacités et la qualité des preuves.
- Le passage d'un code app-first à un modèle entreprise-first est un chantier de réalignement.

### Risques

- **Surcharge** : tout relier sans maturité. Mitigation : Claims, seuils, contradictions, provenance.
- **Dérive applicative** : retomber sur un routeur d'applications. Mitigation : tests d'architecture et jeu d'or.
- **Dérive « outil = architecture »** : confondre le harness avec le noyau. Mitigation : ADR-0004.

## Critères d'acceptation

1. Le prompt de Flore ne présente plus le Mesh comme une source, un outil de vérification ou un catalogue d'applications.
2. Une question de conception greenfield ne mobilise aucun jumeau et ne montre pas l'Atlas.
3. Une question sur l'existant peut citer des Claims, des preuves et des contradictions.
4. Le modèle de domaine accepte un Twin `PROCESS`, `CAPABILITY` ou `JOURNEY` sans modifier le noyau.
5. Les APIs distinguent `DECLARED`, `OBSERVED`, `INFERRED`, `PROPOSED`, `CONFIRMED`.
6. L'UI distingue une proposition d'une observation.
7. Un test d'architecture interdit de présenter le Mesh comme une source ou un simple outil.

## Références

- `docs/MÉRIDIAN — Product Vision & Operating Model.md`
- `docs/MERIDIAN_Domain_Model_Information_Architecture_v1.md`
- `docs/MERIDIAN_Functional_Architecture_v1.md`
- `docs/MERIDIAN_Knowledge_Claims_Architecture_v1.md`
- `docs/MERIDIAN_Technical_Architecture_v1.md`
- `docs/prd/PRD-001-enterprise-intelligence-mesh.md`
