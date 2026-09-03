# Méridian — PRD

## Implémenté (06/2026 — v38, correctifs interactions + mode immersif)
- **Bug pan bloqué** : les étiquettes de domaines invisibles (opacité 0, règle « label au survol ») interceptaient encore le pointeur (`pointer-events: auto`) → le drag démarré dessus ne déplaçait pas la carte. Corrigé : `pointer-events: none` quand le label est masqué. Vérifié : pan fonctionnel depuis ces zones à toutes les tailles (1920/1280/768/390).
- **Mode immersif plein écran** (tablette/mobile ≤1024px) : bouton `btn-immersif` (« Plein écran » / « Quitter ») qui masque totalement sidebar et topbar applicatives (classe `atlas-immersif` sur body + CSS), caméra conservée (zoom et centre monde inchangés via ResizeObserver), pan toujours fluide. Auto-désactivé en repassant desktop.

## Implémenté (06/2026 — v37, clustering niveau 2 + responsive complet — spec utilisateur 20 règles)
- **Clustering (niveau 2 uniquement, jamais lié à l'écran)** : domaines ≥ 5 jumeaux → les 2 plus couverts restent visibles, les autres sont regroupés spatialement (rayon 130 px monde) en grappes « ×N » (`grappe-grappe-<Domaine>-<i>`, badge `grappe-compteur-*`, tooltip membres au survol). Clic sur une grappe = zoom avant explicite (setCenter 1.35) → dissolution au niveau 3 ; elles se reforment au retour niveau 2. Les relations des membres pointent vers la grappe et sont agrégées par paire (« N flux »).
- **Caméra conservée au redimensionnement/orientation** : ResizeObserver — même zoom, même point monde au centre, seule la translation est recalculée ; jamais de fitView automatique (delta centre < 1e-3 px vérifié).
- **Chrome responsive** : mobile ≤640px — minimap remplacée par « Vue d'ensemble » (`btn-vue-ensemble`), composer Flore → bouton flottant (`btn-flore`), recherche → bouton (`btn-recherche`, Enter = premier résultat + recentrage), sidebar applicative repliée par défaut ≤1024px (Layout.jsx), barre du haut compacte.
- **Bottom sheet** (`AtlasPanneau presentation="feuillet"`, tablette ≤1024px et mobile) : poignée + titre (`feuillet-poignee`, `feuillet-titre`, `data-state` reduit/complet), max 60vh, superposée à la carte (jamais de redimensionnement ni recentrage), sélection conservée. Le panneau flottant d'épingle desktop est masqué sur tablette/mobile (pas de double affichage).
- **Tactile (pointer: coarse)** : tap zone vide de membrane = sélection du domaine (priorité au robot) ; zones d'arêtes 22 px (10 px desktop) ; contrôles zoom ≥ 44 px (CSS). Drag des robots toujours uniquement en mode réorganisation.
- Rappels inchangés : monde invariant, niveaux sémantiques par zoom seul, routes/membranes jamais recalculées au resize.
- Tests : **iteration_37 → 93 %**, puis les 3 bugs mobile corrigés et revérifiés (recherche Enter, double affichage, tap fond). Console propre, libavoid intact.

## Implémenté (06/2026 — v34-v36, épuration visuelle + peuplement déséquilibré)
- **Portes supprimées de la carte** (choix utilisateur) : les arêtes inter-domaines suffisent ; la navigation vers un domaine voisin se fait via le panneau détail (chips « Vers X · N » cliquables, `vers-<Domaine>`) et le survol des membranes. Code retiré : bloc portes d'`atlasGraph.js`, branche porte de `TwinNode.jsx`, logique « chemin » d'Atlas.jsx.
- **Labels de domaines révélés au survol** (règle utilisateur) : au repos (niveaux 2-3), les titres PAIEMENT/RISQUE/… et la puce de maturité sont masqués ; l'approche de la frontière d'une membrane les révèle (+ tooltip de synthèse). Au niveau 1 (macro), ils restent toujours visibles (c'est le contenu). Le domaine sélectionné garde son label visible.
- **Peuplement déséquilibré** (2e vague) : +14 jumeaux (38 au total) — Client 8, Paiement 7, Distribution 7, Opérations 6, Risque 5, Support 5. +17 relations (r29–r45). Strates/fraîcheurs complétées, compteurs de maturité des régions à jour.
- Tests : reseed OK, 38 jumeaux / 45 arêtes rendus, 0 porte, labels masqués au repos et révélés au survol (vérifié par captures), console propre, worker libavoid intact. Note : la réinitialisation remet les positions au seed.

## Implémenté (06/2026 — v33, peuplement du Mesh + portes clarifiées)
- **12 jumeaux ajoutés** (seed_data.py) — 2 par domaine (24 au total, 4/domaine) : Prélèvements, Remboursements (Paiement) ; Préférences, Fidélité (Client) ; Scoring Crédit, Filtrage Sanctions (Risque) ; Stocks, Transporteurs (Opérations) ; Base de connaissances, Escalades (Support) ; Catalogue, Recommandations (Distribution). 14 relations supplémentaires (r15–r28 : confirmées, observées, supposée). Strates, sources détaillées et fraîcheurs complétées pour chacun. Compteurs de maturité des régions mis à jour.
- **Portes re-stylées en connecteurs directionnels** (la redondance de noms de domaines venait d'elles) : bordure en pointillés, flèche ↗, fond translucide, taille réduite — clairement distinctes des étiquettes de domaines ; rapprochées de la frontière des membranes (rMax + 14 au lieu de + 30). **v34 : au repos, seule la pastille pointillée colorée est visible ; le label « DOMAINE · N » et l'aperçu ne se révèlent qu'au survol** (demande utilisateur — pas de labels de domaines affichés en permanence sur les portes).
- Tests : reseed OK (200), API vérifiée (24 jumeaux / 28 relations / strates complètes), Atlas et registre Jumeaux rendus correctement (28 arêtes, 12 portes, membranes étendues). Note : la réinitialisation de la démo a remis les positions des jumeaux aux coordonnées du seed.

## Implémenté (06/2026 — v32, « carte continue façon Google Maps » — refonte majeure de la navigation, spec utilisateur)
- **Une seule carte mondiale, coordonnées stables** : suppression TOTALE des vues reconstruites (vue domaine interne avec portes en cercle, focus jumeau radial). Plus de téléportation ni de changement brutal de niveau.
- **Propulsion (v31) supprimée** : le glisser est un pan pur à zoom STRICTEMENT constant (vérifié : scale() identique avant/après, seules les translations changent). Zoom uniquement explicite : molette, boutons, +/−/0, double-clic fond (centré pointeur), « Ajuster à la vue ».
- **Portes compactes « DOMAINE · N » sur la carte mondiale** (12 sur le seed) : en périphérie de chaque membrane, orientées vers le voisin. **Clic = chemin mis en évidence** (arêtes inter-domaines renforcées, autres estompées, panneau du domaine cible) SANS déplacer la caméra ; **double-clic = Explorer** (déplacement animé à zoom constant).
- **« Explorer un domaine » = pan animé à zoom constant** (double-clic membrane/titre, bouton `dom-explorer-btn`, chips `vers-*`) ; **« Ajuster au domaine » = fitBounds explicite** (`dom-ajuster-btn`). **Double-clic jumeau** = pan + zoom explicite centré (×1.6, max 2.4).
- **Fil d'Ariane passif** : `breadcrumb-domaine` = domaine contenant le centre du viewport, stabilisé 400 ms, ne déplace JAMAIS la caméra ; synchronisé explicitement par les navigations programmées (URL profonde ?domaine=, Explorer, double-clic jumeau). « Mesh global » = fitView.
- Niveaux sémantiques GLOBAUX (zoom <0.6 → 1 Capacités, >1.15 → 3 Applications & flux) : même grammaire visuelle partout.
- Tests : **iteration_36 → 92 %** puis les 2 bugs corrigés (contexte passif sur navigation programmée — MEDIUM, corrigé et revérifié ; micro-dérive sub-pixel 0.2 px au clic porte — LOW, comportement interne React Flow, imperceptible, accepté). Anciens testids supprimés : porte-<Domaine> simple → porte-<Region>-vers-<Domaine>, dom-quitter-btn, breadcrumb-domaine-inactif, nav-precedent/suivant.
- **Correctif zoom-out (question utilisateur)** : l'inertie de déplacement n'est plus alimentée par les échantillons où le zoom change (l'ancrage pointeur déplace x/y pendant la molette) — un zoom-out rapide ne déclenche plus de translation parasite ; l'inertie du pan pur est conservée. Rappel : le déplacement x/y PENDANT la molette est l'ancrage au pointeur (spec utilisateur), pas un bug.

## Implémenté (06/2026 — v31, navigation par propulsion — SUPPRIMÉE en v32 sur retour utilisateur)
- **Niveau 4 retiré** (choix utilisateur « pour le moment ») : sources/strates/événements sur robots et capsules « N preuves » supprimés ; NIVEAUX_ZOOM revient à 3 niveaux.
- **Navigation par propulsion (exploration directionnelle)** : clic maintenu sur le FOND de la carte + glissement prolongé vers une direction → la caméra avance et zoome en continu (smoothstep) vers le territoire dans le cône du geste. **Zone morte 0–30 px** (pan classique en dessous), progression 30→220 px, au-delà = 100 %. **Attraction par cône ±41°** : score cos²/(1+dist/3000) — l'alignement prime sur la proximité (corrigé après que Paiement volait la cible d'un geste NE vers Risque).
- **Feedback progressif** : chip près du pointeur (`propulsion-chip` : nom du domaine, %, « Continuer pour entrer » → « Relâcher pour entrer → » à ≥85 %) ; la membrane cible se révèle (contour/fond renforcés au fil de la progression), ses robots prennent anneau + léger scale, les relations vers la cible sont renforcées. En vue domaine, les cibles sont les passerelles (chip de porte illuminé).
- **Relâchement** : ≥85 % → entrée dans le domaine (fil d'Ariane « Mesh global › Domaine X ») ; sinon la caméra se stabilise sur place, sans retour brutal ; ramener le pointeur dans la zone morte = annulation. Inertie du pan inhibée après une propulsion.
- **Bugs corrigés post-test** : la garde `closest('.react-flow__pane')` capturait aussi les nœuds (les nœuds sont descendants du pane dans React Flow) → `e.target.classList.contains('react-flow__pane')` ; propulsion désormais inhibée en mode réorganisation (le drag de robot reste un déplacement).
- Tests : **iteration_35 → retrait N4 100 %, propulsion 6/7** puis les 2 bugs HIGH corrigés et revérifiés par navigateur (a/b/c OK, 0 erreur console, worker libavoid intact).

## Implémenté (06/2026 — v30, ALIGNEMENT COMPLET sur la spec utilisateur du moteur de routage : libavoid WASM + Web Worker)
- **Architecture de la spec appliquée** : React Flow = affichage (pan/zoom/sélection/drag) ; le calcul final des arêtes est déporté dans **libavoid (WASM) exécuté dans un Web Worker** (`lib/routageWorker.js`, `libavoid-js@0.5.0-beta.5`, wasm servi depuis `public/libavoid.wasm`). Le routeur maison (`routeur.js`) ne sert plus que de **provisoire pendant le drag** et de **secours** si le Worker échoue (`console.warn '[routage] Worker libavoid en échec'`).
- **Ports N/E/S/W** : 8 handles React Flow par nœud (source+cible × 4 côtés) sur robots ET passerelles/pastilles (bug trouvé : les pastilles n'avaient que l/r → les arêtes verticales de passerelles étaient perdues par React Flow ; corrigé dans `TwinNode.jsx`, vue domaine Paiement : 6 → 8 arêtes).
- **Obstacles étendus** (`atlasGraph.js geometrieNoeud/obstacleTitreRegion`) : avatars, App ID, badges +N, noms (niveau 3), pastilles de passerelles, **titres de domaines** — la membrane n'est JAMAIS un obstacle (les relations la traversent).
- **Fonction de coût** côté libavoid : crossingPenalty 140 > fixedSharedPathPenalty 80 > shapeBufferDistance 16 (marge de sécurité) > anglePenalty 24 > segmentPenalty 10, idealNudgingDistance 6 (voies 5–7 px), nudging des segments partagés activé. **Routage par priorité** : contestée 80 > observée/validation 60 > supposée 50 > déclarée 40 > obsolète 20.
- **Pipeline** (`lib/routage.js`, hook `useRoutageFinal`) : snapshot géométrique → signature dédupliquée (arrondie 2 px) → Worker → **interpolation 240 ms** easing-out des anciens vers les nouveaux trajets. Jamais de recalcul au pan/zoom (signature stable) ; pendant le drag, trajet provisoire simple sans obstacles ; recalcul final au relâchement.
- **Agrégation « N flux »** : au-delà de 5 relations entre un même couple, une voie unique épaisse (label permanent « N flux », membres masqués) ; le survol déploie temporairement les routes membres (`data.groupe`, tooltip `agregat-tooltip`).
- **Écart corrigé en route** : enum libavoid navigateur — `RouterFlag.OrthogonalRouting.value` (l'objet enum seul est rejeté par l'embind du build web ; `Avoid.OrthogonalRouting` n'existe pas contrairement à la d.ts).
- Tests : **iteration_34 → 100 % frontend** (14 arêtes finales libavoid, orthogonalité vérifiée au path, ponts aux croisements, stabilité idle+zoom 0 recalcul, drag provisoire→final sans saut, hover/clic, focus jumeau, 0 erreur console).

## Implémenté (06/2026 — v28, navigation cartographique façon Google Maps — spec utilisateur)
- **Pan avec inertie** : échantillonnage du viewport pendant le glissement, décélération exponentielle amortie au relâchement (~300-500 ms), curseurs grab/grabbing, sélection de texte désactivée. **Cause racine d'un blocage du pan** : les zones d'interaction invisibles des arêtes (20 px par défaut) interceptaient le glisser — réduites à `interactionWidth: 8`.
- **Zoom** : molette centrée pointeur (natif RF), **double-clic sur zone vide = zoom centré sur le pointeur** (viewport recalculé, 240 ms), raccourcis **+/−/0**, boutons ±, ajuster à la vue. Niveau sémantique affiché « Niveau 2 · Domaines ».
- **Zoom sémantique enrichi** : Niveau 1 « Capacités » = robots masqués, membranes macro avec agrégats « N jumeaux · N flux · N écarts », corridors agrégés ; Niveau 2 = robots + IDs + membranes ; Niveau 3 « Applications & flux » = robots agrandis, **noms sous les App ID**, **ports d'entrée/sortie visibles**, labels de flux sur les arêtes.
- **Membranes à ressort** : le rect affiché poursuit sa cible par rAF (α≈9/s, stabilisation ~300 ms, sans vibration) pendant/après le drag — matière souple professionnelle.
- **Mode réorganisation explicite** (`outil-edition`, chip d'aide) : robots déplaçables uniquement dans ce mode ; **position fantôme** au point de départ ; halo renforcé ; au relâchement : arêtes recalculées, **position persistée** (`PATCH /api/jumeaux/{id}`, nouvelle route backend), **reclassification proposée par toast si le robot atterrit dans un autre domaine — jamais automatique** (action « Reclasser dans X »), « appartenance à qualifier » si éloigné de tout cluster.
- **Survol membrane** : autres domaines atténués (membranes + robots) ; **survol robot** : avatar +6 %, App ID accentué ; recherche → caméra animée + **halo bref membrane+robot** + panneau épinglé.
- Correctifs post-test : 404 sur PATCH jumeau inconnu (était 200), pluriel « 1 écart ».
- Tests : **iteration_32 → 100 % frontend + backend 6/6** (inertie mesurée au transform, dblclick zoom, niveaux 1/3, fantôme, persistance vérifiée via GET /mesh, couches, tooltip, 2 reloads 14/14 arêtes).

## Implémenté (06/2026 — v27, refonte complète de l'Atlas selon la spec « cartographie vivante » utilisateur)
- **Jumeaux = avatars robot** (`/assets/robot-jumeau.jpg`, image générée : tête blanche arrondie, écran facial sombre, yeux turquoise, antenne) dans un médaillon blanc, **identifiant numérique monospace à 4 chiffres au-dessus** (`idNumerique`, hash stable) — le nom complet n'apparaît plus sur la carte. Halo turquoise au survol, ping si actif.
- **Membranes = coques CONCAVES polygonales** (`concaveman`, concavité 2.2, replis entre nœuds éloignés, marge ~18 px autour des avatars, angles adoucis mais géométrie polygonale) — géométrie calculée uniquement sur les centres des avatars, élastique (drag/ajout/suppression).
- **Arêtes orthogonales à 3 sémantiques** : gris ardoise plein (BCM déclaré/confirmée), **turquoise pleine + flèche directionnelle** (observée), orange pointillés (supposée/contestée = écarts) ; ports directionnels + offsets conservés.
- **Panneau flottant gauche** au survol robot (aperçu) épinglé au clic : ID, nom, « Jumeau applicatif », confiance, relations observées, écarts au BCM, boutons **Interroger** (ouvre Flore avec le contexte) / **Ouvrir le jumeau** (panneau détail droit) ; Échap/2e clic/clic fond ferme. Arêtes connectées accentuées, autres estompées.
- **Survol membrane par proximité de frontière** (les zones d'interaction des arêtes recouvrent le SVG) : contour renforcé + infobulle (jumeaux, flux observés, écarts, hint « Double-clic : explorer »). N'ouvre jamais le panneau jumeau.
- **Sélecteur de couches** (BCM déclaré / Réalité découverte / Écarts — filtre les arêtes) + **barre de recherche** (jumeau par nom ou ID, domaine → centrage) en haut de carte ; **mini-carte** bas-droite restaurée ; **plein écran** dans les contrôles ; chip **Écarts** ajouté au composer.
- **Correctif de fond (race React Flow)** : les changements de dimensions sont désormais réinjectés dans les nœuds dérivés (`mesures`) — sans cela le store interne ne connaissait pas les ports et les arêtes disparaissaient par intermittence au premier rendu. + amorce post-montage. 4 chargements consécutifs OK.
- Tests : **iteration_31 → 100 % frontend** (agent de test, 10 scénarios : 2 reloads 14/14 arêtes, hover/épinglage, tooltip membrane, couches, recherche, drag 14/14, non-régression zooms/temporel).

## Implémenté (06/2026 — v26e, contacts arêtes/jumeaux revalidés)
- **Retouche demandée** : les arêtes orthogonales traversaient les labels (qui étaient à droite du point, à hauteur du port). Le label passe **sous le point** (point au-dessus, nom + domaine centrés en dessous) — les arêtes arrivent horizontalement sur le point sans jamais croiser le texte, sur les 4 variantes (jumeau, voisin, porte, anonyme).
- Halo d'activité restylé en surbrillance douce arrondie (fond teinté + bord légère) au lieu d'un anneau ovale autour du bloc.
- Vérifié zoom avant + vue globale : contacts propres, 14/14 arêtes, labels dégagés.

## Implémenté (06/2026 — v26d, routage orthogonal assaini — ports directionnels)
- **Bug signalé** : arêtes « sans sens » (boucles), confuses sur les nœuds, croisements — toutes sortaient à droite et entraient à gauche quelle que soit la géographie.
- **Ports directionnels** : chaque jumeau/région/porte expose 4 ports (entrée/sortie × gauche/droite, centrés sur le point jumeau) ; `makeEdge` choisit le côté selon la position relative source→cible (`atlasGraph.js`, toutes les vues : globale, domaine, focus, corridors entreprise).
- **`repartirOffsets()`** : les arêtes partageant un même port sont écartées (offset smoothstep) — fini la superposition confuse sur un nœud.
- Correctif en passant : `posById` non défini en vue domaine (crash) → carte des positions dérivée des nœuds construits.
- Vérifié : 0 erreur, 14/14 arêtes pendant/après drag avec réattachement directionnel en direct, vue domaine + portes OK, coques élastiques intactes.

## Implémenté (06/2026 — v26c, arêtes orthogonales)
- **Demande utilisateur** : routage orthogonal des relations — `makeEdge` passe en `type: "smoothstep"` (segments horizontaux/verticaux, coins légèrement arrondis). Les flux de points animés (observées) et les pointillés (supposées/validation/contestée) suivent les chemins orthogonaux. Vérifié : 14/14 arêtes en smoothstep, lecture façon schéma.

## Implémenté (06/2026 — v26b, correctif : arêtes qui disparaissaient pendant le drag)
- **Bug signalé** : les arêtes disparaissaient pendant le déplacement d'un nœud. Cause : le graphe est reconstruit à chaque tick de drag (`posOverrides` → `construireGraphe`) ; les nœuds remplacés perdaient leurs dimensions mesurées par React Flow → ancres d'arêtes perdues jusqu'à re-mesure.
- Correctif (`Atlas.jsx`) : les `measured` (+ `dragging`) des nœuds internes React Flow sont **reportertés sur les nœuds reconstruits** ; dimensions initiales des nœuds compacts alignées (150×36/40 au lieu de 190×64). Vérifié tick par tick : le nœud suit le pointeur en direct, 14/14 arêtes visibles pendant tout le drag, coque élastique intacte.
- Note : l'avertissement console React Flow #015 (« drag a node that is not initialized ») persiste — bénin (pattern controlled-flow sans applyNodeChanges), aucun impact fonctionnel constaté.

## Implémenté (06/2026 — v26, géographie organique élastique + symbole jumeau)
- **Demande utilisateur** : les domaines ne sont plus des formes rondes fixes — chaque région est une **coque organique** qui épouse la disposition de ses nœuds internes et se déforme élastiquement (déplacement, ajout, suppression).
- **`coqueOrganique()` (`atlasGraph.js`)** : chaque nœud membre est gonflé en octogone → enveloppe convexe (monotone chain) → élargie depuis le centroïde → lissée par Catmull-Rom fermé. Calculée dans `construireGraphe` depuis les positions vivantes (`posOverrides`), donc recalculée à chaque drag — la coque suit le nœud déplacé. Fonctionne à 1, 2 ou N membres (vue globale + vue interne de domaine).
- **`RegionNode.jsx`** : rendu SVG `<path>` (remplissage teinté + contour coloré), titre du domaine positionné au centroïde haut, interactions (clic/double-clic) et testids préservés.
- **Symbole jumeau** : deux cercles concentriques (l'application + son reflet numérique), couleur de domaine, lueur si sélectionné/dégradé, ping si actif — variantes porte/anonyme en pointillés.
- Vérifié par navigateur : coques organiques visibles, déformation élastique au drag (avant/après), entrée domaine + portes + fil d'Ariane OK, 0 erreur console.

## Implémenté (06/2026 — v25, refonte visuelle de l'Atlas sur image de référence utilisateur)
- **Image de référence fournie par l'utilisateur** (atlas « SI Banque » : points+labels, blobs pastel, flux animés) appliquée à notre Atlas.
- **Nœuds jumeaux = point + label** (`TwinNode.jsx` réécrit) : anneau coloré par domaine sur fond blanc (halo ping si actif, lueur si sélectionné/dégradé), nom en gras + domaine en petites capitales — fini les cartes rectangulaires de 180 px. Variantes cohérentes : voisin (point + état de relation), porte externe (pointillé), anonyme (cadenas gris). Aperçus au survol, halos, focus ring et testids préservés.
- **Régions = blobs organiques pastel** (`RegionNode.jsx`) : border-radius asymétrique, remplissage teinté visible, nom du domaine en capitales colorées à l'intérieur + stats compactes.
- **Relations** (`styleParEtat`) : observée = **flux de points animés vert d'eau** (dasharray « 0.1 10 », linecap round, animated) ; supposée = pointillés orange (#D97706, « à qualifier ») ; confirmée = trait plein gris (déclaré) ; validation A2A violet, contestée rouge, obsolète pâle — `ETATS_RELATION` et légende alignés.
- Tests : **iteration_30 → 100 %** (agent de test, parcours Atlas complet : sélection, panneau, survols, zoom domaine/jumeau, portes, lasso, modes temporels, 0 erreur console).

## Implémenté (06/2026 — v24, lisibilité de l'Atlas — fond de carte adapté)
- **Demande utilisateur** : améliorer la lisibilité de l'Atlas avec un fond adapté.
- **Canvas « papier cartographique »** : dégradé radial (centre #FDFDFB → bords #EDECE6) qui détache la carte du fond applicatif et concentre le regard ; trame de points resserrée et plus visible (gap 26, opacité 13 %).
- **Territoires rehaussés** : remplissage des régions 3 % → 6 % d'opacité, bordures colorées 18 % → 27 %, légère ombre portée — l'archipel des domaines se lit d'un coup d'œil.
- Vérifié par capture : contraste nettement supérieur, identité couleur par domaine préservée.

## Implémenté (06/2026 — v23, « Ajouter une source » dans le panneau droit — choix utilisateur)
- La palette modale centrée (CatalogueTiroir) est remplacée par le **panneau droit existant de l'atelier** : « Ajouter une source » ouvre le catalogue dans la colonne inspecteur (recherche, catégories, navigation clavier ↑↓/⏎/esc conservées) ; après ajout, le panneau bascule directement sur l'inspecteur de la nouvelle source à configurer. Aucun overlay modal dans ce flux (ImportModal conservé pour l'import massif seul).
- Correctif visuel au passage : intercalaires de groupes de la file des sources repassés en clair (`#0C0C0C` → `#F0F0EE`, reliquat du thème sombre).
- Vérifié par navigateur : catalogue dans le panneau droit, 0 overlay, ajout Oracle → inspecteur de la nouvelle instance, démo réinitialisée.

## Implémenté (06/2026 — v22, activité visible de Flore — « elle travaille avant de répondre »)
- **Demande utilisateur** : lors des transitions vers le chat, une animation montre que Flore *cherche / s'informe / comprend / a tout ce qu'il faut* — façon chats IA conventionnels.
- **`FloreActivite.jsx`** (composant partagé) : séquence d'étapes progressives (750 ms/pas, étape active = Sparkle pulsante + points animés, étapes passées = ✓ discret, finale verte « A tout ce qu'il faut. »), **wording contextuel par genre** (incident : « Analyse la dérive… croise traces, incidents passés… » ; relation/phénomène : signaux/preuves/confiance ; changement : rejoue le scénario ; travail : relit la mémoire, repère où vous étiez ; rapport : se saisit → rassemble → rédige). Helper `delaiMin()` : la séquence a toujours le temps de se dérouler même si l'API (prescriptée) répond instantanément.
- Intégré aux 4 points d'attente : **Comprendre** (ouverture = séquence « rapport », réponses = wording du genre de l'item), **Conversation d'un Travail**, **Accueil** (y compris création de travail), **panneau Flore** latéral. Testids d'attente préservés.
- Vérifié par navigateur : séquence d'ouverture complète capturée (4 phases) puis rapport affiché ; séquence contextuelle incident pendant une réponse ; 0 erreur console.

## Implémenté (06/2026 — v21, « Comprendre » = conversation dédiée avec Flore sur la situation)
- **Demande utilisateur** : dans Actualités, « Comprendre » ouvre désormais une **page de conversation dédiée** (`/actualites/comprendre/:hid`, `Comprendre.jsx`) au lieu du fil inline dans la carte. Le fil s'ouvre sur le **rapport de Flore sur la situation** (quoi / pourquoi cela compte / reste à comprendre / décisions attendues, preuves pliables, propositions cliquables), composer ancré (POST `/aurora/demander`), **retour ← Actualités**. Valable pour tous les genres : incident, découverte/relation, phénomène possible (badge « non confirmée »), transformation, gouvernance ; les items « travail » gardent « Reprendre » (+ proposition « Reprendre le travail » dans la page).
- **Backend** : `GET /api/actualites/histoire/{hid}` (`actualites_routes.py`) reconstruit l'histoire par préfixe (`sit-`/`rel-`/`case-`/`jrn-`) avec **RBAC identique au feed** (filtre_situation, autorisations) et génère le rapport prescripté structuré — deep-linkable, id inconnu → 404 propre.
- `FilComprendre` inline supprimé d'`Actualites.jsx` ; `GENRES` exporté pour réutilisation.
- Tests : **iteration_29 → 100 %** (backend 8/8 pytest `tests/test_comprendre.py` : 4 préfixes + 404 + RBAC support ; frontend 13/13 : navigation, rapport, preuves, propositions, envoi, retour, deep-link, erreur propre, non-régression feed).

## Implémenté (06/2026 — v20c, cohérence du seed : tout travail naît d'une conversation)
- **Bug utilisateur** : certains travaux affichaient un Aperçu fourni mais une Conversation vide — incohérent avec le paradigme « un travail est une conversation conservée ».
- Cause : 3 cases seedés (`case-migration-oracle`, `case-revue-rgpd`, `case-dette-files`) avaient rapport (questions/résumé/décision) mais `conversation: []`.
- Correctif : conversations seedées cohérentes avec chaque rapport (2 échanges minimum, datés avec le cycle de vie du travail ; `case-dette-files` clos mène à sa décision). `SEED_VERSION` 8 → 9. Vérifié par API (5/5 travaux avec fil) et navigateur.

## Implémenté (06/2026 — v20b, en-tête du Travail épuré — choix utilisateur)
- **Supprimés de l'en-tête** : le bouton « Continuer avec Flore » (redondant — l'onglet Conversation *est* la continuation), les sélecteurs **Responsable** et **Statut** (contrôles d'administration sans place dans le paradigme ; Clore/Rouvrir reste dans le menu ⋯), et « Ouvrir dans Atlas » (l'Atlas reste accessible par la sidebar).
- **L'en-tête ne garde que** : ← Travaux, identité (CASE-0xx, type, sensibilité, titre), participants + dernière évolution, badge « À revoir », Partager, menu ⋯ (Marquer revu / Clore-Rouvrir). Vérifié par navigateur (menu fonctionnel, 0 erreur).

## Implémenté (06/2026 — v20, Travail : deux onglets seulement — Conversation + Aperçu)
- **Demande utilisateur appliquée** : fini les 5 onglets. `TravailDetail.jsx` n'expose plus que **Conversation** (fil pur, composer ancré, reprise au point d'arrêt) et **Aperçu** (rapport structuré). Une URL obsolète (`?vue=decisions|atlas|activite`) retombe proprement sur Conversation.
- **Fusion dans `OngletApercu.jsx`** : l'ex-onglet Décisions & actions devient la section **04** (options avec Retenir/Écarter + ajout d'option, décisions humaines + ajout, testids `option-*`/`decision-*` préservés) ; l'ex-onglet Activité devient la section **09** (flux unifié + 6 filtres + promotions Flore : question/investigation/preuves/ignorer — **sans composer**, le chat vit dans Conversation). Sections renumérotées 01–10, « Prochaine étape » clôt le rapport.
- **`OngletDecisions.jsx`, `OngletActivite.jsx`, `OngletAtlas.jsx` supprimés** (l'Atlas reste accessible via « Ouvrir dans Atlas » de l'en-tête). Doublon de condition `a_revoir` nettoyé dans l'en-tête.
- Tests : **iteration_28 → 100 % frontend** (agent de test, 13 scénarios : 2 onglets, envoi de message, Retenir/Écarter, ajouts option/décision/question/hypothèse/investigation/synthèse, filtres activité, promotions, éditions inline persistées, fallback d'URL, 0 erreur console). Données de démo réinitialisées après les tests.

## Implémenté (26/08/2026 — v19f, Conversation pure + Aperçu en rapport structuré)
- **Conversation = replonger là où le travail s'est arrêté** (demande utilisateur) : le panneau de résumé sort du fil ; à la place, un marqueur « — Nouveau depuis votre dernière visite — » placé au point de reprise (messages postérieurs à la dernière visite) avec scroll automatique sur la coupure. Fil nu + composer ancré, identique à la création.
- **Aperçu = rapport structuré du travail** (pas de mini-cartes) : en-tête « Rapport du travail » (méta : activité, participants, échanges), § Session précédente (définitions Vous étiez ici / Depuis / Reste incertain / Prochaine étape), puis sections numérotées 01–09 : Situation, Compréhension actuelle (Actualiser par Flore), Évolution récente, Décisions & options, Questions, Hypothèses, Investigations, Analyses & livrables, Prochaine étape — édition inline conservée, testids préservés. `ObjetsTravail.jsx` supprimé (contenu fusionné dans le rapport).

## Implémenté (26/08/2026 — v19e, Travail = conversation pleine page, parité création/continuation)
- **L'onglet Conversation est identique à la vue de création** (demande utilisateur, façon ChatGPT/emergent.sh) : colonne centrée (max-w-2xl), résumé « Session précédente — Flore vous replace » en tête, fil nu (bulles), **composer ancré en bas** (Entrée pour envoyer, scroll auto en fin de fil). Continuer un travail = même lecture que le créer, avec l'en-tête du travail en plus.
- **Objets de travail déplacés dans l'Aperçu** (`ObjetsTravail.jsx` partagé : Questions/Hypothèses/Investigations/Analyses & livrables) ; bloc « Questions ouvertes » retiré (doublon) ; bannière « À revoir » désormais visible sur tous les onglets (code mort corrigé).
- Tests : **iteration_27 → 100 %** (parité création/continuation, envoi +2 messages, autoscroll, objets dans Aperçu, 0 erreur console).

## Implémenté (26/08/2026 — v19d, esprit « reprendre une conversation » + navigation)
- **Retour « ← Travaux »** sur la page de création conversationnelle (`/travaux/nouveau`) — manquait (bug utilisateur).
- **Détail d'un travail = reprise de conversation** (bug utilisateur) : l'onglet Conversation s'ouvre sur le **résumé de la session précédente** (« Session précédente — Flore vous replace ») suivi du fil dominant (2/3) avec composer inline ; les objets de travail (questions/hypothèses/investigations/livrables) sont relégués dans un rail droit (1/3).
- 404 parasites éliminées : le panneau Flore ne cherche plus le case « nouveau ».
- Tests : **iteration_26 → 100 %** (frontend, agent de test) — retour création, naissance du travail par conversation, résumé + fil + rail, composer inline (+2 messages sans rechargement), 5 onglets, aucun formulaire résiduel.

## Implémenté (26/08/2026 — v19c, création conversationnelle des Travaux — « comme ChatGPT »)
- **Le formulaire de création de travail est supprimé** (retour utilisateur : un formulaire n'a pas sa place dans un écosystème intelligent). « + Nouveau travail » (sidebar + page) ouvre `/travaux/nouveau` : une conversation (« Que voulez-vous comprendre ou accomplir ? ») ; **le premier échange fait naître le travail** (titre = question, jumeaux = contexte, conversation injectée) puis bascule dans l'onglet Conversation. Accueil général conserve la proposition « Conserver comme travail » pour les consultations.
- **Le fil de conversation vit dans l'onglet Conversation** (`case-conversation` : bulles, contributions, propositions cliquables, composer inline via `POST /cases/{id}/messages`) — auparavant il n'existait que dans le panneau latéral. Reprise Flore en tête, objets structurés (questions/hypothèses/investigations/livrables) en dessous.
- Vérifié E2E : création par conversation (CASE créé + toast + navigation), envoi de message dans le fil (2→4), récents sidebar à jour.

## Implémenté (26/08/2026 — v19b, Actualités repensée « le brief EST la page »)
- **Une seule rangée de contrôle** : vues segmentées (Brief/Radar/À traiter·badge/Suivis) à gauche ; portées compactes (Personnel/Espace/Global) + **calendrier du Mesh** (‹ date › + popover presets/date) à droite. Fini les 4 rangées de contrôles empilées ; l'overline redondante disparaît (la sidebar porte le contexte).
- Briefing éditorial immédiat (salutation, accroche forte, points, lecture rôle) ; bannière historique et synthèse de période inchangées.
- Bug corrigé : le popover calendrier passait **sous** le briefing (contextes d'empilement dus à l'animation `rise`) → en-tête élevé (`relative z-30`).
- **Travaux densifié façon historique ChatGPT** (retour utilisateur sur l'occupation de l'espace) : une ligne par travail (point de statut + titre + intention/nouveauté tronquées + fraîcheur relative), actions **au survol** ([Continuer] + ••• avec métadonnées reléguées), une seule rangée de contrôles (recherche · Récits ▾ · Mes travaux · types · statuts · +), conteneur élargi (max-w-4xl), suppression du double bouton « Nouveau travail » (la sidebar le porte) ; sections « attention / sans vous / tous » conservées en petits intertitres. Clic ligne → onglet Conversation.
- **Atlas épuré par défaut** (retour utilisateur) : panneaux « Calques/réglages » et « Détail/Chronologie » désormais **fermés à l'ouverture** (plus d'auto-expansion sur grand écran) — dépliage uniquement à la demande ; le panneau Détail continue de s'ouvrir sur une sélection (action utilisateur).
- Vérifié E2E : preset 7j via popover → titre « Du 20 au 26 août » + synthèse ; portées compactes ; pillule « À traiter ».

## Implémenté (26/08/2026 — v19, REFONTE IA-NATIVE inspirée ChatGPT — document MERIDIAN_REDESIGN_UI_AI_NATIVE.md appliqué intégralement)
- **Shell ChatGPT-style** : barre latérale repliable (marque, « + Nouveau travail », nav Accueil/Actualités/Atlas/Travaux/Jumeaux, **Espaces**, **Récents** (3 derniers travaux), Parcours guidé, **Administration masquée selon le rôle**) + en-tête contextuel fin (espace+badge, ● Mesh vivant, **pillule « N à traiter »** → À traiter, notifications, persona). Plus de bouton Flore dans l'en-tête : l'entrée Flore = composer.
- **Composer unique Flore** (`ComposerFlore.jsx`) : textarea + [+ Contexte] (chips retirables : sélection Atlas, périodes, actualité) + [Capacités] (Explorer le Mesh, Comparer deux états → Atlas avant/après, Analyser un changement, Surveiller un phénomène → délégation, Préparer une décision, Créer une synthèse) + [Micro] (toast bientôt) + [Envoyer] → événement flore-ask + panneau Flore. Présent : plein sur Accueil, compact en bas d'Atlas/Actualités/Jumeaux — jamais flottant.
- **Accueil conversationnel** (route `/`) : « Que voulez-vous comprendre dans votre SI ? », composer central, 3 suggestions adaptées au rôle, cartes rapides (Changements du jour / Reprendre un travail / Explorer mon espace). Actualités déplacées sur `/actualites` (vue pilotée par `?vue=`, source de vérité URL).
- **Travail = conversation d'abord** : onglet « Conversation » par défaut avec panneau « Où en sommes-nous ? — Flore vous replace » (reprise) en tête ; Aperçu/Atlas/Décisions/Activité en secondaire.
- **Jumeaux** : suggestion locale de Flore en bas de registre (Comprendre/Examiner/masquer) + composer compact. Registre plat + colonne Domaine conservé (choix utilisateur antérieur).
- Bugs corrigés en itération 25 : gating Administration (champ `espaces` absent de /api/personas → `espaces.some(global)`), désync onglets Actualités/pillule (vue dérivée de l'URL).
- **Accueil = hôte de conversation** (retour utilisateur : le chat latéral n'a pas de sens sur l'Accueil) : après la 1ʳᵉ question, le fil se déroule **dans la page** (à la ChatGPT) — bulles utilisateur, réponses Flore avec contributions jumeaux / preuves pliables / propositions cliquables qui prolongent le fil / périmètre d'investigation ; proposition de conservation en Travail après ≥2 échanges (fusion de la conversation) ; le panneau latéral reste réservé aux autres pages.
- Tests : **iteration_25 → 15/15 après corrections** ; backend 96/96 (2 flaky xdist connus, passent isolément).

## Implémenté (26/08/2026 — v18, GRAMMAIRE D'INTERACTION DU MESH, Phases A+B)
Application du manifeste « grammaire d'interaction » (utilisateur, 26/08) : qui peut demander quoi, qui peut initier quoi, jusqu'où sans validation humaine.
- **Initiative du Mesh** (concept central) : collection `initiatives` + seed cohérent démo (confirmation contrat v2/v3 et délai 7j/5j → propriétaire Paiements ; investigation recommandée + décision UTC + admission Conformité → architecte ; « à surveiller » + information ambiantes) avec champs complets (déclencheur, raison, preuves, confiance, impact, urgence, destinataire, pourquoi_vous, attendu, autonomie, interruption). Endpoints `/api/initiatives` (vues RBAC), `/compteurs`, `POST /{id}/repondre` (confirmer / rejeter **avec motif conservé** / ajouter à un travail / créer un travail investigation / surveiller — 409 si déjà répondu, écriture journal = apprentissage).
- **Actualités en 4 vues** : [Brief] · [Radar] (situations candidates, ambiants) · **[À traiter · badge]** (initiatives exigeant une réponse, niveau sollicitation) · [Suivis] (phénomènes suivis + délégations actives). Carte initiative structurée par les **7 questions** (pourquoi vous / découverte+preuves / confiance / impact / attendu). Les cartes répondues quittent « À traiter » (visibles via `vue=traitees` côté API).
- **« Déléguer »** : tâches bornées depuis Flore (`flore-deleguer-surveillance/comparaison/confirmation` sur la sélection Atlas) — périmètre, durée, sources, livrable et limite de validation affichés dans Suivis.
- **Gouvernance de l'autonomie par type d'action** (jamais globale) : `gouvernance` par jumeau (Délégué/Supervisé/Interdit), table dans la Revue jumeau ; niveau 6 limité aux actions bornées préautorisées (modèle en place, exécution non ouverte).
- Bug corrigé en cours de route : `"ajouter" in string` (TypeError après POST réussi → faux toast d'erreur) ; `/demo/reinitialiser` étendu à initiatives/délégations (SEED_VERSION 8).
- Tests : **iteration_24 → 100 %** (backend 96/96 dont 8 tests initiatives ; frontend 11/11 scénarios, 0 erreur console).

## Implémenté (26/08/2026 — v17b, cohérence de navigation + registre Jumeaux)
- **Registre Jumeaux : liste plate avec colonne Domaine** (choix utilisateur — le regroupement par domaine était redondant avec le filtre domaine) ; tri : jumeaux à traiter en tête, puis couverture croissante ; sélecteur « Grouper par » supprimé ; puce domaine colorée par ligne.
- **Registre Jumeaux corrigé** : intercalaires de groupes restés noirs après le codemod (`bg-[#0C0C0C]` → clair sticky), colonnes Fraîcheur élargies avec info-bulle (troncature « il y a… »), titres harmonisés.
- **Hiérarchie typographique unifiée** sur toutes les pages : overline `font-code` indigo + H1 `font-display text-3xl font-black` (Jumeaux/Investigations/Administration/InvestigationDetail alignés sur Actualités/Travaux).
- **Libellés de retour cohérents** : Revue jumeau « ← Jumeaux » (était « Registre »).

## Implémenté (26/08/2026 — v17, alignement sur le manuscrit validé par l'utilisateur)
Après relecture critique de la vision, rédaction d'un **déroulé-manuscrit d'une journée type** (5 actes) validé par l'utilisateur, puis alignement de l'interface :
- **Briefing honnête sur le doute** : accroche « La plus importante : … — encore supposée, non confirmée » quand l'histoire vedette est incertaine (`briefing.accroche`/`detail` séparés dans l'API).
- **Preuves comptées dans le fil Flore inline** : « Cette conclusion repose sur N preuves · afficher ».
- **Conservation à 3 options** : [Conserver comme travail] / **[Ajouter à un travail existant]** (fusion de la conversation dans le travail choisi via PATCH conversation + entrée d'historique, endpoint `CasePatch.conversation` ajouté) / [Continuer sans conserver].
- **Reprise de travail** : libellés du manuscrit (« Vous étiez ici / Depuis / Reste incertain / Prochaine étape »).
- **Liens Atlas contextuels** : histoires relation/phénomène/transformation → `?avant-apres=<date du phénomène>` (la carte montre la forme du problème) ; autres → photographie `?date=`.
- **Fragment Atlas retiré des actualités** (veto utilisateur) : l'Atlas est le lieu du regard, Actualités celui du récit.
- Processus retenu pour la suite : principes d'abord, déroulé en texte validé par l'utilisateur, puis code (documenté dans cette section).

## Implémenté (26/08/2026 — v16, seconde passe « briefing vivant du Mesh »)
Alignement profond sur l'esprit du document de vision (pas seulement la surface) après retour utilisateur.
- **Actualités = briefing intelligent et vivant** (« Voici ce qui a changé dans le Mesh, pourquoi cela compte pour vous, ce que vous pouvez faire maintenant ») : salutation + « L'essentiel aujourd'hui » rédigé par Flore, **adapté au rôle** (Lecture architecte/exploitation/décideur — classement ET formulation changent, jamais la vérité) ; feed organisé en **sections de signification** (L'essentiel / Vos travaux / Découvertes / Transformations / À surveiller / Dans votre espace / Mesh global) ; histoire vedette mise en valeur par la typographie uniquement (pas de fragment Atlas embarqué — **choix utilisateur 26/08 : pas de fragment Atlas dans l'actualité, l'Atlas reste le lieu du regard, Actualités celui du récit** ; « Voir dans l'Atlas » reste le pont visuel avec contexte conservé) ; **une action principale par histoire** ([Reprendre]/[Comprendre]/[Suivre la vérification]) + menu ••• ; **« Comprendre » = fil Flore inline** dans la carte (question auto, réponse, « Afficher les preuves », conversation multi-tours contextualisée) ; relations « supposées » affichées en **PHÉNOMÈNE POSSIBLE** ; périodes 7j/30j → **synthèse** (compteurs + tendance principale + « Comparer le X et le Y » → `/atlas?avant-apres=`) ; états du feed : vide (« Rien d'important… » + compteurs Mesh + Explorer), historique, insertion temps réel.
- **Backend `/api/actualites` v2** : sections, regroupement des événements d'un travail en une histoire par période, briefing rôle-adapté (`profil_de`), synthèse de période avec tendance domaines, marquage incertain.
- **Travaux = mémoire narrative** : sections « Ce qui attend votre attention » / « Ce qui a progressé sans vous » (backend : `nb_nouveautes`/`nouveaute_texte` depuis la dernière visite) / « Tous les travaux » ; cartes minimalistes (titre + intention + nouveauté + [Continuer] + •••) ; Kanban/Chronologie relégués dans le menu « Récits ▾ ».
- **Flore propose la conservation** : après ≥2 échanges, encart « Cette exploration implique N jumeaux… [Conserver comme travail] [Continuer sans conserver] ».
- **Atlas** : paramètre `?avant-apres=DATE` ouvre directement le mode Avant/Après (lien depuis la synthèse).
- Tests : **iteration_23 → 100 %** (backend 88/88, frontend 11/11 scénarios, 0 erreur console).

## Implémenté (26/08/2026 — v15, REFONTE UX/UI « nouveau paradigme » complète)
Application intégrale du document `MERIDIAN_UX_UI_NOUVEAU_PARADIGME.md` (choix utilisateur validés : renommage, périmètre maximal, thème clair d'abord, backend adapté librement).
- **Thème clair global** (codemod sur 39 fichiers + design system `/app/design_guidelines.json`) : fond #F7F7F6, surfaces blanches, encre #111110, primaire indigo #3730A3, états sémantiques couleur+libellé ; palette domaines/relations adaptée au clair (`lib/domaines.js`) ; `glass` clair ; focus-visible AA ; `prefers-reduced-motion`.
- **En-tête global unique** (sidebar supprimée) : MÉRIDIAN · sélecteur équipe/espace + badge « Vue complète du périmètre autorisé » · nav centrée **Actualités · Atlas · Travaux · Jumeaux · Administration** · chip « ● Mesh vivant » · bouton Parcours · pilule « Parler à Flore » · notifications · persona (`Topbar.jsx`, `Layout.jsx` allégé).
- **Renommage Cases → Travaux** : routes canoniques `/travaux`, `/travaux/:cid` ; redirections `/cases`→`/travaux`, `/cases/:cid`→`/travaux/:cid`, `/decisions`→`/travaux`, `/aujourdhui`→`/` ; libellés, toasts, notifications et seed alignés ; testids renommés (`travaux-*`, `travail-*`, `flore-creer-travail-btn`) ; « CASE-0xx » conservé comme identifiant interne discret. API backend `/api/cases` inchangée (Case reste l'objet interne).
- **Actualités (nouvelle page `/`)** : feed temporel narratif (histoires regroupées, pas de KPI) — navigation ‹/› + presets (Aujourd'hui/Hier/Il y a 2 jours/7 j/30 j) + date précise, portées **Personnel / Mon espace / Mesh global** (repli + note si non autorisé), bannière « le direct est suspendu » en consultation passée, insertion temps réel sans interruption (« N nouvelles actualités », polling 15 s), actions par histoire (Comprendre → Flore préremplie, Voir dans l'Atlas avec date, Ouvrir le travail, Approfondir), **Résumé par Flore** (déterministe) et « Voir la journée dans l'Atlas ».
- **Backend `GET /api/actualites`** (`actualites_routes.py`, paramètres date/jours/portee) : agrège situations, découvertes/évolutions de relations, historique des travaux, journal de gouvernance ; parser de dates relatives françaises ; tri par score ; **RBAC strict** (jumeaux projetés sur le périmètre — fuite corrigée sur les histoires de travaux).
- **Reprise intelligente** : panneau « Reprise — Flore vous replace » à l'onglet Aperçu dès la 2ᵉ visite (où vous étiez / ce qui a changé / ce qui reste incertain / prochaine action), composé depuis evolutions_recentes/hypothèses/options existants.
- **Atlas temporel** : modes **Direct / Pause / Replay / Historique / Avant-Après** (panneau calques) — Historique masque les relations découvertes après la date (parser `lib/temps.js`, `appliquerTemps` dans `atlasGraph.js`), Replay = relecture animée de la construction du Mesh, Avant/Après surligne les nouvelles relations (tirets cyan) avec compteur ; bandeaux temporels + « Revenir au direct » ; `?date=AAAA-MM-JJ` ouvre l'Atlas en photographie historique (lien depuis Actualités).
- **« Expliquer cette carte »** (WCAG) : bouton toolbar → panneau textuel structuré (résumé Mesh, position, domaines+maturités, relations par état, sélection), `role="complementary"`.
- Tests : **iteration_22 → 100 %** (backend 88/88 dont 6 nouveaux `test_actualites.py` : périodes, portées, RBAC support/paiements ; frontend complet, 0 erreur console). Bug trouvé/corrigé par l'agent de test : clés React dupliquées `jrn-*` (projection `_id` + variable de boucle). Parcours démo acte 3 → `/travaux/case-olympiade`.

## Implémenté (26/08/2026 — v14, le Case devient un cockpit de situation)
Spécification utilisateur appliquée à la lettre : le Case ne s'ouvre plus sur la conversation mais sur un cockpit lisible en moins d'une minute.
- **En-tête permanent** : numéro `CASE-0xx` (num auto-incrémenté), titre, badges type/sensibilité/« À revoir », participants (personas), dernière évolution ; actions « Continuer avec Flore » (ouvre le panneau avec les jumeaux du case en contexte), « Ouvrir dans Atlas », « Partager » (copie du lien), menu ••• (Marquer revu / Clore-Rouvrir).
- **5 vues internes** (`?vue=`) : **Aperçu** (6 blocs — Situation, Compréhension actuelle avec « Actualiser par Flore », Évolution récente **depuis ma dernière visite** trackée par persona côté serveur, Questions ouvertes, Décisions attendues, Prochaine étape) ; **Travail** (questions, hypothèses à 3 statuts cyclables, investigations liées avec ouverture inline → vraie situation créée et liée, livrables) ; **Atlas** (sous-graphe du case en lecture seule + ouverture dans l'Atlas complet) ; **Décisions & actions** (options avec Retenir→décision / Écarter, décisions humaines) ; **Activité** (flux unifié conversation+historique, 6 filtres : Discussions/Flore/Découvertes/Décisions/Changements du Mesh/Tout).
- **Promotions Flore explicites** : chaque réponse de Flore dans un case propose [Ajouter comme question] [Ouvrir une investigation] [Voir les preuves] [Ignorer] — une réponse ne devient jamais automatiquement une vérité du Case. Les messages Flore stockent preuves/propositions/contributions.
- **Cartes /cases enrichies** : chip CASE-0xx, extrait « Compréhension actuelle », stats (jumeaux/participants/questions/décisions attendues), « Modification importante », et deux actions distinctes : « Voir l'aperçu » (cockpit) vs « Continuer » (→ onglet Activité).
- **Flore contextuelle** : depuis un case, le panneau affiche « Flore — CASE-0xx » + bloc Contexte actif (titre, nb jumeaux).
- **Backend** : champs num/resume/sensibilite/prochaine_etape/hypotheses/visites ; endpoints POST `/cases/{id}/resume` (résumé vivant), `/hypotheses`, `/investigations` ; GET détail calcule `evolutions_recentes` par persona ; `DELETE /api/jumeaux/{id}` ajouté (cycle de vie registre, cascade relations + réferences cases) ; bug corrigé : la réinitialisation démo ne purgeait pas les notifications.
- Tests : iteration_21 → **100 %** (82/82 pytest dont 10 nouveaux, cockpit complet, promotions, filtres, Flore contextuelle, 0 erreur console). Note : suite pytest à lancer avec `-o addopts=''` (flakiness connue de l'ingress sous parallélisme, non reproductible en isolation).

## Implémenté (26/08/2026 — v13, Aujourd'hui personnel + équipes + « hypothèse fausse » + refactor)
- **Aujourd'hui refondu en tableau de bord personnel** (choix utilisateur : suivre le modèle produit, pas l'existant) : « Bonjour, {persona} » + date, 4 KPI (cases en cours, décisions en attente, découvertes, alertes connaissance), sections Mes cases, Décisions en attente (situations + cases), Nouvelles découvertes (→ Atlas focus profond), Alertes de connaissance (→ revue jumeau), Activité des jumeaux (live), Suggestions de Flore (→ panneau prérempli), Changements sur le périmètre (journal). L'ancien observatoire 3 colonnes est supprimé.
- **Espaces d'équipe complets** : cases avec `responsable` (persona), `participants` (ids personas) et `espace` ; filtre « Mes cases » ; sélecteur de responsable à la création et dans le détail ; **notifications** (collection + GET/lue/tout-lire + cloche Topbar avec badge et panneau, polling 15 s) ; assignation → notification au responsable.
- **Hypothèse devenue fausse** : confirmation de relation ou admission de jumeau → cases non clos concernés passent `a_revoir` (badge partout + bandeau + « Marquer comme revu »), historique enrichi, participants notifiés. C'est la « connaissance vivante » du modèle.
- **Refactor** : endpoints cases extraits dans `backend/cases_routes.py` (`build_cases_router` avec injection de dépendances) — server.py 1237 → ~1060 lignes, signatures inchangées.
- Tests : iteration_20 → **100 %** (22/22 pytest dont 8 nouveaux `test_notifications_arevoir.py`, frontend complet, 0 erreur console, seed restauré).

## Implémenté (26/06/2026 — v12, PIVOT PRODUIT : Atlas + Cases + Flore)
**Décision utilisateur (modèle produit recommandé)** : Méridian = plateforme de connaissance vivante ; navigation finale « Aujourd'hui · Atlas · Cases · Jumeaux · Administration » + Flore dans l'en-tête. « Voir avec l'Atlas. Travailler dans un Case. Dialoguer avec Flore. »
- **Aurora → Flore** : la barre du bas a disparu ; Flore est un **panneau dédié docké à droite** (`FlorePanel.jsx`, `flore-panel`) ouvert depuis l'en-tête (`flore-btn` + badge de contexte), ⌘K, ou `meridian:flore-ask`. Conversation **multi-tours** persistée en mémoire, contributions/preuves/propositions/TrustBadges conservées, commandes carte actives. La barre d'actions en lot de l'Atelier (`lot-bar`) y est préservée. Anciens testids `aurora-*` → `flore-*`.
- **Cases — nouvelle unité centrale** : collection MongoDB `cases` (5 cases seedés référençant jumeaux + situations) ; endpoints GET/POST `/api/cases`, GET/PATCH `/api/cases/{id}`, POST `/messages` (Flore répond via le moteur extrait `generer_reponse_flore`, avec le contexte jumeaux du case), `/decisions`, `/options`, `/livrables` (synthèse). RBAC : un case n'est visible que si ses jumeaux sont dans le périmètre.
- **Page /cases** : 3 vues (Liste/Kanban/Chronologie), filtres type/statut/recherche, création inline sans modale. **Page /cases/:id** : objectif éditable, questions cochables, conversation Flore persistée, options & scénarios, décisions, livrables, historique automatique, contexte SI → Atlas/registre.
- **Absorption** : pages Décisions et Change Lab supprimées → redirections `/decisions → /cases`, `/change-lab → /cases/case-olympiade` ; l'acte 3 du parcours Olympiade pointe vers le Case. Investigations restent accessibles (méthode de travail dans un Case) mais sortent de la nav.
- **Articulation clé** : « Créer un Case » depuis une conversation Flore (`flore-creer-case-btn`) — titre/objectif/jumeaux/conversation repris automatiquement.
- Tests : iteration_19 → **100 %** (14/14 pytest backend, tous parcours frontend, RBAC support 403 vérifié, Olympiade complet, 0 erreur console).
- Reste du modèle à livrer (phases suivantes) : Aujourd'hui = tableau de bord personnel (cases récents, décisions en attente, suggestions Flore) ; **Flore sur vrai LLM** (clé universelle Emergent) ; participants/espaces par équipe ; mise à jour du Case quand une hypothèse devient fausse.

## Implémenté (26/06/2026 — v11, Atlas sans modes — Territoire unique)
- **Décision utilisateur : suppression des modes Situation et Parcours** (redondants avec le paradigme Découvrir/Comprendre/Décider et avec Aurora). L'Atlas = Territoire, point. La barre de modes disparaît ; le panneau haut-gauche devient un simple bouton « Calques » (`controle-toggle` → `controle-details` : Direct/Pause, dynamiques, badge périmètre, enregistrement de vue). L'outil « Explorer un parcours » est retiré de la toolbar (restent déplacement/lasso/recentrage).
- **Focus profond situation** : `/atlas?situation=<id>` estompe les jumeaux non impliqués + bandeau `map-situation-banner` avec sortie `map-clear-situation`. Liens « Voir dans l'Atlas » ajoutés : cartes d'Aujourd'hui (`voir-atlas-<id>`, au survol) et InvestigationDetail (`voir-atlas-btn`).
- **Nettoyage** : `PARCOURS` statiques retirés du seed et du payload `/api/mesh` (plus aucun lecteur). L'isolation de parcours dynamique par Aurora (commande_carte type parcours) est conservée. Un futur parcours viendrait d'Aurora ou de parcours éditables (backlog P2).
- Testids retirés (intentionnel) : `map-mode-*`, `map-situation-select`, `map-parcours-select`, `outil-parcours`.
- Tests : iteration_18 → 100 % (opacités vérifiées au focus, liens profonds, non-régression zoom/portes/fil d'Ariane/lasso/Aurora, petit écran, Olympiade acte 1, 0 erreur console).
- **v11.1 (retour utilisateur)** : le focus profond **cadre la caméra** sur les jumeaux concernés (`fitBounds` sur `?situation=` et `?focus=`, une fois par cible, inhibé en vue domaine/jumeau) et **le contexte Aurora suit toujours le focus** : les jumeaux de la situation deviennent la sélection (chips + suggestions contextuelles immédiates). Vue globale sans focus inchangée (pas de sélection imposée).

## Implémenté (26/06/2026 — v10, refactor Atlas + petit écran)
- **Refactor d'Atlas.jsx (1335 → 441 lignes), sans changement de comportement** : `lib/atlasGraph.js` (MODES/COUCHES/NIVEAUX_ZOOM, styleParEtat, makeEdge, statsDuDomaine, construireGraphe — pur, testable) ; hooks `components/map/useNavigationAtlas.js` (focus domaine/jumeau, historique, fil d'Ariane, majUrl) et `useZoomSemantique.js` (molette sémantique, seuils, survol) ; composants `AtlasControle` (modes, Direct/Pause, couches, vues), `AtlasToolbar`, `FilAriane`, `AtlasLegende`, `AtlasPanneau` (+ `details.jsx` : RelationDetail/DomaineDetail/ComparaisonDomaines/TwinDetail). Tous les data-testid préservés.
- **Petit écran (<1500px)** : panneau latéral démarre replié (bouton « Détail », `panneau-ouvrir-btn`), légende démarre pliée (`legende-toggle`) ; toute sélection rouvre le panneau ; `panneau-fermer-btn` replie ; repli automatique au redimensionnement (matchMedia) ; légende dépliée surélevée (`bottom-24`) sous 1500 px pour ne pas chevaucher la barre Aurora. Toute la carte est visible en 1366×768.
- Tests : iteration_17 → ~95 % (non-régression Atlas complète 1920 + petit écran 1366, 0 erreur console) ; correctif chevauchement légende/Aurora vérifié. Note outillage : dans cet environnement, `set_viewport_size`/`reload` ne changent pas `innerWidth` — utiliser un nouveau contexte Playwright ou l'émulation CDP.
- **v10.1 (retour utilisateur, inspiration Google Maps)** : le panneau de contrôle haut-gauche devient une **barre de modes compacte** (Territoire/Situation/Parcours + bouton « calques » `controle-toggle`) ; Direct/Pause, dynamiques, badge périmètre et enregistrement de vue se rangent dans la zone dépliée (`controle-details`) ; replié par défaut sous 1500 px. Les sélecteurs de situation/parcours et le lien « Retirer le filtre » restent toujours visibles quand le mode l'exige.

## Implémenté (25/06/2026 — v9, suppression des modales — revue d'admission)
- **Choix utilisateur : zéro modale, zéro panneau latéral.** La revue d'admission (ex-`examen-dialog`, seule modale de l'app) est remplacée par :
  - **Expansion inline** dans le registre (`Jumeaux.jsx`) : clic sur une ligne (ou « Ouvrir ») → la ligne se déplie et affiche la revue complète (strates, sources, capacités, comportements, relations A2A, contradictions, manquantes, propriétaire, autonomie) + lien « Ouvrir la revue complète → ». Données d'examen chargées paresseusement et mises en cache (`revues`), purgées au changement de périmètre.
  - **Page dédiée plein écran `/jumeaux/:jid/revue`** (`RevueJumeau.jsx`) : en-tête façon Atelier (retour Registre, titre « Revue d'admission — X » en observation, badge statut, « Centrer dans l'Atlas »), contenu complet, bouton « Confirmer l'admission dans le Mesh » (niveau complet requis) → toast + retour au registre. « Revoir l'admission » y navigue directement.
- **Composant partagé `RevueContenu.jsx`** (expansion + page) ; constantes/helpers du registre extraits dans `lib/jumeaux.js`.
- **Bug P0 Topbar non reproduit** : en-tête du registre entièrement cliquable (vérifié par elementFromPoint, plusieurs viewports) — le chevauchement reporté n'existe plus.
- Tests : iteration_16 → 9/9 scénarios frontend, 0 erreur console, aucun role=dialog résiduel, admission + reset démo validés. Correctif mineur : feedback toast si copie presse-papiers impossible.
- **v9.1 (retour utilisateur)** : le bouton d'action de ligne (« Ouvrir » / « Reprendre la construction » / « Revoir l'admission ») navigue désormais **directement** vers `/jumeaux/:jid/revue` — plus de double chemin déplier→« revue complète ».
- **v9.2 (retour utilisateur)** : dépliage inline **entièrement supprimé** — le clic sur la ligne navigue aussi directement vers la page de détail. Le registre redevient une pure table de navigation (cases contexte Aurora, menu ⋯ et filtres inchangés). `RevueContenu.jsx` n'est plus utilisé que par `RevueJumeau.jsx`.

## Problème d'origine (résumé)
Construire Méridian non pas comme un Atlas/graphe centré sur les jumeaux, mais comme un **système de compréhension et de décision pour le SI**, organisé autour de l'objet **Situation**. Repositionnement v2 (utilisateur) : **système qui apprend continuellement la structure et le comportement du SI** — cycle Découverte candidate → Compréhension validée → Décision éclairée → Mémoire du Mesh. L'accueil devient un Observatoire des découvertes (3 colonnes Découvert / À comprendre / À décider), l'Atlas montre l'évolution du savoir (6 états de relations, maturité des domaines, 3 dynamiques temps réel), les investigations couvrent relations/comportements/connaissances/contradictions, chaque décision enrichit la mémoire du Mesh. Code couleur : Découvrir cyan, Comprendre violet, Décider ambre.

## Implémenté (25/06/2026 — v8.1, refonte UX de l'atelier — critique design experte)
- Critique design via design_agent (`/app/design_guidelines.json`) : 5 corrections appliquées.
- **P1 Stabilité spatiale** : grille fixe 8/4 permanente (la file ne se re-fluide plus à l'ouverture de l'inspecteur ; état vide élégant permanent).
- **P2 Palette ⌘K** : le catalogue tiroir latéral devient une palette de commande centrée (auto-focus, navigation ↑↓/Enter/Esc, animation scale+fade) — fini la collision tiroir/inspecteur.
- **P3 Barre morphing** : la barre Aurora globale se transforme en barre d'actions en lot (framer-motion layout) quand des sources sont cochées — lot partagé via `contexte.jsx` (lot/setLot), purge à la navigation ; plus de double barre flottante.
- **P4 Hiérarchie des statuts** : bordure gauche colorée par statut sur chaque ligne (scannable sur 100 sources) + CTA primaire « Corriger → » dans l'inspecteur (focus le premier champ manquant).
- **P5 Stepper compact** : fil d'Ariane dans l'en-tête avec ligne de progression (libère la hauteur verticale).
- Tests : iteration_15 → 14/14, non-régression Atlas/Aujourd'hui/Investigations OK, 0 erreur console.

## Implémenté (25/06/2026 — v8, atelier de commande d'un jumeau)
- **Nouvelle page `/commande/:cid`** (plein écran, remplace la modale à onglets) : 4 étapes — Identité → Sources et connexions → Plan de découverte → Vérifier et lancer ; en-tête persistant (nom, APP-id, domaine, « Brouillon enregistré », quitter, stepper cliquable) ; **brouillons persistés côté serveur** (collection `commandes`, autosauvegarde debounce 900 ms) ; reprise depuis la page Jumeaux (« commandes en cours »).
- **Atelier des sources** : indicateurs de préparation cliquables (filtrent la file), file d'instances avec colonnes (connecteur, environnement, périmètre, propriétaire, état, dernier test), recherche + filtres + regroupement repliable (connecteur/environnement/statut/équipe), cases à cocher → **barre d'actions en lot** (profil, environnement, fréquence, tester, supprimer).
- **Inspecteur adaptatif** : formulaire spécifique par connecteur (PostgreSQL, Oracle, Jira, Datadog, Splunk, ServiceNow, GitHub, Confluence, CMDB, Kafka, Apigee, AWS), test de connexion simulé (progression dans la ligne, erreurs explicites : configuration incomplète / périmètre vide / erreur de connexion + action corrective), cycle de statuts complet.
- **Catalogue tiroir** : recherche prioritaire (nom/besoin/catégorie), capacités, « N instances déjà configurées », 5 modes d'ajout (nouvelle instance, profil, dupliquer, import, CMDB).
- **Import massif** avec aperçu chiffré (détectées/nouvelles/présentes/à mapper) avant confirmation.
- **Plan de découverte** par objectif de connaissance avec contribution de chaque source ; **vérification finale** (prêtes/reportées/erreurs avec détails, couverture attendue, manifeste) et lancement réel du jumeau dans le Mesh (statut observation).
- Backend : `GET /api/connecteurs`, CRUD `/api/commandes`, `POST tester` (simulation déterministe), `import/apercu`, `lancer` — tout journalisé ; brouillon de démo « Remboursements » seedé (8 sources, états variés).
- Tests : iteration_14 → backend 10/10 pytest (`tests/test_commandes.py`), parcours frontend complet validé, 0 erreur console.

## Implémenté (25/06/2026 — v7.2, documentation)
- **`/app/README.md`** rédigé : présentation, espaces, modèle d'interaction de l'Atlas (sélection vs focus, hiérarchie de zoom, portes), Aurora (synchronisation bidirectionnelle), RBAC par personas/espaces, pile technique, démarrage, seed, API principale, tests.

## Implémenté (25/06/2026 — v7.1, correctif zoom jumeau)
- **Bug utilisateur corrigé** : « zoom sur le jumeau très grand + remontée au moindre dézoom ». Cadrage d'entrée du focus jumeau élargi (fitBounds 690×480 → 1090×740, zoom d'entrée ~0.92 au lieu de ~1.5, tous les voisins visibles) ; seuils de remontée molette abaissés (jumeau 55 % → 38 % du zoom d'entrée, domaine 55 % → 45 %). Vérifié : ~6 crans réels de dézoom restent en focus, ~8 crans francs remontent au domaine. Tests : iteration_13 → correctif validé, 0 régression.

## Implémenté (25/06/2026 — v7, hiérarchie complète du zoom Mesh → Domaine → Jumeau)
- **Règle sélection vs focus** : clic = sélection dans le contexte Aurora (la carte ne change pas de niveau) ; double-clic/molette = prise de focus (navigation dans l'élément).
- **Niveau jumeau** : double-clic sur un jumeau → vue locale radiale : jumeau centré (anneau `twin-focus-ring`), voisins en portes périphériques (`voisin-{id}`) avec état de la relation ; survol voisin = aperçu relation (nature, échangé, confiance, claims) ; **clic voisin = transfert de focus** (caméra suit, fil d'Ariane actualisé, Aurora conserve l'historique).
- **Portes = navigation** : clic sur un domaine pointillé → transfert du focus domaine (le corridor s'illumine, la caméra suit) ; survol = aperçu (« Risque · 2 jumeaux accessibles · 1 relation avec Paiement · Cliquer pour explorer ») ; cadenas + « accès limité » si domaine restreint. PorteDetail supprimé (remplacé par aperçu + navigation).
- **Molette sémantique** : zoom avant ≥ 2.3 sur l'élément survolé → entrée ; zoom arrière < 55 % du zoom d'entrée → remontée d'un niveau (jumeau → domaine → Mesh) ; verrou 1 s après chaque transition ; maxZoom 2.6.
- **Navigation** : fil d'Ariane 3 niveaux cliquables + historique ←/→ (`nav-precedent`/`nav-suivant`) + « Revenir à ma sélection (N) » (`nav-selection`, retour vue globale + fitBounds sur la sélection) ; MiniMap existante.
- **Aurora** : « Focus visuel : X » distinct de la sélection analytique ; entrer dans un domaine avec une sélection externe → prompt « Conserver / Retirer / Ajouter les jumeaux de X » (jamais de suppression automatique) ; focusVisuel ajouté au store partagé.
- **Correctif URL** : `majUrl` cumulatif via ref (les appels multiples dans un même tick ne se perdent plus).
- Tests : iteration_12 → 12/12 scénarios frontend, 0 erreur console ; point mineur nav-selection corrigé et retesté.

## Implémenté (25/06/2026 — v6, Aurora interface contextuelle native de l'Atlas)
- **Store partagé Atlas ↔ Aurora** (`lib/contexte.jsx`) : sélection, domaine courant, commandes carte (focusCarte). Synchronisation bidirectionnelle réelle.
- **Atlas épuré** : barre « N jumeaux sélectionnés » supprimée, boutons « Demander à Aurora » supprimés, **barre d'actions du domaine supprimée** (analyse validée par l'utilisateur : 5 actions sur 8 redondantes avec Aurora) — « Explorer / Comparer / Enregistrer comme espace / Utiliser comme périmètre » déplacées dans le panneau latéral DomaineDetail ; indicateur « Périmètre de travail » réinstallé en chip carte (avec retrait ×). Lasso = union avec la sélection existante. Clics inhibés quand l'outil lasso est actif.
- **AuroraBar contextuelle** : chips de sélection (× pour retirer), puce « Domaine X · N jumeaux accessibles », suggestions contextuelles (Comprendre les relations · Dépendances inconnues · Analyser un changement · Points critiques · Optimiser le parcours · Ouvrir une investigation), propositions Aurora→Atlas (Ajouter au contexte / Examiner la justification / Ignorer — jamais sans confirmation), repli en pastille flottante sans perte de contexte. Aucune analyse automatique à la sélection.
- **Backend** : `/api/aurora/demander` reçoit l'enveloppe {selection, domaine} — intentions calculées depuis le vrai Mesh (relations internes, non confirmées, impact, points critiques avec proposition de jumeau dégradé, parcours, investigation), accusé de contexte sans analyse, scénarios prescriptés Olympiade préservés sans sélection ; sélection analytique filtrée RBAC niveau « résumé » minimum.
- **Commandes carte** : Aurora éclaire les relations (commande_carte relations), isole un parcours, navigue vers un domaine ; chip « Vue commandée par Aurora » avec retrait.
- **Correctif robustesse carte** : initialWidth/initialHeight sur tous les nœuds — fini la fenêtre d'invisibilité (visibility:hidden en attente ResizeObserver) qui rendait la carte noire par intermittence et cassait le hit-testing des clics.
- Tests : iteration_11 → backend 10/10, frontend 12/13 (lasso union non concluant côté automate, code correct + garde ajoutée) ; correctifs RBAC/lasso retestés par curl et screenshots.

## Implémenté (25/06/2026 — v5.1, correctif cosmétique)
- **Warning hydration `<span>` dans `<option>` éliminé** : l'instrumentation Emergent injectait un span autour des expressions dynamiques enfants des `<option>`. Les options des sélecteurs (Topbar périmètre/persona, Atlas situation/parcours) utilisent désormais l'attribut `label` (HTML standard) au lieu d'enfants texte. Console 100 % propre (0 warning, 0 erreur), affichage et changements de sélection inchangés.

## Implémenté (25/06/2026 — v5, P1 + domaine premier niveau)
- **Réinitialiser la démo** : `POST /api/demo/reinitialiser` (vide/re-seed les collections + journal d'audit) ; section « Zone de démonstration » dans Administration avec confirmation en 2 clics, toast + reload.
- **Recherche plein texte Aurora** : fallback des scénarios prescriptés — recherche serveur dans jumeaux (nom/mission/domaine/propriétaire), relations (claims, extrémités) et situations (titres), **filtrée par le périmètre RBAC**, scoring par tokens distincts matchés (nom > mission > domaine), désinence du pluriel français ; réponse avec contributions + action de navigation (`/atlas?focus=`). Hors périmètre et fallback « connaissances manquantes » préservés.
- **Persistance du contexte carte dans l'URL** : `?sel=<jumeau>` au clic jumeau, `?domaine=X&interne=1` à l'entrée dans un domaine (replace, pas de spam d'historique) ; restauration au chargement (lien profond) ; clic pane en vue interne conserve le domaine.
- **Résumé de territoire dynamique** : « N jumeaux · N découvertes · N investigations · N zones inconnues » calculé depuis les situations actives (verbe decouvert / a_comprendre) + **point d'activité temps réel** pulsant sur le header du domaine quand un de ses jumeaux émet un événement (`region-activite-{id}`).
- Tests : iteration_10 → backend 7/7 pytest + frontend 8/8, 0 erreur console applicative.

## Implémenté (25/06/2026 — v4.1, domaines interactifs : zoom hiérarchique)
- **Correctif P0 double-clic domaine** : le `onNodeDoubleClick` de React Flow v12 ne se déclenchait jamais (reciblage du 2ᵉ clic vers le pane lors du pan/capture d3). Solution déterministe : détection manuelle du double-clic dans `onNodeClick`/`onPaneClick` (fenêtre 450 ms + `screenToFlowPosition` pour retrouver la région sous le curseur si le 2ᵉ clic est reciblé), `zoomOnDoubleClick={false}`, classe `nopan` sur le header de région (`RegionNode.jsx`).
- **Zoom hiérarchique Mesh → Domaine** : double-clic sur un domaine → vue interne (jumeaux du domaine uniquement) + fil d'Ariane « Mesh global › Domaine X » (clic = sortie, fitView animé) ; fitBounds élargi (rayon = max(w,h)/2+130+120) pour cadrer les portes.
- **Portes externes** : nœuds périphériques « Vers X · N relations » orientés vers les régions externes, non sélectionnables ; clic → focus contextuel (autres portes/relations estompées) + panneau `PorteDetail` (liste des relations inter-domaines avec états) ; toggle au re-clic.
- Tests : iteration_9 → 12/12, 0 erreur console, non-régression sélection/lasso/Pause/zoom sémantique OK.

## Implémenté (24/06/2026 — v4, Atlas 2D à zoom sémantique — direction finale)
- **Suppression du mode Orbite 3D** (force-directed/3D écartés par l'utilisateur). Atlas = carte 2D type Google Maps.
- **Zoom sémantique 3 niveaux** (le zoom change le contenu) : Niveau 1 Entreprise (jumeaux masqués, corridors agrégés inter-domaines « Paiement ↔ Risque · N relations · activité élevée ») ; Niveau 2 Domaine (jumeaux + relations principales) ; Niveau 3 Jumeau (labels de relations détaillés). Niveaux 4 (relation) et 5 (preuves) via le panneau de détail existant.
- **Territoires souples type archipel** : blobs très arrondis à teinte discrète, nom toujours lisible, maturité + stats (jumeaux/découvertes/zones inconnues).
- **Barre d'outils cartographique gauche** : déplacement, lasso (sélection multiple), exploration parcours, recentrage. **Direct/Pause** pour le temps réel (la pause fige la chronologie sans la vider).
- **Focus contextuel** : sélection → voisins éclairés, reste translucide. **Barre contextuelle basse** (≥2 jumeaux) : Demander à Aurora (pré-remplit), Ouvrir une investigation, Rechercher des relations, Analyser un impact, Optimiser le parcours, Enregistrer la sélection (→ vue).
- Sélection native React Flow : clic simple remplace, Ctrl/Meta/Shift+clic cumule, lasso en rectangle partiel ; positions de nœuds déplacés persistées en session ; correctif boucle onNodesChange (garde d'identité).
- Tests : iteration_8 → 11/11, 0 erreur console.

## Implémenté (24/06/2026 — v3.1, Atlas « Orbite 3D » — retiré en v4)
- Mode optionnel **Orbite 3D** dans l'Atlas (`react-force-graph-3d` + three.js) : rotation libre sur tous les axes (drag), zoom/dézoom (molette), translation, auto-rotation lente ; sphères colorées par domaine (taille ∝ couverture), liens colorés par état (validation A2A violet, contestée rouge, supposée cyan), particules directionnelles sur les flux actifs ; hover = identité du jumeau (masquée pour les dépendances restreintes) ; clic → panneau Détail. Respecte le périmètre serveur (données déjà filtrées).

## Implémenté (24/06/2026 — v3, périmètres & autorisations)
- **Modèle 4 concepts** : Mesh global (vérité complète) / Espace (périmètre organisationnel) / Vue (filtre personnel, jamais de droits) / Investigation (périmètre collaboratif temporaire). Chaque requête évaluée côté serveur : identité + espace actif + autorisations (`resoudre_perimetre`, deny-by-default).
- **Personas & Espaces** : 3 personas (architecte, paiements, support), 5 espaces avec niveaux existence/resume/relations/preuves/complet et politiques de dépendances non autorisées (masquage complet / anonymisée « Dépendance externe restreinte » / résumé autorisé « Application restreinte — domaine X »). En-têtes `X-Persona`/`X-Espace` (intercepteur axios + localStorage).
- **Filtrage serveur** sur mesh, situations (404 si hors périmètre), activité temps réel, décisions, jumeaux, Aurora (question hors périmètre → refus explicite ; contributions/preuves filtrées ; suggestions filtrées).
- **Sélecteur de périmètre permanent** (topbar) : espaces + vues enregistrées + Mesh global si autorisé ; badge « Filtré côté serveur » / « Vérité complète du Mesh » ; sélecteur de persona.
- **Atlas contextualisé** : nœuds restreints anonymisés (pointillés, cadenas), badge dépendances restreintes, enregistrement de vues, application des vues (sélection / relations non confirmées / vigilance).
- **Périmètre d'investigation** affiché sur la fiche (propriétaire, participants, jumeaux autorisés, confidentialité, expiration, export).
- **Journal d'accès et de décisions** (collection `journal`, section Administration) ; guards : admettre/examiner/confirmer avec 403/404 appropriés.
- **Tests** : backend_test_perimetres.py 20/20 (matrice de refus) + régression UI 100 % (iteration_5).


- **Aujourd'hui** (`/`) : Observatoire en 3 colonnes verbes (Découvert / À comprendre / À décider), ticker live « En direct », 11 situations typées (nature : relation/comportement/connaissance/contradiction/incident/changement).
- **Atlas** (`/atlas`) : carte de la connaissance — 6 états de relations (observée/supposée/validation A2A/confirmée/contestée/obsolète) avec rendus distincts + légende, panneau détail de relation (découverte, source, confirmée par, claims, observations contraires, évolution, bouton « Confirmer » → mémoire enrichie), 3 couches de dynamiques togglables (opérationnelle/connaissance/mesh), régions avec maturité (« 2 jumeaux · 1 relation émergente · 2 zones inconnues »), modes Territoire/Situation/Parcours conservés, hover card sur les jumeaux.
- **Investigations** : filtres par nature + fiche découverte en 4 blocs (ce qui a été découvert / pourquoi / reste à comprendre / décision attendue) avec actions (investiguer, surveiller, confirmer la relation, classer coïncidence, plus d'observations).
- **Décisions** (`/decisions`) : file de décisions (relations à confirmer, conclusions à valider, admissions de jumeaux) + simulateur Change Lab intégré.
- **Jumeaux** (`/jumeaux`, ex-Registry) + **Administration** (`/administration` : couverture, matrice sources, propriétaires, admissions).
- **Aurora** : 3 comportements labellisés (Exploration cyan / Explication violet / Recommandation ambre), nouvelles suggestions par contexte.
- **Parcours Olympiade v2** : 3 actes (Découvrir /atlas → Comprendre /investigations/sit-relation-emergente → Décider /decisions).
- **Backend** : SEED_VERSION 2 (reseed auto), POST /api/relations/{id}/confirmer, GET /api/decisions, actions coincidence/observer. Redirections /carte→/atlas, /change-lab→/decisions, /registry→/jumeaux.
- **Tests** : backend 23/23 pytest, régression UI Playwright 100 % (rapports iteration_3/4).

## Implémenté (24/06/2026 — v1, base)
- Radar initial, Investigations 4 zones, Change Lab, System Map vivante (@xyflow/react), Registry + parcours d'admission 5 étapes, Aurora barre contextuelle, indicateurs de confiance, parcours 7 actes. Correctif ResizeObserver (filtrage global index.html).

## Choix utilisateur
- Aurora : **réponses simulées/prescriptées** (pas de LLM).
- Données : **jeu de démonstration riche pré-chargé** (Paiements, Comptes, Fraude, Support…), connecteurs simulés.
- Portée : les 5 espaces complets + Aurora, priorité au **parcours de démo Olympiade en 7 actes**.
- Interface **100 % française**, application moderne avec une **carte de qualité, interactive et vivante** (caractère vivant du Mesh).

## Architecture
- **Backend** : FastAPI (`/app/backend/server.py`) + MongoDB (seed idempotent au démarrage depuis `/app/backend/seed_data.py`). Endpoints sous `/api` : `/mesh`, `/jumeaux` (+admettre/examiner), `/situations` (+action/décision), `/change-lab` (+simuler/dossier), `/aurora/demander` + `/aurora/suggestions`, `/demo/actes`, `/activite`.
- **Frontend** : React 19 + Tailwind + shadcn, carte `@xyflow/react`, icônes `@phosphor-icons/react`. Thème « Mission Control » sombre (fond #050505, Chivo/IBM Plex Sans/IBM Plex Mono).
- **État mutable** : situations ignorées/surveillées/décidées, jumeaux créés/admis, dossiers de changement — persistés en MongoDB.

## Personas
- **Exploitant SI / SRE** : détecte et diagnostique via Radar + Investigations.
- **Architecte / lead** : prépare les changements dans Change Lab, explore la System Map.
- **Admin de la plateforme** : commande et admet les jumeaux dans Registry.
- **Présentateur Olympiade** : suit le parcours guidé en 7 actes.

## Implémenté (24/06/2026 — v1, détails historiques)
- **Investigations** : liste + détail en 4 zones (question, chronologie, hypothèses avec preuves pour/contre + confiance + vérifications, conclusion avec synthèse Aurora, contributions des jumeaux, preuves multi-sources, décision humaine persistée).
- **Change Lab** : description de changement, simulation, périmètre/consommateurs/effets indirects/processus/règles/incidents similaires/tests/zones non couvertes, tableau comparatif de 3 scénarios, rayon d'impact SVG, création de dossier de changement (DC-xxxx).
- **System Map** : 3 modes (Territoire avec 6 régions stables / Situation avec focus + relation non documentée mise en évidence / Parcours séquentiel), nœuds vivants (pulsation, halos, compteurs d'événements), arêtes actives animées, panneau latéral Détail/Chronologie live, légende, filtre via `?focus=`.
- **Registry** : table dense (statut, couverture, fraîcheur, autonomie, sources), examen d'un jumeau, admission, parcours de commande en 5 étapes (Déclarer → Connecter → Observer → Examiner → Admettre).
- **Aurora** : barre de commande flottante contextuelle (⌘K), suggestions par espace, réponses prescriptées avec contributions des jumeaux + preuves + indicateurs, action de navigation (filtre carte), fallback « connaissances manquantes ».
- **Indicateurs de confiance** partout : Confiance, Couverture, Fraîcheur, Contradictions.
- **Parcours Olympiade** : visite guidée en 7 actes (signal → situation → investigation → découverte → explication → décision → révélation).
- **Tests** : 18/18 backend pytest + E2E frontend 100 % (rapport `/app/test_reports/iteration_1.json`).

## MOCKÉ (assumé, choix utilisateur)
- AURORA : réponses prescriptées par mots-clés (PAS de LLM).
- Connecteurs Datadog/Splunk/ServiceNow : données de démo simulées.
- Flux `/api/activite` : échantillon simulé.

## Backlog priorisé
- **P0** : — (rien de bloquant).
- **P1** : Flore sur vrai LLM via clé universelle Emergent (utilisateur : « mime le LLM pour le moment ») — réponses, résumés d'Actualités et reprises de Travaux réellement générés ; auto-régénération de la « Compréhension actuelle » quand un travail passe « À revoir » ; thème sombre (utilisateur : « on fera sombre après » — bascule clair/sombre) ; valider manuellement le lasso en union sur un vrai navigateur.
- **P2** : surfaces génératives dynamiques dans les Travaux (fragment Atlas intégré, matrice d'impact, avant/après, comparaison de scénarios nommables/partageables) ; proposition de conservation de Flore (« Ce travail implique 4 jumeaux… [Le conserver] ») ; zoom Atlas Capacité → Connaissance → Preuve ; parcours éditables ; investigation agentique observable (progression ✓/◌/○ + contrôles humains) ; split de seed_data.py ; migration `on_event` → lifespan FastAPI ; durcissement CORS production ; persistance sessionStorage du contexte Flore.
- **Si vraie IA un jour** : brancher Flore sur un LLM via la clé universelle Emergent (budget : Profile → Manage plan → Universal Key).

## Prochaines tâches
1. Recueillir le retour de l'utilisateur sur la refonte (thème clair, Actualités, Travaux, Atlas temporel).
2. Flore LLM réel (P1) si l'utilisateur valide la base visuelle.
3. Thème sombre + bascule utilisateur (P1).
