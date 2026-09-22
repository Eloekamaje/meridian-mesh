# Atlas — Documentation technique détaillée

L'Atlas est la cartographie vivante du Mesh et **la page d'accueil de Méridian** : une **carte mondiale unique et continue** (façon Google Maps) sur laquelle les jumeaux applicatifs, leurs domaines et leurs relations sont rendus. L'application suit un shell classique (en-tête + rail latéral permanents, zone centrale interchangeable) : l'Atlas partage la zone centrale avec les pages Actualités, Travaux, Jumeaux et Administration, et **son état (viewport, zoom, sélection, couches) est mémorisé entre les navigations**. Flore est la présence conversationnelle globale (en-tête + panneau droit). Ce document décrit son implémentation.

---

## 1. Principes fondamentaux (invariants)

Ces règles sont des **principes**, jamais des options :

1. **Monde continu** : une seule carte, des coordonnées monde stables. Aucune vue reconstruite, aucune téléportation, aucune « porte ».
2. **Zoom sémantique global** : le niveau de détail dépend **uniquement du facteur de zoom**, jamais de la taille d'écran ni du domaine traversé.
3. **Zéro chevauchement** : les nœuds (avatars + étiquettes) ne se superposent jamais — garanti par un algorithme de séparation déterministe.
4. **Responsive = chrome uniquement** : la taille d'écran ne change que l'interface autour de la carte (panneaux, boutons). La géographie du Mesh est invariante.
5. **Caméra conservée** : au redimensionnement ou changement d'orientation, le zoom et le point monde au centre sont strictement conservés. Jamais de `fitView` automatique.
6. **Glisser = pan pur** : le zoom reste **strictement constant** pendant un déplacement. Le zoom est toujours une action explicite (molette, boutons, double-clic, raccourcis).
7. **Chrome immobile** : les ancres d'interface (barre d'outils, zoom, mini-carte, recherche) ne se déplacent **jamais automatiquement**. Les panneaux prennent leur place dans le layout (colonne) ou en tiroir à côté — rien n'est jamais caché visuellement.

---

## 2. Stack technique

| Brique | Rôle |
|---|---|
| `@xyflow/react` (React Flow) | Affichage : pan, zoom, sélection, drag, rendu des nœuds |
| `libavoid-js` (WASM) dans un **Web Worker** | Routage orthogonal final des arêtes avec évitement d'obstacles |
| `routeur.js` (routeur maison) | Routage provisoire pendant le drag + secours si le Worker échoue |
| `concaveman` | Coques concaves (membranes) des domaines |
| Zustand (`useMesh`, `usePerimetre`, `useContexte`) | Données du Mesh, périmètre autorisé, contexte partagé (sélection, Flore) |

---

## 3. Architecture des fichiers

```
frontend/src/
├── pages/
│   └── Atlas.jsx                  # Hôte principal : état, interactions, pipeline graphe
├── lib/
│   ├── atlasGraph.js              # Construction du graphe (pur, testable)
│   ├── routage.js                 # Pont ↔ Worker libavoid (useRoutageFinal)
│   ├── routageWorker.js           # Web Worker : routage libavoid WASM
│   ├── routeur.js                 # Routeur orthogonal maison (provisoire/secours)
│   ├── domaines.js                # Couleurs de domaines, états de relations
│   ├── memoire.js                 # Mémoire personnelle locale (favoris, récents, recherches)
│   └── temps.js                   # Parsing dates, projection temporelle
└── components/map/
    ├── TwinNode.jsx               # Nœud jumeau (robot + App ID)
    ├── RegionNode.jsx             # Membrane de domaine (coque concave SVG)
    ├── AreteOrthogonale.jsx       # Rendu SVG d'une arête (points fournis par le routeur)
    ├── useNavigationAtlas.js      # Navigation (Explorer, fil d'Ariane passif…)
    ├── useZoomSemantique.js       # Niveaux de zoom sémantique
    ├── AtlasControle.jsx          # Panneau calques + modes temporels
    ├── AtlasToolbar.jsx           # Outils (déplacement, lasso, réorganisation…)
    ├── AtlasPanneau.jsx           # Panneau détail (desktop) / bottom sheet (mobile)
    ├── AtlasLegende.jsx           # Légende repliable
    ├── ExpliquerCarte.jsx         # Résumé textuel de la vue (WCAG)
    ├── FilAriane.jsx              # Fil d'Ariane passif
    └── details.jsx                # Vues détail (jumeau, relation, domaine)
```

---

## 4. Pipeline de construction du graphe

Le cœur est `construireGraphe()` dans `atlasGraph.js` — fonction **pure** qui prend le Mesh + l'état d'affichage et retourne `{ nodes, edges, snapshot }`.

```
mesh (API /api/mesh)
  │
  ├─ 1. Séparation anti-collision (separerNoeuds)
  │      Positions initiales (seed ou drag persisté) écartées itérativement
  │      pour garantir ≥ 105 px entre centres de jumeaux.
  │
  ├─ 2. Membranes (coqueOrganique)
  │      Coque concave (concaveman) calculée sur les centres des avatars
  │      de chaque domaine → path SVG polygonal + position du titre.
  │
  ├─ 3. Nœuds jumeaux
  │      Tous les jumeaux sont affichés individuellement (pas de regroupement).
  │
  ├─ 4. Arêtes (fabriqueOrtho)
  │      Choix des ports directionnels → géométrie des nœuds (geometrieNoeud)
  │      → routes provisoires (routeur maison) ou finales (libavoid)
  │      → ponts aux croisements → agrégation « N flux » (> 5 par paire).
  │
  └─ 5. Projection temporelle (appliquerTemps)
         Historique / avant-après filtrent ou mettent en évidence les relations.
```

Le `snapshot` géométrique retourné est poussé vers le Web Worker (§7).

### Réinjection des mesures React Flow

Le graphe est reconstruit à chaque tick de drag. Sans précaution, les nœuds reconstruits perdent leurs dimensions mesurées par React Flow et les arêtes disparaissent. `Atlas.jsx` conserve donc `measured`/`dragging` des nœuds internes et les reporte sur les nœuds reconstruits (`mesures`, `onNodesChange`).

---

## 5. Zoom sémantique — 4 niveaux

`useZoomSemantique.js` dérive le niveau du facteur de zoom, de façon **globale et uniforme** :

| Niveau | Seuil | Contenu |
|---|---|---|
| **1 — Capacités** | zoom < 0.6 | Robots masqués. Macro-territoires avec agrégats (« N jumeaux · N flux · N écarts »), corridors inter-domaines agrégés. Titres de domaines toujours visibles. |
| **2 — Domaines** | 0.6 ≤ zoom ≤ 1.15 | Robots (avatar 48 px) + App ID, membranes, routes orthogonales. Titres de domaines révélés au survol de la membrane. |
| **3 — Applications & flux** | 1.15 < zoom ≤ 1.9 | Robots agrandis (56 px), ports d'entrée/sortie visibles, labels de flux arbitrés par le moteur de labels. |
| **4 — Composants & preuves** | zoom > 1.9 | Carte de détail par jumeau : 6 icônes de sources (code, BDD, observabilité, incidents, documentation, événements) + 5 jauges de strates (identité, comportement, relations, trajectoire, mémoire). Placement directionnel arbitré (sous puis au-dessus du robot). |

Le niveau est affiché en bas de carte (`zoom-niveau`). Les seuils ne dépendent jamais de l'écran.

---

## 6. Les nœuds jumeaux (`TwinNode.jsx`)

Un jumeau = **avatar robot** (`/assets/robot-jumeau.jpg`, médaillon circulaire blanc) + **App ID** (identifiant numérique à 4 chiffres, hash stable `idNumerique()`) affiché **sous** l'avatar. Le nom complet n'apparaît pas sur la carte (il vit dans le panneau détail et le survol).

Variantes :
- **Normal** : robot + App ID.
- **Anonyme** (hors périmètre) : pastille pointillée + App ID + puce « résumé » — pas de robot, données limitées.
- **États visuels** : halo de domaine, anneau turquoise (sélection / relation liée), ping animé si actif, opacité réduite si hors focus.

### Anti-collision déterministe (`separerNoeuds`)

Avant toute construction, les positions sont corrigées : pour toute paire de jumeaux dont les centres distent de moins de **105 px** (avatar 56 px max + étiquette + marge), les deux sont écartés symétriquement le long de leur axe (angle déterministe par spirale de Fibonacci en cas de superposition parfaite). Jusqu'à 20 passes, convergence garantie. Le résultat alimente membranes, nœuds et routage — la cohérence est totale.

### Ports de connexion (Handles)

Chaque jumeau expose 8 handles React Flow (source + cible × 4 côtés : `s-r/t-r`, `s-l/t-l`, `s-t/t-t`, `s-b/t-b`). Les handles du bas sont placés **sous l'étiquette App ID** (et non sous l'avatar) pour coïncider avec la forme connectable déclarée au routeur (§7).

---

## 7. Routage orthogonal des arêtes

### Architecture à deux niveaux

| Étape | Moteur | Quand |
|---|---|---|
| **Provisoire** | Routeur maison (`routeur.js`) | Pendant le drag d'un robot (synchrone, immédiat) |
| **Final** | libavoid WASM dans un **Web Worker** (`routageWorker.js`) | Au repos — calcul asynchrone, jamais de blocage UI |
| **Secours** | Routeur maison | Si le Worker/WASM est indisponible (`console.warn`) |

### Géométrie déclarée au routeur (`geometrieNoeud`)

Pour chaque nœud, on déclare à libavoid :
- **Une forme connectable** (rectangle) avec 4 pins N/E/S/O. Pour un jumeau normal, elle englobe **l'avatar ET l'étiquette App ID + 4 px de marge** — ainsi une arête arrivant par le bas s'attache *sous* l'étiquette, sans jamais la toucher.
- **Des obstacles non connectables** : titres de domaines (`obstacleTitreRegion`), étiquettes des pastilles.
- La **membrane n'est jamais un obstacle** : les relations peuvent la traverser.

### Coûts et priorités (Worker)

Fonction de coût libavoid : `crossingPenalty 140` ≫ `fixedSharedPathPenalty 80` > `shapeBufferDistance 16` > `anglePenalty 24` > `segmentPenalty 10`, nudging des segments partagés activé (voies parallèles espacées de 5–7 px).

Les arêtes sont routées **par priorité décroissante** : `contestée 80` > `observée/validation 60` > `supposée 50` > `confirmée 40` > `obsolète 20` — les relations importantes obtiennent les corridors directs.

### Pipeline asynchrone (`useRoutageFinal`)

```
snapshot géométrique → signature dédupliquée (arrondie 2 px)
  → si inchangée : rien (pan/zoom ne recalcule JAMAIS les routes)
  → sinon : Worker → routes → interpolation 240 ms (easing-out)
    des anciens trajets vers les nouveaux (jamais de saut visuel)
```

### Rendu (`AreteOrthogonale.jsx`)

L'arête est dessinée en SVG **uniquement depuis `data.points`** (pas de rendu automatique React Flow) : segments orthogonaux, coins arrondis (rayon 6), ponts aux croisements (`sauts`), point d'arrivée coloré par domaine cible, marqueurs directionnels sur les relations observées, animation « point lumineux » au survol, capsule de label sur le segment horizontal le plus long.

### Agrégation « N flux »

Au-delà de **5 relations entre le même couple** de jumeaux : une voie unique épaisse « N flux » ; le survol déploie temporairement les routes membres (tooltip `agregat-tooltip`).

---

## 8. Membranes de domaines (`RegionNode.jsx` + `coqueOrganique`)

- Chaque domaine est une **coque concave polygonale** (`concaveman`, concavité 2.2) calculée sur les centres des avatars gonflés (marge ~50 px), angles adoucis quadratiquement.
- **Élastique** : recalculée à chaque déplacement/ajout/suppression de nœud. Un ressort rAF (poursuite exponentielle α≈9/s, ~300 ms) anime la membrane affichée vers sa cible — matière souple, sans vibration.
- **Titre du domaine** : rendu via `ViewportPortal` (au-dessus des arêtes), révélé **au survol de la frontière** (détection par distance point-segment, seuil 18 px / zoom), si le domaine est sélectionné, si la couche « Capacités » est active, ou au niveau 1. Arbitré par le **moteur de labels** (§7.5).
- Le titre est un **obstacle de routage** : aucune arête ne le traverse.

### 7.5 Moteur de priorité des labels (`placerLabels`)

Façon Google Maps : tous les labels ne sont jamais affichés en même temps. `placerLabels(candidats, obstacles)` pose les rectangles par **priorité décroissante** ; en cas de collision avec un label déjà placé ou un obstacle (bloc robot + App ID), le label le moins prioritaire **disparaît**. Un élément ne se masque jamais lui-même (exclusion par id).

Appliqué à :
- **Cartes niveau 4** : placement directionnel (sous le robot, puis au-dessus) ; priorité sélection > halo > couverture.
- **Labels de relations** (niveau 3+) : agrégats « N flux » > contestées > observées > supposées > confirmées.
- **Titres de domaines** : domaine sélectionné > survolé > halo > investigations actives.

---

## 9. Navigation & caméra

### Gestes (façon Google Maps)

| Action | Effet |
|---|---|
| Glisser fond | Pan pur, **zoom strictement constant**, avec **inertie** (échantillonnage 180 ms, décélération exponentielle amortie) |
| Molette | Zoom ancré au pointeur (natif React Flow) |
| Double-clic zone vide | Zoom +35 % centré sur le pointeur |
| `+` / `−` / `0` | Zoom avant / arrière / ajuster à la vue |
| Double-clic membrane ou titre | **Explorer** : déplacement animé à zoom constant |
| Double-clic jumeau | Déplacement + zoom explicite centré (×1.6, borné [1.5, 2.4]) |
| « Ajuster au domaine » | `fitBounds` explicite |
| « Mesh global » (fil d'Ariane) | `fitView` explicite |

### Fil d'Ariane passif (`useNavigationAtlas`)

Le domaine affiché est celui qui contient le **centre du viewport**, stabilisé 400 ms (pas de clignotement entre deux membranes). Il **ne déplace jamais la caméra** ; il est synchronisé explicitement par les navigations programmées (URL `?domaine=`, Explorer, double-clic).

### Conservation au redimensionnement

Un `ResizeObserver` recalcule uniquement la translation pour conserver le **même zoom** et le **même point monde au centre** (delta < 1e-3 px). Jamais de `fitView` automatique.

---

## 10. Modes temporels (`AtlasControle.jsx` + `appliquerTemps`)

Projection des relations selon leur date de découverte (`decouverte_quand`) :

- **Direct** : temps réel, activité simulée (halos).
- **Pause** : fige l'activité.
- **Replay** : relecture animée de la construction du Mesh (50 pas de la 1ʳᵉ relation à maintenant).
- **Historique** (`?date=AAAA-MM-JJ`) : masque les relations découvertes après la date.
- **Avant/Après** (`?avant-apres=AAAA-MM-JJ`) : surligne en tirets cyan les nouvelles relations (« nouvelle »), estompe les anciennes, compteur dans le bandeau.

---

## 11. Interactions principales

### Couches (catégories façon Google Maps)

Six puces en haut de carte — **jamais de déplacement des jumeaux**, uniquement visibilité/importance :
- **Relations** : BCM déclaré, Réalité découverte, Écarts (masquent les arêtes correspondantes).
- **Carte** : Situations (point violet sur les jumeaux impliqués), Capacités (titres + agrégats des domaines épinglés), Transformations (badge ambre pointillé sur les jumeaux en construction/observation).
- Sur petit écran : un bouton « Couches » ouvre les options secondaires.

### Navigation personnelle (barre verticale)

Sous les outils de la barre gauche : **Favoris**, **Consultés récemment**, **Investigations**, **Situations** — chacun ouvre la liste correspondante dans le panneau contextuel. Mémoire **locale** (`localStorage meridian:*`) : étoile favori dans le détail jumeau, récents alimentés par la consultation, recherches mémorisées.

### Panneau contextuel

Le panneau ne décrit que l'élément actif (jumeau, relation, domaine, comparaison, liste). **À vide**, il montre : favoris, jumeaux consultés récemment, recherches récentes, situations à reprendre. Fermable pour retrouver toute la surface. La barre conversationnelle Flore est un **FAB flottant repliable** (bas-droite desktop, bas-centré mobile) — jamais un pied de page.

- **Survol robot** : panneau flottant d'aperçu (desktop) ; arêtes connectées accentuées, autres estompées.
- **Clic robot** : épingle l'aperçu + ouvre le détail dans le panneau / la bottom sheet.
- **Clic membrane** : sélection du domaine → panneau détail (stats, flux, écarts, équipes, actions Explorer/Ajuster/Comparer/Enregistrer comme vue).
- **Survol arête** : trajet mis en avant, tooltip (état, extrémités).
- **Lasso** (outil dédié) : sélection multiple, ajoutée à la sélection existante.
- **Mode réorganisation** (explicite) : seul mode où les robots sont déplaçables. Position fantôme au départ ; au relâchement, persistance (`PATCH /api/jumeaux/{id}`) et **reclassification proposée, jamais automatique** si le robot atterrit dans un autre domaine.
- **Recherche** : jumeau (nom ou App ID) ou domaine → caméra animée + halo.
- **Focus profond** (`?situation=` / `?focus=`) : cadre les jumeaux concernés, estompe les autres, bandeau de contexte.

### Positionnement du chrome — modèle Google Maps (invariant 7)

Le **chrome ne bouge jamais** : barre d'outils (gauche, centrée), contrôles zoom et mini-carte (bas-droite), recherche (haut-centre) ont des ancrages fixes. Aucun décalage automatique.

- **Panneau détail = colonne de layout** à droite (`AtlasPanneau presentation="colonne"`, 320/336 px, pleine hauteur). La carte se redimensionne (`flex`) : la mini-carte et le zoom restent ancrés aux coins du conteneur carte — jamais cachés, jamais déplacés. Panneau fermé avec sélection active : rail fin de 40 px (bouton de réouverture). La caméra est conservée par le `ResizeObserver` (centre monde invariant).
- **Panneau Calques = tiroir** : déplié, il s'ouvre à `left:74px`, à droite de la barre d'outils qui reste fixe ; rétracté, simple chip à `left:16px`.
- **Piles verticales** : recherche + fil d'Ariane + bannières (situation, périmètre) empilés en haut ; chips contextuelles (vue Flore, mode réorganisation, bandeaux temporels) + niveau de zoom empilés en bas — chaque élément occupe sa propre ligne, jamais de superposition.
- **Déplacement manuel** : la barre d'outils et le panneau Calques restent glissables par poignée (`useGlissable`, persistance `localStorage atlas.chrome.decals`, bornés au conteneur, double-clic sur la poignée = retour à l'ancrage par défaut).
- **Flore** reste un overlay fixe à droite (440 px) : la caméra glisse de 220 px pour compenser (pan pur, zoom constant).

---

## 12. Responsive (chrome uniquement)

| Taille | Adaptations |
|---|---|
| Mobile ≤ 640 px | Bottom sheet (`AtlasPanneau presentation="feuillet"`) au lieu du panneau latéral ; minimap → bouton « Vue d'ensemble » ; recherche et composer Flore → boutons flottants |
| Tablette ≤ 1024 px | Bottom sheet ; sidebar applicative repliée ; **mode immersif plein écran** (`atlas-immersif` masque sidebar + topbar, caméra conservée) |
| Tactile (`pointer: coarse`) | Tap zone vide de membrane = sélection du domaine ; zones d'interaction des arêtes élargies (22 px) ; contrôles ≥ 44 px |

**Jamais** de changement de géographie, de niveau sémantique ou de routage en fonction de l'écran.

---

## 13. Accessibilité

- **« Expliquer cette carte »** (`ExpliquerCarte.jsx`) : résumé textuel structuré de la vue courante (résumé Mesh, position, domaines + maturités, relations par état, sélection), `role="complementary"`.
- Contrastes AA, focus visibles, `prefers-reduced-motion` respecté.

---

## 14. Données

| Source | Contenu |
|---|---|
| `GET /api/mesh` | Jumeaux (positions stables, strates, couverture), relations (état, dates de découverte), régions |
| `PATCH /api/jumeaux/{id}` | Persistance position (drag) / reclassification |
| `POST /api/relations/{id}/confirmer` | Validation d'une relation découverte |
| `GET /api/activite` | Activité simulée (halos, mode direct) |
| `GET /api/situations` | Stats de domaines (investigations, découvertes) |
| `GET /api/mesh/vue` | Vue bornée du Mesh (fenêtre monde + zoom) pour le passage à l'échelle — voir §15 |

États de relation : `confirmee` (BCM déclaré, ardoise plein), `observee` (réalité découverte, turquoise + flèche), `supposee` / `contestee` (écarts, orange pointillés), `validation` (A2A, violet), `obsolete` (gris pâle).

---

## 15. Rendu « graphe » et passage à l'échelle

**Rendu par défaut** (`?rendu=classique` rétablit l'ancien) : mêmes coordonnées et mêmes panneaux, mais plus de territoires : fond uni avec trame de points (comme `/labo/atlas`), les domaines se lisent par leur couleur et par la légende-filtre en bas à gauche (case = afficher/masquer, nom = ouvrir le domaine). Le détail du jumeau ou du domaine s'ouvre à droite et replie la barre latérale en icônes tant qu'il reste ouvert. Le survol affiche la fiche d'aperçu du labo. La recherche vole jusqu'au jumeau (zoom 1,2). « Parler au jumeau » crée un travail (avec le jumeau en contexte) et ouvre sa page ; les jumeaux sont les robots du film teintés par domaine (taille selon le degré, nom affiché pour les plus connectés, écart de communauté en pointillé), les liens sont des courbes directes stylées selon l'état de la relation. Au survol d'un jumeau, ses voisins restent éclairés et le reste s'estompe. Il n'y a plus de vue « étoile » ni de corridors « N flux » : les robots sont visibles à tous les zooms. Code : `NoeudGraphe`, `AreteGraphe`, `lib/atlasRendu.js`.

**Échelle.** Au-delà de 300 jumeaux (ou avec `?echelle=N`, jeu synthétique de N jumeaux), l'Atlas ne charge plus le graphe : `AtlasEchelle` (canvas) demande à `GET /api/mesh/vue` la fenêtre visible et le zoom. Le serveur (`backend/pyramide.py`) répond avec un nombre **borné** d'éléments, quel que soit n : grappes de domaines, de groupes ou de communautés (avec leurs signaux : écarts en violet, situations en orange), puis points, puis jumeaux individuels et leurs liens. Les droits s'appliquent **avant** l'agrégation : une grappe ne compte jamais un jumeau que le persona ne peut pas voir. Mesuré : 1 M de jumeaux, construction ≈ 0,6 s, chaque vue 1 à 15 ms côté serveur.

Limites connues : `/api/mesh` reste plafonné à 200 jumeaux ; la recherche, le panneau du jumeau et la sélection multiple de l'Atlas s'appuient encore sur ce Mesh chargé (en vue à l'échelle, seuls les jumeaux qu'il contient s'ouvrent) ; les dépendances restreintes anonymisées ne figurent pas dans les vues agrégées.

**Palette : le bleu du site.** Le style de hubstechs.com (polices, angles vifs, rouge, capitales) a été essayé puis abandonné ; seule sa couleur bleue est retenue, partout : le violet et le turquoise d'accent sont remplacés par `#60A5FA` (clair `#93C5FD`, très clair `#BFDBFE`, foncé `#3B82F6`) dans le code (classes, styles, `rgba`), et `--primary`, `--accent`, `--ring` sont bleus. Ce qui reste hors bleu est volontaire : les couleurs de domaine, le vert de succès (« actif », « prête »), l'ambre et le rouge d'alerte. États de lien : observée = bleu, validation A2A = bleu clair (en tirets), supposée = ambre, contestée = rouge.

**Polices : celles de l'appareil.** Méridian n'embarque ni ne télécharge aucune police : `--font-sans`, `--font-display` et `--font-mono` (dans `index.css`) désignent la police système de l'appareil qui l'ouvre (San Francisco sur Mac/iOS, Segoe UI sur Windows, Roboto sur Android, la police système sur Linux ; `ui-monospace` pour le code et les étiquettes), avec les polices d'emoji en secours. Pas de dépendance à internet (kiosque hors ligne compris) ; en contrepartie les largeurs de texte varient d'un appareil à l'autre — ne pas aligner l'interface au pixel sur une largeur de texte.

**Responsive.** Trois tailles (`lib/ecran.js`, `useEcran()`) : *bureau* ≥ 1024 px, *tablette* 768–1023 px, *mobile* < 768 px. La coquille (`Layout`) s'adapte : bureau = barre latérale en colonne (repliable) ; tablette = rail d'icônes de 56 px, la barre complète s'ouvre en tiroir par-dessus le contenu ; mobile = barre supérieure (menu, logo, « + Nouveau travail ») et menu en tiroir. Le tiroir se ferme au changement de page, au toucher du fond et sur Échap. Pages : marges réduites, barres d'outils qui passent à la ligne, listes qui masquent leurs colonnes secondaires (Jumeaux) ou leurs actions de survol (Travaux : la ligne entière est cliquable), tableaux qui défilent horizontalement plutôt que de s'écraser. Travail : le volet Résultats & Sources est fermé par défaut hors grand écran et s'ouvre en feuille pleine largeur ; le canvas passe en plein écran par-dessus la conversation. Atlas : les panneaux de détail deviennent des feuilles en bas d'écran, le zoom minimal est abaissé pour voir tout le Mesh. La démonstration reste conçue pour un grand écran tactile.

**Cohérence des pages (revue critique).** En-tête commun `EntetePage` / `BoutonRetour` pour les pages de détail (revue d'un jumeau, commande, rapport « Comprendre », travail, investigation) : bouton retour au même endroit et de même style (icône seule sur téléphone), titre, repères, actions ; le bouton décisif de la revue (« Confirmer l'admission ») reste collé en bas de l'écran. Lisibilité : plancher de 11 px (les micro-étiquettes 8–10 px sont relevées, `index.css`) ; au toucher, boutons et champs ≥ 40 px, cases à cocher 24 px. Actualités : titre de page (lecteurs d'écran), « L'essentiel » non répété. Il n'y a plus de page « Investigations » : une situation à investiguer est un travail (voir ci-dessous). Jumeaux : barre d'action dès qu'un jumeau est coché ; « Revoir l'admission » en contour. Administration : filtre par jumeau, couleur des barres = niveau de couverture (pas le domaine) avec légende, jumeaux cliquables vers leur revue, matrice avec coche/tiret. Commande : sur petit écran, l'inspecteur et le catalogue s'ouvrent en feuille, l'étape en une ligne. Démonstration : le parcours disponible est mis en avant, les autres sont listés en « Prochains parcours ». Les pages `/labo/*` ne sont servies qu'en développement (ou avec `REACT_APP_LABO=1`).

**Veille après décision.** (Projet-Meridian : Continuous Improvement & Learning Model, « Decision Handoff ».) Une décision enregistrée avec sa *note de passation* (hypothèses, résultats attendus avec départ et cible, risques à surveiller avec seuil, inconnues, date de revue) met le travail en veille. Les jumeaux rapportent des observations (`POST /api/cases/{id}/veille/observations`) ; `backend/veille.py` (module pur) les confronte à la note et n'écrit dans le fil que ce qui change la compréhension de la décision : **écart avec l'attendu**, **risque matérialisé**, **revue due** (niveau 1, « décision remise en question »), **objectif atteint**, **inconnue levée** (niveau 2), progression ou risque maîtrisé (niveau 3). Événements calculés à la lecture, identifiants stables (jamais dupliqués), filtrés par périmètre (un jumeau hors droits n'apparaît pas). **La revue est une question de Flore, pas un bouton** : quand la date est atteinte, Flore écrit dans le fil, à la première personne, le bilan (objectifs atteints, écarts, risques matérialisés, inconnues levées), recommande une issue et propose trois réponses rapides sous son message (rouvrir, maintenir, clore). Le choix apparaît comme le message de la personne, Flore répond (rouvrir : ce qui a changé et quelle option réexaminer ; maintenir : nouvelle revue dans 30 jours). Les faits observés par les jumeaux restent des cartes d'événement (source et jumeau visibles) ; l'écriture des événements est atomique (lectures simultanées sans doublon). Mise en avant : événements « Nouveau » dans le fil, pastille dans « Récentes » (le travail qui bouge monte), compteur sur « Travaux », « En veille / à examiner » dans la liste, carte « Décision en veille » avec « Pourquoi maintenant » dans Actualités. Les observations de démonstration sont amorcées dans `seed_data.py` (travail « Réduire la dépendance aux files legacy ») ; le moteur de raisonnement réel devra exposer ces mesures.

**Un travail en veille se lit comme une conversation.** Chronologie du fil : les échanges, puis **la décision** (Flore l'enregistre dans la conversation, dit ce qu'elle observera et quand elle reviendra), puis les faits observés (cartes), puis la question de revue. À la réouverture, le fil se place sur « Nouveau depuis votre dernière visite » et **Flore accueille avant les cartes** (« Bon retour. Depuis votre dernière visite… », ce qui demande l'attention) ; ce message est calculé pour la personne, rien n'est stocké. Le positionnement du fil ne dépend plus du nombre d'exécutions de l'effet (le mode développement de React les double).

**Une actualité qu'on ouvre devient un travail.** `POST /api/actualites/histoire/{id}/travail` (intention : `comprendre`, `suivre`, `investiguer`) crée le travail — ou rouvre celui de cette actualité pour cette personne, sans doublon, en y ajoutant l'intention nouvelle — et y écrit la première parole de Flore, selon ce qui a été demandé : *comprendre* = Flore présente la situation (lecture, pourquoi cela compte, ce qui reste à comprendre, décisions attendues) ; *suivre* = elle explique qu'un phénomène est incertain et le garde sous vérification ; *investiguer* = elle pose la question de l'investigation et propose de la cadrer (`backend/ouverture_travail.py`). Le message porte ses preuves (dépliables) et des pistes à creuser (un clic les envoie comme question). C'est la même page que tout travail ; on y arrive avec le retour vers Actualités mis en évidence (`location.state.retour`). L'ancienne page « Comprendre » n'est plus qu'une redirection vers le travail. Le repère « nouveau depuis votre dernière visite » ne compte plus vos propres messages, et la fenêtre « Sources & Jumeaux » est fermée par défaut.

**Propositions du Mesh et situations : même chemin.** Les cartes du Radar et de « À traiter » suivent la même logique que les actualités. `POST /api/initiatives/{id}/travail` (idempotent par `origine.initiative_id` et responsable) ouvre un travail où Flore présente ce que Méridian a découvert (raison, « pourquoi vous », impact, confiance, périmètre, ce qui est attendu) ; « Suivre » et « Créer un travail » passent par le même helper (`travail_de_initiative`, intentions `suivre` / `investiguer`), « Ajouter » écrit un message de Flore dans le travail existant. Les **décisions attendues** d'une situation sont des réponses rapides sous le message de Flore ; un clic les envoie comme message de la personne (`POST /api/cases/{id}/decision-attendue` : statut de la situation, confirmation de relation ou décision selon le cas), Flore répond et une trace « Décision prise » reste dans le fil. Les pages `Investigations` et `InvestigationDetail` sont supprimées : `/investigations` redirige vers `/travaux`, `/investigations/:id` ouvre le travail de la situation, et l'entrée de menu a disparu.

**Aujourd'hui : un budget d'attention.** (Projet-Meridian : « Attention budget », « Why now ».) La vue du jour (`GET /api/actualites`, onglet « Aujourd'hui ») ne montre que ce qui mérite l'attention : **trois choses critiques au plus** (incident prioritaire, décision en veille remise en question) puis **cinq pertinentes au plus** ; le journal de gouvernance n'est jamais une priorité. Le reste est replié derrière « Le reste — N autres » (sections, six cartes par section puis « Afficher N de plus »). Le briefing de Flore compte ce qui est montré, pas tout. Une période (7 ou 30 jours) n'a pas de budget. Chaque carte porte son *pourquoi maintenant* quand il existe (fait observé, décision attendue, coût de l'inaction d'une opportunité) et son *action recommandée* (« Revoir la décision », « Décider », « Évaluer l'opportunité »). L'heure d'une carte n'est affichée que si le fait date d'aujourd'hui, sinon le jour (une heure sans jour trompait). **Écarter** : menu de la carte → raison (déjà connu, ne me concerne pas, trop tôt, traité ailleurs) ; l'actualité sort de la vue de la personne (`POST /api/actualites/histoire/{id}/ecarter`), la raison est gardée, la liste « N écartées » permet de la rétablir (ou « Annuler » dans la notification).

**Opportunités : un genre à part entière.** Une situation de nature `opportunite` porte un bloc `opportunite` (gain, effort, ce qui se passe si rien n'est fait). Elle a sa section « Opportunités », son type de travail (`opportunite`), sa couleur (vert) et sa parole de Flore (« J'ai repéré une opportunité… » : ce qu'on peut y gagner, ce que cela demande, si rien n'est fait). Une opportunité n'est jamais urgente : sans place réservée elle ne serait jamais vue, la meilleure occupe donc toujours une des places « pertinentes ». Décisions attendues : *Poursuivre* (situation « poursuivie », Flore propose la note de passation), *Reporter*, *Écarter* (statut et trace conservés pour ne pas la reproposer sans élément nouveau). Les opportunités de démonstration sont amorcées par une migration douce au démarrage (`server.py`), sans réinitialiser la base.

**Consigner une décision, avec sa note de passation.** Depuis le fil : après une décision qui engage (poursuivre une opportunité, décision d'une situation), Flore propose « Consigner ce que j'en attends » ; depuis n'importe quel travail : menu « ⋯ » → « Consigner une décision ». Un volet s'ouvre (`DecisionPassation`) : la décision, ce sur quoi elle repose (hypothèses), ce qu'on en attend (indicateur, départ, cible, unité), ce qu'on surveille (risque, jumeau, seuil, sens), ce qu'on ignore encore, la date de revue. Flore préremplit ce qu'elle sait (`GET /api/cases/{id}/passation/brouillon` : hypothèses et inconnues de la situation, revue à 30 jours, gain annoncé rappelé) mais **n'invente ni indicateur ni chiffre** ; le bouton reste bloqué tant qu'il n'y a rien à observer ou qu'une ligne est à moitié remplie. Le serveur normalise la note (`normaliser_passation` : identifiants stables, sens déduit du départ et de la cible, nombres et date validés → 400 sinon). Une note sans rien à observer garde la décision mais ne met pas en veille. Consignée, la décision met le travail en veille (Flore l'écrit dans le fil, dit ce qu'elle observera et quand elle reviendra).

Tests : `tests/test_attention_opportunites.py` (budget, opportunités, écart, passation) ; les tests qui créent des travaux les suppriment en base à la fin du module (`tests/nettoyage.py`).

**Suivre = vérifier : la veille avant la décision.** (`backend/maturation.py`, module pur.) Quand on suit un phénomène encore incertain (« Suivre la vérification » sur une actualité, « Suivre » sur une proposition du Radar), le travail entre en veille de *maturation* (`veille.mode = "maturation"`) : Flore dit ce qu'elle guette (confiance de départ, seuil de confirmation, seuil d'abandon) puis observe si les preuves s'accumulent ou s'effritent. Les jumeaux rapportent des indices (`POST /api/cases/{id}/veille/observations` avec `effet` en points de confiance, entre −40 et 40, et le texte observé). Seuils par défaut : confirmer à 75 % (ou départ + 10 au-delà de 70), écarter sous départ − 25. **Entre les deux, Flore ne dérange pas** : les indices s'ajoutent au fil (cartes « Indice en faveur / contraire », niveau 3). Quand un seuil est franchi (une seule fois, message atomique), Flore pose la question à la première personne, avec sa recommandation et trois réponses rapides : *Confirmer* (la relation passe à « confirmée » si la personne a la permission « Valider », sinon 403), *Continuer d'observer*, *Écarter* (la situation est classée, la trace des indices contraires est gardée). Le bandeau du travail affiche la confiance et les seuils ; « En vérification » remplace « En veille » dans la liste ; l'actualité correspondante est du genre « Vérification en cours » avec l'action « Trancher ». Démonstration : le travail « Vérifier la relation possible Fraude → Conformité » (relation r12), ajouté par migration douce.

**Répondre à une proposition, confier un mandat : dans un travail.** Une réponse à une proposition du Mesh (choisir une option, « Comparer les options », « Demander une validation », « Je ne sais pas ») s'écrit dans le travail : rattachée au travail existant de la proposition, sinon elle en ouvre un ; la réponse est *votre message*, Flore l'enregistre et, pour un choix, propose de consigner ce qu'on en attend (note de passation). « Rejeter » et « Ignorer » restent de simples réponses. Une **délégation** (« Surveiller 24 h », « Comparer les scénarios », « Demander confirmation ») est aussi un travail : Flore y dit le mandat (périmètre, durée, sources, ce qu'elle produira, limites) ; une fois l'échéance passée, la délégation est « terminée », son travail est clos et Flore le dit sans prétendre de résultat. Les délégations d'avant sont rattachées à un travail à la première lecture. Suivis : chaque délégation et chaque proposition suivie a son « Ouvrir le travail ».

**À qui appartient un travail : trois portées.** (`backend/portee.py`.) Une personne emploie Méridian pour ses besoins et *cède* ce qu'elle veut à son équipe ou à l'entreprise ; le responsable décide, par le bouton de l'en-tête du travail (« Moi seul / Équipe / Entreprise », `POST /api/cases/{id}/portee`, tracé dans l'historique). **Personnel** : le responsable et les participants ; **Équipe** : en plus, tous ceux qui travaillent dans le même espace ; **Entreprise** : tous ceux dont les droits sur les jumeaux le permettent. La portée ne donne jamais plus que le périmètre : un jumeau hors droits reste invisible. Tout travail neuf (ouvert depuis une actualité, une proposition, une délégation, ou créé) est **personnel** ; les travaux du jeu de données d'origine, sans portée, sont d'entreprise. Un travail personnel ou d'équipe n'est pas non plus une actualité pour ceux qui ne le voient pas, et donne 403 s'ils tentent de l'ouvrir. Écarter une actualité se choisit aussi **pour moi** ou **pour l'équipe** (l'espace courant) ; un collègue de l'espace peut la rétablir, l'écart personnel prime.

**Aller plus loin sur les limites.** *Observations* : `POST /api/observations` est le point d'entrée des jumeaux (réservé aux rôles du Mesh global) ; le moteur de raisonnement rapporte UNE mesure et Méridian l'aiguille vers toutes les veilles ouvertes qu'elle concerne : une vérification (par `relation_id` et `effet`, seulement si le jumeau fait partie du travail) ou la note de passation d'une décision (par le libellé de l'indicateur, du risque ou de l'inconnue). Réponse : la liste des veilles atteintes. *Équipes* : `EQUIPES` et le champ `equipe` des personas (un second membre de l'équipe Paiements, M. Diallo, permet de la vivre) ; la portée « équipe » d'un travail désigne l'équipe de son responsable, quel que soit l'espace choisi ; écarter « pour l'équipe » suit la même équipe ; les travaux partagés avant les équipes retombent sur l'espace. *Confier* : « ⋯ → Confier à… » associe une personne nommée au travail ou lui en transfère la responsabilité (seul le responsable ; la personne doit avoir les droits sur les jumeaux, sinon 403 ; elle est notifiée ; Flore l'écrit dans le fil). *Propositions déjà suivies* : rattachées à leur vérification à la première lecture de « Suivis » par celui qui les a suivies.

**Panneau du jumeau : le même à toutes les tailles.** `PanneauJumeau` est le seul panneau de détail d'un jumeau : colonne de 400 px sur bureau, superposé à droite de la carte sur tablette (641–1024 px), feuille en bas d'écran sur téléphone (poignée pour le réduire). Même contenu partout (sources, voisins, changements récents, actions), plus d'onglet Chronologie propre au jumeau sur petit écran. Le panneau des domaines, relations et listes suit la même règle (colonne / superposé / feuille).

**Palette : plus de turquoise.** Le bleu du site (`#60A5FA`, `#93C5FD`, `#BFDBFE`, `#3B82F6`) remplace les bleus ciel et cyan (`#38BDF8`, `sky-*`, `#0891B2`) des accents. Les domaines n'ont plus de teinte cyan/turquoise : Opérations est lime (`#A3E635`), Client vert franc (`#4ADE80`). Vérifié par un audit des styles calculés de toutes les pages et de l'Atlas (aucun élément de teinte 165–200°). Ce qui reste hors bleu est volontaire : verts de succès, ambre, rouge.

Limites restantes : les observations viennent d'un appel d'API (la démonstration les amorce en base) — aucun moteur de raisonnement réel n'appelle encore `/api/observations` ; les équipes sont une liste du jeu de données, sans gestion (création, membres) ; on confie à une personne, pas à un rôle ni à une équipe entière.

**Gestion de projet : ce que les jumeaux savent par Jira.** (Projet-Meridian : Jira est une source — projets, tickets, historique, liens ; Continuous Improvement § 8 : *Méridian ne doit pas devenir Jira*.) Jira devient une source des jumeaux (`sources.projet`, listée dans « Sources de connaissance » et dans la matrice d'Administration) et alimente leur strate « trajectoire ». Le Mesh ne garde pas les tickets : il garde les **chantiers** (`EPICS` : référence, statut *en cours / planifié / bloqué / reporté / livré*, échéance, décompte des tickets ouverts et bloqués, jumeau porteur, jumeaux touchés, travail Méridian lié) — ce qui éclaire le Mesh et relie une décision à son action. Projetés par `projete_jumeau` : `projets_resume` (vivants, bloqués, prochain jalon) dès le niveau « résumé », `projets` dès « preuves » ; **les droits s'appliquent** : les jumeaux touchés hors périmètre sont retirés, un chantier porté par un jumeau invisible reste connu mais son porteur est masqué. Où cela se voit : *Atlas* — couche « Projets (Jira) » (pastille avec le nombre de chantiers sur chaque robot, rouge s'il y a des tickets bloqués), ligne « N chantiers Jira · M bloqués » dans la fiche d'aperçu, recherche d'un chantier (« PAY-122 » vole jusqu'au porteur et éclaire les jumeaux touchés) ; *panneau du jumeau* — rubrique « Gestion de projet · Jira » (bloqués d'abord, jumeaux touchés cliquables, lien vers la décision liée) ; *Flore* — répond sur les chantiers (« quels chantiers sont bloqués ? », avec ou sans sélection, dans les droits de la personne) ; *Actualités* — genre « Trajectoire » (la trajectoire déclarée dans Jira contredite par la réalité observée : PAY-140 suppose la fin d'OPS-15, qui est bloqué) ; *décision* — la note de passation porte une **référence de chantier externe** (`reference` : Jira PAY-140, validée, complétée du titre si connu ; le brouillon de Flore propose le chantier déjà rattaché au travail). Limites : données amorcées en base (le connecteur Jira réel n'existe pas encore) ; pas d'écriture vers Jira ; la couche n'affiche qu'un décompte, pas la carte des dépendances entre chantiers.

**Salutation et heure du jour.** « Bonjour » porte le nom du profil connecté (celui de la barre latérale, `useIdentite`), pas celui du rôle joué. La vue du jour ne transmet plus de date au serveur : « aujourd'hui » est celui du serveur (UTC) ; avant, le soir dans un fuseau en retard sur UTC, la vue devenait « hier » et perdait son budget d'attention.

**Un seul panneau de détail dans l'Atlas.** Le panneau à onglets « Détail / Chronologie » est supprimé. `PanneauLateral` est la coque unique (en-tête, fermeture, colonne / superposé / feuille) ; le jumeau (`PanneauJumeau`) et le domaine, la relation, la comparaison et les listes personnelles (`AtlasPanneau`, désormais un simple contenu) s'y posent chacun avec leurs propres informations. La chronologie n'est plus un onglet : c'est une rubrique « Chronologie » du détail d'un domaine (les événements de ses jumeaux). Quand Flore occupe la colonne droite, le panneau (jumeau compris) s'efface : les deux se remplacent.

**Laboratoire · Atlas à l'échelle, avec des centaines de domaines.** (`/labo/atlas-etendu`, remplace l'ancien « Atlas vivant » — projection isolée, données et rendu qui n'étaient pas ceux du produit.) Le laboratoire ne réimplémente rien : il réutilise `AtlasEchelle` (le composant que l'Atlas réel bascule sur, au-delà de 300 jumeaux) et les mêmes panneaux (`PanneauJumeau`, `PanneauLateral`), branchés sur un essai synthétique — jusqu'à 5 millions de jumeaux, jusqu'à 2 000 domaines fictifs. Mêmes comportements que l'Atlas réel : fiche d'aperçu au survol, panneau de détail à droite, recherche qui vole jusqu'à sa cible (un numéro trouve un jumeau, un nom trouve son domaine — `GET /api/mesh/vue/localiser`), « Parler au jumeau » qui ouvre un travail (sans `jumeaux` : l'identifiant synthétique n'existe dans aucun périmètre réel, l'y mettre bloquerait ensuite l'accès au travail), légende groupée par famille et triée par population (les plus gros domaines d'abord, le reste filtrable), menu qui se replie tant qu'un panneau est ouvert.

Détail d'un jumeau à la demande : `GET /api/mesh/vue/jumeau` (mission, propriétaire, statut, autonomie, couverture, fraîcheur, capacités, sources — générées, déterministes par (graine, domaines, i), jamais dans la réponse d'un viewport qui doit rester légère).

**Disposition organique, des centaines de domaines sans grille.** (`backend/pyramide.py` : `palette_domaines`, `_disposer_domaines`.) Une COULEUR par domaine, groupée par FAMILLE (teinte de base sur ≈ √D emplacements du cercle, nuance de luminosité/saturation pour chaque domaine de la famille) — déterministe, ne dépend que du nombre de domaines. Une loi de puissance BORNÉE donne quelques domaines « hubs » sans qu'aucun n'avale une part disproportionnée du Mesh (essai vérifié : jamais plus de 5 % à des centaines de domaines — sans plafond, un seul astre géant et de la poussière, plus de galaxie). Les centres de domaines se placent par une DOUBLE SPIRALE DE VOGEL (tournesol : angle d'or, rayon en racine du rang — la même technique que celle qui place déjà les jumeaux au sein d'un domaine, ici appliquée au niveau des domaines) : chaque famille occupe un bras de la spirale grossière, ses domaines une spirale locale autour du centre de leur famille. Purement déterministe, bornée, quasiment sans chevauchement de territoire (vérifié à 300+ domaines). Dézoomé au maximum, l'œil ne distingue que des galaxies de couleur groupées par famille (comme `graphify-out/graph.html`, un graphe forceAtlas2 coloré par communauté) ; en zoomant, elles se résolvent en grappes puis, tout près, en robots individuels.

Limites : les identifiants synthétiques (`synth-…`) ne correspondent à aucun jumeau réel — « Parler au jumeau » depuis le laboratoire crée un vrai travail (sans jumeaux rattachés) ; un peu de chevauchement de territoire subsiste à plus de 500 domaines (quelques paires sur des centaines de milliers).

