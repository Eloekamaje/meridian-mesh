# Parseur PL/I ANTLR

Le sidecar `PliSemanticSidecar` remplace l'analyse structurelle par un vrai
parseur ANTLR pour le langage PL/I.

## Source et licence

- `pl1.g4` est une copie de
  `https://raw.githubusercontent.com/antlr/grammars-v4/master/pl1/pl1.g4`.
- La grammaire est distribuée sous licence BSD 3-Clause (Copyright (c) 2026,
  Tom Everett). Son en-tête de licence est conservé dans le fichier.
- Runtime Python : `antlr4-python3-runtime==4.13.2` (voir
  `backend/requirements.txt`).
- Outil de génération : `antlr-4.13.2-complete.jar` (Java 11+).

## Génération du parseur

Les fichiers générés et le jar ne sont pas versionnés : ils sont produits
localement dans `tools/pli/generated` et `tools/pli/lib`.

```bash
cd tools/pli
./generate.sh
```

Le script télécharge le jar s'il est absent puis exécute :

```bash
java -jar lib/antlr-4.13.2-complete.jar \
  -Dlanguage=Python3 -o generated -visitor -no-listener pl1.g4
```

Pour utiliser un autre emplacement, définir `MERIDIAN_PLI_ANTLR_DIR` vers le
dossier contenant `pl1Lexer.py`, `pl1Parser.py` et `pl1Visitor.py`.

Sans parseur généré, `PliSemanticSidecar` reste importable :
`parser_disponible()` renvoie `False`, `index()` ne rend aucune observation et
la couverture est `non_supporte`. Les tests `test_pli_semantic.py` sont alors
ignorés proprement.

## Fonctionnement

Le sidecar :

1. neutralise les commentaires PL/I (`/* ... */`, `*` en début de ligne,
   `//`) en conservant les numéros de ligne ;
2. tokenise avec le lexer ANTLR ;
3. prépare une variante grammaticale des constructions non couvertes par la
   grammaire amont (`PROC`/`DCL`, `OPTIONS(...)` des procédures, virgule
   finale de `%INCLUDE`, cibles ou étiquettes homonymes de mots-clés) ;
4. parse l'arbre avec `pl1Parser` et visite les règles procédure, entry,
   declare, call, include et labels ;
5. complète par les tokens du statement pour les constructions absentes de la
   grammaire amont, notamment les blocs `EXEC SQL` et les alias `CHAR`, `BIN`
   ou `INIT`.

La grammaire `grammars-v4/pl1` est incomplète (elle ne couvre ni `PROC`/`DCL`,
ni SQL, ni certaines options). Ces écarts sont donc traités par normalisation
et par lecture du flux de tokens ; une erreur de syntaxe ne lève jamais
d'exception et marque seulement le fichier comme `partiel` en couverture.

## Tests

```bash
cd backend
.venv/bin/python -m pytest meridian/tests/test_pli_semantic.py meridian/tests/test_pli_sidecar.py -q
```
