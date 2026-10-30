# MÉRIDIAN — Le chat de Flore face aux standards de l'industrie
## Interface, protocole, bibliothèques, et capacité à traiter un sujet complexe

**Statut :** Analyse et recommandation, à valider
**Version :** 1.0
**Date :** 2026-10-28 (relevés de ce jour)
**Documents liés :** Flore Conversational Architecture v1, UX Interaction Design Specification v1, Jumeau Harness
Agentique v3, Écarts Intelligence v1, Plan de remédiation v1, Non-Functional Requirements (§5, §8)
**Tagline :** **DÉCOUVRIR · COMPRENDRE · DÉCIDER**

---

# 0. Objet et méthode

Ce document répond à deux questions :

1. Notre chat est-il au niveau des standards de l'industrie ?
2. A-t-on ce qu'il faut pour traiter un sujet complexe ?

Il s'appuie sur quatre études menées en parallèle le 2026-10-28 :
- l'inventaire du code de nos deux conversations (le panneau Flore et le fil d'un Travail) ;
- l'étude d'**OpenBot de CopilotKit**, dont le code a été cloné et lu ;
- le protocole **AG-UI** et les bibliothèques JavaScript de chat ;
- une grille des capacités attendues d'un chat d'entreprise (ChatGPT, Claude, Gemini, Microsoft 365 Copilot, Glean,
  Open WebUI, LibreChat).

Le volet cognitif (§6) compare à la manière dont Claude Code traite un sujet complexe. Une affirmation sur un produit
tiers non vérifiée dans une source est signalée « à confirmer » (voir §9).

---

# 1. Le verdict en une page

- **Sur la confiance, Méridian est en avance.** États de vérification, schémas prouvés flèche par flèche, relecture
  affichée, incertitude dite : presque aucun produit n'indique son incertitude, c'est un espace libre (étude
  « standards »). Il faut le garder.
- **Sur l'ergonomie de base, Méridian est en retard.** Sur les 10 capacités que tout produit sérieux possède (§4),
  nous en avons **2 complètes**. On ne peut pas arrêter une réponse. Le panneau perd tout au rechargement. Le même
  texte est mis en forme dans le Travail et brut dans le panneau. Et **plusieurs boutons font semblant**.
- **Sur le protocole, la voie est tracée.** AG-UI est devenu le contrat standard entre un agent et son interface. Un
  adaptateur pour Strands existe (`ag_ui_strands`). OpenBot montre en production le chemin avec CopilotKit.
- **Sur le sujet complexe, la réponse est « en partie ».** Le Travail porte déjà un état de tâche durable (plan,
  hypothèses, options, livrables), mais il manque ce qui permet de **tenir dans la durée** : reprendre la main en
  cours de route, travailler en arrière-plan, lancer des sous-tâches en parallèle, mettre une hypothèse à l'épreuve
  (§6).

---

# 2. Notre chat aujourd'hui (inventaire du code)

| Capacité | Panneau | Travail |
|---|---|---|
| Arrêter une réponse | ✗ (champ désactivé, pas d'`AbortController`) | ✗ |
| Régénérer | ✗ | **factice** : remet la question dans le champ |
| Éditer une question | ✗ | ✗ |
| Copier | ✗ | ✓ |
| Retour 👍/👎 | ✗ | **factice** : un message, aucun appel serveur |
| Reprise après coupure | ✗ | ✗ (le texte saisi est restauré) |
| Historique | ✗ (perdu au rechargement) | ✓ (persisté) |
| Recherche dans l'historique | ✗ | ✗ |
| Markdown | **texte brut** | partiel (titres, listes, gras) ; ni code coloré, ni liens, ni formules |
| Schémas | ✓ | ✓ |
| Pièces jointes, voix | ✗ | **factices** (« + » et micro sans action) |
| Mention, commandes | partiel (menu « Capacités », puces de contexte) | ✗ |
| Preuves | volet | volet |
| Étapes réelles | ✓ | ✓ |
| Approbation humaine | ✗ | ✓ (décisions attendues, précisions) |
| Interrompre, réorienter | ✗ | ✗ |
| Partage, export | partiel | partiel ; « Partager » **factice** |
| Accessibilité | faible (aucun `aria`) | partielle |

**Trois incohérences entre les deux conversations** :
1. Deux rendus du même texte : trois analyseurs Markdown différents en tout.
2. Deux façons de garder l'activité (`trace` et `_activite`).
3. Deux compositeurs : le menu de capacités n'existe que dans le panneau.

**Le défaut le plus grave** est celui que le plan de remédiation combat : **des boutons qui promettent une action
qu'ils ne font pas**. Il doit être corrigé avant toute nouvelle capacité.

---

# 3. OpenBot de CopilotKit : ce qu'il faut regarder

**Ce que c'est.** Un dépôt public, sous licence MIT ([github.com/CopilotKit/OpenBot](https://github.com/CopilotKit/OpenBot)),
en version 0.2.0 (« beta »), qui se présente comme « un modèle, pas un produit ». On le clone et on remplace l'exemple
`examples/fintech`.
- **Dépendance obligatoire** : *CopilotKit Intelligence*, un service sous licence (offre gratuite pour développeur,
  auto-hébergeable) qui garde les fils et la mémoire.
- **Correction d'une idée reçue** : l'index pgvector avec droits par document a été **retiré** (CHANGELOG). Il n'y a
  pas de RAG propre ; le bot Knowledge passe par les outils documentaires accordés.
- **Pile** : React 19.2, Vite 7, Tailwind 4, `@copilotkit/react-core` 1.83 (API v2 : `useAgent`, `useFrontendTool`,
  `useHumanInTheLoop`, `useRenderTool`), `@ag-ui/core` 1.0.2, `streamdown` pour le Markdown, serveur Hono avec
  `@copilotkit/runtime`.

**À reprendre (motifs vérifiés dans le code)** :

| Motif d'OpenBot | Pourquoi pour Méridian |
|---|---|
| **Un message envoyé pendant un tour est mis en file**, puis rejoué au tour suivant ; « Stop » sert à corriger la trajectoire (`composer/queue.ts`) | C'est l'interruption et la réorientation qui nous manquent |
| **Approbation en ligne**, sur la même boîte de réception que la page Approbations, **exécutée une seule fois côté serveur** (`approvals/inline-approval.tsx`) | Notre « décision attendue » existe, mais pas dans le panneau |
| **Réparation de l'historique** : appels d'outil restés sans réponse (`repair-history.ts`), reprise d'un fil (`handoff-resume.ts`), **explication d'un tour arrêté** (`stopped-turn.ts`) | Reprise après coupure, et honnêteté sur ce qui n'a pas abouti |
| **Lignes d'outil et onglet Activité en direct** (`tool-line.tsx`, `tool-activity.tsx`) | Va au-delà de nos libellés d'étape |
| **Interface générée par l'agent, gouvernée** : catalogue A2UI 1.0, galerie de composants approuvés | Le bon cadre pour nos schémas et nos futurs livrables visuels |
| **Fil de groupe avec `@Nom`** pour s'adresser à un agent | Mobiliser un jumeau nommément |
| **Passerelle unique de droits, fermée par défaut, avec une ligne d'audit avant chaque action** ; SSO OIDC et SAML | Notre verrou n° 2 (identité) |
| `role="log"` et `aria-live` sur la transcription | L'accessibilité minimale |

**À ne pas reprendre** :
- la dépendance à un service externe sous licence pour garder les fils ;
- l'absence de citations à l'écran (seul le prompt les demande) et d'évaluation.

Sur ces deux points, Méridian est déjà plus exigeant.

---

# 4. La grille des standards : les 10 capacités que tout produit sérieux possède

État de Méridian au 2026-10-28 :

| # | Capacité | Méridian |
|---|---|---|
| 1 | Réponse en flux, **arrêtable**, régénérable, copiable | partiel : flux oui ; arrêter non ; régénérer factice ; copier dans le Travail seulement |
| 2 | **Historique cherchable**, renommer, supprimer | Travail seulement, sans recherche |
| 3 | Markdown complet : tableaux, code coloré avec bouton copier, formules | partiel dans le Travail, absent dans le panneau |
| 4 | Pièces jointes, glisser-déposer, collage d'image | ✗ (boutons factices) |
| 5 | Citations cliquables vers la source | ✓ (volet de preuves) |
| 6 | Retour 👍/👎 | factice |
| 7 | Partage d'une conversation par lien | factice |
| 8 | Projets ou espaces avec instructions | ✓ en partie (Travaux, consignes d'équipe sans interface) |
| 9 | Mémoire et préférences pilotables | ✗ (rien côté utilisateur) |
| 10 | Étapes et outils visibles, approbation des actions sensibles | ✓ étapes ; approbation dans le Travail seulement |

**Ce qui distingue les meilleurs** : reprise après coupure (LibreChat), coût affiché (LibreChat, Glean), édition avec
rebranchement du fil (ChatGPT, Open WebUI, LibreChat), fil d'équipe (Open WebUI Channels). Et l'indication
d'incertitude : **personne**. C'est la place de Méridian.

---

# 5. Protocole et bibliothèques : la recommandation

**5.1 Adopter AG-UI comme contrat entre l'agent et l'interface.** Le protocole ([docs.ag-ui.com](https://docs.ag-ui.com/concepts/events))
permet ce que notre contrat maison (`etape`, `texte`, `relecture`, `final`, `erreur`) ne permet pas :
- **outils structurés** : début, arguments et résultat d'un appel, reliés par un identifiant ;
- **outils côté navigateur** ;
- **interruption avec reprise** : la base de l'approbation par un humain ;
- **état partagé incrémental** (JSON-Patch) ;
- **reprise par instantané des messages** ;
- **sous-agents et raisonnement visible**.

Mise en œuvre recommandée :
- **Garder `flux.en_flux` et lui faire émettre des événements AG-UI** (`ag_ui.core`, `EventEncoder`). Notre relecture,
  nos contrôles et le juge s'exécutent **après** l'agent, et l'adaptateur `ag_ui_strands` 1.0.2 ne les prévoit pas.
  L'adaptateur reste utile comme référence.
- **Correspondance** :
  - `etape` → `ToolCallStart` / `ToolCallResult`, plus `StepStarted` ;
  - `texte` → `TextMessageContent` ;
  - `relecture` → `Custom("relecture")` ;
  - `final` → `MessagesSnapshot`, plus un `StateSnapshot` qui porte `relecture_etat`, `origine` et `durees`.
- **Estimation** de l'étude : 1 à 2 jours. À confirmer : la prise en charge de `S3SessionManager` par l'adaptateur.

**5.2 Une seule conversation, construite sur une bibliothèque**, utilisée par le panneau et le Travail. Elle supprime
les trois incohérences du §2.

| | assistant-ui | CopilotKit |
|---|---|---|
| AG-UI | via `@assistant-ui/react-ag-ui` **0.1.1 (jeune)** | natif |
| Style | sans style imposé, primitives proches de Radix (notre pile) | composants prêts, personnalisables |
| Branches, édition, régénération | oui | à confirmer |
| Approbation (interruptions), état partagé | à confirmer | oui (`useHumanInTheLoop`, utilisé par OpenBot) |
| React 19 | oui | oui |
| Licence | MIT | MIT |

Vercel AI SDK est écarté : il n'a pas de transport AG-UI, et sa plage de versions React (`~19.0.1`) exclut la nôtre
(19.0.0).

**Recommandation : CopilotKit**, pour trois raisons :
- l'approbation et l'état partagé sont les capacités qui comptent pour Méridian, et il les fournit ;
- il est natif AG-UI, alors que l'adaptateur assistant-ui est en 0.1 ;
- OpenBot en montre l'usage réel.

Le style Méridian se garde en habillant ses composants dans les écrans existants (règle « suivre l'existant ») :
aucun nouvel écran. **Coût estimé par l'étude** : 3 à 5 jours pour réhabiller le fil.

---

# 6. A-t-on ce qu'il faut pour traiter un sujet complexe ?

**Comment Claude Code traite un sujet complexe** :
1. Il **découpe** et rend le plan visible (liste de tâches).
2. Il **explore avec ses outils** plutôt que de deviner.
3. Il **délègue** à des sous-agents au contexte isolé, en parallèle, et recueille leurs résultats.
4. Il **vérifie en exécutant** (tests, requêtes) et tient un avis pour une affirmation à vérifier.
5. Il **garde le fil sur la durée** : compaction, mémoire et sa raison, reprise.
6. Il **ne pose que les questions qui reviennent à l'utilisateur**.
7. Il **rend compte en « vérifié / non vérifié »**.
8. Il **accepte d'être interrompu et réorienté** en cours de route.
9. Il **fait le long travail en arrière-plan** et prévient à la fin.

| Pratique | Méridian | Ce qui manque |
|---|---|---|
| 1. Plan visible | ✓ Travail : `planifier`, `lever_etape` | Le plan n'est pas proposé avant de partir sur un grand sujet |
| 2. Explorer par les outils | ✓ outils de code, sources, `suivre_appels` | Sources réelles non branchées |
| 3. Déléguer en parallèle | partiel : mobilisation des jumeaux **l'un après l'autre** | Consultation parallèle ; experts (Vision §7) absents |
| 4. Vérifier en exécutant | ✓ recettes, juge cité, recoupement, garde-fous | Mettre une **hypothèse** à l'épreuve (moteur d'investigation) |
| 5. Tenir sur la durée | partiel : Travail persisté, compaction | Mémoire de l'utilisateur ; reprise d'un tour coupé |
| 6. Questions justes | ✓ `demander_precision` (Travail) | Absent du panneau |
| 7. Rendre compte honnêtement | ✓ états, « relu / non relu », origine | — |
| 8. Interruption, réorientation | ✗ | La file des messages d'OpenBot (§3) |
| 9. Arrière-plan et notification | partiel : le gardien veille | Une analyse lourde devenue tâche suivie (NFR §8 : accusé < 2 s, progression < 3 s) |

**Verdict.** Méridian traite bien une **question complexe sur une application** : comprendre une fonctionnalité,
l'illustrer, la vérifier. Il ne sait pas encore mener une **investigation complexe** sur plusieurs applications et
dans la durée, comme « que se passe-t-il si l'on retire TBT ? ». Pour cela, il faut les pratiques 3, 4, 8 et 9 :
- déléguer en parallèle ;
- mettre une hypothèse à l'épreuve ;
- pouvoir être réorienté ;
- travailler en arrière-plan.

Ce sont des capacités du **harness**, pas du modèle. On peut donc les construire.

---

# 7. Feuille de route

Chaque étape a un critère vérifiable.

**P0 — Honnêteté (1 jour).** Plus aucun bouton factice :
- 👍/👎 enregistrés côté serveur, ou retirés ;
- « Partager », « + », micro et « Régénérer » réalisés, ou retirés jusqu'à leur réalisation.

Critère : un test parcourt les actions de message, et chacune déclenche un appel réel.

**P1 — Les fondamentaux (1 à 2 semaines).**
- Une **seule conversation partagée** par le panneau et le Travail. Critère : un seul rendu.
- **Markdown complet** : code coloré avec copie, liens, tableaux, formules.
- **Arrêter** : `AbortController` côté client, annulation de la tâche côté serveur.
- **Régénérer** et **éditer une question**.
- **Historique du panneau persisté**, avec recherche.
- **Accessibilité** : `role="log"`, `aria-live`, libellés.

Critère : les capacités 1, 2, 3 et 6 du §4 sont complètes.

**P2 — Le protocole (1 semaine).**

> **Avancement (2026-10-28).** Fait : `en_flux` parle AG-UI (`ag-ui-protocol` 1.0.0, traduction unique dans
> `jumeau/protocole.py`, sortie identique à l'encodeur officiel) ; chaque outil réel est émis (début, arguments,
> issue, durée, extrait) et affiché ligne par ligne, détail au clic (maquette `p2-protocole-v1`, option A).
> **CopilotKit : proposé au retrait** (vérifié le 2026-10-28 : `@copilotkit/react-core` 1.83.0 publiée le jour même,
> 31 dépendances et `maplibre-gl` exigée, serveur Node/Express ; l'interopérabilité est portée par AG-UI, et
> l'adopter remplacerait les composants de P1). En attente de la décision de l'utilisateur.
> Fait ensuite : l'activité du tour est enregistrée avec la réponse ; un tour arrêté s'explique (outils faits, en
> cours, texte écrit, « non relu », « Reprendre la réponse ») ; **reprise après coupure** (`flux.Tour` : seul
> « Arrêter » arrête, `POST /api/tours/{id}/arreter` ; une coupure se renoue par `GET /api/tours/{id}/flux?depuis=n`) ;
> **approbation en ligne** des connaissances proposées pendant le tour (`POST /cases/{cid}/messages/{n}/approbation`,
> permission « Valider », une seule exécution sous verrou Postgres, décision inscrite dans le message ; panneau
> comme Travail). P2 est terminé côté fonctions ; l'écran reste à voir.
- `en_flux` parle AG-UI.
- La conversation passe sur CopilotKit, dans les écrans existants.
- **Outils structurés** à l'écran.
- **Approbation en ligne**, exécutée une fois côté serveur, dans le panneau comme dans le Travail.
- **Reprise après coupure** (instantané des messages) et **explication d'un tour arrêté**.

**P3 — Le sujet complexe (2 à 4 semaines).**
- **File des messages** pendant un tour (réorientation, à la manière d'OpenBot).
- **Analyse lourde devenue tâche suivie**, avec notification.
- **Consultation des jumeaux en parallèle.**
- **Investigation** : hypothèses mises à l'épreuve par les outils, puis options comparées avec leurs preuves.
- **Plan proposé avant un grand sujet.**

Critère : « que se passe-t-il si Conduit tombe ? » rend une note d'impact où chaque effet a sa preuve, avec accusé
en moins de 2 s.

**P4 — Le confort.** Pièces jointes (versées comme sources du Travail, pas comme vérité), voix, mention `@jumeau`,
commandes `/`, partage par lien avec les droits, coût et temps affichés.

> **Avancement (2026-10-29).** Fait : **pièces jointes du Travail**. Dépôt borné (PDF, Word, PowerPoint, Excel,
> OpenDocument, RTF, EPUB, CSV, texte, Markdown, JSON, HTML ; 10 Mo et 10 pièces par travail), conversion des
> formats bureautiques par **anydoc** (MIT, locale, détection par le contenu, sans OCR hébergé), extraction bornée
> (caractères, pages, durée, bombes zip), stockage GridFS partagé entre workers, téléchargement `attachment` +
> `nosniff`, retrait par l'auteur ou le responsable, cascade avec la conversation et la réinitialisation de la démo.
> Le texte est injecté dans le contexte de Flore comme **donnée non vérifiée** (nom, auteur, date ; « d'après la
> pièce jointe… »), jamais comme un Claim. Le Markdown est découpé en **sections** (titres, slides, préambule) :
> Flore reçoit un sommaire et les sections pertinentes pour la question, puis peut lire une section non fournie
> avec `lire_piece` (fenêtre `debut`), chercher avec `chercher_pieces` et lire un tableau avec `lire_table`
> (bornés au Travail, plafonnés). Les citations portent `pièce:<id>#<section>` et sont vérifiées contre le
> sommaire réel par le contradicteur, sans être confondues avec des preuves de code ; les citations invalides sont
> retirées après révision. Un harnais `evaluation_pieces` mesure recall@k et MRR. En mode proxy/OIDC, l'envoi au
> modèle externe est coupé par défaut (`PIECES_ENVOI_MODELE_EXTERNE`). Intégrité plateforme : mutations de
> conversation réservées aux contributeurs, PATCH de conversation refusé, fusion serveur réservée au responsable
> (pièces déplacées sous quota atomique), journal filtré et non forgeable, rate limiting (tours et pièces), purge des
> dérivés et des retours à la suppression, CORS sans credentials. Les pièces sont injectées comme données
> utilisateur, jamais dans le prompt système ; avec des pièces, Flore n'écrit dans le Travail que si l'utilisateur
> l'autorise explicitement pour le tour, et l'extraction tourne dans un processus séparé borné. Limites honnêtes :
> pas d'OCR (un scan reste sans texte),
> variantes macro (`.docm`, `.xlsm`, `.pptm`) et images refusées. **Coût et temps affichés** : fait (durées,
> premier mot, jetons, estimation tarifaire, relecture et sous-agents compris). **Mention `@jumeau`**, **commandes
> `/`** (consignes explicites, relues avant envoi) et **partage par lien** (lien du Travail, portée et périmètre
> appliqués à l'ouverture) : faits. Le volet **Sources & Jumeaux** reprend les jumeaux réellement consultés et
> leurs sources, et s'ouvre une fois quand une réponse en apporte. Le **Canvas des documents réels** ouvre les
> livrables du Travail (copie, téléchargement, plein écran) ; le document de démonstration reste un cas à part.
> Reste la voix, volontairement hors périmètre.

**Avant d'écrire le code de P1 et de P2**, la maquette passe par le compagnon visuel (règle du projet).

---

# 8. Ce qu'il faut garder, et qui distingue Méridian

- Les **états de vérification** affichés : vérifié, d'après, recoupé, en partie, incertain.
- La **relecture affichée honnêtement** : relu, non relu, corrigé.
- Les **schémas prouvés flèche par flèche**.
- L'**origine** d'une réponse : calculée ou récitée.
- **Ce que l'on ignore**, dit dans la réponse.

Les études n'ont trouvé ces garanties dans aucun des produits comparés.

---

# 9. Sources

- OpenBot : https://github.com/CopilotKit/OpenBot (README, CHANGELOG, `app/package.json`, `server/package.json`,
  composants cités ; commit 72a0b1f) ; https://copilotkit.ai/openbot
- AG-UI : https://docs.ag-ui.com/concepts/events ; https://docs.ag-ui.com/concepts/tools ;
  https://docs.ag-ui.com/integrations ; https://www.copilotkit.ai/blog/aws-strands-agents-now-compatible-with-ag-ui ;
  PyPI `ag_ui_strands` 1.0.2
- assistant-ui : https://www.assistant-ui.com/docs ; Vercel AI SDK : https://ai-sdk.dev/docs/ai-sdk-ui/chatbot
- Open WebUI : https://github.com/open-webui/open-webui ; LibreChat : https://github.com/danny-avila/LibreChat ,
  https://www.librechat.ai/docs/features/resumable_streams
- Glean : https://docs.glean.com/release-notes/releases/2026-07-15-july-release ;
  https://docs.glean.com/release-notes/releases/2025-12-03-december-release
- Microsoft 365 Copilot : https://support.microsoft.com/en-us/topic/schedule-your-most-used-copilot-prompts-29dfd5fb-211a-4515-88a6-730b8074e489
- Claude : https://support.claude.com/en/articles/14116274 ; ChatGPT (branches) :
  https://bgr.com/1959993/chatgpt-branch-conversations-new-feature-now-available/

**À confirmer.**
- **Produits grand public** : les cellules ChatGPT, Claude, Gemini et Copilot de l'étude « standards » qui ne sont
  pas citées ci-dessus viennent de la connaissance de l'agent ; leurs pages d'aide n'ont pas pu être lues.
- **Bibliothèques** : l'accessibilité réelle n'a été vérifiée pour aucune ; l'approbation dans assistant-ui n'est pas
  confirmée, ni les branches dans CopilotKit.
- **OpenBot** : son code n'a pas été exécuté.
