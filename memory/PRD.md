# Méridian — PRD

Plateforme de compréhension des systèmes TI et d'aide à la décision : une IA conversationnelle (Flore) et une carte de connaissance continue (Atlas, zoom sémantique 4 niveaux, membranes de domaines concaves, routage orthogonal confiné) sur thème sombre « nuit profonde ». Mode kiosque de démonstration scénarisée « Polaris » (spécification `MERIDIAN_POLARIS_SPECIFICATION_IMPLEMENTATION.md`) : entrée `/demo`, la démo pilote la VRAIE application alimentée par des fixtures locales (adaptateur axios simulé, zéro réseau).

> Historique complet des implémentations : `CHANGELOG.md` — Backlog et prochaines tâches : `ROADMAP.md`.

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

## MOCKÉ (assumé, choix utilisateur)
- AURORA : réponses prescriptées par mots-clés (PAS de LLM).
- Connecteurs Datadog/Splunk/ServiceNow : données de démo simulées.
- Flux `/api/activite` : échantillon simulé.

