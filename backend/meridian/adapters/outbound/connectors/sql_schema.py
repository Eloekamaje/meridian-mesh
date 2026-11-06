"""Sidecar SQL structurel : lit du DDL local et rend des observations, sans connexion ni exécution."""
from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Iterator, Optional

from meridian.domain.code_index import CouvertureFichier, Observation

__all__ = ["SqlSchemaSidecar"]

PROVIDER = "sql"
PARSER = "sql-structural"
PARSER_VERSION = "1.0"
LANGAGE = "sql"
EXTENSIONS = frozenset({".sql", ".ddl", ".pks", ".pkb", ".pls", ".prc"})
DOSSIERS_IGNORES = frozenset({
    ".git", "node_modules", "vendor", "build", "dist", ".venv", "__pycache__", ".cache",
})
TAILLE_MAX = 4_000_000

_MOTS_FIN_TYPE = frozenset({
    "CONSTRAINT", "NOT", "NULL", "DEFAULT", "PRIMARY", "REFERENCES", "UNIQUE",
    "CHECK", "GENERATED", "IDENTITY", "COLLATE", "COMMENT", "ENABLE", "DISABLE",
})
_MOTS_DEBUT_INSTRUCTION = frozenset({
    "CREATE", "ALTER", "COMMENT", "GRANT", "REVOKE", "DROP", "INSERT", "UPDATE",
    "DELETE", "MERGE", "TRUNCATE", "SELECT", "WITH", "COMMIT", "ROLLBACK", "SET",
})
_MODIFICATEURS_CREATE = frozenset({
    "OR", "REPLACE", "GLOBAL", "LOCAL", "TEMPORARY", "TEMP", "UNLOGGED", "EXTERNAL",
    "MATERIALIZED", "UNIQUE", "BITMAP", "FORCE", "NO", "EDITIONABLE", "NONEDITIONABLE",
})
_KINDS_ROUTINE = {
    "PROCEDURE": "sql_procedure",
    "FUNCTION": "sql_function",
    "PACKAGE": "sql_package",
}


@dataclass(frozen=True)
class _Jeton:
    valeur: str
    genre: str
    debut: int
    fin: int

    @property
    def mot(self) -> str:
        return self.valeur.upper()


@dataclass
class _Colonne:
    nom: str
    type: str
    nullable: bool = True
    defaut: str = ""
    unique: bool = False
    references: str = ""
    on_delete: str = ""
    colonnes_referencees: list[str] = field(default_factory=list)


@dataclass
class _Contrainte:
    genre: str
    nom: str = ""
    colonnes: list[str] = field(default_factory=list)
    expression: str = ""
    references: str = ""
    on_delete: str = ""
    colonnes_referencees: list[str] = field(default_factory=list)


class _ErreurSyntaxe(ValueError):
    """Un fragment DDL n'a pas pu être interprété ; le fichier reste lisible en partie."""


def _tokeniser(texte: str) -> tuple[list[_Jeton], list[str]]:
    """Découpe le texte en jetons en ignorant commentaires et séparateurs PL/SQL."""
    jetons: list[_Jeton] = []
    erreurs: list[str] = []
    i, taille = 0, len(texte)
    while i < taille:
        caractere = texte[i]
        if caractere.isspace():
            i += 1
            continue
        if texte.startswith("--", i):
            fin = texte.find("\n", i + 2)
            i = taille if fin < 0 else fin + 1
            continue
        if texte.startswith("/*", i):
            fin = texte.find("*/", i + 2)
            if fin < 0:
                erreurs.append("commentaire /* non fermé")
                break
            i = fin + 2
            continue
        if caractere == "'":
            debut, i = i, i + 1
            morceaux: list[str] = []
            ferme = False
            while i < taille:
                if texte[i] == "'":
                    if i + 1 < taille and texte[i + 1] == "'":
                        morceaux.append("'")
                        i += 2
                        continue
                    i += 1
                    ferme = True
                    break
                morceaux.append(texte[i])
                i += 1
            if not ferme:
                erreurs.append("chaîne non fermée")
            jetons.append(_Jeton("".join(morceaux), "chaine", debut, i))
            continue
        if caractere == '"':
            debut, i = i, i + 1
            morceaux = []
            ferme = False
            while i < taille:
                if texte[i] == '"':
                    if i + 1 < taille and texte[i + 1] == '"':
                        morceaux.append('"')
                        i += 2
                        continue
                    i += 1
                    ferme = True
                    break
                morceaux.append(texte[i])
                i += 1
            if not ferme:
                erreurs.append("identifiant entre guillemets non fermé")
            jetons.append(_Jeton("".join(morceaux), "ident", debut, i))
            continue
        if caractere in "(),;./":
            jetons.append(_Jeton(caractere, "ponct", i, i + 1))
            i += 1
            continue
        if caractere.isalnum() or caractere in "_$#":
            debut = i
            while i < taille and (texte[i].isalnum() or texte[i] in "_$#"):
                i += 1
            jetons.append(_Jeton(texte[debut:i], "mot", debut, i))
            continue
        if i + 1 < taille and texte[i:i + 2] in ("<=", ">=", "<>", "!=", "||", ":=", "=>", "::"):
            jetons.append(_Jeton(texte[i:i + 2], "op", i, i + 2))
            i += 2
            continue
        jetons.append(_Jeton(caractere, "op", i, i + 1))
        i += 1
    return jetons, erreurs


def _est_plsql(jetons: list[_Jeton]) -> bool:
    mots = [jeton for jeton in jetons if jeton.genre in ("mot", "ident")]
    if not mots or mots[0].mot != "CREATE":
        return False
    i = 1
    while i < len(mots) and mots[i].mot in ("OR", "REPLACE", "EDITIONABLE", "NONEDITIONABLE"):
        i += 1
    return i < len(mots) and mots[i].mot in ("PROCEDURE", "FUNCTION", "PACKAGE")


def _identifiant(jetons: list[_Jeton], debut: int) -> tuple[str, int]:
    if debut >= len(jetons) or jetons[debut].genre not in ("mot", "ident"):
        return "", debut
    parties = [jetons[debut].valeur]
    i = debut + 1
    while i + 1 < len(jetons) and jetons[i].valeur == "." and jetons[i + 1].genre in ("mot", "ident"):
        parties.append(jetons[i + 1].valeur)
        i += 2
    return ".".join(parties), i


def _nom_court(nom: str) -> str:
    return (nom.rsplit(".", 1)[-1] if nom else "").strip('"').upper()


def _racine_unite(jetons: list[_Jeton]) -> str:
    i = 0
    while i < len(jetons) and jetons[i].genre not in ("mot", "ident"):
        i += 1
    if i >= len(jetons):
        return ""
    if jetons[i].mot != "CREATE":
        return ""
    i += 1
    while i < len(jetons) and jetons[i].genre in ("mot", "ident") and jetons[i].mot in (
            "OR", "REPLACE", "EDITIONABLE", "NONEDITIONABLE"):
        i += 1
    if i >= len(jetons):
        return ""
    mot = jetons[i].mot
    if mot in ("PROCEDURE", "FUNCTION"):
        i += 1
    elif mot == "PACKAGE":
        i += 1
        if i < len(jetons) and jetons[i].genre in ("mot", "ident") and jetons[i].mot == "BODY":
            i += 1
    else:
        return ""
    nom, _ = _identifiant(jetons, i)
    return nom


def _peut_terminer(jetons: list[_Jeton], position: int, nom: str, racine: str) -> bool:
    if nom:
        return _nom_court(nom) == _nom_court(racine)
    if position >= len(jetons):
        return True
    suivant = jetons[position]
    if suivant.genre == "ponct" and suivant.valeur == "/":
        return True
    return suivant.genre in ("mot", "ident") and suivant.mot in _MOTS_DEBUT_INSTRUCTION


def _decouper(jetons: list[_Jeton]) -> tuple[list[tuple[list[_Jeton], int, int]], list[str]]:
    """Sépare les instructions ; un bloc PL/SQL garde ses points-virgules internes."""
    instructions: list[tuple[list[_Jeton], int, int]] = []
    erreurs: list[str] = []
    courant: list[_Jeton] = []
    pile: list[str] = []
    plsql = False
    terminer = False
    ignorer = ""
    racine = ""

    i = 0
    while i < len(jetons):
        jeton = jetons[i]
        if jeton.valeur == "/" and not courant:
            i += 1
            continue
        courant.append(jeton)
        if not plsql and _est_plsql(courant):
            plsql = True
            racine = _racine_unite(courant)
        if plsql and jeton.genre in ("mot", "ident"):
            mot = jeton.mot
            if ignorer and mot == ignorer:
                ignorer = ""
            elif mot == "BEGIN":
                pile.append("begin")
            elif mot == "IF":
                pile.append("if")
            elif mot == "LOOP":
                pile.append("loop")
            elif mot == "CASE":
                pile.append("case")
            elif mot == "END":
                suivant = jetons[i + 1].mot if i + 1 < len(jetons) else ""
                if suivant in ("IF", "LOOP", "CASE"):
                    if pile:
                        pile.pop()
                    ignorer = suivant
                else:
                    if pile:
                        pile.pop()
                    if not pile:
                        racine = _racine_unite(courant)
                        nom, position = "", i + 1
                        if (position < len(jetons) and jetons[position].genre in ("mot", "ident")
                                and jetons[position].mot not in ("IF", "LOOP", "CASE")):
                            nom = jetons[position].valeur
                            position += 1
                        if (position < len(jetons) and jetons[position].genre == "ponct"
                                and jetons[position].valeur == ";"
                                and _peut_terminer(jetons, position + 1, nom, racine)):
                            terminer = True
        if jeton.valeur == ";":
            if not plsql or terminer:
                instruction = courant[:-1]
                if instruction:
                    instructions.append((instruction, instruction[0].debut, jeton.fin))
                courant, pile, plsql, terminer, ignorer, racine = [], [], False, False, "", ""
        i += 1

    if courant:
        erreurs.append("instruction non terminée")
        if len(courant) > 1 or courant[0].valeur != "/":
            instructions.append((courant, courant[0].debut, courant[-1].fin))
    return instructions, erreurs


def _texte_source(texte: str, jetons: list[_Jeton]) -> str:
    if not jetons:
        return ""
    return texte[jetons[0].debut:jetons[-1].fin].strip()


def _fermer_parenthese(jetons: list[_Jeton], ouverture: int) -> int:
    profondeur = 0
    for i in range(ouverture, len(jetons)):
        if jetons[i].valeur == "(":
            profondeur += 1
        elif jetons[i].valeur == ")":
            profondeur -= 1
            if profondeur == 0:
                return i
    return -1


def _morceaux(jetons: list[_Jeton], debut: int, fin: int) -> list[list[_Jeton]]:
    morceaux: list[list[_Jeton]] = []
    courant: list[_Jeton] = []
    profondeur = 0
    for jeton in jetons[debut:fin]:
        if jeton.valeur == "(":
            profondeur += 1
        elif jeton.valeur == ")":
            profondeur -= 1
        if jeton.valeur == "," and profondeur == 0:
            if courant:
                morceaux.append(courant)
            courant = []
        else:
            courant.append(jeton)
    if courant:
        morceaux.append(courant)
    return morceaux


def _noms_colonnes(jetons: list[_Jeton], debut: int, fin: int) -> list[str]:
    noms: list[str] = []
    for morceau in _morceaux(jetons, debut, fin):
        nom, _ = _identifiant(morceau, 0)
        if nom:
            noms.append(nom)
    return noms


def _colonnes_parentheses(jetons: list[_Jeton], debut: int) -> tuple[list[str], int]:
    if debut >= len(jetons) or jetons[debut].valeur != "(":
        return [], debut
    fermeture = _fermer_parenthese(jetons, debut)
    if fermeture < 0:
        raise _ErreurSyntaxe("parenthèse fermante absente")
    return _noms_colonnes(jetons, debut + 1, fermeture), fermeture + 1


def _expression_parentheses(texte: str, jetons: list[_Jeton], debut: int) -> tuple[str, int]:
    if debut >= len(jetons) or jetons[debut].valeur != "(":
        raise _ErreurSyntaxe("expression entre parenthèses attendue")
    fermeture = _fermer_parenthese(jetons, debut)
    if fermeture < 0:
        raise _ErreurSyntaxe("parenthèse fermante absente")
    return _texte_source(texte, jetons[debut + 1:fermeture]), fermeture + 1


def _expression(texte: str, jetons: list[_Jeton], debut: int) -> tuple[str, int]:
    profondeur = 0
    i = debut
    while i < len(jetons):
        jeton = jetons[i]
        if (i > debut and profondeur == 0 and jeton.genre in ("mot", "ident")
                and jeton.mot in _MOTS_FIN_TYPE):
            break
        if jeton.valeur == "(":
            profondeur += 1
        elif jeton.valeur == ")":
            profondeur -= 1
        i += 1
    return _texte_source(texte, jetons[debut:i]), i


def _references(jetons: list[_Jeton], debut: int) -> tuple[str, list[str], str, int]:
    table, i = _identifiant(jetons, debut + 1)
    if not table:
        raise _ErreurSyntaxe("REFERENCES sans table cible")
    colonnes: list[str] = []
    if i < len(jetons) and jetons[i].valeur == "(":
        colonnes, i = _colonnes_parentheses(jetons, i)
    action = ""
    if i < len(jetons) and jetons[i].mot == "ON":
        if i + 1 < len(jetons) and jetons[i + 1].mot == "DELETE":
            i += 2
            parties: list[str] = []
            while i < len(jetons) and jetons[i].mot in (
                    "CASCADE", "RESTRICT", "SET", "NULL", "DEFAULT", "NO", "ACTION"):
                parties.append(jetons[i].mot)
                i += 1
            action = " ".join(parties)
    return table, colonnes, action, i


def _contrainte(texte: str, jetons: list[_Jeton], debut: int, nom: str,
                contraintes: list[_Contrainte]) -> int:
    mot = jetons[debut].mot
    if mot == "PRIMARY":
        i = debut + 1
        if i < len(jetons) and jetons[i].mot == "KEY":
            i += 1
        colonnes, i = _colonnes_parentheses(jetons, i)
        contraintes.append(_Contrainte("sql_pk", nom, colonnes))
        return i
    if mot == "FOREIGN":
        i = debut + 1
        if i < len(jetons) and jetons[i].mot == "KEY":
            i += 1
        colonnes, i = _colonnes_parentheses(jetons, i)
        if i >= len(jetons) or jetons[i].mot != "REFERENCES":
            raise _ErreurSyntaxe("FOREIGN KEY sans REFERENCES")
        table, colonnes_ref, action, i = _references(jetons, i)
        contraintes.append(_Contrainte(
            "sql_fk", nom, colonnes, references=table, on_delete=action,
            colonnes_referencees=colonnes_ref,
        ))
        return i
    if mot == "UNIQUE":
        i = debut + 1
        if i < len(jetons) and jetons[i].mot == "KEY":
            i += 1
        if (i + 1 < len(jetons) and jetons[i].genre in ("mot", "ident")
                and jetons[i + 1].valeur == "("):
            i += 1
        colonnes, i = _colonnes_parentheses(jetons, i)
        contraintes.append(_Contrainte("sql_unique", nom, colonnes))
        return i
    if mot == "CHECK":
        expression, i = _expression_parentheses(texte, jetons, debut + 1)
        contraintes.append(_Contrainte("sql_check", nom, expression=expression))
        return i
    return debut + 1


def _colonne(texte: str, jetons: list[_Jeton], colonnes: list[_Colonne],
             contraintes: list[_Contrainte]) -> None:
    nom, i = _identifiant(jetons, 0)
    if not nom:
        raise _ErreurSyntaxe("colonne sans nom")
    debut_type = i
    profondeur = 0
    while i < len(jetons):
        jeton = jetons[i]
        if jeton.valeur == "(":
            profondeur += 1
        elif jeton.valeur == ")":
            profondeur -= 1
        if (profondeur == 0 and jeton.genre in ("mot", "ident")
                and jeton.mot in _MOTS_FIN_TYPE):
            break
        i += 1
    type_sql = _texte_source(texte, jetons[debut_type:i])
    if not type_sql:
        raise _ErreurSyntaxe(f"colonne {nom} sans type")
    colonne = _Colonne(nom, type_sql)
    nom_contrainte = ""
    while i < len(jetons):
        mot = jetons[i].mot
        if mot == "CONSTRAINT":
            if i + 1 >= len(jetons):
                raise _ErreurSyntaxe("contrainte sans nom")
            nom_contrainte = jetons[i + 1].valeur
            i += 2
        elif mot == "NOT" and i + 1 < len(jetons) and jetons[i + 1].mot == "NULL":
            colonne.nullable = False
            i += 2
        elif mot == "NULL":
            colonne.nullable = True
            i += 1
        elif mot == "DEFAULT":
            colonne.defaut, i = _expression(texte, jetons, i + 1)
        elif mot == "PRIMARY":
            i += 1
            if i < len(jetons) and jetons[i].mot == "KEY":
                i += 1
            contraintes.append(_Contrainte("sql_pk", nom_contrainte, [nom]))
            nom_contrainte = ""
        elif mot == "UNIQUE":
            colonne.unique = True
            contraintes.append(_Contrainte("sql_unique", nom_contrainte, [nom]))
            nom_contrainte = ""
            i += 1
        elif mot == "REFERENCES":
            cible, colonnes_ref, action, i = _references(jetons, i)
            colonne.references, colonne.on_delete = cible, action
            colonne.colonnes_referencees = colonnes_ref
            contraintes.append(_Contrainte(
                "sql_fk", nom_contrainte, [nom], references=cible,
                on_delete=action, colonnes_referencees=colonnes_ref,
            ))
            nom_contrainte = ""
        elif mot == "CHECK":
            expression, i = _expression_parentheses(texte, jetons, i + 1)
            contraintes.append(_Contrainte("sql_check", nom_contrainte, [nom], expression=expression))
            nom_contrainte = ""
        else:
            i += 1
    colonnes.append(colonne)


def _element_table(texte: str, jetons: list[_Jeton], table: str, colonnes: list[_Colonne],
                   contraintes: list[_Contrainte]) -> None:
    if not jetons:
        return
    nom_contrainte = ""
    i = 0
    if jetons[i].mot == "CONSTRAINT":
        if i + 1 >= len(jetons):
            raise _ErreurSyntaxe("contrainte sans nom")
        nom_contrainte = jetons[i + 1].valeur
        i += 2
    if i >= len(jetons):
        raise _ErreurSyntaxe("contrainte vide")
    mot = jetons[i].mot
    if mot in ("PRIMARY", "FOREIGN", "UNIQUE", "CHECK"):
        _contrainte(texte, jetons, i, nom_contrainte, contraintes)
        return
    if mot in ("KEY", "INDEX"):
        return
    if nom_contrainte:
        raise _ErreurSyntaxe(f"contrainte {nom_contrainte} non reconnue")
    _colonne(texte, jetons[i:], colonnes, contraintes)


def _appliquer_contraintes(colonnes: list[_Colonne], contraintes: list[_Contrainte]) -> None:
    par_nom = {_nom_court(colonne.nom): colonne for colonne in colonnes}
    for contrainte in contraintes:
        if contrainte.genre == "sql_fk":
            for nom in contrainte.colonnes:
                colonne = par_nom.get(_nom_court(nom))
                if colonne is not None:
                    colonne.references = contrainte.references
                    colonne.on_delete = contrainte.on_delete
                    colonne.colonnes_referencees = list(contrainte.colonnes_referencees)
        elif contrainte.genre == "sql_unique":
            for nom in contrainte.colonnes:
                colonne = par_nom.get(_nom_court(nom))
                if colonne is not None:
                    colonne.unique = True


def _observation(fichier: str, kind: str, symbol: str, attributes: dict,
                 debut: int, fin: int) -> Observation:
    return Observation(
        provider=PROVIDER, parser=PARSER, parser_version=PARSER_VERSION,
        file=fichier, language=LANGAGE, kind=kind, symbol=symbol,
        start=debut, end=fin, attributes=attributes,
    )


def _symbole_contrainte(table: str, contrainte: _Contrainte) -> str:
    if contrainte.nom:
        return contrainte.nom
    suffixe = {
        "sql_pk": "PK", "sql_fk": "FK", "sql_unique": "UNIQUE", "sql_check": "CHECK",
    }.get(contrainte.genre, "CONTRAINTE")
    colonnes = ",".join(contrainte.colonnes)
    return f"{table}.{suffixe}({colonnes})" if colonnes else f"{table}.{suffixe}"


def _observations_colonnes(table: str, colonnes: list[_Colonne], contraintes: list[_Contrainte],
                           fichier: str, debut: int, fin: int) -> list[Observation]:
    _appliquer_contraintes(colonnes, contraintes)
    observations: list[Observation] = []
    for colonne in colonnes:
        attributs = {
            "table": table,
            "type": colonne.type,
            "nullable": colonne.nullable,
            "unique": colonne.unique,
        }
        if colonne.defaut:
            attributs["default"] = colonne.defaut
        if colonne.references:
            attributs["references"] = colonne.references
        if colonne.on_delete:
            attributs["on_delete"] = colonne.on_delete
        if colonne.colonnes_referencees:
            attributs["colonnes_referencees"] = list(colonne.colonnes_referencees)
        observations.append(_observation(
            fichier, "sql_column", f"{table}.{colonne.nom}", attributs, debut, fin))
    for contrainte in contraintes:
        attributs = {"table": table, "colonnes": list(contrainte.colonnes)}
        if contrainte.nom:
            attributs["nom"] = contrainte.nom
        if contrainte.expression:
            attributs["expression"] = contrainte.expression
        if contrainte.references:
            attributs["references"] = contrainte.references
        if contrainte.on_delete:
            attributs["on_delete"] = contrainte.on_delete
        if contrainte.colonnes_referencees:
            attributs["colonnes_referencees"] = list(contrainte.colonnes_referencees)
        observations.append(_observation(
            fichier, contrainte.genre, _symbole_contrainte(table, contrainte),
            attributs, debut, fin))
    return observations


def _analyser_table(texte: str, jetons: list[_Jeton], fichier: str,
                    debut: int, fin: int) -> list[Observation]:
    i = next((k for k, jeton in enumerate(jetons)
              if jeton.genre in ("mot", "ident") and jeton.mot == "TABLE"), -1)
    if i < 0:
        raise _ErreurSyntaxe("CREATE TABLE sans mot TABLE")
    i += 1
    if i + 2 < len(jetons) and jetons[i].mot == "IF" and jetons[i + 1].mot == "NOT" \
            and jetons[i + 2].mot == "EXISTS":
        i += 3
    table, i = _identifiant(jetons, i)
    if not table:
        raise _ErreurSyntaxe("CREATE TABLE sans nom")
    if i >= len(jetons) or jetons[i].valeur != "(":
        if i < len(jetons) and jetons[i].mot == "AS":
            attributs = {"colonnes": []}
            if "." in table:
                attributs["schema"] = table.rsplit(".", 1)[0]
            return [_observation(fichier, "sql_table", table, attributs, debut, fin)]
        raise _ErreurSyntaxe(f"liste de colonnes absente pour {table}")
    fermeture = _fermer_parenthese(jetons, i)
    if fermeture < 0:
        raise _ErreurSyntaxe(f"parenthèse fermante absente pour {table}")
    colonnes: list[_Colonne] = []
    contraintes: list[_Contrainte] = []
    for element in _morceaux(jetons, i + 1, fermeture):
        _element_table(texte, element, table, colonnes, contraintes)
    attributs = {"colonnes": [colonne.nom for colonne in colonnes]}
    if "." in table:
        attributs["schema"] = table.rsplit(".", 1)[0]
    observations = [_observation(fichier, "sql_table", table, attributs, debut, fin)]
    observations.extend(_observations_colonnes(
        table, colonnes, contraintes, fichier, debut, fin))
    return observations


def _analyser_alter(texte: str, jetons: list[_Jeton], fichier: str,
                    debut: int, fin: int) -> list[Observation]:
    i = next((k for k, jeton in enumerate(jetons)
              if jeton.genre in ("mot", "ident") and jeton.mot == "TABLE"), -1)
    if i < 0:
        return []
    i += 1
    if i < len(jetons) and jetons[i].mot == "ONLY":
        i += 1
    table, i = _identifiant(jetons, i)
    if not table:
        raise _ErreurSyntaxe("ALTER TABLE sans nom")
    action = next((k for k in range(i, len(jetons))
                   if jetons[k].genre in ("mot", "ident") and jetons[k].mot == "ADD"), -1)
    if action < 0:
        return []
    i = action + 1
    if i < len(jetons) and jetons[i].mot == "COLUMN":
        i += 1
    colonnes: list[_Colonne] = []
    contraintes: list[_Contrainte] = []
    if i < len(jetons) and jetons[i].valeur == "(":
        fermeture = _fermer_parenthese(jetons, i)
        if fermeture < 0:
            raise _ErreurSyntaxe(f"parenthèse fermante absente pour {table}")
        elements = _morceaux(jetons, i + 1, fermeture)
    else:
        elements = _morceaux(jetons, i, len(jetons))
    for element in elements:
        _element_table(texte, element, table, colonnes, contraintes)
    return _observations_colonnes(table, colonnes, contraintes, fichier, debut, fin)


def _analyser_vue(jetons: list[_Jeton], fichier: str, debut: int, fin: int) -> list[Observation]:
    i = next((k for k, jeton in enumerate(jetons)
              if jeton.genre in ("mot", "ident") and jeton.mot == "VIEW"), -1)
    if i < 0:
        raise _ErreurSyntaxe("CREATE VIEW sans mot VIEW")
    nom, i = _identifiant(jetons, i + 1)
    if not nom:
        raise _ErreurSyntaxe("CREATE VIEW sans nom")
    colonnes: list[str] = []
    if i < len(jetons) and jetons[i].valeur == "(":
        colonnes, i = _colonnes_parentheses(jetons, i)
    attributs = {"colonnes": colonnes}
    if "." in nom:
        attributs["schema"] = nom.rsplit(".", 1)[0]
    return [_observation(fichier, "sql_view", nom, attributs, debut, fin)]


def _analyser_index(jetons: list[_Jeton], fichier: str, debut: int, fin: int) -> list[Observation]:
    positions = [k for k, jeton in enumerate(jetons)
                 if jeton.genre in ("mot", "ident") and jeton.mot == "INDEX"]
    if not positions:
        raise _ErreurSyntaxe("CREATE INDEX sans mot INDEX")
    i = positions[0]
    unique = any(jeton.mot == "UNIQUE" for jeton in jetons[:i] if jeton.genre in ("mot", "ident"))
    nom, i = _identifiant(jetons, i + 1)
    if not nom:
        raise _ErreurSyntaxe("CREATE INDEX sans nom")
    on = next((k for k in range(i, len(jetons))
               if jetons[k].genre in ("mot", "ident") and jetons[k].mot == "ON"), -1)
    table = ""
    colonnes: list[str] = []
    if on >= 0:
        table, i = _identifiant(jetons, on + 1)
        ouverture = next((k for k in range(i, len(jetons)) if jetons[k].valeur == "("), -1)
        if ouverture >= 0:
            colonnes, _ = _colonnes_parentheses(jetons, ouverture)
    attributs = {"table": table, "colonnes": colonnes, "unique": unique}
    return [_observation(fichier, "sql_index", nom, attributs, debut, fin)]


def _analyser_routine(texte: str, jetons: list[_Jeton], mot: str, fichier: str,
                      debut: int, fin: int) -> list[Observation]:
    kind = _KINDS_ROUTINE.get(mot)
    if kind is None:
        return []
    i = next((k for k, jeton in enumerate(jetons)
              if jeton.genre in ("mot", "ident") and jeton.mot == mot), -1)
    if i < 0:
        return []
    i += 1
    corps = False
    if kind == "sql_package" and i < len(jetons) and jetons[i].mot == "BODY":
        corps = True
        i += 1
    nom, i = _identifiant(jetons, i)
    if not nom:
        raise _ErreurSyntaxe(f"CREATE {mot} sans nom")
    attributs = {"corps": corps} if kind == "sql_package" else {}
    if kind == "sql_function":
        retour = next((k for k in range(i, len(jetons))
                       if jetons[k].genre in ("mot", "ident") and jetons[k].mot == "RETURN"), -1)
        if retour >= 0:
            j = retour + 1
            while j < len(jetons) and jetons[j].mot not in ("IS", "AS", "DETERMINISTIC", "AUTHID", "PIPELINED"):
                j += 1
            type_retour = _texte_source(texte, jetons[retour + 1:j])
            if type_retour:
                attributs["type_retour"] = type_retour
    if "." in nom:
        attributs["schema"] = nom.rsplit(".", 1)[0]
    return [_observation(fichier, kind, nom, attributs, debut, fin)]


def _analyser_commentaire(jetons: list[_Jeton], fichier: str,
                          debut: int, fin: int) -> list[Observation]:
    i = 1
    if i < len(jetons) and jetons[i].mot == "ON":
        i += 1
    if i >= len(jetons) or jetons[i].genre not in ("mot", "ident"):
        raise _ErreurSyntaxe("COMMENT ON sans objet")
    objet = jetons[i].mot
    i += 1
    cible, i = _identifiant(jetons, i)
    if not cible:
        raise _ErreurSyntaxe("COMMENT ON sans cible")
    is_index = next((k for k in range(i, len(jetons))
                     if jetons[k].genre in ("mot", "ident") and jetons[k].mot == "IS"), -1)
    if is_index < 0 or is_index + 1 >= len(jetons):
        raise _ErreurSyntaxe("COMMENT ON sans texte")
    commentaire = jetons[is_index + 1].valeur
    attributs = {"objet": objet.lower(), "commentaire": commentaire}
    if objet == "COLUMN" and "." in cible:
        attributs["table"] = cible.rsplit(".", 1)[0]
        attributs["colonne"] = cible.rsplit(".", 1)[1]
    return [_observation(fichier, "sql_comment", cible, attributs, debut, fin)]


def _analyser_instruction(texte: str, jetons: list[_Jeton], fichier: str,
                          debut: int, fin: int) -> list[Observation]:
    if not jetons:
        return []
    premier = jetons[0].mot
    if premier == "CREATE":
        i = 1
        while i < len(jetons) and jetons[i].genre in ("mot", "ident") \
                and jetons[i].mot in _MODIFICATEURS_CREATE:
            i += 1
        if i >= len(jetons):
            return []
        mot = jetons[i].mot
        if mot == "TABLE":
            return _analyser_table(texte, jetons, fichier, debut, fin)
        if mot == "VIEW":
            return _analyser_vue(jetons, fichier, debut, fin)
        if mot == "INDEX":
            return _analyser_index(jetons, fichier, debut, fin)
        if mot in _KINDS_ROUTINE:
            return _analyser_routine(texte, jetons, mot, fichier, debut, fin)
        return []
    if premier == "ALTER":
        return _analyser_alter(texte, jetons, fichier, debut, fin)
    if premier == "COMMENT":
        return _analyser_commentaire(jetons, fichier, debut, fin)
    return []


def _locator(chemin: Path, racine: Path) -> str:
    try:
        return chemin.resolve().relative_to(racine.resolve()).as_posix()
    except (OSError, ValueError):
        return chemin.as_posix()


def _decoder(donnees: bytes) -> Optional[str]:
    try:
        return donnees.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            return donnees.decode("latin-1")
        except UnicodeDecodeError:
            return None


def _analyser_fichier(chemin: Path, racine: Path) -> tuple[list[Observation], list[str]]:
    try:
        donnees = chemin.read_bytes()
    except OSError as erreur:
        return [], [f"fichier illisible ({type(erreur).__name__})"]
    if len(donnees) > TAILLE_MAX:
        return [], [f"fichier trop volumineux (> {TAILLE_MAX} octets)"]
    if b"\x00" in donnees[:4096]:
        return [], ["fichier binaire ignoré"]
    texte = _decoder(donnees)
    if texte is None:
        return [], ["encodage non textuel"]
    fichier = _locator(chemin, racine)
    jetons, erreurs = _tokeniser(texte)
    instructions, erreurs_decoupage = _decouper(jetons)
    erreurs.extend(erreurs_decoupage)
    observations: list[Observation] = []
    for instruction, debut, fin in instructions:
        try:
            observations.extend(_analyser_instruction(texte, instruction, fichier, debut, fin))
        except _ErreurSyntaxe as erreur:
            erreurs.append(str(erreur))
        except Exception as erreur:  # un fichier ne doit jamais faire tomber l'indexation
            erreurs.append(f"analyse impossible ({type(erreur).__name__})")
    if observations:
        observations = [
            replace(
                observation,
                start=texte.count("\n", 0, max(0, observation.start)) + 1,
                end=texte.count("\n", 0, max(0, observation.end - 1)) + 1,
            )
            for observation in observations
        ]
    if erreurs and observations:
        observations = [replace(observation, status="ambiguous") for observation in observations]
    return observations, erreurs


def _fichiers_demandes(valeur) -> tuple:
    if valeur is None:
        return ()
    if isinstance(valeur, (str, os.PathLike)):
        return (valeur,)
    return tuple(valeur)


def _supporte(chemin: Path) -> bool:
    return chemin.suffix.lower() in EXTENSIONS


def _candidats(racine: Path, fichiers=()) -> Iterator[Path]:
    demandes = _fichiers_demandes(fichiers)
    if demandes:
        vus: set[str] = set()
        for valeur in demandes:
            chemin = Path(valeur)
            if not chemin.is_absolute():
                chemin = racine / chemin
            cle = str(chemin)
            if cle not in vus:
                vus.add(cle)
                yield chemin
        return
    for dossier, sous_dossiers, noms in os.walk(racine, followlinks=False):
        sous_dossiers[:] = sorted(
            nom for nom in sous_dossiers
            if nom.lower() not in DOSSIERS_IGNORES and not (Path(dossier) / nom).is_symlink()
        )
        for nom in sorted(noms):
            chemin = Path(dossier) / nom
            if _supporte(chemin) and not chemin.is_symlink():
                yield chemin


class SqlSchemaSidecar:
    """Indexe un arbre de fichiers SQL en observations structurelles, sans exécuter le DDL."""

    provider = PROVIDER
    parser = PARSER
    parser_version = PARSER_VERSION
    extensions = EXTENSIONS

    def index(self, racine, fichiers=()) -> list[Observation]:
        """Rend une observation par table, colonne, contrainte, vue, index ou routine."""
        base = Path(racine)
        if not base.is_dir():
            raise ValueError("racine introuvable ou n'est pas un dossier")
        observations: list[Observation] = []
        for chemin in _candidats(base, fichiers):
            if not _supporte(chemin):
                continue
            trouvees, _ = _analyser_fichier(chemin, base)
            observations.extend(trouvees)
        return sorted(observations, key=lambda o: (o.file, o.start, o.kind, o.symbol))

    def couverture(self, racine, fichiers=()) -> list[CouvertureFichier]:
        """Une ligne par fichier demandé ou découvert, avec `partiel` pour un DDL incomplet."""
        base = Path(racine)
        if not base.is_dir():
            raise ValueError("racine introuvable ou n'est pas un dossier")
        lignes: list[CouvertureFichier] = []
        for chemin in _candidats(base, fichiers):
            fichier = _locator(chemin, base)
            if not _supporte(chemin):
                lignes.append(CouvertureFichier(
                    file=fichier, parser=PARSER, statut="non_supporte",
                    raison="extension SQL non prise en charge",
                ))
                continue
            if not chemin.is_file():
                lignes.append(CouvertureFichier(
                    file=fichier, parser=PARSER, statut="ignore", raison="fichier introuvable",
                ))
                continue
            observations, erreurs = _analyser_fichier(chemin, base)
            if erreurs:
                raison = "analyse partielle : " + "; ".join(erreurs)
                lignes.append(CouvertureFichier(
                    file=fichier, language=LANGAGE, parser=PARSER,
                    statut="partiel", raison=raison,
                ))
            elif observations:
                lignes.append(CouvertureFichier(
                    file=fichier, language=LANGAGE, parser=PARSER, statut="indexe",
                ))
            else:
                lignes.append(CouvertureFichier(
                    file=fichier, language=LANGAGE, parser=PARSER, statut="ignore",
                    raison="aucun objet SQL reconnu",
                ))
        return sorted(lignes, key=lambda ligne: ligne.file)
