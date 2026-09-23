# MÉRIDIAN — Product Blueprint
## Fonctionnalités, expériences, objets métier et parcours d’exploitation

**Statut :** Blueprint produit de référence  
**Version :** 1.0  
**Produit :** MÉRIDIAN  
**Tagline :** **DÉCOUVRIR · COMPRENDRE · DÉCIDER**

---

# 0. Résumé exécutif

Méridian est un système d’intelligence vivante de l’entreprise.

Sa fondation est constituée d’un réseau de jumeaux applicatifs et de connaissances reliées entre elles. Cette fondation permet de découvrir progressivement le fonctionnement réel de l’entreprise, de construire des Claims, de confronter les sources, de détecter les contradictions et de maintenir une représentation vivante du système d’information et de son environnement.

Mais le produit ne doit pas être centré sur le réseau lui-même.

La valeur de Méridian apparaît lorsqu’il transforme cette compréhension en exploitation continue :

> **Découvrir → Maturer → Exprimer → Investiguer → Décider → Agir → Mesurer → Apprendre**

Le Product Blueprint décrit comment cette logique devient un produit concret.

Il définit :

- les utilisateurs ;
- les principales expériences ;
- les surfaces produit ;
- les objets métier ;
- les cycles de vie ;
- les interactions avec Flore ;
- le rôle d’Atlas ;
- le rôle des experts spécialisés ;
- la gestion des opportunités, risques et investigations ;
- les règles de confiance et de preuve ;
- les mécanismes de gouvernance ;
- les fonctionnalités minimales attendues.

L’objectif n’est pas de créer un simple outil de cartographie du SI.

L’objectif est de créer un environnement où l’entreprise peut continuellement répondre à la question :

> **Qu’est-ce que nous devons comprendre, décider ou améliorer maintenant ?**

---

# 1. Objectif du Product Blueprint

Le document de vision explique pourquoi Méridian existe et comment il crée de la valeur.

Le Product Blueprint répond à une question différente :

> **Quel produit devons-nous réellement construire pour rendre cette vision utilisable ?**

Le Blueprint doit servir de référence commune pour :

- Product Management ;
- Product Ownership ;
- UX/UI ;
- architecture ;
- ingénierie ;
- équipes IA/agents ;
- responsables métier ;
- sponsors ;
- équipes de gouvernance.

Il ne décrit pas encore l’implémentation technique détaillée.

Il définit d’abord :

- les comportements attendus ;
- les objets visibles ;
- les parcours utilisateurs ;
- les transitions d’état ;
- les règles de fonctionnement ;
- les responsabilités de chaque surface.

---

# 2. Définition produit

## 2.1 Définition longue

> **Méridian est un système d’intelligence vivante de l’entreprise qui découvre continuellement son fonctionnement réel, fait mûrir la connaissance, révèle les phénomènes significatifs, mobilise les expertises nécessaires, accompagne les investigations et décisions, puis mesure leurs résultats afin d’améliorer continuellement sa compréhension.**

---

## 2.2 Définition courte

> **Méridian transforme la compréhension vivante de l’entreprise en amélioration continue.**

---

## 2.3 Ce que Méridian n’est pas

Méridian n’est pas simplement :

- un Knowledge Graph ;
- une CMDB augmentée ;
- un outil d’observabilité ;
- un outil de documentation ;
- un assistant conversationnel ;
- un outil de process mining ;
- un moteur de recherche ;
- un outil d’architecture ;
- une plateforme multi-agents ;
- un simple Digital Twin.

Il peut incorporer certaines capacités de ces familles de produits.

La différence vient de la boucle complète :

> **observer → comprendre → faire émerger → investiguer → décider → mesurer → apprendre**

---

# 3. Principes produit

## 3.1 Découverte avant conclusion

Méridian observe avant d’affirmer.

Un fait isolé ne devient jamais automatiquement une vérité globale.

---

## 3.2 Preuve avant certitude

Chaque conclusion importante doit être reliée à :

- une ou plusieurs sources ;
- des Claims ;
- un historique ;
- des relations vérifiables ;
- un niveau de confiance ;
- des contradictions éventuelles.

---

## 3.3 Incertitude explicite

Le produit doit savoir afficher :

> « Nous ne savons pas encore. »

ou :

> « Cette conclusion reste hypothétique. »

L’incertitude est une propriété normale du système.

---

## 3.4 Maturation progressive

Une connaissance peut évoluer.

Exemple :

**Observation → Hypothèse → Claim → Claim renforcé → Connaissance mature**

La maturité doit être visible.

---

## 3.5 Exploitation avant contemplation

L’utilisateur ne doit pas ouvrir Méridian principalement pour observer une carte.

Il doit pouvoir immédiatement savoir :

- ce qui émerge ;
- ce qui mérite son attention ;
- ce qui doit être investigué ;
- ce qui attend une décision ;
- ce qui s’est amélioré ;
- ce qui n’a pas fonctionné.

---

## 3.6 Opportunités autant que problèmes

Méridian ne doit pas seulement chercher les anomalies.

Il doit également détecter :

- simplifications ;
- consolidations ;
- automatisations ;
- rationalisations ;
- gains d’expérience client ;
- réductions de friction employé ;
- opportunités de modernisation.

---

## 3.7 Human-in-the-loop

Méridian peut :

- observer ;
- proposer ;
- expliquer ;
- recommander ;
- simuler ;
- comparer ;
- suivre.

Les décisions significatives restent gouvernées par l’humain.

---

## 3.8 Mémoire avant répétition

Une organisation ne devrait pas refaire la même investigation plusieurs fois sans bénéficier de l’expérience précédente.

Méridian doit conserver :

- les décisions ;
- les raisons ;
- les scénarios étudiés ;
- les résultats ;
- les effets secondaires ;
- les apprentissages.

---

# 4. Utilisateurs du produit

Méridian doit rester transversal.

Le produit ne doit pas supposer un seul type d’utilisateur.

---

## 4.1 Direction / décideurs

### Questions principales

- Quels risques émergent ?
- Où sont les opportunités ?
- Quelles transformations ont le plus de valeur ?
- Quels sujets exigent un arbitrage ?
- Quels changements produisent réellement les résultats attendus ?

### Besoins

- synthèse ;
- impact ;
- valeur ;
- risque ;
- confiance ;
- scénarios ;
- historique de décision.

---

## 4.2 Gestionnaires métier

### Questions principales

- Pourquoi mon processus se dégrade-t-il ?
- Où est la friction ?
- Quels systèmes contribuent au problème ?
- Que peut-on améliorer ?
- Quel sera l’impact d’une modification ?

### Besoins

- parcours métier ;
- processus ;
- dépendances ;
- impacts clients ;
- impacts employés ;
- causes probables.

---

## 4.3 Product Managers / Product Owners

### Questions principales

- Quels problèmes réels devons-nous prioriser ?
- Quelles opportunités émergent ?
- Quelles fonctionnalités ont réellement produit de la valeur ?
- Quelles dépendances doivent être considérées avant un changement ?

---

## 4.4 Architectes

### Questions principales

- Comment l’entreprise fonctionne réellement ?
- Quels liens sont documentés et lesquels sont découverts ?
- Quelles dépendances sont critiques ?
- Quels domaines émergent ?
- Quels systèmes peuvent être consolidés ?

---

## 4.5 Développeurs / responsables applicatifs

### Questions principales

- Que sait Méridian de mon application ?
- Quels changements récents sont significatifs ?
- Qui dépend de mon application ?
- Quels incidents ou comportements sont associés à mes changements ?
- Quelles règles métier ont été découvertes ?

---

## 4.6 Opérations / SRE / support

### Questions principales

- Qu’est-ce qui se passe ?
- Est-ce local ou propagé ?
- Qu’est-ce qui a changé ?
- Quelles situations similaires ont déjà existé ?
- Quelles applications sont impliquées ?

---

## 4.7 Risque / sécurité / conformité

### Questions principales

- Quelles modifications changent notre exposition ?
- Où existent des dépendances cachées ?
- Quelles capacités sont insuffisamment contrôlées ?
- Quelles décisions historiques ont créé un risque ?

---

## 4.8 Employés non techniques

Méridian doit également pouvoir exposer certaines expériences simples.

Exemples :

- comprendre un processus ;
- signaler une friction ;
- explorer l’origine d’une règle ;
- demander à Flore pourquoi une procédure existe ;
- contribuer à une investigation.

---

# 5. Jobs-to-be-Done

Les principaux Jobs-to-be-Done de Méridian sont :

## JTBD-01 — Comprendre

> Quand je dois comprendre une partie complexe de l’entreprise, je veux disposer d’une représentation actuelle, sourcée et explicable afin de ne pas dépendre uniquement de connaissances dispersées.

---

## JTBD-02 — Détecter

> Quand quelque chose commence à changer ou à se dégrader, je veux que Méridian le fasse émerger avant qu’il devienne un problème majeur.

---

## JTBD-03 — Identifier une opportunité

> Quand l’entreprise fonctionne sans incident apparent, je veux tout de même identifier les endroits où elle pourrait être simplifiée ou améliorée.

---

## JTBD-04 — Investiguer

> Quand une situation mérite une analyse, je veux que Méridian rassemble les preuves, mobilise les expertises et structure l’investigation.

---

## JTBD-05 — Décider

> Quand plusieurs options existent, je veux comprendre leurs impacts, risques et dépendances afin de prendre une décision éclairée.

---

## JTBD-06 — Vérifier

> Après une décision, je veux savoir si l’amélioration attendue s’est réellement produite.

---

## JTBD-07 — Apprendre

> Quand une situation ressemble à quelque chose que l’entreprise a déjà vécu, je veux bénéficier immédiatement de l’expérience historique.

---

# 6. Modèle mental du produit

Le produit repose sur quatre couches conceptuelles.

```text
┌──────────────────────────────────────────────────────────────┐
│  EXPLOITATION                                                │
│  Opportunités · Risques · Investigations · Décisions        │
│  Initiatives · Résultats · Apprentissage                    │
├──────────────────────────────────────────────────────────────┤
│  INTELLIGENCE                                                │
│  Experts · Maturation · Raisonnement · Contradiction        │
│  Scénarios · Hypothèses · Synthèses                         │
├──────────────────────────────────────────────────────────────┤
│  CONNAISSANCE VIVANTE                                       │
│  Jumeaux · Claims · Entités · Relations · Historique        │
├──────────────────────────────────────────────────────────────┤
│  SOURCES                                                     │
│  Code · DB · Jira · Confluence · ServiceNow · CMDB          │
│  Datadog · Splunk · CRM · Processus · Documents · etc.      │
└──────────────────────────────────────────────────────────────┘
```

Le produit visible doit privilégier la couche **Exploitation**.

Les couches inférieures doivent rester accessibles lorsque l’utilisateur veut comprendre ou vérifier.

---

# 7. Architecture de l’expérience

Le produit est organisé autour des surfaces suivantes :

1. **Aujourd’hui**
2. **Atlas**
3. **Flore**
4. **Opportunités**
5. **Investigations**
6. **Radar / Signaux**
7. **Jumeaux**
8. **Domaines**
9. **Sources**
10. **Feed**
11. **Décisions / Initiatives**
12. **Administration**

---

# 8. Surface « Aujourd’hui »

## 8.1 Rôle

« Aujourd’hui » est la page d’accueil opérationnelle de Méridian.

Elle répond à :

> **Qu’est-ce qui mérite mon attention maintenant ?**

Elle ne doit pas devenir un dashboard de métriques.

Elle doit présenter des **éléments interprétés**.

---

## 8.2 Structure proposée

```text
┌─────────────────────────────────────────────────────────────┐
│ MÉRIDIAN                                      [Flore] [Moi] │
├─────────────────────────────────────────────────────────────┤
│ Aujourd’hui                                                  │
│                                                             │
│  Ce qui émerge                                              │
│  ┌────────────────┐ ┌────────────────┐ ┌────────────────┐  │
│  │ Opportunité    │ │ Situation      │ │ Risque         │  │
│  │ Rationalisation│ │ Paiements      │ │ Résilience     │  │
│  └────────────────┘ └────────────────┘ └────────────────┘  │
│                                                             │
│  À décider                                                  │
│  • Investigation X prête pour arbitrage                    │
│                                                             │
│  En amélioration                                            │
│  • Initiative Y : impact réel disponible                   │
│                                                             │
│  Pour vous                                                  │
│  • 2 sujets liés à votre domaine                           │
└─────────────────────────────────────────────────────────────┘
```

---

## 8.3 Sections possibles

### Ce qui émerge

Affiche :

- nouvelles expressions ;
- opportunités ;
- risques ;
- situations candidates importantes.

### Ce qui demande une décision

Affiche :

- investigations prêtes ;
- scénarios à arbitrer ;
- recommandations nécessitant une validation.

### Ce qui évolue

Affiche :

- changements importants ;
- découvertes structurelles ;
- nouveaux liens entre jumeaux ;
- modifications de domaine.

### Ce qui apprend

Affiche :

- initiatives dont les résultats arrivent ;
- écarts entre résultats attendus et observés ;
- apprentissages nouveaux.

### Pour moi / Mon équipe

Le contenu est filtré selon :

- responsabilités ;
- domaines ;
- applications ;
- investigations suivies ;
- rôles.

---

## 8.4 Action universelle

Chaque carte significative doit proposer :

> **Pourquoi Méridian pense cela**

Cette action ouvre la chaîne de preuve.

---

# 9. Atlas

## 9.1 Rôle

Atlas est la géographie de Méridian.

Il permet de répondre à :

- où se trouve le phénomène ;
- quelles entités sont touchées ;
- quelles relations sont impliquées ;
- quel domaine est concerné ;
- où se propage une situation.

---

## 9.2 Principes UX

Navigation inspirée d’une carte :

- zoom ;
- pan ;
- focus ;
- lasso ;
- multi-sélection ;
- retour au contexte ;
- mini-map éventuelle ;
- couches activables.

---

## 9.3 Éléments

### Jumeaux

Représentés comme entités intelligentes.

### Domaines

Représentés par des zones ou membranes.

### Relations

Priorité aux relations compréhensibles.

Éviter le « spaghetti graph ».

### Phénomènes

Les phénomènes doivent pouvoir apparaître comme une couche.

Exemple :

- zone de chaleur ;
- halo ;
- propagation ;
- radar ;
- pulsation.

---

## 9.4 Couches Atlas

Exemples :

- structure connue ;
- structure découverte ;
- incidents ;
- changements ;
- opportunités ;
- risques ;
- processus ;
- parcours client ;
- flux de données ;
- dépendances critiques.

---

## 9.5 Vue découverte vs vue officielle

Atlas doit pouvoir confronter :

### Vue déclarée

- BCM ;
- domaines officiels ;
- CMDB ;
- architecture connue.

### Vue découverte

- relations observées ;
- dépendances inférées ;
- regroupements émergents ;
- comportements réels.

La différence devient elle-même exploitable.

---

# 10. Flore

## 10.1 Positionnement

Flore est l’interface conversationnelle d’exploitation de Méridian.

Flore n’est pas Méridian.

Flore n’est pas le Mesh.

Flore n’est pas un jumeau.

Elle permet à l’humain de dialoguer avec l’intelligence accumulée.

---

## 10.2 Flore doit être contextuelle

Le contexte dépend de la surface.

### Depuis Atlas

> « Explique-moi ce domaine. »

### Depuis un jumeau

> « Quelles nouvelles fonctionnalités ont été ajoutées sur les trois dernières années ? »

### Depuis une opportunité

> « Quelles preuves supportent cette opportunité ? »

### Depuis une investigation

> « Quelle hypothèse est actuellement la plus forte ? »

---

## 10.3 Actions de Flore

Flore peut :

- expliquer ;
- rechercher ;
- synthétiser ;
- comparer ;
- interroger un jumeau ;
- traverser plusieurs jumeaux ;
- proposer une investigation ;
- lancer une investigation ;
- demander l’intervention d’une expertise ;
- générer un rapport ;
- explorer l’historique ;
- préparer des scénarios ;
- expliquer une contradiction.

---

## 10.4 Flore ne doit pas cacher la preuve

Toute réponse importante doit pouvoir exposer :

- les sources ;
- les Claims ;
- les jumeaux impliqués ;
- les experts consultés ;
- le niveau de confiance ;
- les incertitudes.

---

# 11. Radar et Signaux

## 11.1 Rôle

Le Radar est l’espace où Méridian expose les phénomènes en cours de détection ou de qualification.

Il ne doit pas devenir une boîte d’alertes.

---

## 11.2 Pipeline de qualification

Le pipeline historique est conservé :

> **Signal → Situation candidate → Qualification → Investigation**

Mais il est enrichi.

Le modèle complet devient :

```text
Signal
   ↓
Situation candidate
   ↓
Qualification / Maturation
   ↓
Expression
   ├──→ Opportunité
   ├──→ Risque
   ├──→ Investigation
   └──→ Observation conservée
```

Une opportunité ou un risque peut ensuite déclencher une investigation.

---

## 11.3 Signal

Un Signal peut provenir :

- du monitoring ;
- d’un changement de code ;
- d’un ticket ;
- d’une base de données ;
- d’une modification de configuration ;
- d’un événement métier ;
- d’un comportement client ;
- d’un feedback employé ;
- d’un agent ;
- d’un humain.

---

## 11.4 Situation candidate

Plusieurs signaux peuvent être regroupés.

Méridian propose :

- une hypothèse ;
- les éléments reliés ;
- la proximité temporelle ;
- les entités concernées ;
- un niveau de confiance.

---

# 12. Expression

## 12.1 Définition

Une Expression est une formulation interprétée d’un phénomène suffisamment mature pour être exposé à l’utilisateur.

---

## 12.2 Contenu minimal

```text
Expression
├── Titre
├── Résumé
├── Type
├── Importance
├── Confiance
├── Maturité
├── Faits observés
├── Hypothèses
├── Claims
├── Contradictions
├── Jumeaux concernés
├── Domaines concernés
├── Population impactée
├── Timeline
└── Actions proposées
```

---

## 12.3 Types

- opportunité ;
- risque ;
- anomalie ;
- dérive ;
- contradiction ;
- changement émergent ;
- simplification ;
- duplication ;
- évolution comportementale.

---

# 13. Opportunités

## 13.1 Définition

Une Opportunité est une Expression indiquant qu’une amélioration potentielle peut créer de la valeur.

---

## 13.2 Cycle de vie

```text
Détectée
   ↓
En maturation
   ↓
Qualifiée
   ↓
À investiguer
   ↓
Scénarios disponibles
   ↓
Décidée
   ↓
Initiative
   ↓
Résultat
   ↓
Apprentissage
```

Une opportunité peut également devenir :

- rejetée ;
- insuffisamment prouvée ;
- fusionnée avec une autre ;
- mise en veille.

---

## 13.3 Carte Opportunité

Doit afficher :

- titre ;
- pourquoi maintenant ;
- valeur potentielle ;
- confiance ;
- domaines concernés ;
- preuves principales ;
- conséquences probables ;
- prochaine action.

---

## 13.4 Familles d’opportunités

- automatisation ;
- simplification ;
- modernisation ;
- réduction de duplication ;
- réduction de coût ;
- amélioration client ;
- amélioration employé ;
- rationalisation applicative ;
- optimisation processus ;
- optimisation données ;
- consolidation.

---

# 14. Risques

Un Risque possède une structure proche de l’Opportunité.

Différences principales :

- probabilité ;
- sévérité ;
- exposition ;
- propagation ;
- délai probable ;
- contrôles existants ;
- réversibilité.

Un risque peut évoluer en investigation sans attendre qu’un incident survienne.

---

# 15. Investigations

## 15.1 Définition

Une Investigation est un espace structuré de raisonnement collectif visant à comprendre suffisamment une situation pour permettre une décision.

---

## 15.2 Une investigation n’est pas un ticket

Elle contient :

- contexte ;
- problème ;
- preuves ;
- timeline ;
- hypothèses ;
- experts ;
- contradictions ;
- sous-questions ;
- découvertes ;
- scénarios ;
- décisions.

---

## 15.3 Structure UI

```text
Investigation : Dégradation parcours renouvellement
──────────────────────────────────────────────────────────────
Résumé               Confiance : Élevée
Statut : En analyse

[Timeline] [Hypothèses] [Preuves] [Experts] [Scénarios]

Hypothèse principale
→ Nouvelle règle métier provoque un appel supplémentaire...

Hypothèses concurrentes
→ Saturation service X
→ Qualité de données

Experts actifs
Performance · Hypothèque · Processus · Client

Flore
> Quelle hypothèse veux-tu approfondir ?
```

---

## 15.4 États

- ouverte ;
- cadrage ;
- collecte ;
- analyse ;
- contradiction ;
- synthèse ;
- scénarios ;
- prête à décider ;
- décision prise ;
- fermée ;
- réouverte.

---

## 15.5 Hypothèses

Chaque hypothèse possède :

- formulation ;
- origine ;
- arguments pour ;
- arguments contre ;
- preuves ;
- niveau de confiance ;
- expert responsable ;
- état.

États :

- ouverte ;
- renforcée ;
- affaiblie ;
- rejetée ;
- confirmée.

---

# 16. Experts spécialisés

## 16.1 Concept

Un expert est une capacité spécialisée de raisonnement.

Il ne doit pas être réduit à un prompt contenant :

> « Tu es un expert en architecture. »

---

## 16.2 Contrat d’expertise

Chaque expert définit :

```text
Expert
├── Domaine
├── Compétences
├── Questions supportées
├── Sources autorisées
├── Outils
├── Méthodes
├── Critères de preuve
├── Limites
├── Mémoire spécialisée
├── Signaux reconnus
└── Types de contribution
```

---

## 16.3 Experts TI

Exemples :

- architecture ;
- source code ;
- bases de données ;
- données ;
- performance ;
- résilience ;
- sécurité ;
- cloud ;
- legacy ;
- observabilité ;
- qualité ;
- modernisation.

---

## 16.4 Experts métier

Exemples banque :

- paiements ;
- crédit ;
- hypothèque ;
- fraude ;
- risque ;
- conformité ;
- finance ;
- opérations ;
- produits.

---

## 16.5 Experts transverses

- processus ;
- parcours client ;
- expérience employé ;
- transformation ;
- stratégie ;
- finance ;
- réglementation.

---

# 17. Orchestration des experts

## 17.1 Principe

Méridian mobilise l’expertise en fonction de la situation.

Il ne déclenche pas systématiquement tous les experts.

---

## 17.2 Exemple d’escalade

```text
Signal performance
      ↓
Expert Performance
      ↓
Découverte d’une règle métier récente
      ↓
+ Expert Métier
      ↓
Reprises manuelles identifiées
      ↓
+ Expert Processus
+ Expert Expérience Employé
      ↓
Abandon client détecté
      ↓
+ Expert Parcours Client
      ↓
Transformation envisagée
      ↓
+ Expert Architecture
+ Expert Finance
+ Expert Transformation
```

---

## 17.3 Contributions possibles

Un expert peut produire :

- Claim ;
- objection ;
- question ;
- hypothèse ;
- preuve ;
- contre-preuve ;
- scénario ;
- risque ;
- recommandation.

---

# 18. Le mécanisme de contradiction

La contradiction doit être un mécanisme de première classe.

Méridian ne doit pas chercher uniquement à confirmer une conclusion.

Il doit pouvoir demander :

> « Quelle preuve pourrait invalider cette hypothèse ? »

---

## 18.1 Sources de contradiction

- autre jumeau ;
- autre source ;
- expert spécialisé ;
- historique ;
- humain ;
- modèle métier officiel.

---

## 18.2 UI

Une conclusion peut afficher :

```text
Confiance : 78 %

POUR
✓ 5 preuves cohérentes
✓ 3 sources indépendantes

CONTRE
⚠ 1 métrique ne suit pas la tendance
⚠ CMDB déclare une dépendance différente

INCONNU
? impact sur un segment client non mesuré
```

---

# 19. Jumeaux applicatifs

## 19.1 Rôle produit

Le jumeau applicatif est une intelligence locale sur une application.

Il connaît progressivement :

- rôle ;
- capacités ;
- fonctionnalités ;
- règles métier ;
- données ;
- API ;
- dépendances ;
- événements ;
- historique ;
- incidents ;
- changements ;
- équipes ;
- voisins.

---

## 19.2 Page Jumeau

Sections proposées :

### Résumé vivant

> Ce que Méridian comprend actuellement de l’application.

### Fonction

- rôle métier ;
- capacités principales ;
- utilisateurs ;
- criticité.

### Connaissances

- Claims ;
- règles ;
- flux ;
- données.

### Relations

- consommateurs ;
- fournisseurs ;
- dépendances ;
- voisins.

### Histoire

- changements ;
- fonctionnalités ajoutées ;
- migrations ;
- incidents.

### Santé cognitive

- couverture des sources ;
- qualité ;
- confiance ;
- contradictions ;
- zones inconnues.

### Activité récente

- nouvelles découvertes ;
- Claims modifiés ;
- relations ajoutées.

---

# 20. Naissance d’un jumeau

## 20.1 Entrée

L’utilisateur crée un jumeau via un wizard.

---

## 20.2 Étapes

```text
1. Identifier l’application
2. Connecter les sources
3. Définir les accès
4. Lancer la découverte initiale
5. Construire la première représentation
6. Générer les Claims initiaux
7. Identifier les voisins potentiels
8. Produire le résumé initial
9. Exposer les zones inconnues
```

---

## 20.3 Expérience

La naissance doit montrer progressivement :

- ce qui a été découvert ;
- les sources analysées ;
- les relations trouvées ;
- les incertitudes ;
- les premières hypothèses ;
- la confiance.

Le produit ne doit pas donner l’impression qu’un jumeau « sait tout » immédiatement.

---

# 21. Domaines

## 21.1 Rôle

Les domaines sont des regroupements fonctionnels ou organisationnels.

Ils peuvent provenir de :

- BCM ;
- architecture d’entreprise ;
- organisation ;
- découverte automatique ;
- classification agentique.

---

## 21.2 Double vérité

Méridian doit pouvoir distinguer :

- domaine déclaré ;
- domaine observé ;
- domaine proposé.

---

## 21.3 Émergence de domaines

Un agent architecte de domaine peut proposer :

> « Ces huit applications semblent former une capacité cohérente autour de l’admissibilité crédit. »

Le système ne remplace pas automatiquement le BCM.

Il expose la différence.

---

# 22. Sources

## 22.1 Catalogue

Le wizard de source doit proposer un catalogue extensible :

- GitHub ;
- GitLab ;
- Bitbucket ;
- Jira ;
- Confluence ;
- ServiceNow ;
- Datadog ;
- Splunk ;
- CMDB ;
- PostgreSQL ;
- Oracle ;
- SQL Server ;
- Kafka ;
- API ;
- stockage documentaire ;
- CRM ;
- etc.

---

## 22.2 Chaque source possède

- statut ;
- propriétaire ;
- permissions ;
- dernière synchronisation ;
- fréquence ;
- couverture ;
- qualité ;
- erreurs ;
- Claims produits.

---

## 22.3 Synchronisation

Méridian doit distinguer :

- découverte initiale ;
- synchronisation continue ;
- événements ;
- retrait ;
- modification de permissions.

---

# 23. Feed

Le Feed montre l’évolution de la connaissance.

Exemples :

> Une nouvelle dépendance a été découverte entre TBT et Service Paiement.

> Le niveau de confiance d’un Claim est passé de 54 % à 81 %.

> Une contradiction a été résolue.

> Une nouvelle opportunité a émergé.

> L’initiative X montre un résultat différent de l’hypothèse initiale.

Le Feed est chronologique.

Il n’est pas la page principale.

---

# 24. Décisions

## 24.1 Pourquoi un objet Décision

Une entreprise perd souvent la raison historique d’une décision.

Méridian doit maintenir :

- ce qui a été décidé ;
- quand ;
- par qui ;
- sur quelles preuves ;
- quelles alternatives ;
- quelles hypothèses ;
- quels risques acceptés ;
- quels résultats attendus.

---

## 24.2 Structure

```text
Décision
├── Sujet
├── Investigation source
├── Scénario retenu
├── Scénarios rejetés
├── Raisons
├── Décideurs
├── Date
├── Hypothèses
├── Impacts attendus
├── Mesures de succès
└── Suivi
```

---

# 25. Initiatives et amélioration

Une Décision peut créer une Initiative.

L’initiative connecte :

- décision ;
- actions ;
- responsables ;
- systèmes concernés ;
- indicateurs ;
- résultats attendus ;
- période d’observation.

---

## 25.1 Écart attendu / observé

Méridian doit explicitement comparer :

| Dimension | Attendu | Observé |
|---|---:|---:|
| Délai | -15 % | -11 % |
| Erreurs | -5 % | -7 % |
| Abandon | -8 % | -5 % |
| Travail manuel | 0 % | +4 % |

Un effet secondaire peut devenir un nouveau Signal.

---

# 26. Mémoire de transformation

La mémoire de transformation relie :

```text
Situation
   ↓
Investigation
   ↓
Hypothèses
   ↓
Décision
   ↓
Initiative
   ↓
Résultat
   ↓
Apprentissage
```

Elle permet de répondre :

> Avons-nous déjà vu cela ?

> Qu’avions-nous essayé ?

> Qu’est-ce qui avait fonctionné ?

> Quels effets secondaires étaient apparus ?

> Cette décision ressemble-t-elle à une décision précédente ?

---

# 27. Recherche globale

La recherche doit fonctionner sur :

- jumeaux ;
- applications ;
- Claims ;
- sources ;
- personnes autorisées ;
- domaines ;
- opportunités ;
- risques ;
- investigations ;
- décisions ;
- initiatives ;
- rapports.

---

## 27.1 Recherche sémantique

Exemple :

> « application qui calcule l’admissibilité des prêts »

même si aucun objet ne porte exactement ce nom.

---

# 28. Temporalité

Méridian doit être profondément temporel.

Chaque connaissance importante doit pouvoir répondre :

- quand a-t-elle été découverte ?
- était-elle vraie auparavant ?
- quand a-t-elle changé ?
- quelle était la vision hier ?
- quelle était la vision avant le dernier déploiement ?

---

## 28.1 Sélecteur temporel

Exemples :

- Maintenant
- Aujourd’hui
- Hier
- -2 jours
- Semaine dernière
- Date personnalisée

---

## 28.2 Time travel

À terme :

> **Afficher Atlas tel qu’il était le 15 avril.**

Très utile pour :

- incidents ;
- migrations ;
- transformations ;
- audits.

---

# 29. Portées

Méridian doit proposer plusieurs portées.

### Perso

Ce qui concerne l’utilisateur.

### Mon équipe

Applications, domaines et initiatives de l’équipe.

### Mesh global

Vue transversale selon les droits.

---

# 30. Notifications

Méridian ne doit pas spammer.

Notifications uniquement lorsque :

- un élément atteint un niveau de maturité ;
- une décision est attendue ;
- une investigation demande une contribution ;
- un risque change fortement ;
- une initiative produit un résultat significatif ;
- une contradiction critique apparaît.

---

# 31. Collaboration humaine

Une investigation doit accepter :

- commentaires ;
- mentions ;
- questions ;
- annotations ;
- validation d’un Claim ;
- contestation ;
- apport documentaire ;
- décision.

Une contribution humaine devient une source avec provenance.

---

# 32. Confiance

## 32.1 Score de confiance

Le score ne doit pas être mystérieux.

Il peut être calculé à partir de :

- indépendance des sources ;
- fraîcheur ;
- qualité ;
- cohérence ;
- répétition ;
- contradiction ;
- validation humaine ;
- fiabilité historique.

---

## 32.2 Maturité ≠ confiance

Une situation peut être très mature mais rester incertaine.

Il faut distinguer :

- maturité de l’analyse ;
- confiance dans la conclusion.

---

# 33. Explicabilité

L’utilisateur doit pouvoir dérouler :

```text
Conclusion
↓
Hypothèse
↓
Claims
↓
Faits
↓
Sources
```

C’est un mécanisme produit essentiel.

---

# 34. Gouvernance

Méridian doit supporter :

- RBAC ;
- ABAC si nécessaire ;
- visibilité par domaine ;
- permissions de source ;
- données sensibles ;
- traçabilité ;
- journaux d’accès ;
- provenance ;
- règles de rétention.

---

# 35. Administration

L’administration couvre :

- utilisateurs ;
- équipes ;
- rôles ;
- domaines ;
- sources ;
- experts ;
- politiques ;
- permissions ;
- connecteurs ;
- modèles ;
- coûts ;
- quotas ;
- observabilité de la plateforme.

---

# 36. Cas d’usage 1 — Historique fonctionnel TBT

Question :

> « Quelles sont les fonctionnalités ajoutées à TBT au cours des trois dernières années ? Je veux un rapport détaillé avec les références dans le code. »

Flux :

```text
Flore
↓
Résolution de l’intention
↓
Jumeau TBT
↓
Historique Git + Jira + documentation
↓
Expert Code + Expert Fonctionnel
↓
Regroupement changements → fonctionnalités
↓
Validation croisée
↓
Rapport
↓
Références code + commits + preuves
```

Le résultat doit distinguer :

- fonctionnalité certaine ;
- fonctionnalité probable ;
- changement purement technique.

---

# 37. Cas d’usage 2 — Opportunité de rationalisation

Méridian découvre :

- application A coûte cher ;
- plusieurs fonctions ont migré ;
- peu de consommateurs directs ;
- capacités équivalentes dans B et C.

Méridian produit une Expression :

> « Une opportunité de rationalisation semble exister autour de l’application A. »

Puis :

- expert architecture ;
- expert finance ;
- expert métier ;
- expert risque.

Une investigation peut déterminer :

- ce qui peut être retiré ;
- ce qui bloque ;
- coût ;
- risques ;
- séquence de migration.

---

# 38. Cas d’usage 3 — Friction employé / client

Découverte :

- reprises manuelles ;
- délais ;
- tickets ;
- plaintes ;
- changements récents.

Maturation :

- corrélation ;
- Claims ;
- contre-hypothèses.

Expression :

> « Une friction progressive semble apparaître dans le parcours. »

Investigation :

- performance ;
- processus ;
- métier ;
- employé ;
- client.

Décision :

- modification du processus.

Mesure :

- résultat réel.

Apprentissage :

- effet secondaire détecté.

---

# 39. Cas d’usage 4 — Changement et propagation

Un changement est effectué dans une application.

Méridian peut répondre avant déploiement :

> « Quelles parties du SI pourraient être impactées ? »

Il utilise :

- dépendances ;
- historique ;
- relations ;
- incidents antérieurs ;
- Claims ;
- flux.

Après déploiement :

Méridian observe si les effets attendus apparaissent.

---

# 40. Parcours UX principal

Le parcours principal d’un utilisateur ne doit pas commencer obligatoirement par Atlas.

Exemple :

```text
Aujourd’hui
   ↓
Expression
   ↓
Pourquoi Méridian pense cela ?
   ↓
Preuves / Atlas / Timeline
   ↓
Demander à Flore
   ↓
Créer investigation
   ↓
Experts
   ↓
Hypothèses
   ↓
Scénarios
   ↓
Décision
   ↓
Initiative
   ↓
Résultat
   ↓
Apprentissage
```

---

# 41. Navigation globale

Proposition :

```text
[MÉRIDIAN]

Aujourd’hui
Atlas
Opportunités
Investigations
Radar

──────────────
Jumeaux
Domaines
Sources

──────────────
Décisions
Feed
Administration

[Flore]
```

Le menu peut rester compact et pliable.

---

# 42. États de chargement et traitements longs

Méridian exécute parfois des traitements agentiques longs.

L’UX ne doit jamais afficher simplement :

> « Analyse en cours… »

Elle doit montrer :

```text
Investigation en cours

✓ Sources identifiées
✓ Historique analysé
✓ 14 Claims rapprochés
● Expert processus en analyse
○ Contradiction inter-domaines
○ Synthèse

Découvertes déjà disponibles :
• ...
• ...
```

Le système doit publier les résultats partiels lorsqu’ils deviennent fiables.

---

# 43. Rapports

Tout objet majeur peut produire un rapport.

Formats :

- synthèse direction ;
- rapport détaillé ;
- rapport technique ;
- rapport de décision ;
- chronologie ;
- preuves ;
- export.

Un rapport n’est qu’une représentation exportable de connaissances déjà présentes dans Méridian.

---

# 44. Métriques produit

Ne pas mesurer principalement :

- nombre de jumeaux ;
- nombre de Claims ;
- nombre de sources.

Mesurer plutôt :

### Compréhension

- couverture ;
- fraîcheur ;
- confiance ;
- contradictions résolues.

### Exploitation

- opportunités qualifiées ;
- investigations utiles ;
- temps vers compréhension ;
- temps vers décision.

### Impact

- valeur créée ;
- risques évités ;
- travail manuel réduit ;
- coûts supprimés ;
- améliorations observées.

### Apprentissage

- réutilisation d’investigations précédentes ;
- amélioration des recommandations ;
- réduction de répétition.

---

# 45. Exigences fonctionnelles minimales

## FR-01

Créer un jumeau à partir de plusieurs sources.

## FR-02

Synchroniser les sources dans le temps.

## FR-03

Créer, versionner et relier des Claims.

## FR-04

Afficher provenance et preuve.

## FR-05

Détecter des contradictions.

## FR-06

Relier les jumeaux.

## FR-07

Afficher Atlas.

## FR-08

Interroger un jumeau avec Flore.

## FR-09

Interroger plusieurs jumeaux.

## FR-10

Créer un Signal.

## FR-11

Regrouper des Signaux en Situation candidate.

## FR-12

Qualifier et maturer une Situation.

## FR-13

Créer une Expression.

## FR-14

Créer une Opportunité ou un Risque.

## FR-15

Créer une Investigation.

## FR-16

Gérer des Hypothèses.

## FR-17

Mobiliser des Experts.

## FR-18

Associer preuves et contre-preuves.

## FR-19

Créer plusieurs scénarios.

## FR-20

Enregistrer une Décision.

## FR-21

Créer une Initiative.

## FR-22

Définir les résultats attendus.

## FR-23

Observer les résultats réels.

## FR-24

Créer un Apprentissage.

## FR-25

Relier l’Apprentissage aux futures situations.

---

# 46. Non-objectifs initiaux

Méridian ne doit pas initialement chercher à :

- exécuter automatiquement des transformations critiques ;
- remplacer tous les outils SI ;
- devenir le référentiel maître universel ;
- prendre des décisions autonomes à fort impact ;
- ingérer toutes les sources possibles dès le départ ;
- construire tous les types de jumeaux simultanément.

La priorité est la qualité de la boucle d’exploitation.

---

# 47. MVP produit recommandé

Le MVP doit démontrer la boucle complète sur une portée réduite.

## Fondation

- quelques jumeaux ;
- code ;
- documentation ;
- monitoring ;
- Claims ;
- relations ;
- Atlas.

## Exploitation

- Signal ;
- Situation ;
- Expression ;
- Opportunité ;
- Investigation ;
- Hypothèses ;
- Experts ;
- Décision ;
- Résultat.

## Interfaces

- Aujourd’hui ;
- Atlas ;
- Flore ;
- Investigation ;
- Jumeau.

Le MVP est réussi si l’utilisateur peut suivre une situation de bout en bout :

> **découverte → compréhension → investigation → décision → observation**

---

# 48. Évolution produit

## Génération 1 — Comprendre

- jumeaux ;
- Claims ;
- sources ;
- Atlas ;
- Flore ;
- historique ;
- relations.

## Génération 2 — Exploiter

- maturation ;
- opportunités ;
- risques ;
- experts ;
- investigations ;
- scénarios ;
- décisions.

## Génération 3 — Améliorer

- résultats ;
- apprentissage ;
- mémoire de transformation ;
- détection de patterns ;
- recommandations basées sur l’expérience.

---

# 49. Question directrice pour toute fonctionnalité

Avant d’ajouter une fonctionnalité, poser :

> **Cette fonctionnalité aide-t-elle Méridian à découvrir, comprendre, décider ou apprendre ?**

Si la réponse est non, sa place dans le produit doit être remise en question.

---

# 50. North Star

La North Star de Méridian n’est pas :

> « Construire la meilleure carte du SI. »

Elle est :

> **Réduire la distance entre ce qui se passe réellement dans l’entreprise et sa capacité à le comprendre puis à agir correctement.**

---

# 51. Vision d’expérience finale

L’expérience idéale peut se résumer ainsi.

L’utilisateur arrive dans Méridian.

Il ne voit pas un océan de données.

Il voit ce qui compte.

Méridian lui indique :

> « Voici ce qui émerge. »

L’utilisateur demande :

> « Pourquoi ? »

Méridian expose les preuves.

L’utilisateur demande :

> « Qu’est-ce que cela signifie pour nous ? »

Les expertises appropriées sont mobilisées.

L’utilisateur demande :

> « Que pouvons-nous faire ? »

Méridian construit plusieurs scénarios.

L’entreprise décide.

Méridian continue d’observer.

Quelques semaines plus tard, il revient :

> « Voici ce qui s’est réellement produit. »

Et cette expérience devient une nouvelle partie de la mémoire de l’entreprise.

C’est cette boucle qui fait de Méridian un produit vivant.

---

# 52. Conclusion

Le réseau de jumeaux, les Claims, les sources et Atlas constituent le système de compréhension de Méridian.

Le Product Blueprint déplace volontairement le centre de gravité vers l’exploitation.

Le produit doit être conçu autour de ce qui arrive **après** la découverte :

- maturation ;
- expression ;
- opportunité ;
- investigation ;
- contradiction ;
- scénarios ;
- décision ;
- amélioration ;
- apprentissage.

Méridian devient ainsi un environnement où l’entreprise ne se contente plus de stocker sa connaissance.

Elle peut l’exploiter continuellement.

> **Découvrir ce qui existe.  
> Comprendre ce qui émerge.  
> Décider ce qui doit changer.  
> Mesurer ce qui s’est réellement passé.  
> Apprendre pour la prochaine fois.**
