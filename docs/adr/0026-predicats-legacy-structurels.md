# ADR-0026 — Prédicats legacy structurels prouvables

**Date :** 2026-11-03
**Statut :** accepted
**Décideurs :** Architecture, Domaine, Ingestion legacy

## Contexte

Les packs legacy (JSP, JEE/JPA, COBOL/JCL, SQL) produisent des `Finding` localisés, mais tous
restaient `candidate`. Seules les routes Spring pouvaient devenir `claim`, car leurs prédicats
(`DEPEND_DE`, `EXPOSE`, `LIT_VARIABLE`, `EXECUTE_IMAGE`) figuraient déjà dans
`recettes.PREDICATS`, `connaissance.PROUVABLES` et la fonction SQL `predicat_prouvable`.

Or une ligne de code établit directement certains liens legacy : un `CALL`, un `COPY`, un
`EXEC PGM=`/`EXEC PROC=`/`PROGRAM-ID.`, un `DSN=`/`ASSIGN TO`, une clause `REFERENCES`. Ces
constats ont une preuve localisée sur la bonne ligne, un commit et une recette déterministe
possible. À l'inverse, `STOCKE_DANS`, `INJECTE`, `COMPOSANT_JEE`, `INTERFACE_UTILISATEUR` et
`TABLE` reposent sur une observation de parser ou un raisonnement inter-fichiers : leur preuve
actuelle n'est pas localisée sur la ligne qui établirait le lien.

## Décision

Ajouter **uniquement** cinq prédicats structurels, car une ligne de code les établit directement :

| Prédicat | Forme reconnue |
|----------|----------------|
| `APPELLE` | `CALL 'PROG'` ou `CALL "PROG"` |
| `COPIE` | `COPY COPYBOOK` |
| `EXECUTE` | `EXEC PGM=PROG`, `EXEC PROC=PROC` ou `PROGRAM-ID. PROG` |
| `LIT_DATASET` | `DSN=DATASET` ou `ASSIGN TO DATASET` |
| `REFERENCE` | `REFERENCES TABLE` |

Ils sont ajoutés à `recettes.PREDICATS` et `_RECETTES`, à `connaissance.PROUVABLES` et à la
fonction SQL `predicat_prouvable`, avec la même liste exacte des deux côtés.

Les recettes sont pures, insensibles à la casse, exigent des mots entiers et ignorent les lignes
de commentaire `*`, `//*`, `--` et `#`. L'objet est toujours échappé (`re.escape`), et un nom plus
long ou qualifié (`ACME.CLIENTS` vs `ACME.CLIENTS.X`) ne vaut pas pour l'objet cité.

Dans `legacy_packs` :

- un `Finding` dont le prédicat est dans `PREDICATS`, la preuve localisée et le commit présent
  passe `status="claim"` — pas seulement les routes Spring ;
- `claims_promouvables(findings, lire)` rejoue la recette sur les lignes `[start, end]` lues par
  `lire` ; si elle ne rend pas `verifie`, aucun Claim n'est produit ;
- aucun Claim n'est produit sans citation, hash, locator et commit ;
- les constats non couverts (`STOCKE_DANS`, `INJECTE`, `COMPOSANT_JEE`,
  `INTERFACE_UTILISATEUR`, `TABLE`) restent `candidate` et ne fabriquent jamais de Claim.

## Alternatives considérées

### Alternative 1 — Promouvoir tous les constats legacy sur la seule observation du parser

- **Avantages :** aucun nouveau motif à maintenir, couverture maximale.
- **Inconvénients :** le parser peut avoir observé le construct ailleurs que sur la ligne citée ;
  la preuve ne localise pas le lien.
- **Pourquoi non :** un Claim doit rester vérifiable sur ses lignes citées.

### Alternative 2 — Ne garder que les routes Spring

- **Avantages :** périmètre minimal, aucun risque nouveau.
- **Inconvénients :** des liens legacy directement lisibles restent éternellement candidats.
- **Pourquoi non :** `CALL 'PROG'` ou `DSN=DATASET` sont aussi prouvables qu'un `@GetMapping`.

### Alternative 3 — Faire juger les constats legacy par le modèle

- **Avantages :** couverture sémantique plus large.
- **Inconvénients :** non déterministe, non localisé, coût par constat.
- **Pourquoi non :** la règle de preuve du code doit rester une comparaison pure.

### Alternative 4 — Ajouter aussi `STOCKE_DANS`, `INJECTE`, `COMPOSANT_JEE`,
`INTERFACE_UTILISATEUR` et `TABLE`

- **Avantages :** plus de constats promus.
- **Inconvénients :** leur preuve actuelle n'est pas localisée sur la ligne qui établit le lien.
- **Pourquoi non :** ce serait confondre « le parser l'a vu » avec « la ligne citée le prouve ».

## Conséquences

### Positives

- Les liens legacy directement prouvables deviennent des Claims traçables (citation, hash,
  locator, commit).
- La promotion est déterministe et testable sans base ni modèle.
- Python et SQL exposent la même liste de prédicats prouvables.

### Négatives et limites

- Les recettes reconnaissent des formes lexicales : elles ne résolvent ni les macros, ni les
  continuations COBOL, ni les concaténations de littéraux, ni les alias de programme.
- Le nom doit être cité tel quel ; une résolution inter-fichiers (copybook vers fichier,
  programme vers source) reste hors recette.
- Les prédicats sémantiques et les liens legacy non localisés restent `candidate`.
- La fonction SQL doit être rechargée sur une base existante (`schema.sql`) pour que la maturité
  suive la même règle que le code Python.

### Risques

- Un faux positif reste possible si une variante de commentaire n'est pas couverte ; le jeu de
  tests de recettes doit être étendu à chaque nouvelle forme rencontrée.
- Sans `lire` ni citation déjà présente, aucun Claim n'est produit : c'est volontaire, mais cela
  rend l'indexation dépendante d'un lecteur de fichiers.

## Références

- `backend/meridian/domain/recettes.py`
- `backend/meridian/application/legacy_packs.py`
- `backend/meridian/adapters/outbound/postgres/connaissance.py`
- `backend/meridian/adapters/outbound/postgres/schema.sql`
- ADR-0010 (monolithe modulaire hexagonal), ADR-0021 (retrieval unifié et preuve documentaire)
