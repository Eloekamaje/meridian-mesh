# Méridian — PRD

## Implémenté (26/06/2026 — v11, Atlas sans modes — Territoire unique)
- **Décision utilisateur : suppression des modes Situation et Parcours** (redondants avec le paradigme Découvrir/Comprendre/Décider et avec Aurora). L'Atlas = Territoire, point. La barre de modes disparaît ; le panneau haut-gauche devient un simple bouton « Calques » (`controle-toggle` → `controle-details` : Direct/Pause, dynamiques, badge périmètre, enregistrement de vue). L'outil « Explorer un parcours » est retiré de la toolbar (restent déplacement/lasso/recentrage).
- **Focus profond situation** : `/atlas?situation=<id>` estompe les jumeaux non impliqués + bandeau `map-situation-banner` avec sortie `map-clear-situation`. Liens « Voir dans l'Atlas » ajoutés : cartes d'Aujourd'hui (`voir-atlas-<id>`, au survol) et InvestigationDetail (`voir-atlas-btn`).
- **Nettoyage** : `PARCOURS` statiques retirés du seed et du payload `/api/mesh` (plus aucun lecteur). L'isolation de parcours dynamique par Aurora (commande_carte type parcours) est conservée. Un futur parcours viendrait d'Aurora ou de parcours éditables (backlog P2).
- Testids retirés (intentionnel) : `map-mode-*`, `map-situation-select`, `map-parcours-select`, `outil-parcours`.
- Tests : iteration_18 → 100 % (opacités vérifiées au focus, liens profonds, non-régression zoom/portes/fil d'Ariane/lasso/Aurora, petit écran, Olympiade acte 1, 0 erreur console).

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
- **P1** : valider manuellement le lasso en union sur un vrai navigateur (automate Playwright non concluant, code vérifié).
- **P2** : split de seed_data.py si le catalogue de connecteurs grandit ; persistance sessionStorage du contexte Aurora ; migration `on_event` → lifespan FastAPI ; durcissement CORS pour la production ; découverte automatique de relations pour les nouveaux jumeaux admis ; vue Parcours éditable ; niveaux de zoom Claim → Preuve (drill-down relation, aujourd'hui via panneau latéral) ; choix des colonnes secondaires de la file des sources (actuellement fixes).
- **Si vraie IA un jour** : brancher Aurora sur un LLM via la clé universelle Emergent (budget : Profile → Manage plan → Universal Key).

## Prochaines tâches
1. Recueillir le retour de l'utilisateur sur le parcours Olympiade.
2. Étoffer les situations secondaires (chronologies/hypothèses complètes).
3. Éventuellement : mode édition du Mesh (ajout manuel de relations).
