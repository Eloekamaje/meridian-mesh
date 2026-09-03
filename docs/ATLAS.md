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

États de relation : `confirmee` (BCM déclaré, ardoise plein), `observee` (réalité découverte, turquoise + flèche), `supposee` / `contestee` (écarts, orange pointillés), `validation` (A2A, violet), `obsolete` (gris pâle).
