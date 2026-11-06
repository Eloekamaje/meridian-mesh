# ADR-0027 — Prédicats legacy composés : prouver le lien, pas l'observation

**Date :** 2026-11-03
**Statut :** accepted
**Décideurs :** Architecture, Domaine, Ingestion legacy

## Contexte

L'ADR-0026 a promu les liens legacy qu'une ligne établit directement (`APPELLE`, `COPIE`, `EXECUTE`,
`LIT_DATASET`, `REFERENCE`). Cinq constats restaient `candidate` : `TABLE`, `STOCKE_DANS`,
`COMPOSANT_JEE`, `INJECTE` et `INTERFACE_UTILISATEUR`. Le parser les observe souvent, mais
l'observation seule ne dit pas si la ligne citée établit le lien :

- une entité JPA peut mentionner une table sans que la ligne `@Entity` cite `@Table` ;
- un service peut être observé comme composant sans que la ligne citée porte `@Stateless` ;
- un champ peut être observé comme injecté sans que sa déclaration localisée porte le type et
  l'annotation d'injection ;
- un formulaire JSP peut être observé sans que la ligne citée porte l'action ou l'include.

Promouvoir sur la seule observation transformerait le parser en oracle : il aurait vu le lien
ailleurs, mais le Claim citerait une ligne qui ne le prouve pas.

## Décision

Un Claim n'est produit que si **la ligne citée établit elle-même le lien**. L'observation du parser
localise le constat ; elle ne le prouve pas à sa place. Les cinq prédicats composés sont ajoutés à
`recettes.PREDICATS`, `recettes._RECETTES`, `connaissance.PROUVABLES` et à la fonction SQL
`predicat_prouvable`, avec la même liste exacte des deux côtés.

| Prédicat | Objet | Preuve localisée |
|----------|-------|------------------|
| `TABLE` | Nom de table | `CREATE TABLE <objet>` ou `@Table(... <objet> ...)` |
| `STOCKE_DANS` | Nom de table | Observation `jpa_table`/`sql_table` correspondante : ligne `@Table` ou `CREATE TABLE` |
| `COMPOSANT_JEE` | Stéréotype/type (`Stateless`, `MessageDriven`, `session`, `message-driven`…) | Annotation `@Stateless` (ou équivalent) ou élément XML correspondant (`<session>`, `<message-driven>`…) |
| `INJECTE` | Type injecté | Champ Java localisé portant le type **et** `@EJB`/`@Autowired`/`@Inject`/`@PersistenceContext`/`@PersistenceUnit` ; ou `resource-ref` XML portant `<res-type>` |
| `INTERFACE_UTILISATEUR` | Action ou page JSP | `<form action=...>`, `jsp:include`/`s:include`, `jsp:forward`/`s:forward`, `c:import` ou directive `<%@ include file=... %>` localisé |

Règles de preuve :

- une table **inférée du nom de classe** reste `candidate` : aucune ligne ne déclare cette table ;
- une entité dont la ligne `@Entity` ne porte pas la table reste `candidate` même si un autre constat
  du même fichier la mentionne ; la preuve doit être l'observation de la ligne `@Table`/`CREATE TABLE` ;
- une injection sans champ localisé portant le type reste `candidate` ; un `resource-ref` sans
  `<res-type>` reste `candidate` ;
- un formulaire sans action ou un include sans cible localisée reste `candidate` ;
- un `STOCKE_DANS` de colonne (`TABLE.COLONNE`) reste `candidate` : sa ligne `@Column` ne prouve pas
  la table ;
- sur `CREATE TABLE`, un schéma qualifiant unique (`APP.CLIENTS`) peut précéder l'objet simple
  (`CLIENTS`) ; un suffixe supplémentaire (`CLIENTS.ARCHIVE`) ne vaut jamais pour l'objet cité.

Les recettes sont pures, insensibles à la casse, exigent des mots entiers et échappent l'objet
(`re.escape`). Les commentaires `//`, `/* … */`, `<!-- … -->`, `<%-- … --%>`, `--`, `#` et `*` en
début de ligne sont masqués. Les chaînes restent lisibles : c'est souvent entre guillemets que
figure la table, l'action ou le type cité.

Dans `legacy_packs` :

- `INTERFACE_UTILISATEUR` n'est promouvable que si l'observation localise le formulaire/include et
  que l'objet vient de l'attribut `action`/`page`/`file`/`url` ;
- `COMPOSANT_JEE` porte le stéréotype ou le type XML, jamais le nom de classe ;
- `STOCKE_DANS` utilise la preuve de la table (`jpa_table`, `sql_table` ou lien
  `sql_table_to_jpa_table`) et non la ligne de l'entité ;
- `INJECTE` utilise le champ Java localisé (type + annotation) ou le `resource-ref` XML ;
- `TABLE` utilise la ligne `CREATE TABLE` ou `@Table` ;
- quand la preuve manque, le constat est conservé avec `status="candidate"` et ne fabrique aucun
  Claim ; un constat éligible ne produit un Claim que si la recette rejoue le lien sur les lignes
  citées. Aucun Claim n'est produit sans citation, hash, locator et commit.

## Alternatives considérées

### Alternative 1 — Promouvoir sur la seule observation du parser

- **Avantages :** couverture maximale, aucun nouveau motif à maintenir.
- **Inconvénients :** la ligne citée peut ne pas porter le lien ; le parser devient l'oracle.
- **Pourquoi non :** un Claim doit rester vérifiable sur les lignes qu'il cite.

### Alternative 2 — Laisser les cinq constats éternellement `candidate`

- **Avantages :** aucun risque de faux positif.
- **Inconvénients :** des liens directement lisibles (`CREATE TABLE`, `@Stateless`,
  `<form action=...>`) restent écartés alors qu'une ligne les établit.
- **Pourquoi non :** la règle de preuve peut rester locale et déterministe sans élargir la
  confiance au parser.

### Alternative 3 — Faire juger ces constats par le modèle

- **Avantages :** couverture sémantique plus large.
- **Inconvénients :** non déterministe, non localisé, coût par constat.
- **Pourquoi non :** la promotion d'un lien structurel doit rester une comparaison pure.

### Alternative 4 — Résoudre les liens inter-fichiers dans la recette

- **Avantages :** noms qualifiés, schémas et alias mieux couverts.
- **Inconvénients :** une recette deviendrait un résolveur de projet ; la ligne citée ne suffirait
  plus.
- **Pourquoi non :** l'inter-fichiers déterministe reste le rôle des liens (`sql_table_to_jpa_table`)
  qui fournissent l'observation de preuve ; la recette vérifie ensuite cette ligne.

## Conséquences

### Positives

- Les cinq constats peuvent devenir des Claims traçables lorsque la ligne citée les établit.
- La distinction « le parser l'a observé » / « la ligne citée le prouve » est explicite dans le
  statut et dans la recette.
- Python et SQL exposent la même liste de prédicats prouvables.

### Négatives et limites

- Les recettes reconnaissent des formes lexicales : pas de résolution d'alias, de constantes
  d'annotation, de tables qualifiées par des identifiants entre guillemets multiples, ni de
  concaténations de littéraux.
- `STOCKE_DANS` ne prouve pas les colonnes ; `INJECTE` couvre les champs et `resource-ref`, pas les
  injections par constructeur ou setter.
- Une table inférée du nom de classe, une injection sans champ localisé et un formulaire sans cible
  restent `candidate`.
- La fonction SQL doit être rechargée sur une base existante (`schema.sql`) pour que la maturité
  suive la même règle que le code Python.

### Risques

- Un faux positif reste possible si une variante de commentaire ou de syntaxe n'est pas couverte ;
  le jeu de tests de recettes doit être étendu à chaque nouvelle forme rencontrée.
- Un lien inter-fichiers n'est promu que si le lien déterministe existe déjà ; sinon le constat
  reste `candidate`.

## Références

- `backend/meridian/domain/recettes.py`
- `backend/meridian/application/legacy_packs.py`
- `backend/meridian/adapters/outbound/postgres/connaissance.py`
- `backend/meridian/adapters/outbound/postgres/schema.sql`
- ADR-0026 (prédicats legacy structurels), ADR-0010 (monolithe modulaire hexagonal)
