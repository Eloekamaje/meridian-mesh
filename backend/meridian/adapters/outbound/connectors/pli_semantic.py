"""Sidecar PL/I sémantique fondé sur la grammaire ANTLR grammars-v4/pl1.

Le parseur généré n'est pas versionné : il est produit dans
``tools/pli/generated`` par la commande documentée dans ``tools/pli/README.md``.
En son absence, le sidecar reste importable et ne produit aucune observation.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    from antlr4 import CommonTokenStream, InputStream
    from antlr4.error.ErrorListener import ErrorListener
except Exception:  # runtime absent : le sidecar reste importable, les tests se sautent
    CommonTokenStream = InputStream = None
    ErrorListener = object

from meridian.adapters.outbound.connectors.pli import SUFFIXES, _cle_fichier, _lire
from meridian.domain.code_index import CouvertureFichier, Observation

__all__ = [
    "PliSemanticSidecar", "parser_disponible", "PROVIDER", "PARSER",
    "VERSION", "PARSER_VERSION", "LANGAGE", "SUFFIXES", "EXTENSIONS",
]

PROVIDER = "pli-semantic"
PARSER = "pl1-antlr"
VERSION = "4.13.2"
PARSER_VERSION = VERSION
LANGAGE = "pli"
EXTENSIONS = tuple(sorted(SUFFIXES))

_PARSER = None
_CHARGE = False

_OPTIONS_FIN = frozenset({
    "INITIAL", "INIT", "VALUE", "STATIC", "EXTERNAL", "BASED", "CONTROLLED",
    "AUTOMATIC", "PARAMETER", "DEFINED", "GENERIC", "RETURNS", "OPTIONS",
    "DIMENSION", "LIKE",
})
_SQL_STOPS = frozenset({
    "WHERE", "GROUP", "ORDER", "HAVING", "SET", "VALUES", "SELECT", "INTO",
    "FROM", "ON", "USING", "UNION", "FOR", "WITH", "AS", "FETCH", "RETURNING",
    "WHEN", "END",
})
_DEFINITIONS = frozenset({
    "Procedure2_statementContext", "Procedure_statementContext",
    "Entry_statementContext",
})


def _dossiers_generes():
    vus = set()
    variable = os.environ.get("MERIDIAN_PLI_ANTLR_DIR")
    candidats = []
    if variable:
        candidats.append(Path(variable))
    candidats.append(Path(__file__).resolve().parents[5] / "tools" / "pli" / "generated")
    candidats.append(Path.cwd() / "tools" / "pli" / "generated")
    for dossier in candidats:
        cle = str(dossier)
        if cle in vus:
            continue
        vus.add(cle)
        yield dossier


def _charger_parser():
    """Charge les modules générés, ou rend ``None`` sans jamais lever."""
    global _PARSER, _CHARGE
    if _CHARGE:
        return _PARSER
    _CHARGE = True
    for dossier in _dossiers_generes():
        if not (dossier / "pl1Lexer.py").is_file():
            continue
        if not (dossier / "pl1Parser.py").is_file():
            continue
        if str(dossier) not in sys.path:
            sys.path.insert(0, str(dossier))
        try:
            from pl1Lexer import pl1Lexer
            from pl1Parser import pl1Parser
            from pl1Visitor import pl1Visitor
        except Exception:
            continue
        _PARSER = (pl1Lexer, pl1Parser, pl1Visitor)
        return _PARSER
    _PARSER = None
    return None


def parser_disponible() -> bool:
    """Vrai quand le parseur généré et le runtime ANTLR sont utilisables."""
    return _charger_parser() is not None


def _nom_valide(texte: str) -> bool:
    if not texte:
        return False
    if texte.isdigit():
        return True
    if not (texte[0].isalpha() or texte[0] in "_$"):
        return False
    return all(caractere.isalnum() or caractere in "_$#@" for caractere in texte[1:])


def _neutraliser_commentaires(texte: str) -> str:
    """Blanchit les commentaires ``*`` et ``//`` en conservant les lignes."""
    sortie = list(texte)
    i = 0
    guillemet = None
    dans_bloc = False
    debut_ligne = True
    while i < len(texte):
        caractere = texte[i]
        if dans_bloc:
            if texte.startswith("*/", i):
                dans_bloc = False
                i += 2
                continue
            if caractere not in "\r\n":
                sortie[i] = " "
            i += 1
            continue
        if guillemet:
            if caractere == guillemet:
                if i + 1 < len(texte) and texte[i + 1] == guillemet:
                    i += 2
                    continue
                guillemet = None
            i += 1
            continue
        if caractere in "'\"":
            guillemet = caractere
            i += 1
            continue
        if texte.startswith("/*", i):
            dans_bloc = True
            i += 2
            continue
        if texte.startswith("//", i):
            while i < len(texte) and texte[i] not in "\r\n":
                sortie[i] = " "
                i += 1
            continue
        if caractere in "\r\n":
            debut_ligne = True
            i += 1
            continue
        if debut_ligne:
            if caractere in " \t":
                i += 1
                continue
            if caractere == "*":
                while i < len(texte) and texte[i] not in "\r\n":
                    sortie[i] = " "
                    i += 1
                continue
            debut_ligne = False
        i += 1
    return "".join(sortie)


def _groupes(tokens):
    groupe = []
    for token in tokens:
        groupe.append(token)
        if token.text == ";":
            yield groupe
            groupe = []
    if groupe:
        yield groupe


def _etiquettes(groupe):
    etiquettes = []
    i = 0
    while i + 1 < len(groupe) and groupe[i + 1].text == ":":
        if not (_nom_valide(groupe[i].text) or groupe[i].text.isdigit()):
            break
        etiquettes.append(groupe[i])
        i += 2
    return etiquettes, i


def _couper_tokens(tokens):
    morceaux = []
    tampon = []
    profondeur = 0
    for token in tokens:
        if token.text == "(":
            profondeur += 1
        elif token.text == ")":
            profondeur = max(0, profondeur - 1)
        if token.text == "," and profondeur == 0:
            morceaux.append(tampon)
            tampon = []
        else:
            tampon.append(token)
    if tampon:
        morceaux.append(tampon)
    return morceaux


def _fermeture(tokens, ouverture):
    profondeur = 0
    for i in range(ouverture, len(tokens)):
        if tokens[i].text == "(":
            profondeur += 1
        elif tokens[i].text == ")":
            profondeur -= 1
            if profondeur == 0:
                return i
    return None


def _valeur_noeud(noeud) -> str:
    valeur = getattr(noeud, "text", None)
    if valeur is None and hasattr(noeud, "getText"):
        valeur = noeud.getText()
    return valeur or ""


def _texte_tokens(tokens) -> str:
    texte = ""
    for token in tokens:
        valeur = _valeur_noeud(token)
        if not texte:
            texte = valeur
        elif valeur in {")", "]", ",", ".", ":", ";"}:
            texte += valeur
        elif texte.endswith(("(", "[")):
            texte += valeur
        elif valeur == "(":
            texte += valeur
        else:
            texte += " " + valeur
    return texte


def _compact(tokens) -> str:
    return "".join(_valeur_noeud(token) for token in tokens)


def _declarations_tokens(tokens):
    """Rend ``(token_nom, tokens_type)`` pour chaque nom déclaré."""
    declarations = []
    for morceau in _couper_tokens(tokens):
        if not morceau:
            continue
        if morceau[0].text.isdigit() and len(morceau) > 1:
            morceau = morceau[1:]
        if not morceau:
            continue
        if morceau[0].text == "(":
            fermeture = _fermeture(morceau, 0)
            if fermeture is None:
                continue
            for nom in _couper_tokens(morceau[1:fermeture]):
                if nom and _nom_valide(nom[0].text):
                    declarations.append((nom[0], morceau[fermeture + 1:]))
            continue
        if not _nom_valide(morceau[0].text):
            continue
        reste = morceau[1:]
        if reste and reste[0].text == "(":
            fermeture = _fermeture(reste, 0)
            if fermeture is not None:
                reste = reste[fermeture + 1:]
        declarations.append((morceau[0], reste))
    return declarations


def _type_tokens(tokens) -> str:
    gardes = []
    for token in tokens:
        if token.text == ";" or token.text.upper() in _OPTIONS_FIN:
            break
        gardes.append(token)
    return _texte_tokens(gardes)


def _cible_include(tokens):
    tokens = [token for token in tokens if token.text != ";"]
    if not tokens:
        return None
    if tokens[0].text.upper() == "FILE" and len(tokens) > 2 and tokens[1].text == "(":
        fermeture = _fermeture(tokens, 1)
        if fermeture is not None:
            return _compact(tokens[2:fermeture]).strip("'\"")
    if len(tokens) > 2 and tokens[1].text == "(":
        fermeture = _fermeture(tokens, 1)
        if fermeture is not None:
            return _compact(tokens[2:fermeture]).strip("'\"")
    for i, token in enumerate(tokens):
        if token.text in {",", ")"}:
            return _compact(tokens[:i]).strip("'\"") or None
    return _compact(tokens).strip("'\"") or None


def _table_sql(commande, tokens) -> str:
    mots = [token.text.upper() for token in tokens]
    if commande == "SELECT":
        indice = next((i for i, mot in enumerate(mots) if mot == "FROM"), None)
    elif commande in {"INSERT", "MERGE"}:
        indice = next((i for i, mot in enumerate(mots) if mot == "INTO"), None)
    elif commande == "UPDATE":
        indice = next((i for i, mot in enumerate(mots) if mot == "UPDATE"), None)
    elif commande == "DELETE":
        indice = next((i for i, mot in enumerate(mots) if mot == "FROM"), None)
    else:
        indice = next((i for i, mot in enumerate(mots)
                       if mot in {"FROM", "INTO", "UPDATE"}), None)
    if indice is None:
        return ""
    i = indice + 1
    if i >= len(tokens) or tokens[i].text == "(":
        return ""
    morceaux = []
    precedent = None
    while i < len(tokens):
        token = tokens[i]
        if precedent is not None and token.start != precedent.stop + 1:
            break
        texte = token.text
        if texte in {",", ";", "(", ")"} or texte.upper() in _SQL_STOPS:
            break
        if _nom_valide(texte) or texte in {".", "/", "-", "$", "#", "@"}:
            morceaux.append(texte)
            precedent = token
            i += 1
            continue
        break
    return "".join(morceaux)


def _est_sql(groupe, i) -> bool:
    if i >= len(groupe):
        return False
    mot = groupe[i].text.upper()
    if mot == "EXEC" and i + 1 < len(groupe) and groupe[i + 1].text.upper() == "SQL":
        return True
    if mot == "SELECT":
        mots = {token.text.upper() for token in groupe[i:]}
        return "INTO" in mots and "FROM" in mots
    return False


def _blanc(texte: str) -> str:
    return "".join("\n" if c == "\n" else "\r" if c == "\r" else " "
                   for c in texte)


def _renommer(texte: str, renames: dict) -> str:
    nouveau = "$" + texte[1:] if len(texte) > 1 else "$"
    renames.setdefault(nouveau, texte)
    return nouveau


def _normaliser(texte: str, groupes, pl1Parser):
    """Prépare une variante grammaticale sans déplacer les numéros de ligne."""
    edits = []
    renames = {}

    def remplacer(token, valeur):
        edits.append((token.start, token.stop + 1, valeur))

    def blanchir(debut, fin):
        if fin > debut:
            edits.append((debut, fin, _blanc(texte[debut:fin])))

    def options(groupe, i):
        while i < len(groupe):
            if groupe[i].text.upper() == "OPTIONS" and i + 1 < len(groupe) \
                    and groupe[i + 1].text == "(":
                fermeture = _fermeture(groupe, i + 1)
                if fermeture is not None:
                    blanchir(groupe[i].start, groupe[fermeture].stop + 1)
                    i = fermeture + 1
                    continue
            i += 1

    for groupe in groupes:
        etiquettes, i = _etiquettes(groupe)
        if i >= len(groupe):
            continue
        mot = groupe[i].text.upper()
        for etiquette in etiquettes:
            if etiquette.type != pl1Parser.IDENTIFIER:
                nouveau = _renommer(etiquette.text, renames)
                if nouveau != etiquette.text:
                    remplacer(etiquette, nouveau)
        if mot in {"PROC", "PROCEDURE"}:
            if mot == "PROC":
                remplacer(groupe[i], "PROCEDURE")
            options(groupe, i + 1)
        elif mot == "ENTRY":
            options(groupe, i + 1)
        elif mot in {"DCL", "DECLARE"}:
            if mot == "DCL":
                remplacer(groupe[i], "DECLARE")
            for token, _ in _declarations_tokens(groupe[i + 1:]):
                if token.type != pl1Parser.IDENTIFIER:
                    nouveau = _renommer(token.text, renames)
                    if nouveau != token.text:
                        remplacer(token, nouveau)
        elif mot == "CALL":
            j = i + 1
            if j < len(groupe) and groupe[j].text == "(":
                j += 1
            if j < len(groupe) and _nom_valide(groupe[j].text) \
                    and groupe[j].type != pl1Parser.IDENTIFIER:
                nouveau = _renommer(groupe[j].text, renames)
                if nouveau != groupe[j].text:
                    remplacer(groupe[j], nouveau)
        elif mot == "END":
            if i + 1 < len(groupe) and _nom_valide(groupe[i + 1].text) \
                    and groupe[i + 1].type != pl1Parser.IDENTIFIER:
                nouveau = _renommer(groupe[i + 1].text, renames)
                if nouveau != groupe[i + 1].text:
                    remplacer(groupe[i + 1], nouveau)
        elif mot == "%" and i + 1 < len(groupe) \
                and groupe[i + 1].text.upper() == "INCLUDE":
            j = i + 2
            if j < len(groupe) and groupe[j].type != pl1Parser.IDENTIFIER \
                    and j + 1 < len(groupe) and groupe[j + 1].text == "(" \
                    and _nom_valide(groupe[j].text):
                nouveau = _renommer(groupe[j].text, renames)
                if nouveau != groupe[j].text:
                    remplacer(groupe[j], nouveau)
            if groupe and groupe[-1].text == ";" \
                    and not any(token.text == "," for token in groupe[i:]):
                edits.append((groupe[-1].start, groupe[-1].start, ","))
        if _est_sql(groupe, i):
            fin = groupe[-1].start if groupe[-1].text == ";" else groupe[-1].stop + 1
            blanchir(groupe[i].start, fin)

    edits.sort(key=lambda edit: (edit[0], edit[1], 0 if edit[1] == edit[0] else 1))
    sortie = []
    curseur = 0
    for debut, fin, valeur in edits:
        if debut < curseur:
            continue
        sortie.append(texte[curseur:debut])
        sortie.append(valeur)
        curseur = fin
    sortie.append(texte[curseur:])
    return "".join(sortie), renames


class _Erreurs(ErrorListener):
    def __init__(self):
        super().__init__()
        self.lignes = []

    def syntaxError(self, recognizer, offending_symbol, line, column, message, error):
        self.lignes.append((line, column, message))

    def __len__(self):
        return len(self.lignes)


def _tokens_arbre(ctx):
    valeurs = []
    pile = [ctx]
    while pile:
        noeud = pile.pop()
        if type(noeud).__name__ == "TerminalNodeImpl":
            valeurs.append(noeud.getText())
            continue
        enfants = list(noeud.getChildren() or [])
        if enfants:
            pile.extend(reversed(enfants))
    return valeurs


def _creer_visiteur(pl1Visitor, sidecar, renames):
    class _Visiteur(pl1Visitor):
        def __init__(self):
            super().__init__()
            self.observations = []

        def _symbole(self, texte):
            return renames.get(texte, texte)

        def _observer(self, kind, symbole, ctx, regle, attributs=None):
            attributs = dict(attributs or {})
            attributs.setdefault("rule", regle)
            attributs.setdefault("tokens", _tokens_arbre(ctx)[:80])
            debut = ctx.start.line if ctx.start else 0
            fin = ctx.stop.line if ctx.stop else debut
            self.observations.append(sidecar._obs(
                self._fichier, kind, symbole, debut, fin, attributs))

        def _consomme_etiquettes(self, ctx):
            body = ctx.statement_body() if hasattr(ctx, "statement_body") else None
            if body is None:
                return False
            statement = body.statement()
            if statement is None or not statement.getChildCount():
                return False
            return type(statement.getChild(0)).__name__ in _DEFINITIONS

        def visitProcedure2_statement(self, ctx):
            for nom in ctx.entry_constant() or []:
                symbole = self._symbole(nom.getText())
                self._observer("pli_proc", symbole, ctx, "procedure2_statement",
                               {"proc": symbole})
            return self.visitChildren(ctx)

        def visitProcedure_statement(self, ctx):
            for nom in ctx.entry_name() or []:
                symbole = self._symbole(nom.getText())
                self._observer("pli_proc", symbole, ctx, "procedure_statement",
                               {"proc": symbole})
            return self.visitChildren(ctx)

        def visitEntry_statement(self, ctx):
            for nom in ctx.entry_constant() or []:
                symbole = self._symbole(nom.getText())
                self._observer("pli_entry", symbole, ctx, "entry_statement",
                               {"proc": symbole})
            return self.visitChildren(ctx)

        def visitDeclare2_statement(self, ctx):
            type_ = _texte_tokens(ctx.attribute() or [])
            for variable in ctx.variable() or []:
                symbole = self._symbole(variable.getText())
                attributs = {"type": type_} if type_ else {}
                self._observer("pli_var", symbole, ctx, "declare2_statement", attributs)
            return self.visitChildren(ctx)

        def visitDeclare_statement(self, ctx):
            for nom in ctx.identifier() or []:
                symbole = self._symbole(nom.getText())
                self._observer("pli_var", symbole, ctx, "declare_statement")
            return self.visitChildren(ctx)

        def visitCall_statement(self, ctx):
            cible = None
            for nom in ("entry_reference", "generic_name", "built_in_name"):
                methode = getattr(ctx, nom, None)
                if methode is None:
                    continue
                contexte = methode()
                if isinstance(contexte, list):
                    contexte = contexte[0] if contexte else None
                if contexte is not None:
                    cible = contexte.getText()
                    break
            if cible:
                symbole = self._symbole(cible)
                self._observer("pli_call", symbole, ctx, "call_statement",
                               {"target": symbole})
            return self.visitChildren(ctx)

        def visitInclude_statement(self, ctx):
            for membre in ctx.member_name() or []:
                symbole = self._symbole(membre.getText())
                self._observer("pli_include", symbole, ctx, "include_statement",
                               {"target": symbole, "include": symbole})
            return self.visitChildren(ctx)

        def visitStatements(self, ctx):
            if not self._consomme_etiquettes(ctx):
                for etiquette in ctx.label_prefix() or []:
                    symbole = self._symbole(etiquette.getText())
                    self._observer("pli_label", symbole, etiquette,
                                   "label_prefix")
            return self.visitChildren(ctx)

        def visitPercent_statements(self, ctx):
            if not self._consomme_etiquettes(ctx):
                for etiquette in ctx.label_prefix() or []:
                    symbole = self._symbole(etiquette.getText())
                    self._observer("pli_label", symbole, etiquette,
                                   "label_prefix")
            return self.visitChildren(ctx)

        def visitReturn2_statement(self, ctx):
            parent = ctx.parentCtx
            while parent is not None and type(parent).__name__ not in {
                    "StatementsContext", "Percent_statementsContext"}:
                parent = parent.parentCtx
            if parent is not None and not parent.label_prefix():
                self._observer("pli_label", "RETURN", ctx, "return2_statement")
            return self.visitChildren(ctx)

    visiteur = _Visiteur()
    visiteur._fichier = sidecar._fichier_courant
    return visiteur


class PliSemanticSidecar:
    """Parseur PL/I ANTLR : observations structurelles, jamais d'exécution."""

    provider = PROVIDER
    extensions = EXTENSIONS
    parser = PARSER
    parser_version = VERSION
    language = LANGAGE

    def __init__(self, provider=PROVIDER):
        self.provider = str(provider or PROVIDER).strip() or PROVIDER
        self._fichier_courant = ""

    def index(self, racine: str, fichiers=()) -> list[Observation]:
        fichiers = tuple(fichiers or ())
        observations = []
        for chemin in self._candidats(racine, fichiers):
            if chemin.suffix.lower() not in SUFFIXES or not chemin.is_file():
                continue
            try:
                texte = _lire(chemin)
                self._fichier_courant = _cle_fichier(Path(racine), chemin)
                observations.extend(self._extraire(self._fichier_courant, texte))
            except Exception:
                continue
        return observations

    def couverture(self, racine: str, fichiers=()) -> list[CouvertureFichier]:
        fichiers = tuple(fichiers or ())
        lignes = {}
        for chemin in self._candidats(racine, fichiers):
            cle = _cle_fichier(Path(racine), chemin)
            if cle in lignes:
                continue
            if chemin.suffix.lower() not in SUFFIXES:
                lignes[cle] = CouvertureFichier(
                    file=cle, parser=self.parser, statut="non_supporte",
                    raison="extension non prise en charge")
                continue
            if not chemin.is_file():
                lignes[cle] = CouvertureFichier(
                    file=cle, language=LANGAGE, parser=self.parser, statut="ignore",
                    raison="fichier introuvable ou illisible")
                continue
            if not parser_disponible():
                lignes[cle] = CouvertureFichier(
                    file=cle, language=LANGAGE, parser=self.parser, statut="non_supporte",
                    raison="parseur ANTLR généré absent (voir tools/pli/README.md)")
                continue
            try:
                texte = _lire(chemin)
            except OSError:
                lignes[cle] = CouvertureFichier(
                    file=cle, language=LANGAGE, parser=self.parser, statut="ignore",
                    raison="fichier introuvable ou illisible")
                continue
            observations, erreurs = self._analyser(cle, texte)
            if erreurs:
                lignes[cle] = CouvertureFichier(
                    file=cle, language=LANGAGE, parser=self.parser, statut="partiel",
                    raison=f"{len(erreurs)} erreur(s) de syntaxe ANTLR")
            elif observations:
                lignes[cle] = CouvertureFichier(
                    file=cle, language=LANGAGE, parser=self.parser, statut="indexe")
            else:
                lignes[cle] = CouvertureFichier(
                    file=cle, language=LANGAGE, parser=self.parser, statut="partiel",
                    raison="aucune structure PL/I reconnue")
        return [lignes[cle] for cle in sorted(lignes)]

    @staticmethod
    def _candidats(racine: str, fichiers):
        base = Path(racine)
        if fichiers:
            for nom in fichiers:
                chemin = Path(nom)
                yield chemin if chemin.is_absolute() else base / chemin
            return
        try:
            for chemin in sorted(base.rglob("*")):
                if chemin.is_file() and chemin.suffix.lower() in SUFFIXES:
                    yield chemin
        except OSError:
            return

    def _extraire(self, fichier: str, texte: str) -> list[Observation]:
        observations, _ = self._analyser(fichier, texte)
        return observations

    def _analyser(self, fichier: str, texte: str):
        modules = _charger_parser()
        if modules is None:
            return [], ["parseur ANTLR absent"]
        pl1Lexer, pl1Parser, pl1Visitor = modules
        self._fichier_courant = fichier
        propre = _neutraliser_commentaires(texte)
        erreurs = _Erreurs()
        try:
            lexer = pl1Lexer(InputStream(propre))
            lexer.removeErrorListeners()
            lexer.addErrorListener(erreurs)
            tokens = lexer.getAllTokens()
        except Exception as erreur:
            return [], [str(erreur)]
        groupes = list(_groupes(tokens))
        observations = self._depuis_tokens(fichier, groupes)
        try:
            normalise, renames = _normaliser(propre, groupes, pl1Parser)
            lexer = pl1Lexer(InputStream(normalise))
            lexer.removeErrorListeners()
            lexer.addErrorListener(erreurs)
            parser = pl1Parser(CommonTokenStream(lexer))
            parser.removeErrorListeners()
            parser.addErrorListener(erreurs)
            arbre = parser.program()
            visiteur = _creer_visiteur(pl1Visitor, self, renames)
            arbre.accept(visiteur)
            observations = _fusionner(observations, visiteur.observations)
        except Exception as erreur:
            erreurs.lignes.append((0, 0, str(erreur)))
        return observations, erreurs.lignes

    def _depuis_tokens(self, fichier, groupes):
        observations = []
        procedures = []
        proc = ""
        profondeur = 0
        for groupe in groupes:
            etiquettes, i = _etiquettes(groupe)
            if i >= len(groupe):
                continue
            mot = groupe[i].text.upper()
            if _est_sql(groupe, i):
                self._etiquettes(fichier, etiquettes, proc, observations)
                self._ajouter_sql(fichier, groupe, i, proc, observations)
                continue
            if mot == "END":
                nom = ""
                if i + 1 < len(groupe) and _nom_valide(groupe[i + 1].text):
                    nom = groupe[i + 1].text
                if nom:
                    if procedures and procedures[-1].upper() == nom.upper():
                        procedures.pop()
                    elif any(item.upper() == nom.upper() for item in procedures):
                        while procedures and procedures[-1].upper() != nom.upper():
                            procedures.pop()
                        if procedures:
                            procedures.pop()
                    elif profondeur > 0:
                        profondeur -= 1
                elif profondeur > 0:
                    profondeur -= 1
                elif procedures:
                    procedures.pop()
                proc = procedures[-1] if procedures else ""
                continue
            if mot in {"PROC", "PROCEDURE"}:
                noms = etiquettes or []
                if noms:
                    for etiquette in noms:
                        nom = etiquette.text
                        observations.append(self._obs(
                            fichier, "pli_proc", nom, etiquette.line,
                            groupe[-1].line,
                            {"rule": "procedure2_statement", "proc": nom,
                             "tokens": [token.text for token in groupe][:80]}))
                    procedures.append(noms[-1].text)
                    proc = procedures[-1]
                continue
            if mot == "ENTRY":
                noms = [etiquette.text for etiquette in etiquettes]
                if not noms and proc:
                    noms = [proc]
                debut = etiquettes[0].line if etiquettes else groupe[i].line
                for nom in noms:
                    observations.append(self._obs(
                        fichier, "pli_entry", nom, debut, groupe[-1].line,
                        {"rule": "entry_statement", "proc": nom,
                         "tokens": [token.text for token in groupe][:80]}))
                continue
            self._etiquettes(fichier, etiquettes, proc, observations)
            if mot in {"DCL", "DECLARE"}:
                for token, type_tokens in _declarations_tokens(groupe[i + 1:]):
                    attributs = {"rule": "declare2_statement"}
                    type_ = _type_tokens(type_tokens)
                    if type_:
                        attributs["type"] = type_
                    if proc:
                        attributs["proc"] = proc
                    attributs["tokens"] = [item.text for item in groupe][:80]
                    observations.append(self._obs(
                        fichier, "pli_var", token.text, groupe[0].line,
                        groupe[-1].line, attributs))
                continue
            if mot == "CALL":
                cible = self._cible_appel(groupe, i)
                if cible:
                    attributs = {"rule": "call_statement", "target": cible,
                                 "tokens": [token.text for token in groupe][:80]}
                    if proc:
                        attributs["proc"] = proc
                    observations.append(self._obs(
                        fichier, "pli_call", cible, groupe[0].line,
                        groupe[-1].line, attributs))
                continue
            if mot == "%" and i + 1 < len(groupe) \
                    and groupe[i + 1].text.upper() == "INCLUDE":
                cible = _cible_include(groupe[i + 2:])
                if cible:
                    attributs = {"rule": "include_statement", "target": cible,
                                 "include": cible,
                                 "tokens": [token.text for token in groupe][:80]}
                    if proc:
                        attributs["proc"] = proc
                    observations.append(self._obs(
                        fichier, "pli_include", cible, groupe[0].line,
                        groupe[-1].line, attributs))
                continue
            if mot == "RETURN":
                if not etiquettes:
                    attributs = {"rule": "return2_statement"}
                    if proc:
                        attributs["proc"] = proc
                    attributs["tokens"] = [token.text for token in groupe][:80]
                    observations.append(self._obs(
                        fichier, "pli_label", "RETURN", groupe[0].line,
                        groupe[-1].line, attributs))
                continue
            if self._ouvre_bloc(groupe, i, mot):
                profondeur += 1
        return observations

    def _etiquettes(self, fichier, etiquettes, proc, observations):
        for etiquette in etiquettes:
            attributs = {"rule": "label_prefix",
                         "tokens": [etiquette.text, ":"]}
            if proc:
                attributs["proc"] = proc
            observations.append(Observation(
                provider=self.provider, parser=PARSER, parser_version=VERSION,
                file=fichier, language=LANGAGE, kind="pli_label",
                symbol=etiquette.text, start=etiquette.line, end=etiquette.line,
                attributes=attributs))

    @staticmethod
    def _cible_appel(groupe, i):
        j = i + 1
        if j < len(groupe) and groupe[j].text == "(":
            j += 1
        morceaux = []
        while j < len(groupe) and groupe[j].text not in {"(", ")", ";", ","}:
            morceaux.append(groupe[j].text)
            j += 1
        return "".join(morceaux).strip("'\"") or None

    @staticmethod
    def _ouvre_bloc(groupe, i, mot):
        if mot in {"DO", "BEGIN"}:
            return True
        if mot == "SELECT":
            return not _est_sql(groupe, i)
        if mot == "IF":
            textes = [token.text.upper() for token in groupe[i:]]
            for position, texte in enumerate(textes[:-1]):
                if texte == "THEN" and textes[position + 1] == "DO":
                    return True
        return False

    def _ajouter_sql(self, fichier, groupe, i, proc, observations):
        corps = groupe[i:]
        mot = corps[0].text.upper()
        if mot == "EXEC" and len(corps) > 1 and corps[1].text.upper() == "SQL":
            commande_tokens = corps[2:]
        else:
            commande_tokens = corps
        commande = ""
        for token in commande_tokens:
            if token.text.upper().isalpha():
                commande = token.text.upper()
                break
        if not commande:
            return
        attributs = {"rule": "exec_sql" if mot == "EXEC" else "select_statement",
                     "command": commande,
                     "tokens": [token.text for token in groupe][:80]}
        table = _table_sql(commande, commande_tokens)
        if table:
            attributs["table"] = table
        if proc:
            attributs["proc"] = proc
        observations.append(self._obs(
            fichier, "pli_sql", commande, groupe[i].line, groupe[-1].line,
            attributs))

    def _obs(self, fichier, kind, symbol, debut, fin, attributs=None):
        return Observation(
            provider=self.provider, parser=PARSER, parser_version=VERSION,
            file=fichier, language=LANGAGE, kind=kind, symbol=symbol,
            start=debut, end=fin, attributes=attributs or {})


def _fusionner(base, ast):
    index = {(observation.kind, observation.symbol, observation.start): observation
             for observation in base}
    for observation in ast:
        cle = (observation.kind, observation.symbol, observation.start)
        precedent = index.get(cle)
        if precedent is None:
            index[cle] = observation
            continue
        attributs = dict(precedent.attributes)
        for nom in ("type", "target", "include", "table", "command", "proc"):
            if not attributs.get(nom) and observation.attributes.get(nom):
                attributs[nom] = observation.attributes[nom]
        if observation.attributes.get("rule"):
            attributs["rule"] = observation.attributes["rule"]
        index[cle] = Observation(
            provider=precedent.provider, parser=precedent.parser,
            parser_version=precedent.parser_version, file=precedent.file,
            language=precedent.language, kind=precedent.kind,
            symbol=precedent.symbol, start=precedent.start, end=precedent.end,
            commit=precedent.commit, attributes=attributs,
            confidence=precedent.confidence, status=precedent.status)
    return sorted(index.values(), key=lambda o: (o.file, o.start, o.kind, o.symbol))
