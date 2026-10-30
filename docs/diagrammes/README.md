# Diagrammes Méridian

Trois références autonomes pour les schémas de Méridian Mesh, et le contrat de style que le rendu React `SchemaSvg` doit reprendre.

| Fichier | Type | Sujet |
|---|---|---|
| `architecture.html` | Architecture | Du Travail aux jumeaux, puis au socle de preuve |
| `sequence.html` | Sequence | Une question dans le Travail, du brouillon à la réponse citée |
| `dependency.html` | Dependency graph | Jumeaux, dépôts, registre, pièces et claims |

Les fichiers sont des SVG inline dans un HTML unique : aucun script, aucune image externe, aucune webfont, aucun appel réseau. Ils servent de référence éditoriale ; le rendu applicatif reste plus compact.

## Tokens

Le fond sombre est la seule variante de ces références.

| Rôle | Valeur | Usage |
|---|---|---|
| `paper` | `#071019` | Fond de page, masque des flèches et des étiquettes |
| `paper-2` | `#0C1724` | Fond des nœuds internes, conteneurs |
| `ink` | `#F2F6F8` | Texte principal, contour des nœuds internes |
| `muted` | `#7C93A8` | Texte secondaire, flèches par défaut, sous-labellisés |
| `soft` | `#94A3B8` | Étiquettes de zone, notes, texte tertiaire |
| `rule` | `rgba(255,255,255,0.08)` | Hairlines, séparateurs, bordures |
| `accent` | `#60A5FA` | Élément focal, 1–2 maximum par schéma |
| `accent-tint` | `rgba(96,165,250,0.12)` | Remplissage des nœuds focaux |
| `link` | `#93C5FD` | Appels HTTP/API, flèches externes |

### Couleurs sémantiques de preuve

Elles sont réservées aux flèches qui portent un état de preuve, aux pastilles d'état et à la légende. Elles ne remplacent jamais `paper`, `ink` ou les fonds de nœuds.

| État | Valeur | Sens |
|---|---|---|
| `code` | `#60A5FA` | Ligne lue dans le code, avec un locator |
| `valide` | `#4ADE80` | Connaissance validée par l'équipe |
| `verifie` | `#34D399` | Connaissance vérifiée |
| `recoupe` | `#22D3EE` | Connaissance recoupée par une autre source |
| `selon` | `#93C5FD` | Une seule source |
| `conteste` | `#F2B84B` | Sources en désaccord, trait pointillé |
| `inconnu` | `#7C93A8` | Pas encore vérifié, trait pointillé |

Ces valeurs sont celles de `backend/jumeau/schemas.py` et de `SchemaSvg`. Une flèche sans fondement n'est pas dessinée ; elle n'existe donc pas dans le rendu.

## Règles de composition

- **Pas d'ombre.** Aucun `box-shadow`, aucun `filter: drop-shadow`. La hiérarchie passe par le contour, le remplissage et l'espace.
- **Hairline.** Bordures à `0.8px` ou `1px` ; trait fort à `1.2px`. Les séparateurs sont des lignes, pas des cartes.
- **Grille 4px.** Origines, largeurs, hauteurs, écarts et padding sont divisibles par 4. Les tailles de texte suivent la rampe, pas la grille.
- **1–2 accents.** Un seul nœud focal par schéma en général, deux au maximum. Le reste est `ink`, `muted` ou `soft`. Les couleurs de preuve ne comptent pas comme accents décoratifs : elles ne servent que là où l'état est réel.
- **Densité 4/10.** Neuf nœuds maximum pour l'architecture et les dépendances ; cinq lignes de vie et douze messages maximum pour une séquence. Si ça déborde, on coupe ou on scinde.
- **Pas de webfont.** Piles locales uniquement : serif système pour le titre, sans système pour les noms, mono système pour les valeurs techniques, les étiquettes et les locators. Aucun `<link>` vers Google Fonts.
- **Connecteurs orthogonaux.** Angles arrondis à `r=8`, ports distincts sur une arête partagée, aucun passage derrière un nœud qui n'est pas l'extrémité, pas de diagonales.
- **Cycles maîtrisés.** Le calcul des rangs coupe les arêtes de retour d'un parcours DFS : un cycle ne doit pas écraser tout le schéma dans une colonne. L'arête de retour repart sous le schéma, dans un canal réservé, puis remonte dans le couloir de sa cible.
- **Étiquettes masquées.** Chaque étiquette de flèche a un rectangle opaque `paper` derrière elle, avec 6 à 10px entre le masque et le trait.
- **Légende en bas.** Bandeau horizontal après les nœuds, séparé par une hairline ; jamais flottante dans la zone du schéma.
- **Accessibilité.** `role="img"`, `<title>` en premier enfant du SVG, `<desc>` en une phrase, `aria-labelledby` vers des identifiants uniques. Le contenu doit rester compréhensible sans le visuel.

## Contrat du rendu React `SchemaSvg`

Le rendu applicatif est **déterministe**. L'agent ne produit jamais de HTML ou de SVG à l'exécution.

1. **Source de vérité : la structure vérifiée.** `Dessin.dessiner` (`backend/jumeau/schemas.py`) valide chaque flèche contre une ligne de code, un claim ou une relation, puis persiste :
   - `type` : `sequence`, `flux` ou `architecture` ;
   - `titre` ;
   - `boites` : `id`, `libelle` ;
   - `fleches` : `de`, `vers`, `libelle`, `etat` ;
   - `groupes` : `libelle`, `ids`.
   Le Mermaid vérifié reste un repli/export. `SchemaSvg` consomme la structure, pas le bloc Mermaid ni un texte libre du modèle.
2. **Aucune injection.** `SchemaSvg` rend des éléments React à partir des données. Pas de `dangerouslySetInnerHTML`, pas de balise HTML interprétée, pas de script. Les libellés sont des données échappées par React. Un type inconnu, un état inconnu ou une arête dont une extrémité manque est ignoré ; un état inconnu devient `inconnu` (gris pointillé).
3. **Même système visuel.** Le composant applique `paper`, `ink`, `muted`, `rule`, `accent` et les couleurs d'état ci-dessus. Il garde les rayons 6, les traits 1px, la grille 4px, les connecteurs orthogonaux et les étiquettes masquées. Le rendu applicatif peut être plus compact que ces références (nœuds de 40px au lieu de 72px), mais pas changer les règles.
4. **Même contrat d'accessibilité.** `role="img"`, `<title>` en premier, `<desc>` utile, identifiants uniques générés par `useId` et reliés par `aria-labelledby`. Le titre décrit le sujet, pas la géométrie.
5. **Même discipline de preuve.** Une flèche n'est rendue que si le backend lui a donné un état. `code` est plein bleu, `verifie`/`valide` vert, `recoupe` cyan, `selon` bleu clair, `conteste` orange pointillé, `inconnu` gris pointillé. Aucune couleur de preuve sur les fonds, les titres ou les zones.
6. **Tests.** Un schéma fixe doit produire un SVG stable (snapshot), sans référence distante ni script ; les états doivent rester ceux du backend ; les libellés longs doivent être tronqués ou repliés sans chevaucher les nœuds.

`dependency.html` est une référence éditoriale du graphe de dépendances ; le contrat `SchemaSvg` couvre aujourd'hui `architecture`, `flux` et `sequence`. Si un type `dependency` est ajouté, il reprend le rangement par profondeur, les badges de fan-in et le back-edge accentué, sans changer les tokens.

## Choix de fidélité

- **Architecture** : 9 nœuds. `Pièces jointes` porte le sous-libellé `GridFS · pieces_fichiers` (le stockage est dans le même nœud) ; `Socle de preuve` regroupe `Code · Claims · Preuves` et affiche les trois états réels (`CODE`, `VÉRIFIÉ`, `CONTESTÉ`). `Réponse citée` est le nœud `CANVAS` dans la zone `TRAVAIL`.
- **Séquence** : 5 lignes de vie (maximum de la skill). `Relecture` est le juge d'appui, sans outils ; la réponse finale est l'étiquette `RÉPONSE CITÉE`, et le Canvas est signalé en note, pas comme une sixième ligne de vie.
- **Dépendances** : 8 nœuds, 11 arêtes, badge de fan-in sur chaque nœud. `Dépôts Git` concentre 3 dépendances entrantes. Le seul cycle est réel : le jumeau `Méridian` indexe le code qui contient `Flore`, d'où le retour `Méridian → Flore` en accent pointillé.

## Validation

Depuis la racine du projet :

```bash
python3 .opencode/skills/diagram-design/scripts/self_check.py --offline docs/diagrammes/architecture.html
python3 .opencode/skills/diagram-design/scripts/self_check.py --offline docs/diagrammes/sequence.html
python3 .opencode/skills/diagram-design/scripts/self_check.py --offline docs/diagrammes/dependency.html
python3 .opencode/skills/diagram-design/scripts/verify-geometry.py docs/diagrammes/architecture.html docs/diagrammes/sequence.html docs/diagrammes/dependency.html
python3 .opencode/skills/diagram-design/scripts/lint-render.py docs/diagrammes/architecture.html docs/diagrammes/sequence.html docs/diagrammes/dependency.html
```

Résultats du 29 octobre 2026 :

| Contrôle | Résultat |
|---|---|
| `self_check.py --offline` | 3/3 fichiers `OK` |
| `verify-geometry.py` | 3 fichiers, 0 anomalie |
| `lint-render.py` (Chromium 145, réseau bloqué) | 3 fichiers rendus, 0 anomalie, 0 note |

`lint-render.py` exige Playwright et Chromium. S'ils sont absents, la validation s'arrête au contrôle statique et à la géométrie ; le README le signale plutôt que de le passer sous silence.
