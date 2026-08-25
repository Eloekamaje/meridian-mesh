# Méridian — PRD

## Problème d'origine (résumé)
Construire Méridian non pas comme un Atlas/graphe centré sur les jumeaux, mais comme un **système de compréhension et de décision pour le SI**, organisé autour de l'objet **Situation**. Repositionnement v2 (utilisateur) : **système qui apprend continuellement la structure et le comportement du SI** — cycle Découverte candidate → Compréhension validée → Décision éclairée → Mémoire du Mesh. L'accueil devient un Observatoire des découvertes (3 colonnes Découvert / À comprendre / À décider), l'Atlas montre l'évolution du savoir (6 états de relations, maturité des domaines, 3 dynamiques temps réel), les investigations couvrent relations/comportements/connaissances/contradictions, chaque décision enrichit la mémoire du Mesh. Code couleur : Découvrir cyan, Comprendre violet, Décider ambre.

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
- **P1** : — (tous les P1 sont traités).
- **P2** : scission d'Atlas.jsx (~1200 lignes — hook useDomainNavigation + composant DomainView) ; migration `on_event` → lifespan FastAPI ; durcissement CORS pour la production ; découverte automatique de relations pour les nouveaux jumeaux admis ; vue Parcours éditable ; double-clic sur une porte externe = traverser vers le domaine voisin (suggéré, en attente du retour utilisateur).
- **Si vraie IA un jour** : brancher Aurora sur un LLM via la clé universelle Emergent (budget : Profile → Manage plan → Universal Key).

## Prochaines tâches
1. Recueillir le retour de l'utilisateur sur le parcours Olympiade.
2. Étoffer les situations secondaires (chronologies/hypothèses complètes).
3. Éventuellement : mode édition du Mesh (ajout manuel de relations).
