# MÉRIDIAN — Spécification d’implémentation de l’expérience kiosque Polaris

**Version :** 1.0 — 18 septembre 2026  
**Destinataire :** développeur ou IA de développement travaillant dans le dépôt Méridian.  
**Dépôt :** Eloekamaje/meridian-mesh  
**Branche cible :** `branche-ui-v3`  
**Référence technique vérifiée :** `379bb118e3eb0eace2d222b907e8ad842cdf53a2`, 18 septembre 2026.  
**Source fonctionnelle :** `MERIDIAN_OLYMPIADES_EXPERIENCE_KIOSQUE.md`, version documentaire 1.2, incluant les traites en succursale et MD2.  
**Nature du livrable :** spécification de réalisation. Aucun changement applicatif n’est livré avec ce document.

> MÉRIDIAN — DÉCOUVRIR · COMPRENDRE · DÉCIDER  
> Un visiteur choisit un métier, suit une conversation avec Flore, voit le travail en cours, puis comprend une situation grâce aux résultats qui prennent forme dans l’application.

## Table des matières

1. Contrat de réalisation
2. Ancrage dans le dépôt
3. Parcours général et écrans
4. Architecture de la démonstration
5. Contrats de données
6. Moteur de lecture et règles temporelles
7. Atlas situationnel : contrat de rendu
8. Données communes à préparer
9. Traduction des cinq scénarios en scènes et résultats
10. Exemple de définition d’une séquence
11. Fin, exploration et erreurs
12. Ordre de réalisation pour l’IA de développement
13. Critères de validation
14. Décisions ouvertes et valeurs de départ
15. Sources et limites
A. Dialogues complets et effets attendus

## 1. Contrat de réalisation

Construire dans l’application existante un mode kiosque de démonstration, accessible par une entrée dédiée. Il propose cinq parcours Polaris et orchestre les composants réels de Méridian avec des données préparées.

Le livrable attendu à l’issue de l’implémentation est une expérience utilisable au kiosque : accueil, cinq profils, conversations complètes, activité visible de Flore, Atlas situationnel, preuves consultables, résultats dans les Travaux et l’Investigation prévue, contrôles de lecture et retour propre à l’accueil.

Ce document précise les comportements et les contrats à respecter. Les noms de nouveaux modules sont proposés ; l’IA peut adapter leur organisation à celle du dépôt. Les décisions fonctionnelles, l’ordre des découvertes et les critères de validation restent obligatoires.

### 1.1 Enjeu de l’exposition

Le public comprend des employés de métiers différents et un jury. La démonstration doit rendre perceptible l’utilité de Méridian en deux à trois minutes par profil, sur un laptop, une tablette ou un moniteur de 24–32 pouces.

Polaris poursuit quatre objectifs : améliorer l’expérience client, simplifier les processus, réduire les frictions opérationnelles et accélérer la livraison. Les cinq parcours éclairent ces objectifs depuis des responsabilités différentes.

Le scénario de direction vient d’une situation concrète : une gestionnaire réunit architectes de domaine, architectes de solution, concepteurs et tech leads autour de pistes d’initiatives. L’information reste difficile à rassembler et les questions demeurent difficiles à traiter ensemble. La valeur montrée est une compréhension commune permettant d’avancer dans la réunion.

### 1.2 Décisions obligatoires

| ID | Exigence |
|---|---|
| EXP-01 | L’accueil affiche les cinq profils. Le clic conduit d’abord à Flore seule. |
| EXP-02 | La conversation est une démonstration entre Flore et un personnage identifié par son rôle. Ne pas attribuer les répliques au visiteur. |
| EXP-03 | Gestionnaire et architecte initient leur demande. Flore initie les parcours ligne d’affaires, support TI et développeur. |
| EXP-04 | Le traitement visible précède la matérialisation du résultat. Aucun pilotage de l’Atlas mot par mot. |
| EXP-05 | L’Atlas adapte sa lecture à la question : initiatives, parcours, dépendances, options ou situation d’incident. |
| EXP-06 | Flore explique. Les résultats structurés apparaissent dans les espaces appropriés. |
| EXP-07 | Chaque parcours possède une découverte forte, une preuve accessible et une suite concrète. |
| EXP-08 | La conversation reste unique lorsqu’elle passe de Flore au Travail. |
| EXP-09 | Les données et résultats sont préparés. Le parcours principal fonctionne sans appel LLM et sans disponibilité du backend métier. |
| EXP-10 | Les actions de démonstration ne modifient pas les données réelles. |
| EXP-11 | Pause, reprise, échange suivant, relecture de la découverte et changement de profil fonctionnent sans doublons. |
| EXP-12 | Les fonctions produit restent utilisables hors kiosque. La route produit initiale conserve son comportement. |

### 1.3 Périmètre de la première version

**À réaliser :** les cinq parcours complets, la lecture automatique, le mode pas à pas, l’exploration bornée des résultats et la comparaison des options MD2.

**Extensions ultérieures :** questions libres à un LLM, collecte de retours visiteurs, voix, synchronisation multi-écran, restauration d’une session après rechargement et variantes de dialogue. Elles ne conditionnent pas la première version.

La variante « Comment procéderiez-vous aujourd’hui ? » avec cases à cocher n’est pas dans le parcours principal. Ne pas la rendre obligatoire.

## 2. Ancrage dans le dépôt

### 2.1 Portée de la vérification

La vérification porte sur le code frontend et ses points d’intégration. Quatorze fichiers ont été lus et leurs contenus vérifiés au commit indiqué en tête. L’application n’a pas été exécutée ; cette lecture ne valide ni son rendu ni l’ensemble des contrats backend.

Le document conceptuel cite un commit du 3 septembre. Pour les détails techniques, cette spécification utilise la référence plus récente du 18 septembre. À l’implémentation, vérifier le checkout courant et lire les instructions du dépôt, puis adapter les points d’intégration qui auraient changé.

### 2.2 Existant observé et évolution attendue

Les chemins ci-dessous sont relatifs au dépôt.

| Fichier existant | Observation dans le code | Action d’implémentation attendue |
|---|---|---|
| `frontend/package.json` | React, React Router, React Flow, Framer Motion, Zod ; scripts via CRACO ; Yarn déclaré. | Réutiliser la pile et le gestionnaire du dépôt. Pas de migration de framework nécessaire. |
| `frontend/src/App.js` | `/` redirige vers `/atlas` ; providers globaux ; routes Travaux et Investigations. | Ajouter une branche de routes kiosque et isoler ses providers. |
| `frontend/src/components/Layout.jsx` | En-tête, zone centrale, Flore en colonne latérale, DemoTour ; contenu remonté au changement de pathname. | Ajouter les variantes d’affichage du kiosque ; conserver l’état de session au-dessus des pages remontées. |
| `frontend/src/components/FlorePanel.jsx` | Conversations locales par couples question/réponse ; appels `/aurora/demander` ; panneau masqué sur le détail d’un Travail. | Séparer présentation et source des messages ; autoriser une ouverture proactive sans question fictive. |
| `frontend/src/components/FloreActivite.jsx` | Étapes et temporisations autonomes ; attente minimale possible via `delaiMin`. | Ajouter un mode contrôlé par le moteur du kiosque. Une seule horloge pilote la séquence. |
| `frontend/src/lib/contexte.jsx` | Sélection, contexte Atlas, état de carte et `commanderCarte`. | Point d’appui pour le contexte partagé ; compléter par un adaptateur de scènes avec acquittement. |
| `frontend/src/pages/Atlas.jsx` | React Flow ; nœuds jumeau/région ; commandes parcours/relations/relation/domaine ; modes temporels. | Ajouter les projections situationnelles, les objets métier et les styles de proposition. |
| `frontend/src/lib/mesh.jsx` | Chargement réseau de `/mesh` et rechargement selon le périmètre. | Injecter la source locale du kiosque et éviter le chargement réel dans cette branche. |
| `frontend/src/lib/demo.jsx` | Chargement `/demo/actes` ; index d’acte et navigation simple. | Garder le parcours existant hors kiosque ; créer le moteur nécessaire aux conversations. |
| `frontend/src/components/DemoTour.jsx` | Navigation entre actes au changement d’index. | Ne pas faire fonctionner ce pilote en même temps que le moteur kiosque. |
| `frontend/src/pages/TravailDetail.jsx` | Charge `/cases/:cid`, situations et personas ; onglets Conversation/Aperçu. | Injecter un Travail local et conserver la conversation du scénario. |
| `frontend/src/components/case/OngletTravail.jsx` | Lit `cas.conversation` et envoie les nouveaux messages au backend. | Lire la projection du fil kiosque ; aucun envoi réel depuis la lecture scénarisée. |
| `frontend/src/components/case/OngletApercu.jsx` | Options dont « Recommandée par Flore », hypothèses, décisions, synthèses et mutations. | Alimenter avec les résultats locaux ; distinguer recommandation, sélection visuelle et décision. |
| `frontend/src/lib/api.js` | Instance Axios ; persona et périmètre tirés du localStorage. | Ne pas assimiler profil du personnage et identité produit ; empêcher les appels réels du kiosque. |

### 2.3 Incompatibilités précises à traiter

1. **Une réponse proactive n’a pas de question précédente.** Le modèle local actuel de Flore en couples question/réponse ne suffit pas. Utiliser un fil de messages ordonnés et un rendu compatible avec les messages Flore autonomes.
2. **L’Atlas ferme Flore dans certaines sélections.** L’effet lié à une relation, un domaine, une liste ou une comparaison doit respecter le mode kiosque. Une commande de scénario ne doit pas masquer le fil.
3. **Flore se masque sur le détail d’un Travail.** Faire un transfert contrôlé vers l’onglet Conversation, avec les mêmes messages. Pendant l’affichage de l’Aperçu, un volet Flore du kiosque peut porter ce même fil ; il n’en crée pas un second.
4. **Les commandes Atlas existantes ne sont pas un moteur de scènes.** Elles ne couvrent pas seules les initiatives, étapes métier et propositions futures, et ne signalent pas la fin du rendu. Ajouter ces contrats explicitement.
5. **Avant/Après est une lecture temporelle existante.** Une proposition de remplacement de MD2 ou de simplification du parcours traite doit utiliser un mode « Actuel / Proposition » séparé.
6. **Des appels réseau existent dans plusieurs composants.** Les isoler au niveau des sources de données et des actions, y compris dans les providers parents. Cacher un bouton ne suffit pas.
7. **Les temporisations de Flore et du parcours peuvent se concurrencer.** En kiosque, l’activité, les messages et les animations reçoivent leur état du même moteur.

## 3. Parcours général et écrans

### 3.1 Routes proposées

Les routes suivantes sont nouvelles ; elles n’existent pas encore dans la référence étudiée.

| Route | Fonction |
|---|---|
| `/demo` | Accueil et choix des profils. |
| `/demo/polaris/:profileId` | Lecteur du scénario sélectionné ; l’espace central évolue sans changer de route à chaque réplique. |

Identifiants : `gestionnaire`, `ligne-affaires`, `architecte`, `support-ti`, `developpeur`.

Un profil inconnu ramène à l’accueil avec une indication courte. Un accès direct à un profil crée une nouvelle session propre. Un rechargement redémarre le scénario de ce profil ; aucune reprise implicite en milieu de séquence en première version. Le bouton de retour à l’accueil utilise une navigation explicite vers `/demo`.

La session ne dépend pas du compte, du persona ou du périmètre sélectionné dans le produit. Ne pas écrire dans les clés produit `meridian.persona` et `meridian.perimetre`.

### 3.2 Accueil

Afficher :

- MÉRIDIAN — DÉCOUVRIR · COMPRENDRE · DÉCIDER.
- « Bienvenue dans Méridian. »
- « Qui êtes-vous aujourd’hui ? »
- « Découvrez une situation Polaris à travers votre rôle. »

| Profil | Phrase sur la carte |
|---|---|
| Directeur / Gestionnaire | Éclairer les initiatives à évaluer ensemble. |
| Ligne d’affaires | Réduire le délai d’émission d’une traite en succursale. |
| Architecte | Décommissionner ou réécrire MD2 : comprendre les impacts. |
| Support TI | Relier les alertes et orienter le diagnostic. |
| Développeur | Comprendre un changement et les usages à préserver. |

Le clic sélectionne le profil, charge son état initial, puis ouvre immédiatement la surface Flore. Pendant cette entrée : pas d’Atlas, de tableau de bord ni de menu produit visible. L’en-tête de démonstration peut garder le nom, le rôle, la mention « Démonstration Polaris » et l’action de retour.

### 3.3 Flore seule

Réutiliser l’apparence de Flore, dans une variante centrée d’environ 760 px de largeur maximale. Montrer le rôle et une phrase de contexte. Afficher le premier message dès que les données locales sont prêtes, sans écran intermédiaire de présentation de fonctionnalités.

Le visiteur voit « Gestionnaire », « Architecte », etc., comme auteur des messages du personnage. Ne jamais afficher « Vous » pour ces répliques. La saisie libre est remplacée par les contrôles de lecture et la mention « Conversation de démonstration ».

### 3.4 Révélation des espaces

Au premier résultat Atlas, la zone centrale s’ouvre et Flore passe dans une colonne latérale. La transformation s’effectue une seule fois à cette étape, sans rejouer l’arrivée de Flore à chaque message.

Les pages métier remplacent la zone centrale. Elles ne s’affichent pas comme des fenêtres empilées sur la carte. Les preuves peuvent utiliser un panneau de détail. Les contrôles du lecteur restent accessibles et n’empiètent pas sur les libellés de l’Atlas.

### 3.5 Conversation unique

Conserver un seul `conversationId` et un seul tableau de messages dans la session. Les composants Flore et Conversation d’un Travail sont des vues de ce tableau.

Règles de visibilité :

- Atlas ou Investigation : Flore latérale.
- Travail / Conversation : fil dans l’onglet Conversation ; panneau latéral masqué.
- Travail / Aperçu : résultat dans l’Aperçu ; Flore latérale possible pour poursuivre le même échange.
- Un seul rendu actif du fil à un instant donné ; mêmes identifiants de messages, même position logique.
- Tout changement manuel d’onglet ou ouverture de preuve suspend la lecture automatique jusqu’à « Reprendre ».

En mode scénarisé, aucune réplique déjà publiée n’est renvoyée au backend pour fabriquer la continuité.

### 3.6 Adaptation aux écrans

| Largeur disponible | Disposition cible |
|---|---|
| Au moins 1200 px | Atlas ou page métier + Flore latérale de 360 à 420 px environ. |
| 768 à 1199 px | Une surface principale à la fois si nécessaire ; résultat à sa révélation, résumé du dernier message et bouton pour retrouver le fil. |
| Moins de 768 px | Même alternance en plein écran ; contrôles accessibles ; aucune réduction de la carte en miniature illisible. |

Les seuils sont des valeurs initiales à vérifier. La géométrie des domaines et jumeaux ne se recalcule pas en fonction de la largeur : adapter le viewport et les panneaux. Les textes narratifs visent 16 px ou davantage ; commandes tactiles d’au moins 44 px ; statut lisible sans dépendre uniquement de la couleur. Respecter la préférence de réduction des animations.

## 4. Architecture de la démonstration

### 4.1 Modules et responsabilités

Créer un module `frontend/src/demo/polaris/` ou un équivalent cohérent avec le dépôt.

| Module proposé | Responsabilité |
|---|---|
| `PolarisWelcome.jsx` | Choix du profil et texte d’accueil. |
| `PolarisSessionProvider.jsx` | État de session, cycle de vie et actions du lecteur. |
| `scenarioReducer.js` | Transitions déterministes, messages et résultats. |
| `scenarioScheduler.js` | Horloge suspendable, délais restants, annulations. |
| `scenarioSchema.js` | Validation des scénarios, scènes et références. |
| `PolarisPlayer.jsx` | Composition des surfaces, contrôles, fin et erreurs. |
| `PolarisControls.jsx` | Pause, reprendre, suivant, revoir, accueil. |
| `adapters/` | Adaptation du fil, de l’Atlas, des Travaux, preuves et Investigation aux composants existants. |
| `data/entities.js` | Entités, relations, preuves et gabarits locaux communs. |
| `data/scenes.js` | Vues situationnelles complètes. |
| `scenarios/` | Cinq définitions de parcours et leurs messages. |

Utiliser JavaScript/JSX et les conventions du dépôt. Les contrats typés du document peuvent être traduits en schémas Zod ou JSDoc ; ils n’imposent pas une migration TypeScript.

### 4.2 Composition des providers

La branche produit continue avec ses providers existants. La branche kiosque dispose d’un état local et d’une source de données locale, tout en réutilisant les composants de présentation.

Si des composants nécessitent `useMesh` ou `useContexte`, leur fournir les providers compatibles dans la branche kiosque. Les providers produit qui chargent immédiatement des données réseau ne doivent pas rester au-dessus de cette branche sans un mode explicite désactivant ces effets.

Choix recommandé : identifier la branche de routes avant le montage des providers effectuant des appels réseau ; conserver un provider de contexte de sélection distinct pour chaque mode.

### 4.3 Source de données

En première version, les fixtures sont embarquées dans le bundle frontend. Elles comprennent les entités, relations, preuves, signaux, états initiaux et résultats préparés.

Les composants existants doivent recevoir leurs données et commandes par injection, ou être séparés en conteneur réseau et vue de présentation. Les endpoints actuels ne deviennent pas implicitement des endpoints kiosque.

Un adaptateur local expose au minimum : lecture du Mesh préparé, lecture et mise à jour du Travail local, lecture de l’Investigation locale, lecture des preuves, application d’une scène. Le moteur pilote les résultats ; l’adaptateur ne génère aucune découverte à partir d’un mot-clé.

Les appels sortants vers les API métier et LLM sont interdits dans une session kiosque. Ajouter une protection explicite dans le chemin de données de ce mode ; une commande non prise en charge produit un message local, jamais un retour automatique vers l’API réelle.

### 4.4 Réutilisation des composants

Réutiliser en priorité l’identité visuelle, les jumeaux, les régions, les arêtes et le rendu des Travaux existants. Extraire les sous-composants de présentation si nécessaire. Une copie complète de Flore, Atlas et Travail qui évoluerait séparément ne constitue pas le résultat attendu.

Les adaptations purement kiosque restent activées par un contexte ou des propriétés explicites. Éviter les conditions dispersées fondées sur le nom du profil dans l’ensemble de l’application.

## 5. Contrats de données

Les noms de champs ci-dessous définissent le contrat conceptuel. Toute adaptation au français du dépôt est acceptable si la correspondance est explicite.

### 5.1 Scénario et session

| Objet | Champs nécessaires |
|---|---|
| Scenario | `id`, `version`, `profileId`, `title`, `roleContext`, `openingMode`, `initialStateId`, `steps`, `revelationStepId`, `closingText`. |
| Session | `sessionId`, `generation`, `scenarioId`, `scenarioVersion`, `status`, `stepId`, `beatId`, `playMode`, `conversationId`, `messages`, `activity`, `surface`, `sceneId`, `results`, `remainingMs`, `pendingCommandId`. |
| Step | `id`, `label`, `beats`, `checkpoint`, `expectedSceneId`, `expectedResultIds`. |
| Message | `id`, `speaker` = `flore` ou `persona`, `speakerLabel`, `text`, `stepId`, `evidenceIds` optionnels. |
| Activity | `id`, `label`, `entityIds`, `status` = `pending/running/done`, `durationMs`. |
| Checkpoint | État logique après une séquence : messages publiés, résultats locaux, scène, surface et onglet. |

`openingMode` vaut `user_request`, `opportunity`, `incident_candidate` ou `discovery`.

Ne pas stocker les mêmes messages dans plusieurs stores modifiables. Les messages intégrés dans `cas.conversation` constituent une projection du fil canonique.

### 5.2 Événements de mise en scène

Une séquence comporte des événements, appelés ici `beats`, exécutés dans l’ordre.

| Type | Effet | Condition de fin |
|---|---|---|
| `message` | Publier un message, avec révélation textuelle éventuelle. | Texte entièrement visible puis temps de lecture écoulé. |
| `activity` | Afficher les opérations préparées dans Flore. | Toutes les opérations de cette activité terminées. |
| `apply_scene` | Appliquer une projection Atlas. | Acquittement de rendu pour la commande courante. |
| `upsert_result` | Créer ou remplacer un résultat local par son identifiant stable. | Résultat disponible dans le store. |
| `show_surface` | Afficher Atlas, Travail, Investigation ou Flore seule. | Surface prête avec les données attendues. |
| `observe` | Laisser lire la découverte et le résultat. | Délai écoulé ou commande d’avancement valide. |

Un message de conclusion peut suivre la matérialisation et précéder `observe`. L’observation proactive existe déjà dans les données initiales et peut être annoncée avant une nouvelle activité. Les autres révélations ne précèdent pas leur traitement.

Le moteur ne déduit pas une commande d’interface du texte de Flore. Les commandes, les textes et les références sont déclarés dans le scénario.

### 5.3 Entités et relations

| Objet | Champs nécessaires |
|---|---|
| Entity | `id`, `kind`, `label`, `description`, `domainId` si applicable, `evidenceIds`, `fictional: true`. |
| Relation | `id`, `sourceId`, `targetId`, `kind`, `label`, `knowledgeStatus`, `evidenceIds`. |
| Evidence | `id`, `title`, `sourceType`, `fixtureReference`, `periodLabel`, `excerpt`, `supports`, `limits`, `fictional: true`. |
| Option | `id`, `title`, `description`, `impacts`, `advantages`, `tradeoffs`, `prerequisites`, `unknowns`, `evidenceIds`, `status`. |

Types d’entités : application, initiative, capability, process_step, business_rule, event. Seules les applications portent les attributs de jumeau. Les étapes et règles ne sont pas inscrites comme applications dans le registre.

Séparer trois axes :

- `knowledgeStatus` : observé dans le jeu fictif, à confirmer, hypothèse.
- `temporalStatus` : actuel ou proposé, porté par la scène.
- `decisionStatus` : à évaluer, recommandé, retenu ou écarté, porté par l’option.

Une option sélectionnée pour affichage reste « à évaluer » ou « recommandée » ; la sélection ne constitue pas une décision.

### 5.4 Travail et Investigation

Le Travail local contient : identifiant stable, titre, objectif, rôle, jumeaux mobilisés, référence au fil, synthèse, preuves, options, hypothèses, questions ouvertes, prochaines actions et conditions de validation.

L’Investigation support contient : signaux initiaux, périmètre, hypothèse, preuves favorables, éléments contradictoires ou limites, vérifications à faire et lien au Travail d’intervention.

Créer une couche de correspondance vers la structure `cas` réellement lue par les composants. Les champs backend non documentés ici doivent être vérifiés dans les composants et modèles du checkout ; ne pas inventer un nouvel endpoint pour afficher ces objets.

### 5.5 Identifiants, dates et cohérence

Tous les identifiants locaux commencent par `demo-polaris-`. La même application garde le même identifiant entre profils. Chaque session reçoit une copie modifiable de ses résultats initiaux ; les fixtures partagées sont immuables.

Les événements d’incident utilisent une chronologie relative à un instant de démonstration fixe. Les libellés peuvent afficher « T−5 min », « T0 », etc., avec la mention de chronologie simulée. Ne pas présenter une fixture ancienne comme une alerte réellement survenue à l’ouverture.

L’interface indique discrètement « Démonstration Polaris · données fictives ». Les panneaux de preuve précisent leur nature. Ne pas créer de faux liens ServiceNow, Jira ou GitHub présentés comme de vraies sources internes.

## 6. Moteur de lecture et règles temporelles

### 6.1 États

| État | Signification | Sorties autorisées |
|---|---|---|
| `welcome` | Aucun profil actif. | Sélection d’un profil. |
| `initializing` | Validation et préparation des fixtures. | Lecture ou erreur. |
| `playing` | Exécution ordonnée des événements. | Pause, checkpoint manuel, fin, erreur, retour accueil. |
| `paused` | Horloge arrêtée ; position et temps restant conservés. | Reprise, suivant, relecture ou accueil. |
| `awaiting_continue` | Checkpoint atteint en mode pas à pas. | Séquence suivante ou accueil. |
| `completed` | Dernier résultat affiché. | Exploration bornée, relecture de la découverte, autre profil. |
| `error` | Chargement, données ou surface indisponibles. | Réessayer le checkpoint ou revenir à l’accueil. |

`playMode` vaut `auto` ou `manual`. Le mode automatique est la valeur initiale. Les deux modes utilisent les mêmes séquences et les mêmes résultats.

### 6.2 Rythme par séquence

Ordre usuel : message du personnage → annonce de Flore → activité → révélation du résultat → explication courte de Flore → observation.

Pour les trois ouvertures proactives : message de Flore fondé sur une observation initiale → réaction préparée du personnage → annonce → activité → résultat.

Les scripts en annexe précisent l’ordre exact. Le moteur accepte plusieurs activités ou résultats dans une séquence, notamment la comparaison MD2.

Valeurs initiales configurables :

| Élément | Valeur de départ |
|---|---|
| Lecture d’un message complètement révélé | `max(2500 ms, nombreDeMots × 260 ms)`. |
| Opération d’activité | Environ 700–1100 ms ; deux à quatre opérations utiles. |
| Transition de disposition | 300–500 ms ; nulle ou réduite selon les préférences d’accessibilité. |
| Cadrage Atlas | 400–650 ms ; attendre la géométrie prête. |
| Observation d’un résultat simple | 4000–6000 ms. |
| Observation d’une comparaison | 7000–10000 ms. |
| Délai maximal d’acquittement d’une surface | 5000 ms avant erreur récupérable. |

Le temps de lecture commence après l’affichage complet, pas au début d’un éventuel effet de frappe. Les temporisations sont celles de la mise en scène, pas une mesure de performance de l’IA. Ajuster les durées après lecture chronométrée des cinq parcours ; viser deux à trois minutes sans rendre les textes illisibles.

L’activité affiche des opérations observables : consulter un jumeau, comparer une couverture, vérifier un contrat, rapprocher des événements. Éviter les affirmations « tout est vérifié » quand des inconnues restent présentes.

### 6.3 Contrôles

**Pause :** suspendre horloge, activité, effet de frappe et progression. Une animation de viewport déjà lancée peut se terminer ; elle ne déclenche pas la suite. Conserver le délai restant.

**Reprendre :** reprendre au même événement et au délai restant, sans republier un message ni recréer un résultat.

**Suivant :**

- Pendant une séquence, terminer cette séquence jusqu’à son checkpoint. Publier les messages encore absents et appliquer les effets restants une seule fois ; ne pas sauter au-delà du résultat courant.
- Depuis un checkpoint ou une pause au checkpoint, exécuter la séquence suivante.
- Après cet avancement volontaire, rester en mode manuel jusqu’à « Reprendre la lecture automatique ».
- Coalescer les clics pendant un avancement ; un double clic ne saute pas deux séquences.
- L’action doit rester intitulée « Suivant » ou « Échange suivant », avec une aide indiquant qu’elle avance par séquence.

**Revoir la découverte :** annuler l’exécution, restaurer le checkpoint immédiatement antérieur à la séquence marquante, puis la rejouer. Les messages futurs et résultats postérieurs disparaissent de la projection restaurée ; ils ne sont pas ajoutés une deuxième fois.

**Choisir un autre profil :** annuler la session, vider ses résultats modifiables, remettre les providers kiosque dans leur état initial, puis afficher l’accueil.

### 6.4 Protection contre les courses

Toute commande asynchrone porte `sessionId`, `generation` et `commandId`. Incrémenter `generation` lors d’une réinitialisation, d’un changement de profil ou d’une restauration de checkpoint. Ignorer les retours qui ne correspondent plus à la génération active.

Les messages et résultats utilisent des identifiants déterministes, par scénario, séquence et événement. `upsert_result` remplace le même résultat local. La reprise ne crée pas un nouveau Travail.

Une commande Atlas reste dans le store jusqu’à son acquittement ou son annulation. Ne pas envoyer uniquement un événement navigateur qui serait perdu si Atlas n’est pas encore monté.

L’application d’une scène doit être idempotente. Si une erreur arrive après création du résultat mais avant son affichage, « Réessayer » réaffiche le résultat existant au lieu de le recréer.

### 6.5 Onglet masqué, inactivité et navigation

Au passage de l’onglet navigateur en arrière-plan, suspendre la lecture. Au retour, proposer « Reprendre ». Ne pas rattraper instantanément tous les événements écoulés.

Pendant une lecture automatique visible, le visiteur peut regarder sans cliquer : l’absence d’interaction n’est pas une inactivité déclenchant un reset.

Après 90 secondes sans interaction dans un état arrêté, manuel ou terminé, proposer « Continuer » ou « Revenir à l’accueil ». Après 30 secondes supplémentaires sans réponse, retourner à l’accueil. Ces délais sont configurables ; pause de la lecture avant toute proposition.

Le bouton retour navigateur, la sortie de route et le démontage annulent les tâches de la session. Une nouvelle entrée démarre proprement. L’ancien DemoTour ne doit pas reprendre son pilotage automatiquement.

## 7. Atlas situationnel : contrat de rendu

### 7.1 Une scène est une projection complète

Chaque scène décrit :

- `id`, `title`, `question`, `viewKind`.
- `entityIds`, `relationIds` et `overlayIds`.
- Entités ou relations accentuées, atténuées et masquées.
- Statuts des connaissances et légende.
- Mode actuel, proposition ou comparaison d’options.
- Positions ou référence à un jeu de positions stable.
- Cible de cadrage et politique de viewport.
- Références de preuves et actions d’exploration autorisées.

`viewKind` distingue initiatives, process, dependencies, options, incident et rule_usage. Chaque scène précise l’ensemble de son état visuel. Ne pas accumuler des classes de couleur ou des sélections provenant de la scène précédente.

### 7.2 Mise en œuvre dans l’Atlas existant

Conserver le rendu des jumeaux, domaines et arêtes. Ajouter une projection de démonstration alimentant le graphe et ses superpositions. Les objets métier peuvent être des nouveaux types de nœuds React Flow ou des superpositions attachées à la scène, avec types et légende explicites.

Le mode kiosque sélectionne cette projection au lieu des événements, animations de découverte et filtres spontanés du mode produit. Les halos et activités non liés au scénario doivent être suspendus. Les capacités de zoom/pan restent disponibles lors d’une pause.

Les coordonnées de chaque application restent stables dans une même famille de vues. Si un parcours métier nécessite une disposition différente, préserver ses identifiants, son style et un retour au cadrage précédent. Ne pas déplacer aléatoirement tous les nœuds après chaque réplique.

Pour les lectures métier, privilégier quelques étapes ou capacités lisibles. Révéler les applications quand elles servent l’explication. Les trois initiatives du gestionnaire ne doivent pas apparaître comme trois robots-jumeaux.

### 7.3 Acquittement d’une scène

L’adaptateur `applyScene(sceneId, commandId)` :

1. Vérifie toutes les références.
2. Monte la surface si nécessaire.
3. Applique les données, statuts et superpositions.
4. Attend que les dimensions utiles soient mesurées et le graphe prêt.
5. Applique le cadrage, en tenant compte de la largeur occupée par Flore.
6. Émet un acquittement de la commande courante.

Seul cet acquittement autorise le moteur à poursuivre vers l’explication ou la pause d’observation. Ne pas utiliser un délai fixe comme preuve que le graphe est prêt.

### 7.4 Langage visuel

| État | Traitement |
|---|---|
| Élément établi dans les fixtures | Trait normal et preuve accessible ; label « Observé » si utile. |
| Élément à confirmer | Marque textuelle et accent ambre. |
| Hypothèse causale | Trait distinct et label « Hypothèse » ; ne pas utiliser un lien causal affirmatif. |
| Relation proposée | Pointillés et mention « Proposition ». |
| Fonction retirée dans une cible | Visible comme retirée ou remplacée dans cette proposition ; l’actuel reste consultable. |
| Élément hors périmètre | Atténué sans perdre les repères. |

Les couleurs existantes des domaines restent reconnaissables. La légende différencie le type d’objet, le statut de connaissance et l’état proposé. Une fonction et une application ne partagent pas une apparence ambiguë.

### 7.5 Interactions pendant le parcours

Ouvrir une preuve, cliquer une relation, déplacer la carte ou choisir une option suspend la progression automatique. Un libellé « Lecture en pause » apparaît. « Reprendre » restaure la scène attendue si le visiteur en a modifié le cadrage, puis continue au point logique conservé.

L’ouverture et la fermeture d’un panneau de preuve ne suppriment ni le contexte ni les messages. Restaurer le viewport antérieur à la fermeture, sauf demande explicite de recentrage.

Pendant la comparaison MD2, sélectionner une option manuellement affiche sa scène après une courte activité contrôlée. Cette inspection conserve le curseur narratif ; à la reprise, retrouver la scène du curseur avant de continuer. Une inspection ne marque aucune option « retenue ».

## 8. Données communes à préparer

Les identifiants courts de ce chapitre reçoivent tous le préfixe `demo-polaris-` dans les données. Les noms et capacités décrits sont fictifs. Les critères de correspondance réels doivent être validés avant une future connexion à des sources métier.

### 8.1 Applications

| ID court | Libellé | Utilisation |
|---|---|---|
| `app-portail` | Portail client | Gestionnaire, support. |
| `app-conseiller` | Poste conseiller | Gestionnaire, ligne d’affaires, support, développeur. |
| `app-dossiers` | Gestion des dossiers | Gestionnaire, développeur. |
| `app-documents` | Gestion documentaire | Développeur et contexte des pièces. |
| `app-validation` | Validation documentaire | Support, développeur. |
| `app-statuts` | Diffusion des statuts | Réutilisation du suivi des dossiers. |
| `app-traites` | Émission des traites | Ligne d’affaires. |
| `app-md2` | MD2 | Architecte. |
| `app-cible-md2` | Service cible Polaris | Capacité de remplacement fictive pour l’architecte. |

Les applications sont communes au jeu Polaris ; les vues de chaque scénario n’affichent que celles utiles à leur question. Le cas de la traite n’a pas automatiquement la même cause que l’incident documentaire.

### 8.2 Objets métier minimaux

| Groupe | Contenu préparé |
|---|---|
| Gestionnaire | Trois initiatives : suivi client, poste conseiller, reprises manuelles ; capacité « état fiable du dossier » ; besoins communs et spécifiques. |
| Ligne d’affaires | Demande, préparation des informations, saisie pour émission, contrôles à valider avec le métier, remise ; une information fictive réutilisable ; cas d’information manquante ou incohérente. |
| Architecte | Fonctions MD2 regroupées pour la démo en capacité déjà couverte et règles spécifiques restantes ; consommateurs et données associés ; trois options. |
| Support | Deux familles de signaux, parcours avec et sans validation documentaire, changement récent, hypothèse et vérifications. |
| Développeur | Évolution existante, règle partagée, dossier courant, reprise d’ancien dossier, cinq cas de test proposés. |

Pour la traite, ces étapes sont une maquette de processus, explicitement fictive. Garder les contrôles comme objets à préserver ; ne pas leur attribuer une règle bancaire réelle non fournie. Aucun chiffre de délai par défaut.

Pour MD2, les catégories de fonctions servent à la démonstration. Ne pas inventer des noms de fonctionnalités prétendument issus de son code réel. La relation « fonction couverte ailleurs » doit pointer vers une preuve de démonstration qui expose aussi la limite.

### 8.3 Catalogue de preuves

| ID court | Pièce locale attendue | Ce qu’elle soutient |
|---|---|---|
| `ev-g-initiatives` | Trois fiches d’initiative fictives. | Besoin commun et différences. |
| `ev-g-couverture` | Matrice de couverture du suivi des dossiers. | Réutilisation partielle. |
| `ev-b-parcours` | Parcours préparé de demande à remise. | Position de l’intervention dans le parcours. |
| `ev-b-ressaisie` | Exemple d’échange et formulaire fictifs. | Information disponible en amont, ressaisie en aval. |
| `ev-b-controles` | Règles de démonstration et exceptions. | Conditions de préremplissage et maintien des contrôles. |
| `ev-a-usages` | Matrice fonctions MD2 / consommateurs. | Usages à préserver et impacts. |
| `ev-a-couverture` | Matrice de couverture de la cible fictive. | Réutilisation et écarts. |
| `ev-a-transition` | Contraintes préparées de transfert et coexistence. | Compromis et conditions de recommandation. |
| `ev-s-signaux` | Événements simulés des deux canaux. | Proximité des symptômes et périmètre. |
| `ev-s-changement` | Journal de configuration fictif. | Antériorité d’un changement, sans causalité acquise. |
| `ev-s-verifications` | Vérifications proposées et observations sans erreur. | Limites du diagnostic et périmètre de contrôle. |
| `ev-d-regle` | Extrait local fictif de règle et appels. | Usage partagé de la validation. |
| `ev-d-tests` | Matrice de comportements et couverture. | Cas à préserver et tests manquants. |

Chaque preuve présente un contenu lisible, pas seulement un lien ou le titre d’une source. Les références de code fictives se lisent dans un panneau local identifié comme exemple.

### 8.4 Résultats locaux

Préparer cinq Travaux et une Investigation :

- `work-g` : base commune de la réunion Polaris.
- `work-b` : réduire le délai d’émission d’une traite en succursale.
- `work-a` : trajectoire de modernisation de MD2.
- `work-s` : intervention et contrôles de retour au service.
- `work-d` : évolution déjà ouverte sur la réutilisation des pièces valides.
- `investigation-s` : qualification des erreurs et hypothèse de configuration.

Les quatre premiers Travaux sont matérialisés pendant leur parcours. Le Travail développeur existe dans l’état initial, mais ses résultats futurs ne sont pas visibles avant les étapes correspondantes.

## 9. Traduction des cinq scénarios en scènes et résultats

Les identifiants de scènes et de résultats ci-dessous sont des alias courts, préfixés dans les fixtures. Les dialogues complets de l’annexe A sont la référence éditoriale. Les tableaux ajoutent les obligations de rendu, sans remplacer le dialogue par des réponses génériques.

### 9.1 Gestionnaire

**État initial :** trois fiches d’initiative disponibles ; aucune estimation ni allocation budgétaire décidée.  
**Ouverture :** personnage Gestionnaire.  
**Découverte à rejouer :** G2.

| Étape | Activité puis résultat | Scène / surface | Postcondition observable |
|---|---|---|---|
| G1 — Rapprocher les initiatives | Lire les fiches, rapprocher processus et capacités. | `g-initiatives` : trois initiatives reliées à leurs objectifs ; applications secondaires. | Les trois pistes sont visibles et identifiables. Aucun réseau global encombrant. |
| G2 — Trouver le point commun et l’existant | Flore explique le besoin d’état fiable, puis vérifie la couverture à la demande du personnage. | `g-commun`, puis `g-reutilisation` : capacité commune, Dossiers et diffusion des statuts. | Le besoin commun est visible ; existant et raccordements à étudier sont distincts ; preuve `ev-g-couverture`. |
| G3 — Préparer la réunion | Regrouper commun, spécifique et validations. | `work-g` / Aperçu ; retour possible vers `g-reutilisation`. | Trois rubriques remplies : commun, spécifique, à valider avant estimation. |

La scène `g-commun` est une découverte intermédiaire issue de G1, affichée avec l’explication de Flore au début de G2 ; elle n’ajoute pas une analyse non annoncée. Le Travail comporte la couverture manquante, les équipes à confirmer et les questions d’effort. Ne pas produire un classement financier automatique.

**Conclusion :** « Vos initiatives disposent maintenant d’une base commune pour être évaluées. »

### 9.2 Ligne d’affaires — Traites en succursale

**État initial :** objectif connu de réduction du délai ; observation candidate disponible ; aucun gain chiffré.  
**Ouverture :** Flore, opportunité.  
**Découverte à rejouer :** B3, avec le point de friction B2 déjà présent au checkpoint précédent.

| Étape | Activité puis résultat | Scène / surface | Postcondition observable |
|---|---|---|---|
| B1 — Examiner l’opportunité | Après la réaction du personnage, examiner étapes, échanges et interventions. | `b-parcours` : demande → étapes fictives → remise. | Parcours métier lisible ; applications rattachées aux interventions. |
| B2 — Localiser la ressaisie | Vérifier disponibilité de l’information, échange et règles. | `b-ressaisie` : information amont et saisie aval accentuées ; panneau `ev-b-ressaisie`. | Le visiteur identifie le geste répété ; constat établi uniquement dans les fixtures. |
| B3 — Montrer la proposition | Examiner réutilisation, contrôles et exceptions. | `b-proposition` : bascule Actuel / Proposition. | La ressaisie est remplacée par transmission ou préremplissage conditionnel ; contrôles maintenus ; exception visible. |
| B4 — Préparer validation et mesure | Regrouper adaptations et mesures. | `work-b` / Aperçu. | Périmètre, validations métier et critères de mesure présents ; aucun gain inventé. |

La proposition représente le cas où l’information est disponible et conforme. Un chemin d’exception conserve une intervention si elle est absente ou incohérente. Ne pas effacer visuellement tous les gestes de l’employé.

Mesures dans le Travail : demande à remise, temps de ressaisie, attente, corrections, conditions de comparaison. Valeur initiale « À mesurer » en l’absence de jeu chiffré validé.

**Conclusion :** « Vous savez quelle intervention pourrait être évitée et comment en vérifier l’effet sur le délai. »

### 9.3 Architecte — MD2

**État initial :** besoin Polaris de choisir entre décommissionnement et réécriture ; usages et couverture fictifs disponibles.  
**Ouverture :** personnage Architecte.  
**Découverte à rejouer :** A2.

| Étape | Activité puis résultat | Scène / surface | Postcondition observable |
|---|---|---|---|
| A1 — Comprendre MD2 | Examiner usages, consommateurs et besoins Polaris. | `a-actuel`. | MD2, consommateurs, fonctions utiles et dépendances sont visibles. |
| A2 — Identifier la réutilisation | Comparer fonctions nécessaires, capacités et écarts. | `a-couverture` ; preuve `ev-a-couverture`. | Des capacités existantes apparaissent ; les règles spécifiques restent à prendre en charge. |
| A3 — Comparer les trajectoires | Comparer transferts, interfaces, données et risques. | `work-a` créé avec trois options ; puis vues `a-retrait`, `a-reecriture`, `a-progressif`. | Chaque option montre ce qui change ; un contrôle persistant permet de passer de l’une à l’autre. |
| A4 — Expliquer la recommandation | Flore recommande conditionnellement ; elle prépare preuves et prérequis. | `a-recommandation`, puis `work-a` / Aperçu enrichi. | L’option progressive est « Recommandée par Flore », jamais « Retenue » sans décision ; inconnues explicites. |

A3 se matérialise d’abord dans l’Aperçu du Travail, puis ouvre l’Atlas sur la comparaison. Le contrôle des trois options y reste disponible et renvoie au même jeu d’options du Travail. Il ne s’agit pas de deux comparaisons indépendantes.

| Option | Résultat visuel précis |
|---|---|
| Décommissionnement après reprise | Fonctions transférées aux candidats ; consommateurs redirigés ; MD2 proposée au retrait seulement après couverture validée. |
| Réécriture | Cible MD2 réécrite identifiée comme proposition ; fonctions reconstruites, données migrées et interfaces adaptées. |
| Remplacement progressif puis retrait | Capacités réutilisées par étapes ; fonctions restantes encore dans MD2 ; coexistence temporaire et condition de fin. |

A4 conserve l’ordre du script : première formulation de la recommandation sur les résultats déjà analysés, activité de consolidation, puis trajectoire et dossier détaillé. Ne pas refaire croire à une analyse nouvelle de toutes les options.

Le tableau compare besoins couverts, éléments à construire, réutilisation, dépendances, migration des données, bascule, coexistence et inconnues. Coût et délai restent « À estimer ». La recommandation dépend des capacités candidates, de leurs contraintes et de l’effort de transition.

**Conclusion :** « Vous voyez les impacts des options pour MD2 et les conditions de la trajectoire recommandée. »

### 9.4 Support TI

**État initial :** signaux simulés sur deux canaux, situation candidate ; cause inconnue.  
**Ouverture :** Flore, incident potentiel.  
**Découverte à rejouer :** S2.

| Étape | Activité puis résultat | Scène / surface | Postcondition observable |
|---|---|---|---|
| S1 — Qualifier la situation | Rapprocher signaux, chronologies et dépendances. | `s-perimetre`. | Portail et conseiller touchés ; autres parcours atténués ; situation candidate identifiée. |
| S2 — Concentrer le diagnostic | Montrer la validation commune puis examiner le changement récent. | `s-convergence`, puis `s-chronologie`. | Service partagé visible ; changement antérieur marqué comme hypothèse, preuve consultable. |
| S3 — Préparer l’intervention | Regrouper vérifications, responsabilités et contrôles. | `investigation-s`, `work-s`, scène de retour `s-surveillance`. | Plan proposé et hypothèse conservés ; aucun état « rétabli » sans observation. |

La convergence est issue de l’analyse de S1 ; S2 approfondit la chronologie. Après l’activité de S3, créer l’Investigation et le Travail liés. Montrer brièvement l’Investigation, puis le Travail d’intervention ; les liens locaux permettent de retourner aux preuves et à l’Atlas.

États de la situation : signal → candidate → qualifiée sur son périmètre → investigation ouverte. La qualification du périmètre ne confirme pas la cause. Aucune commande de retour arrière n’est réellement exécutée.

**Conclusion :** « Le périmètre est plus clair ; les vérifications et les équipes à mobiliser sont identifiées. »

### 9.5 Développeur

**État initial :** `work-d` existe ; objectif « Ne plus redemander une pièce déjà valide » ; découverte récente préparée et liée à ce Travail.  
**Ouverture :** Flore, nouvelle découverte.  
**Découverte à rejouer :** D2.

| Étape | Activité puis résultat | Scène / surface | Postcondition observable |
|---|---|---|---|
| D1 — Reprendre le travail | Signaler l’usage découvert, puis examiner parcours, appels et règle. | `d-parcours` ; détail `ev-d-regle`. | Poste conseiller → Dossiers → validation ; règle et références lisibles hors carte. |
| D2 — Montrer le cas à préserver | Examiner autres appels, reprise et tests. | `d-usages`. | Deux chemins : dossier courant et ancien dossier repris ; besoin éventuel de revalidation visible. |
| D3 — Préparer une modification ciblée | Regrouper points de modification, contrats, tests et questions métier. | `work-d` / Aperçu enrichi. | Le Travail initial est actualisé ; cinq cas de test et inconnues présents. |

Tests à présenter : pièce valide, pièce refusée, validation expirée, dossier repris, statut inconnu. Ils sont proposés, pas affichés comme exécutés. L’Atlas ne transforme pas les méthodes ou fichiers de code en jumeaux.

**Conclusion :** « Votre évolution est reliée au code, à ses usages et aux comportements à préserver. »

## 10. Exemple de définition d’une séquence

Cet extrait illustre le contrat du moteur. Il ne constitue pas un fichier applicatif livré. Les autres séquences doivent suivre le même principe ; les messages complets sont en annexe A.

```json
{
  "id": "demo-polaris-a2",
  "label": "Identifier la réutilisation",
  "checkpoint": true,
  "expectedSceneId": "demo-polaris-a-couverture",
  "expectedResultIds": [],
  "beats": [
    {
      "id": "demo-polaris-a2-m1",
      "type": "message",
      "speaker": "persona",
      "speakerLabel": "Architecte",
      "text": "Est-ce qu’il faut tout reconstruire ?"
    },
    {
      "id": "demo-polaris-a2-m2",
      "type": "message",
      "speaker": "flore",
      "speakerLabel": "Flore",
      "text": "Je vais comparer les fonctions nécessaires avec les capacités existantes."
    },
    {
      "id": "demo-polaris-a2-activity",
      "type": "activity",
      "items": [
        {
          "id": "demo-polaris-a2-act1",
          "label": "Comparaison des capacités",
          "entityIds": ["demo-polaris-app-md2", "demo-polaris-app-cible-md2"],
          "durationMs": 900
        },
        {
          "id": "demo-polaris-a2-act2",
          "label": "Examen des règles et contrats",
          "entityIds": ["demo-polaris-app-md2"],
          "durationMs": 1000
        },
        {
          "id": "demo-polaris-a2-act3",
          "label": "Identification des écarts",
          "entityIds": ["demo-polaris-app-md2", "demo-polaris-app-cible-md2"],
          "durationMs": 900
        }
      ]
    },
    {
      "id": "demo-polaris-a2-scene",
      "type": "apply_scene",
      "sceneId": "demo-polaris-a-couverture"
    },
    {
      "id": "demo-polaris-a2-m3",
      "type": "message",
      "speaker": "flore",
      "speakerLabel": "Flore",
      "text": "Certaines fonctions sont déjà couvertes ailleurs. Une réécriture complète les reconstruirait. Il reste cependant des règles spécifiques à reprendre.",
      "evidenceIds": ["demo-polaris-ev-a-couverture"]
    },
    {
      "id": "demo-polaris-a2-observe",
      "type": "observe",
      "durationMs": 6000
    }
  ]
}
```

À l’exécution, le moteur ajoute `stepId` au message publié et initialise les statuts d’activité. La présence d’un `sceneId` doit être validée dans le catalogue avant la lecture. L’événement `apply_scene` active la surface Atlas si nécessaire et attend son acquittement ; aucun `show_surface` supplémentaire n’est requis pour ce cas.

## 11. Fin, exploration et erreurs

### 11.1 Fin de parcours

Après la dernière séquence, afficher la conclusion du rôle et deux actions principales : « Revoir la découverte » et « Choisir un autre rôle ».

L’exploration de fin reste bornée aux résultats préparés : ouvrir une preuve, consulter le Travail, revenir à la dernière scène et comparer les options MD2. Ces actions n’ajoutent pas de répliques prétendument saisies par le visiteur.

Les contrôles de décision des composants produit sont soit adaptés à une action locale explicitement marquée « Démonstration », soit masqués s’ils ne font pas partie du parcours. Aucun bouton visible ne doit paraître disponible puis appeler silencieusement le backend réel.

### 11.2 Erreurs à traiter

| Cas | Comportement |
|---|---|
| Profil inconnu | Retour à l’accueil, message bref. |
| Référence de scène ou preuve absente | Erreur de validation avant lecture ; diagnostic précis pour le développeur. |
| Échec de rendu de scène | Pause ; « La vue n’a pas pu s’afficher. Réessayer / Revenir à l’accueil ». |
| Acquittement périmé | Ignoré ; aucune mutation de la session suivante. |
| Travail local absent | Erreur récupérable ; ne pas chercher un Travail de même nom dans le produit. |
| Ressource locale indispensable indisponible | Message de chargement échoué ; reprise possible. |
| Clic sur un contrôle hors périmètre préparé | Contrôle désactivé ou masqué avec comportement explicite ; aucun faux résultat. |

Le détail technique figure dans les logs de développement, pas dans le dialogue de Flore. Une erreur de rendu ne devient pas une « découverte » métier.

### 11.3 Ce que conserve la session

Les Travaux et l’Investigation persistent pendant la session de démonstration. Ils montrent la mémoire que le produit pourrait conserver ; ils sont réinitialisés au changement de profil ou au retour à l’accueil.

La première version ne promet pas une sauvegarde backend de la démonstration. Les résultats initiaux du développeur sont réinstallés depuis les fixtures à chaque session.

## 12. Ordre de réalisation pour l’IA de développement

### Lot 1 — Vérifier le checkout et préparer les points d’injection

Lire les instructions du dépôt, identifier le commit de travail et vérifier les fichiers du chapitre 2. Confirmer les props des composants réutilisés, les appels réseau indirects et les champs réellement lus dans les Travaux.

Produire une courte note des écarts avec cette référence. Une différence technique se résout en adaptant l’intégration ; elle ne justifie pas de modifier les scénarios.

**Sortie attendue :** choix des points d’injection et séparation claire entre mode produit et kiosque.

### Lot 2 — Installer le moteur avec un parcours complet

Créer les routes, l’accueil, le provider, le reducer, l’horloge suspendable, les schémas et les données minimales. Réaliser le parcours gestionnaire de bout en bout avec Atlas, preuve et Travail.

**Sortie attendue :** premier parcours complet permettant de vérifier l’ensemble du mécanisme. Ne pas livrer cinq débuts de parcours sans fin.

### Lot 3 — Ajouter les vues métier et la comparaison

Implémenter le parcours traite, Actuel / Proposition et exceptions. Ajouter MD2, couverture fonctionnelle, trois options, sélection et recommandation conditionnelle.

**Sortie attendue :** réutilisation du même moteur ; chaque différence est principalement déclarée dans les scènes et données.

### Lot 4 — Ajouter les ouvertures proactives et la continuité

Finaliser support TI et développeur : observations initiales, Investigation, Travail préexistant et nouvelle découverte. Vérifier que les profils proactifs n’exigent aucune question initiale.

**Sortie attendue :** cinq parcours autonomes et complets, deux ouverts par le personnage et trois par Flore.

### Lot 5 — Stabiliser l’expérience du kiosque

Vérifier lisibilité, contrôles tactiles, pauses, reprise, navigation, relecture, erreurs, absence d’appels métier, temps des parcours et comportement hors kiosque.

**Sortie attendue :** démonstration répétable sur le matériel cible, avec un compte rendu de validation et les limites restantes.

### Livrables attendus de l’implémentation

- Le mode kiosque intégré au dépôt.
- Les cinq scénarios déclaratifs et leurs fixtures cohérentes.
- Les adaptateurs et composants nécessaires, avec réutilisation de la présentation existante.
- Les tests ciblés du moteur et des intégrations critiques.
- Une documentation courte : route d’entrée, démarrage selon le dépôt, modification des textes/durées, ajout d’une scène et reset.
- Un relevé des validations effectuées et de celles non effectuées.

## 13. Critères de validation

Ces critères définissent les tests à faire pendant l’implémentation. Ils n’ont pas été exécutés pour produire cette spécification.

### 13.1 Tests du moteur

Utiliser une horloge contrôlée pour vérifier les comportements qui portent un risque réel :

| ID | Test | Résultat attendu |
|---|---|---|
| M01 | Pause pendant une activité puis reprise. | Délai restant conservé ; aucun événement ne passe pendant la pause. |
| M02 | Double clic sur Suivant. | Une seule séquence terminée ; pas de saut supplémentaire. |
| M03 | Changement de profil avant un acquittement Atlas. | Le retour périmé n’affecte pas le nouveau profil. |
| M04 | Relecture de la découverte après fin. | Checkpoint restauré ; aucun message ou Travail dupliqué. |
| M05 | Échec de surface puis nouvelle tentative. | Résultat local réutilisé ; fil inchangé ; scène affichée. |
| M06 | Message Flore en première position. | Rendu sans bulle personnage vide ni question synthétique. |
| M07 | Montage/démontage répété des effets en développement. | Un seul scheduler actif ; pas de message doublé. |

Valider automatiquement toutes les références des cinq scénarios : entités, relations, preuves, scènes, résultats et checkpoint de découverte. Vérifier qu’une relation relie deux objets existants et qu’un résultat utilisé est créé ou présent dans l’état initial.

### 13.2 Tests d’intégration

| ID | Situation | Résultat attendu |
|---|---|---|
| I01 | Ouvrir chacun des cinq profils depuis l’accueil. | Flore seule initialement ; premier auteur conforme. |
| I02 | Première révélation Atlas. | L’activité finit avant la vue ; l’explication ne dépasse pas l’acquittement du rendu. |
| I03 | Sélection scénarisée d’une relation ou d’une option. | Flore reste accessible ; fil et curseur narratif conservés. |
| I04 | Passage Atlas → Travail / Aperçu → Conversation. | Même conversation ; aucun redémarrage de session. |
| I05 | Ouvrir une preuve puis fermer. | Pause, contexte et cadrage conservés ; reprise explicite. |
| I06 | Fin puis choix d’un autre profil. | Aucun élément du précédent scénario ne persiste par erreur. |
| I07 | Backend métier et LLM indisponibles. | Les cinq parcours continuent avec les ressources locales chargées. |
| I08 | Observer les requêtes réseau de la session. | Aucun appel vers les endpoints métier ou LLM ; ressources statiques autorisées. |
| I09 | Quitter le kiosque et ouvrir les routes produit. | Comportement produit conservé ; aucune fixture kiosque injectée. |
| I10 | Rechargement direct d’une route profil. | Le même profil redémarre proprement ; pas de mélange avec un ancien checkpoint. |

La prise en charge d’un chargement initial entièrement hors réseau n’est pas requise : le site et ses ressources statiques doivent pouvoir être servis. L’indépendance attendue concerne les API métier et LLM une fois l’application chargée.

### 13.3 Validation spécifique par profil

| Profil | Condition de réussite | Erreur bloquante |
|---|---|---|
| Gestionnaire | Le visiteur voit la capacité commune et la couverture partielle. | Initiatives réduites à un réseau d’applications sans besoin métier, ou budget inventé. |
| Ligne d’affaires | Ressaisie localisée, proposition visible, contrôles et exceptions maintenus. | Gain chiffré non étayé ou disparition de tous les contrôles. |
| Architecte | Trois options comparables, impacts propres et recommandation justifiée. | Même carte sous trois titres, ou recommandation affichée comme décision prise. |
| Support | Signaux reliés, hypothèse et vérifications distinctes. | Cause confirmée par simple proximité temporelle, ou service déclaré rétabli. |
| Développeur | Règle partagée, cas de reprise et tests proposés visibles. | Changement présenté comme déployé ou tests proposés affichés comme réussis. |

### 13.4 Vérification visuelle et éditoriale

Effectuer une lecture complète de chaque parcours aux dimensions 1366×768 et tablette paysage 1024×768, puis vérifier le fonctionnement en disposition étroite. Capturer au minimum : accueil, Flore seule, chaque découverte, comparaison MD2 et résultat final.

Vérifier : textes non tronqués, contrôles accessibles, absence de superposition gênante, identification des objets, statut des propositions, lisibilité des preuves et respect des animations réduites.

Chronométrer chaque profil sans interruption. Si le parcours dépasse sensiblement trois minutes, réduire les formulations redondantes ou simplifier la présentation avec validation éditoriale ; ne pas accélérer tous les messages jusqu’à les rendre illisibles.

### 13.5 Définition de terminé

La réalisation est terminée lorsque les cinq profils se déroulent entièrement, les découvertes et résultats correspondent aux scripts, les tests critiques passent, les actions restent locales, la démonstration est répétable et les routes produit conservent leur comportement.

Un inventaire de pages, une conversation statique ou une animation de carte sans résultats consultables ne satisfait pas ces critères.

## 14. Décisions ouvertes et valeurs de départ

| Sujet | Valeur de départ retenue | Ce qui pourra évoluer |
|---|---|---|
| Texte et audio | Texte seul, autonome. | Voix optionnelle après stabilisation. |
| Réponses | Préparées et déterministes. | Questions libres dans une extension identifiée. |
| Persistance kiosque | Mémoire de session. | Reprise locale ou sauvegarde dédiée si demandée. |
| Processus traite | Maquette fictive avec ressaisie et contrôles conservés. | Étapes et règles après validation métier. |
| Fonctions MD2 | Capacités fictives regroupées par couverture et écarts. | Détails après analyse réelle autorisée. |
| Recommandation MD2 | Progressive dans le scénario, conditionnelle aux preuves préparées. | Autre recommandation si le jeu de faits change. |
| Rythme | Valeurs du chapitre 6 puis lecture chronométrée. | Ajustement sur matériel du kiosque. |

Ces choix permettent de commencer l’implémentation sans nouvelle clarification générale. Les données fictives doivent rester identifiées. Une modification des besoins métier doit être reflétée dans les dialogues, scènes, preuves, résultats et critères de validation concernés.

## 15. Sources et limites de la spécification

La source éditoriale est le document d’expérience version 1.2. L’annexe A reprend ses cinq scripts afin que ce fichier soit autonome. La traduction technique des chapitres précédents complète ces scripts ; elle n’autorise pas à remplacer les cas de la traite ou de MD2 par des exemples génériques.

Les nouveaux modules, routes de démonstration, scènes et contrats d’acquittement sont des éléments à construire. Leur présence dans cette spécification ne signifie pas qu’ils existent déjà dans le dépôt.

Les faits techniques du chapitre 2 proviennent d’une lecture ciblée du frontend au commit indiqué. Le backend, les infrastructures, les performances et le rendu en navigateur ne sont pas évalués ici. L’IA de développement doit vérifier les contrats des composants qu’elle modifie, sans entreprendre une refonte générale du produit.

### Fichiers vérifiés

- [frontend/package.json](https://github.com/Eloekamaje/meridian-mesh/blob/379bb118e3eb0eace2d222b907e8ad842cdf53a2/frontend/package.json) — contenu vérifié ; blob `5b37f5de1dcbf8ec9389b943ccfea5ab8730b8ee`.
- [frontend/src/App.js](https://github.com/Eloekamaje/meridian-mesh/blob/379bb118e3eb0eace2d222b907e8ad842cdf53a2/frontend/src/App.js) — contenu vérifié ; blob `279821ac87d2f19dad50f3e517b7de8f96cf4333`.
- [frontend/src/components/FlorePanel.jsx](https://github.com/Eloekamaje/meridian-mesh/blob/379bb118e3eb0eace2d222b907e8ad842cdf53a2/frontend/src/components/FlorePanel.jsx) — contenu vérifié ; blob `e4644cac562fc6c66100377578d5392e48b8af25`.
- [frontend/src/lib/contexte.jsx](https://github.com/Eloekamaje/meridian-mesh/blob/379bb118e3eb0eace2d222b907e8ad842cdf53a2/frontend/src/lib/contexte.jsx) — contenu vérifié ; blob `2da2dd010c7bbb72899d1cf1f630f95741d6e5e6`.
- [frontend/src/components/DemoTour.jsx](https://github.com/Eloekamaje/meridian-mesh/blob/379bb118e3eb0eace2d222b907e8ad842cdf53a2/frontend/src/components/DemoTour.jsx) — contenu vérifié ; blob `bb9ea01186da8f9b5f590a483e94ee851464063b`.
- [frontend/src/components/Layout.jsx](https://github.com/Eloekamaje/meridian-mesh/blob/379bb118e3eb0eace2d222b907e8ad842cdf53a2/frontend/src/components/Layout.jsx) — contenu vérifié ; blob `82b090b8d92bcf551457a189933e24dec8dfd77b`.
- [frontend/src/lib/demo.jsx](https://github.com/Eloekamaje/meridian-mesh/blob/379bb118e3eb0eace2d222b907e8ad842cdf53a2/frontend/src/lib/demo.jsx) — contenu vérifié ; blob `f24c2c7a4f98c89c5145bcd34c8ece1f0d185a9d`.
- [frontend/src/lib/mesh.jsx](https://github.com/Eloekamaje/meridian-mesh/blob/379bb118e3eb0eace2d222b907e8ad842cdf53a2/frontend/src/lib/mesh.jsx) — contenu vérifié ; blob `270d9470eda39fc0b6d98e0140dea109da0b237b`.
- [frontend/src/components/FloreActivite.jsx](https://github.com/Eloekamaje/meridian-mesh/blob/379bb118e3eb0eace2d222b907e8ad842cdf53a2/frontend/src/components/FloreActivite.jsx) — contenu vérifié ; blob `af9d806ac336cf7c6db61465404e1a6b79996081`.
- [frontend/src/pages/Atlas.jsx](https://github.com/Eloekamaje/meridian-mesh/blob/379bb118e3eb0eace2d222b907e8ad842cdf53a2/frontend/src/pages/Atlas.jsx) — contenu vérifié ; blob `122fd68bf6b0c5000f45e9a87a7176bd68d3ebb9`.
- [frontend/src/pages/TravailDetail.jsx](https://github.com/Eloekamaje/meridian-mesh/blob/379bb118e3eb0eace2d222b907e8ad842cdf53a2/frontend/src/pages/TravailDetail.jsx) — contenu vérifié ; blob `3f4f4fbfa02a5c574a640b86b536709b06b67ded`.
- [frontend/src/components/case/OngletTravail.jsx](https://github.com/Eloekamaje/meridian-mesh/blob/379bb118e3eb0eace2d222b907e8ad842cdf53a2/frontend/src/components/case/OngletTravail.jsx) — contenu vérifié ; blob `3384abebfebd5087e4f199adde930c7e11001728`.
- [frontend/src/components/case/OngletApercu.jsx](https://github.com/Eloekamaje/meridian-mesh/blob/379bb118e3eb0eace2d222b907e8ad842cdf53a2/frontend/src/components/case/OngletApercu.jsx) — contenu vérifié ; blob `08bbb13271b26c4e57f9ca04bbd03c9ede40e71c`.
- [frontend/src/lib/api.js](https://github.com/Eloekamaje/meridian-mesh/blob/379bb118e3eb0eace2d222b907e8ad842cdf53a2/frontend/src/lib/api.js) — contenu vérifié ; blob `323753701e2fca2b224b4db1de15945311a42303`.

## Annexe A — Dialogues complets et effets attendus

Textes issus du document de conception version 1.2. Les opérations sont des activités de démonstration. Chaque résultat doit être observable avant de poursuivre selon le rythme défini au chapitre 6.

### A.1. Gestionnaire — Faire avancer la réunion sur les initiatives

Mission : comprendre comment les pistes d’initiatives s’articulent avant de recommander les investissements des trois prochaines années.
Révélation : plusieurs initiatives dépendent d’une capacité commune, partiellement existante.
Lectures successives de l’Atlas : initiatives → capacités et processus communs → applications et réutilisation → périmètre à instruire.

#### Séquence 1 — Poser les pistes

**Déclencheur : besoin formulé par la gestionnaire en préparation de la réunion.** Une courte indication de rôle précède la première prise de parole.

**Gestionnaire :** « Nous avons trois pistes : le suivi des demandes clients, le poste conseiller et la réduction des reprises manuelles. Nous avons du mal à voir ce qu’elles impliquent et ce qui se recoupe. »

**Flore :** « Je vais rapprocher leurs objectifs des processus et capacités concernés. »

**Activité visible :** lecture des trois fiches d’initiative ; consultation des connaissances des jumeaux concernés ; recherche des points communs.

**Résultat :** l’Atlas s’ouvre sur « Polaris — lecture des initiatives ». Trois cartes d’initiative sont reliées aux parties du parcours qu’elles veulent améliorer. Les applications restent au second plan. Une liste de mots techniques ou un réseau complet ne précède pas cette lecture métier.

#### Séquence 2 — Révéler le point commun

**Flore :** « Les trois pistes ont un besoin commun : connaître l’état réel du dossier. Aujourd’hui, le client, le conseiller et les opérations n’en disposent pas de la même façon. »

**Gestionnaire :** « Devons-nous tout construire pour partager cette information ? »

**Flore :** « Je vérifie les capacités déjà disponibles et leurs limites. »

**Activité visible :** examen de la gestion des dossiers ; vérification des interfaces et de leurs usages ; rapprochement avec les besoins des trois initiatives.

**Résultat :** l’Atlas passe à « Capacités existantes ». Le service Dossiers devient visible sous le besoin commun. Une relation est marquée « existante » ; les raccordements envisagés portent « à étudier ». Le visiteur peut comprendre ce qui pourrait être partagé sans croire que tous les besoins sont déjà couverts.

**Flore :** « Une partie du suivi existe déjà. Sa couverture ne répond pas encore à tous les besoins des trois initiatives. Nous pouvons examiner un socle commun et les adaptations propres à chacune. »

#### Séquence 3 — Donner une suite à la réunion

**Gestionnaire :** « Prépare ce qu’il nous faut pour évaluer cette piste ensemble. »

**Flore :** « Je rassemble le périmètre commun, les différences et les points à faire valider. »

**Activité visible :** regroupement des besoins communs ; identification des responsables ; préparation des questions d’effort, de couverture et de capacité.

**Résultat :** un Travail présente « Commun aux trois initiatives », « Spécifique à chacune » et « À valider avant estimation ». L’Atlas reste accessible sur le périmètre concerné ; les estimations manquantes ne sont pas inventées.

**Flore :** « Voici une base commune pour votre réunion : ce qui pourrait être partagé, ce qui reste spécifique et les validations nécessaires pour comparer les options. »

**Effet mémorable :** trois discussions dispersées deviennent une question collective précise.
**Bénéfice :** mieux préparer l’arbitrage, avec une connaissance commune et vérifiable.

### A.2. Ligne d’affaires — Réduire le délai d’émission d’une traite en succursale

**Mission :** réduire le temps entre la demande du client et la remise de sa traite bancaire en succursale, tout en simplifiant le travail de l’employé et en conservant les contrôles nécessaires.

**Origine de la conversation :** Flore prend l’initiative en lien avec cet objectif déjà connu de la ligne d’affaires.

**Hypothèse de démonstration :** une information déjà disponible dans une application doit être ressaisie dans une autre. Cette ressaisie ajoute une intervention et peut entraîner une correction. La friction réelle, les applications, les étapes et les règles doivent être confirmées avec les équipes métier avant de figer le scénario. Aucun gain chiffré n’est présumé.

**Lectures successives de l’Atlas :** parcours en succursale → point de ressaisie et applications concernées → parcours actuel et proposition → périmètre des adaptations.

#### Séquence 1 — Flore signale une possibilité d’amélioration

**Déclencheur :** dans le jeu de démonstration préparé, une observation du parcours suggère une intervention potentiellement évitable. Un indicateur « Opportunité — émission d’une traite » apparaît. La ligne d’affaires n’a pas encore posé de question.

**Flore :** « Vous souhaitez réduire le délai d’émission des traites en succursale. J’ai repéré une étape du parcours qui pourrait contribuer à cette attente. Voulez-vous l’examiner ? »

**Ligne d’affaires :** « Oui. Montre-moi où le temps est perdu. »

**Flore :** « Je vais examiner les étapes, les échanges entre applications et les interventions de l’employé, depuis la demande du client jusqu’à la remise de la traite. »

**Activité visible :** rapprochement des étapes et événements disponibles ; examen des échanges entre applications ; distinction entre temps de traitement et temps d’attente.

**Résultat :** l’Atlas s’ouvre en lecture « Émission d’une traite en succursale ». Le parcours présente la demande et la remise comme bornes. Entre les deux, il représente les étapes validées pour la démonstration, les interventions de l’employé et les applications concernées. Les délais sont chiffrés seulement si les données préparées permettent de les étayer.

#### Séquence 2 — Rendre la friction visible

**Flore :** « Cette étape semble demander à l’employé de saisir une information déjà disponible dans l’application précédente. Je vais vérifier si elle peut être réutilisée. »

**Ligne d’affaires :** « Pourquoi faut-il la saisir de nouveau ? »

**Flore :** « Je vérifie comment l’information circule et quelles règles s’appliquent à son utilisation. »

**Activité visible :** consultation des informations disponibles en amont ; examen de l’échange avec l’application d’émission ; vérification des règles et des corrections éventuelles.

**Résultat :** l’Atlas isole le passage entre les applications. Il affiche « Information déjà disponible » en amont et « Ressaisie par l’employé » en aval. Le reste du parcours s’atténue. Un panneau de preuve présente les événements, la procédure ou le contrat préparés qui soutiennent ce constat.

**Flore :** « Dans le parcours examiné, l’information est disponible en amont mais doit être saisie à nouveau ici. Cette intervention ajoute du travail et peut entraîner une correction. »

**Précision de conception :** cette réponse correspond au fait établi dans le jeu fictif une fois l’hypothèse choisie et documentée. Elle n’affirme pas que ce dysfonctionnement existe dans le processus réel de la banque. Si la vérification du scénario ne permet pas d’établir le fait, Flore conserve le statut « à confirmer ».

#### Séquence 3 — Montrer la simplification possible

**Ligne d’affaires :** « Que faudrait-il changer pour éviter cette ressaisie ? »

**Flore :** « Je vais examiner la réutilisation de cette information, en conservant les contrôles et les cas qui nécessitent une intervention. »

**Activité visible :** examen du raccordement possible ; vérification des conditions de réutilisation ; identification des exceptions et du fonctionnement en cas d’information absente ou incohérente.

**Résultat :** l’Atlas passe à « Actuel / Proposition ». Le parcours actuel montre la ressaisie. Dans le parcours proposé, l’information serait transmise ou préremplie à partir de la source validée. Les contrôles nécessaires restent visibles ; la proposition ne supprime aucune validation métier par défaut.

**Flore :** « Cette proposition évite la ressaisie lorsque l’information est disponible et conforme aux règles. Voici les adaptations et les exceptions à valider. »

**Effet marquant :** l’intervention répétée disparaît visiblement du parcours proposé. Le visiteur comprend le lien entre la simplification du geste employé et la réduction possible de l’attente du client.

#### Séquence 4 — Préparer la mise en œuvre et la mesure

**Ligne d’affaires :** « Prépare les éléments à valider avec les équipes et la manière de mesurer le résultat. »

**Flore :** « Je rassemble les adaptations, les responsables, les contrôles à préserver et les mesures de délai nécessaires. »

**Activité visible :** préparation des critères d’acceptation ; regroupement des équipes et applications concernées ; définition des observations utiles pour comparer les parcours.

**Résultat :** un Travail « Réduire le délai d’émission d’une traite en succursale » conserve le parcours actuel, la proposition, les preuves préparées, les adaptations candidates et les validations métier. L’Atlas montre le périmètre concerné et permet de revenir au point de friction.

Les mesures à préparer comprennent le temps entre demande et remise, le temps consacré à la ressaisie, les attentes et les corrections. Les conditions de comparaison doivent être précisées afin de ne pas attribuer automatiquement toute variation à la modification proposée.

**Flore :** « Voici ce qu’il faut valider pour simplifier l’opération, et les mesures qui permettront de vérifier si le client attend moins longtemps. »

**Bénéfice à retenir :** « Méridian me montre où agir pour accélérer l’émission d’une traite et simplifier le travail en succursale. »

### A.3. Architecte — Décommissionner ou réécrire MD2 ?

Mission : éclairer le choix de Polaris entre décommissionnement et réécriture de MD2, à partir des besoins, des impacts et des possibilités de réutilisation.
Révélation préparée : certaines fonctions utiles de MD2 sont déjà couvertes ailleurs, mais des règles ou usages restent à prendre en charge. Une réécriture complète pourrait donc reconstruire des capacités existantes.
Lectures successives de l’Atlas : MD2 et ses usages → capacités utiles et réutilisables → impacts comparés → transition recommandée.

**Cadre de démonstration :** la couverture fonctionnelle, les dépendances et les règles de MD2 ci-dessous sont des données fictives à préparer et à valider pour le scénario. Elles ne constituent pas une analyse réelle de MD2. La recommandation dépend de ces éléments ; aucun coût, délai ou gain mesuré n’est inventé.

#### Séquence 1 — Poser le choix et rendre ses conséquences visibles

**Déclencheur : l’architecte formule un besoin d’aide à la décision dans Polaris.**

**Architecte :** « Polaris envisage de décommissionner MD2 ou de la réécrire. Quels seraient les impacts et quelle option recommandes-tu ? »

**Flore :** « Je vais examiner ses usages, ses dépendances et les capacités déjà disponibles ailleurs. »

**Activité visible :** consultation du jumeau MD2 ; vérification des consommateurs auprès des jumeaux voisins ; rapprochement des fonctions utilisées avec les besoins de Polaris.

**Résultat :** après le traitement, l’Atlas s’ouvre en lecture « MD2 aujourd’hui ». Il montre les applications et processus qui en dépendent, puis met en évidence les fonctions encore utiles. Les preuves et les zones de connaissance incomplète sont consultables.

**Flore :** « Des processus dépendent encore de MD2. Son retrait suppose de reprendre les fonctions qu’ils utilisent. »

Un temps d’observation précède la question suivante. La carte ne se transforme pas à chaque mot de Flore.

#### Séquence 2 — Découvrir ce qui pourrait être réutilisé

**Architecte :** « Est-ce qu’il faut tout reconstruire ? »

**Flore :** « Je vais comparer les fonctions nécessaires avec les capacités existantes. »

**Activité visible :** comparaison des capacités ; examen des règles et contrats ; identification des écarts fonctionnels et des contraintes de reprise.

**Résultat :** l’Atlas passe à « Fonctions à préserver et capacités existantes ». Il relie les fonctions de MD2 à leurs consommateurs et aux applications candidates pour les reprendre. Une légende distingue « couverture établie dans la démonstration », « couverture partielle » et « à confirmer ». Le rapprochement d’un nom de fonction ne suffit pas à établir son équivalence.

**Flore :** « Certaines fonctions sont déjà couvertes ailleurs. Une réécriture complète les reconstruirait. Il reste cependant des règles spécifiques à reprendre. »

**Effet de découverte :** le visiteur voit ce qu’il serait possible de réutiliser et ce qui exige encore du travail. Une preuve présente la couverture et ses limites.

#### Séquence 3 — Comparer les options et leurs impacts

**Architecte :** « Montre-moi les conséquences des différentes options. »

**Flore :** « Je compare le remplacement avant retrait, la réécriture et une transition progressive. »

**Activité visible :** évaluation de la couverture par option ; repérage des interfaces et données à transférer ; examen des risques de bascule et de coexistence.

**Résultat :** trois options apparaissent dans le Travail. Dans la conversation préparée, leur sélection successive fait réagir l’Atlas après le traitement de Flore. Chaque vue porte le nom de l’option et la mention « Proposition ». MD2 et ses voisins gardent leur identité et leurs repères.

| Option | Ce que l’Atlas montre | Compromis à expliquer |
|---|---|---|
| Décommissionner après reprise des fonctions utiles | Fonctions transférées vers les solutions candidates, consommateurs redirigés et MD2 proposée au retrait final. | Toute la couverture nécessaire doit être validée avant l’arrêt ; la bascule concentre les dépendances à maîtriser. |
| Réécrire MD2 | Fonctions reconstruites dans la cible, interfaces à adapter et migration des données. | Peut répondre à des besoins spécifiques ; exige aussi de reconstruire et valider ce qui existe déjà ailleurs. |
| Remplacer progressivement, puis décommissionner | Fonctions reprises par étapes, MD2 conservée temporairement pour le périmètre restant, puis conditions de sortie. | Permet des validations successives ; impose une coexistence temporaire et une cohérence des données à gérer. |

Les trois options restent comparées au même périmètre fonctionnel. Le Travail distingue les impacts documentés des efforts, coûts et délais restant à estimer. L’Atlas représente les conséquences proposées, sans prétendre exécuter une simulation technique validée.

#### Séquence 4 — Recommander une trajectoire et préparer la décision

**Architecte :** « Quelle option recommandes-tu pour Polaris, et à quelles conditions ? »

**Flore :** « Avec les éléments disponibles dans ce scénario, je recommande un remplacement progressif, puis le retrait de MD2. Il permettrait de réutiliser les capacités existantes et de valider les reprises par étapes. La coexistence temporaire reste à maîtriser. »

**Activité visible :** préparation de la synthèse comparative ; regroupement des preuves ; identification des prérequis, responsables à confirmer et inconnues pouvant modifier le choix.

**Résultat :** l’Atlas affiche « Transition recommandée — à valider ». Il distingue ce qui est réutilisé, ce qui doit être adapté et ce qui reste temporairement dans MD2. Le Travail conserve :

- Les besoins Polaris auxquels la trajectoire répond.
- Les raisons de la recommandation et les compromis des autres options.
- Les règles, interfaces et données à reprendre.
- Les validations de couverture et de capacité des solutions candidates.
- Les tests, conditions de bascule, de retour arrière et de retrait final.
- Les équipes à mobiliser, les estimations manquantes et les points susceptibles de changer la recommandation.

**Flore :** « La prochaine étape est de valider les capacités de remplacement et d’estimer la transition avec les équipes. Si elles ne couvrent pas les besoins ou les contraintes de Polaris, la recommandation devra être revue. »

**Effet mémorable :** « Je vois les conséquences de chaque option et je comprends pourquoi l’une serait préférable. »
**Bénéfice :** décider d’une trajectoire de modernisation en reliant les besoins métier, les dépendances et les possibilités de réutilisation.

### A.4. Support TI — Relier les alertes à une situation exploitable

Mission : orienter le diagnostic lorsque des clients ne peuvent plus terminer leur demande.
Révélation : plusieurs symptômes ont une dépendance commune ; un changement récent fournit une hypothèse à vérifier.
Lectures successives de l’Atlas : symptômes → propagation et parcours touchés → hypothèse et périmètre de rétablissement.

#### Séquence 1 — Flore signale une situation à examiner

**Déclencheur : plusieurs signaux d’erreur du pilote Polaris ont été rapprochés.** Un indicateur « Situation à examiner » apparaît. L’équipe support n’a pas encore interrogé Flore.

**Flore :** « Des erreurs de validation de demandes apparaissent sur le portail et le poste conseiller. Les signaux sont proches dans le temps. Une situation commune est à examiner ; son origine n’est pas encore établie. »

**Support TI :** « Montre-moi les parcours touchés et ce qui pourrait relier ces erreurs. »

**Flore :** « Je vais qualifier le périmètre et examiner les dépendances communes. »

**Activité visible :** collecte des signaux préparés ; rapprochement des chronologies ; examen des dépendances communes.

**Résultat :** l’Atlas s’ouvre en lecture « Situation en cours ». Il montre les points où les erreurs sont observées et leurs parcours métier. Les éléments non touchés restent atténués pour délimiter le problème.

#### Séquence 2 — Concentrer le diagnostic

**Flore :** « Ces deux parcours utilisent la validation documentaire. Les erreurs y convergent ; les consultations sans validation continuent de fonctionner. »

**Support TI :** « Qu’est-ce qui a changé avant les premières erreurs ? »

**Flore :** « Je compare les changements récents aux premiers symptômes. »

**Activité visible :** consultation du journal des changements ; comparaison avec les erreurs ; recherche d’éléments compatibles ou contradictoires.

**Résultat :** le service partagé devient le centre de la lecture. Une chronologie associe le changement de configuration et le début des symptômes. Le lien causal porte « hypothèse à vérifier », jamais « cause confirmée » sur la seule base des horaires.

**Flore :** « Un changement de configuration précède les premières erreurs. C’est une piste prioritaire. Il faut vérifier la connectivité du service et la différence de configuration. »

#### Séquence 3 — Préparer l’intervention

**Support TI :** « Prépare l’intervention et ce qu’il faudra surveiller. »

**Flore :** « Je rassemble les vérifications, l’équipe responsable et les parcours à contrôler après intervention. »

**Activité visible :** consultation de la procédure disponible ; identification des conditions d’un retour arrière ; préparation des contrôles fonctionnels.

**Résultat :** une Investigation conserve l’hypothèse et les preuves. Le Travail lié présente les actions à valider. L’Atlas affiche les parcours à surveiller après rétablissement ; il ne les colore pas en “rétablis” sans observations.

**Flore :** « Voici le plan proposé et les contrôles de retour au service. Aucune modification n’a été exécutée. »

**Effet mémorable :** plusieurs alertes prennent la forme d’une situation compréhensible.
**Bénéfice :** concentrer le diagnostic et préparer une intervention avec ses limites.

### A.5. Développeur — Comprendre où intervenir et ce qu’il faut préserver

Mission : reprendre une évolution en cours pour éviter de redemander des pièces déjà valides ; tenir compte d’une connaissance nouvellement découverte.
Révélation : une règle partagée protège aussi la reprise d’anciens dossiers, dont certaines pièces peuvent ne plus être valides.
Lectures successives de l’Atlas : besoin métier → chemin applicatif → usages de la règle et impacts du changement.

#### Séquence 1 — Flore apporte une découverte au travail en cours

**Déclencheur : une nouvelle connaissance relie la règle étudiée à un autre parcours.** Le Travail du développeur existe déjà dans le scénario. Il porte l’évolution « Ne plus redemander une pièce déjà valide ». Un indicateur « Nouvelle connaissance liée à votre travail » apparaît.

**Flore :** « Une nouvelle utilisation de la règle que vous comptez modifier a été identifiée : elle intervient aussi dans la reprise d’anciens dossiers. Cela peut changer le périmètre de vos tests. »

**Développeur :** « Montre-moi où elle intervient et ce que cela change pour mon évolution. »

**Flore :** « Je vais préciser les conditions d’utilisation et les comportements à préserver. »

**Activité visible :** consultation du parcours ; recherche du point d’entrée ; examen des appels et de la règle métier associée.

**Résultat :** l’Atlas suit le chemin poste conseiller → service Dossiers → validation documentaire. Un panneau de détail présente la règle et ses références de code préparées. Les symboles de code ne sont pas présentés comme de nouveaux jumeaux.

#### Séquence 2 — Révéler le cas à préserver

**Flore :** « Cette règle est également utilisée lorsqu’un ancien dossier est repris. Certaines pièces peuvent alors nécessiter une nouvelle validation. »

**Développeur :** « Donc supprimer la vérification partout toucherait aussi ce parcours ? »

**Flore :** « Je vérifie les appels concernés et les tests disponibles. »

**Activité visible :** recherche des autres appels ; lecture des conditions de reprise ; examen des tests et des cas non couverts.

**Résultat :** l’Atlas passe à « Usages de la règle ». Deux chemins sont visibles : dossier courant et reprise d’un ancien dossier. Le second porte le cas particulier à préserver. Les preuves de code et de tests s’ouvrent à la demande.

**Flore :** « Oui. Pour répondre au besoin, il faut distinguer la pièce déjà valide de celle qui nécessite une nouvelle validation. »

#### Séquence 3 — Préparer une modification ciblée

**Développeur :** « Prépare le périmètre de modification et les tests à prévoir. »

**Flore :** « Je rassemble les points concernés et les comportements à vérifier. »

**Activité visible :** identification de l’adaptation candidate ; regroupement des références ; préparation des cas de test et des questions métier.

**Résultat :** un Travail présente les références à examiner, les contrats concernés et les tests : pièce valide, pièce refusée, validation expirée, dossier repris, statut inconnu. Les règles précises de validité restent à confirmer si elles ne sont pas établies.

**Flore :** « Voici une base de modification ciblée. Les comportements à préserver et les questions restantes sont attachés au travail. »

**Effet mémorable :** un ticket prend un sens métier, avec ses impacts au-delà du premier écran.
**Bénéfice :** préparer la livraison à partir d’une compréhension du code et de ses usages.

