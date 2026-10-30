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
- **Mentions et commandes** : dans le Travail, `@Nom` ouvre la liste des jumeaux visibles et route explicitement la question vers celui qui est mentionné (les droits serveur filtrent toujours) ; `/resumer`, `/investiguer`, `/decision`, `/preuves`, `/pieces` et `/aide` remplissent une consigne explicite, que l'on relit avant l'envoi. Aucune commande n'exécute une action cachée.
- **Sources & Jumeaux** : le volet reprend les jumeaux du Travail **et ceux réellement consultés** (mention ou routage automatique), avec leurs sources (dépôts, lecteurs) ; il s'ouvre une fois quand une réponse apporte une source, puis reste fermé si l'utilisateur le referme.
- **Partage par lien** : le bouton « Partager » copie le lien du Travail et rappelle que la portée et le périmètre s'appliquent à l'ouverture ; le lien n'élargit jamais les droits.
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

### Plusieurs workers (Redis)

Le bus SSE et l'état des tours partagés passent par Redis dès que `REDIS_URL` est défini. Avec plusieurs
workers uvicorn, Redis est **obligatoire** : le démarrage échoue plutôt que de laisser chaque worker croire
qu'il est seul.

```bash
docker compose up -d redis
export REDIS_URL=redis://127.0.0.1:6379/0
cd backend && uvicorn server:app --host 0.0.0.0 --port 8001 --workers 2
```

`TOUR_TTL` (secondes, défaut 600) règle la conservation du flux et des métadonnées d'un tour.
`TOUR_HEARTBEAT` (5 s), `TOUR_STALE` (30 s) et `TOUR_REAPER` (10 s) règlent le battement de cœur du worker
propriétaire et le ramassage d'un tour dont le worker a disparu. Le flux SSE porte un `id:` Redis Stream :
une reprise utilise cet identifiant opaque, pas un index de tableau. Les notifications restent persistées
dans Mongo ; Redis ne porte que le temps réel. En production, Redis doit être authentifié (ACL/TLS) et
l'URL ne doit pas apparaître dans les logs.

## Identité

`AUTH_MODE` décide qui fixe la persona :

- `demo` (défaut local) : `X-Persona` est accepté, mais doit désigner une persona connue. **Interdit en production.**
- `proxy` : un proxy authentifiant (oauth2-proxy, ALB, etc.) fournit `X-Auth-Request-User` /
  `X-Auth-Request-Groups` et `X-Auth-Proxy-Secret`. Le client ne peut pas imposer `X-Persona`.
  `AUTH_PERSONA_MAP` associe utilisateurs ou groupes aux personas : `{"grp-arch":"architecte"}`.
- `oidc` : l'API vérifie un JWT `Authorization: Bearer` avec `AUTH_OIDC_JWKS_URL` (ou `AUTH_OIDC_SECRET`
  pour HS256), `AUTH_AUDIENCE`, `AUTH_ISSUER`, puis lit `persona` ou `groups` (`AUTH_GROUPS_CLAIM`).

Sans mapping, OIDC accepte une claim `persona` valide. Le header `X-Persona` est toujours remplacé par
l'identité résolue côté serveur. `GET /api/moi` expose la persona et le mode au frontend, qui masque alors
le sélecteur de rôle. En production, définir `APP_ENV=production` : `AUTH_MODE=demo` est refusé au démarrage.

## Pièces jointes d'un Travail

Un Travail accepte des pièces jointes : PDF, Word (`.doc`/`.docx`), PowerPoint (`.ppt`/`.pptx`/`.pps`/`.ppsx`/`.pot`),
Excel (`.xls`/`.xlsx`/`.xlsb`), OpenDocument (`.odt`/`.ods`/`.odp`), RTF, EPUB, CSV, texte, Markdown, JSON, HTML.
Les formats bureautiques passent par [anydoc](https://github.com/firecrawl/anydoc) (MIT, conversion locale en
Markdown, détection par le contenu) ; en cas d'absence du wheel natif, PDF/Word/Excel gardent un extracteur Python
de repli. anydoc est un wheel natif (Linux/macOS/Windows, Python ≥ 3.10) : sur une plateforme sans wheel, prévoir
Rust, ou retirer la dépendance et accepter le repli. **Aucun OCR hébergé** : un PDF scanné reste une pièce sans
texte, jamais envoyée à un service externe. Les variantes macro (`.docm`, `.xlsm`, `.pptm`, `.ppsm`) sont refusées.

Elles sont **versées comme sources du Travail, jamais comme des connaissances** : Flore les lit avec leur nom,
leur auteur et leur date, dit « d'après la pièce jointe … » et ne les cite jamais comme du code. Un document joint
ne crée ni Claim ni relation ; il reste dans le travail et disparaît avec lui.

Le Markdown est découpé en **sections** à l'upload (titres ATX, slides PowerPoint, préambule). À chaque tour, Flore
reçoit un **sommaire** et les sections les plus pertinentes pour la question (sélection lexicale bornée, budget
réservé par pièce), pas le document entier. Une section non fournie se lit avec `lire_piece` (fenêtre `debut`),
et les passages peuvent être recherchés avec `chercher_pieces` ; les deux sont limités au Travail courant et à un
plafond de lectures. Les tableaux (CSV, Excel, OpenDocument) exposent leurs feuilles/colonnes/lignes via
`lire_table`, qui rend une fenêtre bornée en Markdown — jamais de SQL ni de code exécuté.

Une citation de pièce est formulée « d'après la pièce “nom”, § titre » et porte le repère vérifiable
`pièce:<id>#<section>` (ou `pièce:<id>#table:<feuille>:<début>-<fin>`) : le contradicteur le contrôle contre le
sommaire réel, sans le confondre avec une preuve de code. Les citations de section sont cliquables dans le Travail
et ouvrent la section source. Ce n'est jamais un Claim. Les images distantes ne sont jamais chargées depuis une
réponse.

Seuls le **responsable** et les **participants** du Travail peuvent déposer une pièce ; un lecteur simple peut la
télécharger mais pas en ajouter. En mode `proxy`/`oidc`, les pièces ne sont transmises au modèle que si
`PIECES_ENVOI_MODELE_EXTERNE=1` (ou si `JUMEAU_MODELE` n'est pas un modèle externe) ; en `demo`, l'envoi est
autorisé par défaut. Sinon Flore dit qu'elle ne les a pas reçues — le fichier reste dans le Travail.

Limites par défaut (variables d'environnement) :

- `PIECES_MAX_OCTETS` (10 Mo) : taille d'un fichier ; `PIECES_MAX_PAR_CASE` (10) : nombre par travail.
- `PIECES_MAX_CARACTERES` (200 000) : texte conservé par pièce ; `PIECES_MAX_CARACTERES_PROMPT` (40 000) et
  `PIECES_MAX_CARACTERES_PIECE_PROMPT` (12 000) : budget du contexte envoyé à Flore à chaque tour.
- `PIECES_MAX_PAGES_PDF` (300) et `PIECES_MAX_FEUILLES_XLSX` (20) : bornes du **repli Python** ; le chemin anydoc
  a ses propres limites de ressources et le texte est de toute façon tronqué après conversion.
- `PIECES_DUREE_EXTRACTION` (15 s) : durée au-delà de laquelle l'ajout est refusé (le fil d'extraction ne peut pas
  être tué ; le pool dédié en borne l'impact).
- `PIECES_MAX_DECOMPRESSE` (40 Mo) : refus des archives bureautiques qui se décompressent au-delà.
- `PIECES_CONCURRENCE` (2) : extractions simultanées au plus par worker (un pool dédié, borné).
- `PIECES_MAX_CARACTERES_TOC` (4 000), `PIECES_MAX_SECTIONS` (300) et `PIECES_MAX_SECTIONS_PIECE_PROMPT` (4) :
  bornes du sommaire et du nombre de sections proposées à Flore.

Le contenu est stocké dans Mongo (GridFS) et partagé par les workers ; la réinitialisation de la démo et la
suppression d'une conversation suppriment aussi les fichiers. Retirer une pièce purge ses dérivés dans le fil
(`pieces_lectures`, `pieces_selection`, activité des outils de pièces) ; les citations déjà écrites peuvent rester
dans le texte, mais ne pointent plus vers un fichier. Les formats non lisibles (scan sans OCR, images) sont
refusés, ou conservés sans texte avec un état affiché honnêtement.

La recherche de sections est **lexicale** (titres + texte), complétée par `chercher_pieces` et `lire_piece` ; c'est
le choix complet à l'échelle d'un Travail (10 pièces), sans dépendance à un modèle d'embedding ni envoi de texte à
un service tiers. `evaluation_pieces` mesure recall@k/MRR ; une extension sémantique reste possible mais n'est pas
nécessaire au fonctionnement. Les images distantes d'une réponse ne sont jamais chargées.

Le contenu des pièces n'entre **jamais dans le prompt système** : il est fourni comme données balisées dans le
message utilisateur. Avec des pièces, Flore n'écrit dans le Travail que si l'utilisateur coche « Autoriser Flore à
modifier le travail » pour le tour ; sinon elle propose l'action sans l'exécuter. L'extraction (anydoc, pypdf,
python-docx, openpyxl) tourne dans un **processus séparé** avec timeout, mémoire/CPU bornés et réseau coupé
(`PIECES_EXTRACTION_PROCESSUS=0` pour les tests/développement). Au démarrage, les compteurs de quota des pièces sont
réconciliés avec la base.

| Endpoint | Rôle |
|---|---|
| `GET /api/cases/{cid}/pieces` | Métadonnées des pièces (jamais le texte) |
| `POST /api/cases/{cid}/pieces` | Dépôt multipart (`fichier`) |
| `GET /api/cases/{cid}/pieces/{pid}` | Téléchargement en pièce jointe (`nosniff`) |
| `GET /api/cases/{cid}/pieces/{pid}/extrait` | Texte extrait, borné |
| `GET /api/cases/{cid}/pieces/{pid}/sections/{sid}` | Fenêtre d'une section (`debut`, `limite`) |
| `DELETE /api/cases/{cid}/pieces/{pid}` | Retrait par l'auteur ou le responsable |

## Évaluation de la sélection de sections

Un harnais reproductible mesure la sélection lexicale sans base :
`backend/evaluation_pieces.py` lit un JSONL `{question, piece, section}` et un JSON de pièces, puis calcule
`recall@k` et `MRR` sur les sections réellement incluses par `sections_pour_prompt_detail`.

```bash
cd backend
python -m evaluation_pieces --docs docs.json --questions questions.jsonl --k 4
```

## Limites de plateforme

- `PATCH /api/cases/{cid}` ne modifie **jamais** la conversation (400) ; elle s'ajoute par `POST /messages` ou
  `POST /cases/{cid}/fusion`. Toutes les mutations de conversation (messages, versions, branches, régénération,
  modification) sont réservées au **responsable ou aux participants**.
- La fusion est réservée au **responsable** de la cible : elle réserve la source, déplace ses pièces sous quota
  atomique, normalise les messages importés (sans preuves/approbations clientes), puis supprime la source.
- Le journal est filtré par périmètre et les conversations privées n'y exposent ni titre ni nom de pièce ;
  `POST /api/journal` n'accepte que les changements d'identité/périmètre, avec un détail dérivé serveur.
- Décider ou agir sur une situation exige que **tous ses jumeaux** soient dans le périmètre (la lecture peut être
  partielle) ; l'audit est écrit dans l'espace résolu, jamais dans le header brut.
- Rate limiting : `TOURS_RATE_MAX` (30/60 s par défaut en production, appliqué aussi à `/aurora` et aux
  régénérations), `PIECES_RATE_UPLOAD_MAX` (30/300 s) et `PIECES_RATE_LECTURE_MAX` (240/60 s) ; désactivé hors
  production sauf réglage explicite. Redis partage les compteurs (script Lua atomique), avec repli mémoire hors Redis.
- CORS : `allow_credentials=False` (auth par en-têtes) ; `APP_ENV=production` refuse `CORS_ORIGINS=*` au démarrage.
- Suppression : pièces, fichiers GridFS, dérivés de conversation et entrées `retours` du Travail sont purgés.
- Mongo du compose de démonstration est **local** (127.0.0.1, sans auth). Pour un déploiement partagé :
  `docker compose --env-file .env.prod -f docker-compose.prod.yml up -d` (Mongo `--auth`, Redis mot de passe,
  Postgres, ports en boucle locale) ; copier `.env.prod.example` vers `.env.prod` et renseigner les secrets.
- `starlette>=1.6,<2` est requis par le middleware de limite de corps ; les embeddings/pgvector restent une
  décision d'infrastructure fondée sur `evaluation_pieces`.

## Coût et temps affichés

Chaque réponse de Flore conserve ses **durées** (total, premier mot, phases) et son **usage** (jetons d'entrée,
de sortie, cache) — agent principal, relecture et sous-agents compris. Le message affiche une ligne discrète
`12,4 s · premier mot 1,8 s · 3 245 jetons · ~0,0034 $`, avec le détail des phases au survol.

Le coût est une **estimation** : `JUMEAU_COUT_ENTREE_MILLION` (0,27 par défaut pour DeepSeek),
`JUMEAU_COUT_SORTIE_MILLION` (1,10) et `JUMEAU_COUT_DEVISE` (USD). Mettre les deux tarifs à `0` masque le coût.
Pour Bedrock ou un autre fournisseur, renseigner ses propres tarifs.

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
| `POST /api/cases/{cid}/fusion` | Ajout serveur d'une conversation à un Travail (append-only) |
| `POST /api/relations/{id}/confirmer` | Confirmation A2A d'une relation |
| `GET /api/journal` | Journal d'audit (accès, décisions, exports) |

## Tests

```bash
cd backend && pytest tests/ -q
```

Rapports d'itérations d'assurance qualité : `/app/test_reports/iteration_*.json`.
