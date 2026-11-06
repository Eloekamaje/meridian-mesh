# Parseur RPGLE ANTLR (Analyze.java)

`Analyze.java` analyse un source ILE RPG / RPGLE (fixed et free) avec la
grammaire ANTLR [`rpgleparser`](https://github.com/rpgleparser/rpgleparser)
et écrit un JSON UTF-8 sur `stdout`. Il sert de moteur au sidecar Python
`meridian.adapters.outbound.connectors.rpg_semantic.RpgSemanticSidecar`.

Le parseur produit un **vrai parse tree** (règles, texte, lignes) et des
symboles extraits : `DCL-F`, `DCL-PROC`, `DCL-S`, `DCL-DS`, `CALLP`, `EXSR`,
`CALL`, `CHAIN`, `READ*`, `WRITE`, `UPDATE`, `DELETE`, `SELECT`, `EXEC SQL`.

## Prérequis

- Java 17 (`java`, `javac`)
- Les jars Maven Central :
  - `com.github.rpgleparser:rpgleparser:1.0.0` — LGPL 2.1
  - `org.antlr:antlr4:4.5.3` — BSD 3-clause
  - `org.antlr:antlr4-runtime:4.5.3` — BSD 3-clause (runtime ANTLR)

Les jars ne sont pas versionnés (`tools/rpgle/lib/*.jar` est ignoré par Git).

## Téléchargement des jars

```bash
cd tools/rpgle
mkdir -p lib classes
curl -sSfL -o lib/rpgleparser-1.0.0.jar \
  https://repo1.maven.org/maven2/com/github/rpgleparser/rpgleparser/1.0.0/rpgleparser-1.0.0.jar
curl -sSfL -o lib/antlr4-4.5.3.jar \
  https://repo1.maven.org/maven2/org/antlr/antlr4/4.5.3/antlr4-4.5.3.jar
curl -sSfL -o lib/antlr4-runtime-4.5.3.jar \
  https://repo1.maven.org/maven2/org/antlr/antlr4-runtime/4.5.3/antlr4-runtime-4.5.3.jar
```

## Compilation

```bash
cd tools/rpgle
javac -encoding UTF-8 \
  -cp "lib/rpgleparser-1.0.0.jar:lib/antlr4-runtime-4.5.3.jar:lib/antlr4-4.5.3.jar" \
  -d classes Analyze.java
```

Sous Windows, remplacer `:` par `;` dans le classpath.

## Exécution

```bash
java -Xss8m -cp "classes:lib/*" Analyze chemin/vers/programme.rpgle
```

Le code de sortie est `0` même quand le parse est partiel : le statut est dans
le JSON. Le sidecar Python lance cette commande avec un timeout et un classpath
calculé automatiquement. On peut forcer la JVM avec `JAVA=/chemin/java`.

## Format JSON

```json
{
  "fichier": "...",
  "statut": "ok | partiel | erreur",
  "free": true,
  "tokens": [
    {"type": "FS_FreeFile", "texte": "DCL-F", "ligne": 2, "colonne": 6, "canal": 0}
  ],
  "noeuds": [
    {"regle": "fspec", "debut": 2, "fin": 2, "texte": "DCL-F CUSTMAST ..."}
  ],
  "symboles": [
    {
      "regle": "fspec",
      "cible": "CUSTMAST",
      "debut": 2,
      "fin": 2,
      "texte": "DCL-F CUSTMAST DISK ...",
      "tokens": ["DCL-F", "CUSTMAST", "DISK"],
      "proc": ""
    }
  ],
  "erreurs": [
    {"ligne": 5, "colonne": 28, "message": "...", "source": "parser"}
  ],
  "tronque": false
}
```

- `statut` vaut `ok` sans erreur de lexer/parser, `partiel` si l'AST a pu être
  construit malgré des erreurs, `erreur` si le fichier n'a pas pu être analysé.
- `noeuds` est un parse tree simplifié : une entrée par règle ANTLR, avec le
  texte source (tronqué à 300 caractères) et les lignes de début/fin.
- `symboles` contient uniquement les règles utiles au mapping CodeIndex.
  `proc` porte la procédure englobante ; `operation` et `table` sont ajoutés
  pour les opérations et le SQL.
- Les listes sont plafonnées (`tokens`/`noeuds` à 20 000, `symboles` à 5 000)
  et `tronque` signale le dépassement.

## Sources `**FREE`

`rpgleparser` 1.0.0 attend la directive `/FREE` et des lignes de largeur fixe.
`Analyze.java` normalise donc les sources dont le marqueur est `**FREE` ou
`/FREE` : le marqueur devient `      /FREE`, les lignes free sont indentées à
au moins 6 colonnes, et les lignes fixes précédant le marqueur sont conservées.
Les fichiers fixes sont passés tels quels à `FixedWidthBufferedReader`.

## Robustesse

- Encodage : UTF-8, puis windows-1252, puis ISO-8859-1.
- Toute erreur de lecture ou de parse produit un JSON `statut=erreur` ou
  `partiel` avec la liste `erreurs` ; le programme ne lève pas d'exception
  non gérée.
- Limite de pile augmentée (`-Xss8m`) pour les gros programmes.

## Tests Python

```bash
cd backend
.venv/bin/python -m pytest meridian/tests/test_rpg_semantic.py \
  meridian/tests/test_rpg_sidecar.py -q
```

Le test réel est ignoré automatiquement si `tools/rpgle/classes/Analyze.class`
ou les jars sont absents. Le test à runner factice ne dépend pas de Java.
