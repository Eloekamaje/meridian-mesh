# Méridian

**Méridian** est une plateforme de compréhension et de décision sur un système d'information. Elle n'est pas un simple graphe de topologie : le système est organisé autour de **Situations** (incidents, changements, découvertes) et suit le paradigme **Découvrir → Comprendre → Décider**.

> Dans Méridian, sélectionner le SI revient à donner du contexte à Aurora. Interroger Aurora revient à transformer la vue du SI.

## Les espaces

| Page | Rôle |
|---|---|
| **Aujourd'hui** (`/`) | Observatoire : nouvelles connaissances, anomalies, flux d'activité temps réel |
| **Atlas** (`/atlas`) | Carte 2D cartographique à zoom sémantique avec territoires stables (façon Google Maps) |
| **Investigations** (`/investigations`) | Approfondissement : relations, comportements, contradictions, hypothèses |
| **Décisions** (`/decisions`) | Change Lab : simulation de scénarios de changement |
| **Jumeaux** (`/jumeaux`) | Registre des jumeaux numériques (admission, administration) |
| **Administration** (`/administration`) | Espaces, journal d'audit, réinitialisation de la démo |

## L'Atlas — navigation hiérarchique

Hiérarchie du zoom : **Mesh global → Domaine → Jumeau** (puis Relation → Claim → Preuve via le panneau latéral).

Règle essentielle : **sélectionner ≠ prendre le focus**.

| Action | Domaine | Jumeau |
|---|---|---|
| Survol | Aperçu (jumeaux, découvertes, relations) | Aperçu rapide (mission, état, couverture) |
| Clic | Sélection dans le contexte Aurora | Sélection dans le contexte Aurora |
| Double-clic | **Focus** : entrée dans le domaine | **Focus** : vue locale radiale du jumeau |
| Molette avant | Entrée progressive dans l'élément survolé | Idem |
| Molette arrière | Retour au Mesh | Retour au domaine |
| Clic sur une porte pointillée | Transfert du focus vers le domaine voisin | Transfert du focus vers le jumeau voisin |

- **Territoires** : résumé dynamique « N jumeaux · N découvertes · N investigations · N zones inconnues » + point d'activité temps réel.
- **Portes externes** : les domaines connexes restent visibles en périphérie (pointillé = accessible, cadenas = accès limité) ; le survol affiche un aperçu avant de naviguer.
- **Focus jumeau** : le jumeau est centré, ses voisins disposés en portes radiales avec l'état de chaque relation ; cliquer un voisin transfère le focus — on parcourt le SI par ses relations.
- **Navigation** : fil d'Ariane cliquable (`Mesh global › Domaine › Jumeau`), historique ←/→, « Revenir à ma sélection », mini-carte.
- **Sélection multiple** : Ctrl/Maj+clic (toggle), lasso (union avec la sélection existante), focus contextuel (le reste s'estompe).
- **Zoom sémantique** : niveau 1 = corridors agrégés entre domaines, niveau 2 = domaines, niveau 3 = relations détaillées.
- **Périmètre de travail** : un domaine peut devenir un filtre de travail volontaire (distinct de la sécurité RBAC).
- **Liens profonds** : l'URL reflète le contexte (`?domaine=X&interne=1&jumeau=Y&sel=Z`) — partageable et restaurable.

## Aurora — copilote contextuel

Barre persistante en bas de l'application, **synchronisée bidirectionnellement avec l'Atlas** :

- **Atlas → Aurora** : toute sélection (clic, Maj+clic, lasso, domaine) met à jour le contexte actif d'Aurora (chips avec retrait individuel) et propose des intentions : *Comprendre leurs relations · Dépendances inconnues · Analyser un changement · Points critiques · Optimiser ce parcours · Ouvrir une investigation*.
- **Aurora → Atlas** : Aurora commande la carte (éclairer des relations, isoler un parcours, naviguer vers un domaine) et propose des voisins pertinents avec justification — jamais sans confirmation (*Ajouter au contexte / Examiner / Ignorer*).
- **Focus visuel ≠ sélection analytique** : entrer dans un domaine conserve la sélection ; Aurora propose alors de la conserver, la retirer ou d'ajouter les jumeaux du domaine.
- Réponses **calculées depuis le vrai Mesh** (toujours filtrées par les autorisations serveur) : recherche plein texte avec scoring de pertinence, scénarios prescriptés pour le parcours de démonstration, accusé de contexte sans analyse automatique.
- La barre se replie en pastille flottante sans perdre le contexte (`⌘K` pour la rappeler).

## Sécurité — RBAC côté serveur

Pas d'authentification (démo) : le périmètre se pilote via les sélecteurs de la barre supérieure (persona + espace), envoyés au backend par les en-têtes `X-Persona` / `X-Espace`. **Tout le filtrage est fait côté serveur** — les données non autorisées ne quittent jamais l'API.

| Persona | Accès |
|---|---|
| `architecte` (A. Rousseau) | Mesh global + tous les espaces |
| `paiements` (L. Marchand) | Espace Paiements : paiements/facturation complets, comptes en lecture relations |
| `support` (J. Morel) | Espace Support : support/notifications complets, paiements au niveau « existence » (dépendances anonymisées) |

Niveaux d'autorisation par jumeau : `existence` → `résumé` → `preuves` → `complet`. Aurora refuse les questions hors périmètre et filtre ses analyses au niveau « résumé » minimum.

## Pile technique

- **Frontend** : React 19, Tailwind CSS, `@xyflow/react` (React Flow v12) pour la cartographie, Phosphor Icons, Sonner (toasts)
- **Backend** : FastAPI + Motor (MongoDB async), Pydantic v2
- **Base** : MongoDB (collections : `jumeaux`, `relations`, `situations`, `change_lab`, `dossiers`, `vues`, `journal`, `meta`)

```
/app
├── backend/
│   ├── server.py        # API, RBAC par espaces, intentions Aurora, seed
│   ├── seed_data.py     # Jeu de démonstration (SEED_VERSION, reseed auto)
│   └── tests/           # Tests pytest des endpoints
└── frontend/src/
    ├── pages/           # Atlas, Aujourdhui, Investigations, ChangeLab, Jumeaux, Administration
    ├── components/      # Topbar, AuroraBar, Layout, map/ (TwinNode, RegionNode)
    └── lib/             # api.js, perimetre.jsx, contexte.jsx (store Atlas↔Aurora), mesh.jsx, domaines.js
```

## Démarrage

```bash
# Backend (port 8001)
cd backend && pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8001 --reload

# Frontend (port 3000)
cd frontend && yarn install && yarn start
```

Variables d'environnement : `backend/.env` (`MONGO_URL`, `DB_NAME`), `frontend/.env` (`REACT_APP_BACKEND_URL`).

## Données de démonstration

Seed automatique au démarrage (clé `SEED_VERSION` : un changement réinitialise les données). Bouton **« Réinitialiser la démo »** dans Administration (trace au journal d'audit). Jeu : 12 jumeaux, 14 relations (6 états : observée, supposée, validation A2A, contestée, obsolète, confirmée), 11 situations, situation principale « Latence du parcours de paiement ». Un **Parcours Olympiade** guidé (bouton dans la barre latérale) fait la démonstration complète.

## API principale

| Endpoint | Rôle |
|---|---|
| `GET /api/mesh` | Mesh complet filtré par périmètre (jumeaux, relations, régions, parcours) |
| `GET /api/jumeaux` · `/api/relations` · `/api/situations` | Collections filtrées RBAC |
| `POST /api/aurora/demander` | Copilote : `{contexte, question, selection, domaine}` → réponse + propositions + commandes carte |
| `GET /api/activite` | Flux d'événements temps réel (simulé) |
| `POST /api/demo/reinitialiser` | Réinitialisation du jeu de démo (journalisée) |
| `POST /api/perimetre/set` · `GET /api/perimetre` | Gestion persona/espace/vue active |
| `POST /api/relations/{id}/confirmer` | Confirmation A2A d'une relation |
| `GET /api/journal` | Journal d'audit (accès, décisions, exports) |

## Tests

```bash
cd backend && pytest tests/ -q
```

Rapports d'itérations d'assurance qualité : `/app/test_reports/iteration_*.json`.
