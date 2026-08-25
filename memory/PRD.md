# Méridian — PRD

## Problème d'origine (résumé)
Construire Méridian non pas comme un Atlas/graphe centré sur les jumeaux, mais comme un **système de compréhension et de décision pour le SI**, organisé autour de l'objet **Situation**. Repositionnement v2 (utilisateur) : **système qui apprend continuellement la structure et le comportement du SI** — cycle Découverte candidate → Compréhension validée → Décision éclairée → Mémoire du Mesh. L'accueil devient un Observatoire des découvertes (3 colonnes Découvert / À comprendre / À décider), l'Atlas montre l'évolution du savoir (6 états de relations, maturité des domaines, 3 dynamiques temps réel), les investigations couvrent relations/comportements/connaissances/contradictions, chaque décision enrichit la mémoire du Mesh. Code couleur : Découvrir cyan, Comprendre violet, Décider ambre.

## Implémenté (24/06/2026 — v2, repositionnement « système qui apprend »)
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
- **P1** : réinitialisation de l'état démo (bouton « réinitialiser la démo ») ; recherche plein texte dans Aurora ; persistance du focus carte dans l'URL au clic.
- **P2** : migration `on_event` → lifespan FastAPI ; durcissement CORS pour la production ; découverte automatique de relations pour les nouveaux jumeaux admis ; vue Parcours éditable.
- **Si vraie IA un jour** : brancher Aurora sur un LLM via la clé universelle Emergent (budget : Profile → Manage plan → Universal Key).

## Prochaines tâches
1. Recueillir le retour de l'utilisateur sur le parcours Olympiade.
2. Étoffer les situations secondaires (chronologies/hypothèses complètes).
3. Éventuellement : mode édition du Mesh (ajout manuel de relations).
