"""Sidecar SQL vivant : lecture des catalogues par SELECT, sans écriture ni concaténation."""
from __future__ import annotations

import re
from collections.abc import Mapping

from meridian.domain.code_index import CouvertureFichier, Observation

__all__ = [
    "SqlLiveSidecar", "PROVIDER", "PARSER", "PARSER_VERSION", "LANGAGE", "DIALECTES",
]

PROVIDER = "sql-live"
PARSER = "sql-catalog"
PARSER_VERSION = "1.0"
LANGAGE = "sql"
DIALECTES = ("postgres", "oracle")

_KINDS_CONTRAINTE = {
    "P": "sql_live_pk", "PRIMARY KEY": "sql_live_pk", "PRIMARY_KEY": "sql_live_pk",
    "PRIMARY": "sql_live_pk",
    "R": "sql_live_fk", "FOREIGN KEY": "sql_live_fk", "FOREIGN_KEY": "sql_live_fk",
    "FOREIGN": "sql_live_fk",
    "U": "sql_live_unique", "UNIQUE": "sql_live_unique",
}
_SUFFIXES_CONTRAINTE = {
    "sql_live_pk": "PK",
    "sql_live_fk": "FK",
    "sql_live_unique": "UNIQUE",
}


def _texte(valeur) -> str:
    return str(valeur).strip() if valeur is not None else ""


def _entier(valeur) -> int:
    try:
        return int(str(valeur).strip())
    except (TypeError, ValueError):
        return 0


def _booleen(valeur, defaut=True) -> bool:
    if valeur is None:
        return defaut
    if isinstance(valeur, bool):
        return valeur
    return str(valeur).strip().upper() in {"YES", "Y", "TRUE", "1", "T"}


def _unique(valeur, defaut=False) -> bool:
    if valeur is None:
        return defaut
    if isinstance(valeur, bool):
        return valeur
    return str(valeur).strip().upper() in {"YES", "Y", "TRUE", "1", "T", "UNIQUE"}


def _ligne_normalisee(ligne) -> dict:
    if not isinstance(ligne, Mapping):
        return {}
    return {str(cle).strip().lower(): valeur for cle, valeur in ligne.items()}


def _valeur(ligne: dict, *noms):
    for nom in noms:
        valeur = ligne.get(nom.lower())
        if valeur is not None:
            return valeur
    return None


def _decouper_liste(texte: str) -> list[str]:
    morceaux: list[str] = []
    courant: list[str] = []
    profondeur = 0
    guillemet = ""
    for caractere in texte:
        if guillemet:
            courant.append(caractere)
            if caractere == guillemet:
                guillemet = ""
            continue
        if caractere in "'\"":
            guillemet = caractere
            courant.append(caractere)
        elif caractere == "(":
            profondeur += 1
            courant.append(caractere)
        elif caractere == ")":
            profondeur -= 1
            courant.append(caractere)
        elif caractere == "," and profondeur == 0:
            morceaux.append("".join(courant))
            courant = []
        else:
            courant.append(caractere)
    if courant:
        morceaux.append("".join(courant))
    return [morceau.strip().strip('"').strip("'") for morceau in morceaux if morceau.strip()]


def _colonnes_index(definition) -> list[str]:
    texte = _texte(definition)
    if not texte:
        return []
    trouve = re.search(r"\bON\b.*?\bUSING\b[^(]*\((.*)\)", texte, re.IGNORECASE | re.DOTALL)
    if trouve:
        contenu = trouve.group(1)
    else:
        debut, fin = texte.find("("), texte.rfind(")")
        if debut < 0 or fin <= debut:
            return []
        contenu = texte[debut + 1:fin]
    return _decouper_liste(contenu)


def _reference(schema_cible, table_cible) -> str:
    schema = _texte(schema_cible)
    table = _texte(table_cible)
    if not table:
        return ""
    return f"{schema}.{table}" if schema else table


class SqlLiveSidecar:
    """Indexe un catalogue SQL par des SELECT en lecture seule sur des paramètres liés."""

    provider = PROVIDER
    parser = PARSER
    parser_version = PARSER_VERSION
    language = LANGAGE

    def __init__(self, dialecte, executer, schema=None):
        normalise = _texte(dialecte).lower()
        if normalise not in DIALECTES:
            raise ValueError(f"dialecte SQL inconnu : {dialecte!r}")
        if not callable(executer):
            raise ValueError("executer doit être appelable")
        self.dialecte = normalise
        self.executer = executer
        self.schema = _texte(schema) or None

    def index(self, racine=None, fichiers=()) -> list[Observation]:
        """Rend les observations des tables, colonnes, contraintes, index, vues et procédures."""
        observations, _, _ = self._collecter()
        return observations

    def couverture(self, racine=None, fichiers=()) -> list[CouvertureFichier]:
        """Une ligne par table synthétique ; une panne donne `partiel` sans lever."""
        try:
            _, erreurs, tables = self._collecter()
        except Exception as erreur:
            tables = {}
            erreurs = [f"{type(erreur).__name__}: {erreur}"]
        partiel = bool(erreurs)
        raison = "analyse partielle : " + "; ".join(erreurs) if partiel else ""
        fichiers_tables = {self._fichier(schema, table) for schema, table in tables}
        lignes = [
            CouvertureFichier(
                file=fichier, language=LANGAGE, parser=PARSER,
                statut="partiel" if partiel else "indexe",
                raison=raison if partiel else "",
            )
            for fichier in sorted(fichiers_tables)
        ]
        if not lignes and partiel:
            lignes.append(CouvertureFichier(
                file=self._fichier("", "*"), language=LANGAGE, parser=PARSER,
                statut="partiel", raison=raison,
            ))
        return lignes

    def _fichier(self, schema, table) -> str:
        return f"db://{self.dialecte}/{_texte(schema) or 'default'}/{_texte(table)}"

    def _predicat(self, colonne: str) -> tuple[str, tuple]:
        if not self.schema:
            return "", ()
        marqueur = "%s" if self.dialecte == "postgres" else ":1"
        return f" AND {colonne} = {marqueur}", (self.schema,)

    def _lire(self, erreurs: list[str], sql: str, params=()) -> list[dict]:
        if not sql.lstrip().upper().startswith("SELECT"):
            raise ValueError("seule une instruction SELECT est autorisée")
        try:
            lignes = list(self.executer(sql, params=params) or ())
        except Exception as erreur:
            erreurs.append(f"{type(erreur).__name__}: {erreur}")
            return []
        resultat = []
        for ligne in lignes:
            normalisee = _ligne_normalisee(ligne)
            if normalisee:
                resultat.append(normalisee)
        return resultat

    def _collecter(self):
        erreurs: list[str] = []
        tables: dict[tuple[str, str], dict] = {}
        colonnes: dict[tuple[str, str, str], dict] = {}
        contraintes: dict[tuple[str, str, str, str], dict] = {}
        indexs: dict[tuple[str, str, str], dict] = {}
        procedures: dict[tuple[str, str], dict] = {}
        if self.dialecte == "postgres":
            self._catalogues_postgres(tables, colonnes, contraintes, indexs, erreurs)
        else:
            self._catalogues_oracle(tables, colonnes, contraintes, indexs, procedures, erreurs)
        self._appliquer_references(colonnes, contraintes)
        observations = self._observations(tables, colonnes, contraintes, indexs, procedures)
        return observations, erreurs, tables

    def _catalogues_postgres(self, tables, colonnes, contraintes, indexs, erreurs) -> None:
        predicat, params = self._predicat("table_schema")
        lignes = self._lire(erreurs, (
            "SELECT table_schema, table_name, table_type FROM information_schema.tables "
            "WHERE table_type IN ('BASE TABLE', 'VIEW') "
            "AND table_schema NOT IN ('pg_catalog', 'information_schema')"
            f"{predicat} ORDER BY table_schema, table_name"
        ), params)
        for ligne in lignes:
            schema = _texte(_valeur(ligne, "table_schema", "schema", "owner")) or self.schema or ""
            table = _texte(_valeur(ligne, "table_name", "table", "name"))
            if not table:
                continue
            genre = _texte(_valeur(ligne, "table_type", "type")).upper()
            kind = "sql_live_view" if "VIEW" in genre else "sql_live_table"
            self._declarer_table(tables, schema, table, kind)

        predicat, params = self._predicat("table_schema")
        lignes = self._lire(erreurs, (
            "SELECT table_schema, table_name, column_name, data_type, is_nullable, ordinal_position "
            "FROM information_schema.columns "
            "WHERE table_schema NOT IN ('pg_catalog', 'information_schema')"
            f"{predicat} ORDER BY table_schema, table_name, ordinal_position"
        ), params)
        for ligne in lignes:
            self._ajouter_colonne(ligne, colonnes, tables, None)

        predicat, params = self._predicat("tc.table_schema")
        lignes = self._lire(erreurs, (
            "SELECT tc.table_schema AS table_schema, tc.table_name AS table_name, "
            "tc.constraint_name AS constraint_name, tc.constraint_type AS constraint_type, "
            "kcu.column_name AS column_name, kcu.ordinal_position AS ordinal_position, "
            "rc.delete_rule AS on_delete, kref.table_schema AS ref_schema, "
            "kref.table_name AS ref_table, kref.column_name AS ref_column "
            "FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu "
            "ON kcu.constraint_schema = tc.constraint_schema "
            "AND kcu.constraint_name = tc.constraint_name "
            "AND kcu.table_schema = tc.table_schema AND kcu.table_name = tc.table_name "
            "LEFT JOIN information_schema.referential_constraints rc "
            "ON rc.constraint_schema = tc.constraint_schema "
            "AND rc.constraint_name = tc.constraint_name "
            "LEFT JOIN information_schema.key_column_usage kref "
            "ON kref.constraint_schema = rc.unique_constraint_schema "
            "AND kref.constraint_name = rc.unique_constraint_name "
            "AND kref.ordinal_position = kcu.ordinal_position "
            "WHERE tc.constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY', 'UNIQUE')"
            f"{predicat} ORDER BY tc.table_schema, tc.table_name, tc.constraint_name, "
            "kcu.ordinal_position"
        ), params)
        for ligne in lignes:
            self._ajouter_contrainte(ligne, contraintes, tables)

        predicat, params = self._predicat("schemaname")
        lignes = self._lire(erreurs, (
            "SELECT schemaname, tablename, indexname, indexdef FROM pg_indexes "
            "WHERE schemaname NOT IN ('pg_catalog', 'information_schema')"
            f"{predicat} ORDER BY schemaname, tablename, indexname"
        ), params)
        for ligne in lignes:
            schema = _texte(_valeur(ligne, "schemaname", "schema", "table_schema")) or self.schema or ""
            table = _texte(_valeur(ligne, "tablename", "table_name", "table"))
            nom = _texte(_valeur(ligne, "indexname", "index_name", "name"))
            if not table:
                continue
            definition = _valeur(ligne, "indexdef", "index_definition")
            liste = _valeur(ligne, "colonnes", "columns")
            if not isinstance(liste, (list, tuple)):
                liste = _colonnes_index(definition)
            unique = _unique(_valeur(ligne, "unique", "is_unique", "uniqueness"), False)
            if "UNIQUE" in _texte(definition).upper():
                unique = True
            cle = (schema, table, nom or f"{table}.INDEX({','.join(liste)})")
            indexs.setdefault(cle, {
                "schema": schema, "table": table, "nom": cle[2],
                "colonnes": [_texte(colonne) for colonne in liste if _texte(colonne)],
                "unique": unique,
            })
            self._declarer_table(tables, schema, table, "sql_live_table")

    def _catalogues_oracle(self, tables, colonnes, contraintes, indexs, procedures, erreurs) -> None:
        predicat, params = self._predicat("owner")
        lignes = self._lire(erreurs, (
            "SELECT owner, table_name FROM ALL_TABLES"
            f" WHERE 1 = 1{predicat} ORDER BY owner, table_name"
        ), params)
        for ligne in lignes:
            schema = _texte(_valeur(ligne, "owner", "table_schema", "schema")) or self.schema or ""
            table = _texte(_valeur(ligne, "table_name", "table", "name"))
            if table:
                self._declarer_table(tables, schema, table, "sql_live_table")

        predicat, params = self._predicat("owner")
        lignes = self._lire(erreurs, (
            "SELECT owner, table_name, column_name, data_type, nullable, column_id "
            f"FROM ALL_TAB_COLUMNS WHERE 1 = 1{predicat} "
            "ORDER BY owner, table_name, column_id"
        ), params)
        for ligne in lignes:
            self._ajouter_colonne(ligne, colonnes, tables, "column_id")

        predicat, params = self._predicat("c.owner")
        lignes = self._lire(erreurs, (
            "SELECT c.owner AS owner, c.table_name AS table_name, "
            "c.constraint_name AS constraint_name, c.constraint_type AS constraint_type, "
            "cc.column_name AS column_name, cc.position AS position, "
            "c.delete_rule AS on_delete, r.owner AS ref_schema, "
            "r.table_name AS ref_table "
            "FROM ALL_CONSTRAINTS c "
            "LEFT JOIN ALL_CONS_COLUMNS cc ON cc.owner = c.owner "
            "AND cc.constraint_name = c.constraint_name AND cc.table_name = c.table_name "
            "LEFT JOIN ALL_CONSTRAINTS r ON r.owner = c.r_owner "
            "AND r.constraint_name = c.r_constraint_name "
            "WHERE c.constraint_type IN ('P', 'R', 'U')"
            f"{predicat} ORDER BY c.owner, c.table_name, c.constraint_name, cc.position"
        ), params)
        for ligne in lignes:
            self._ajouter_contrainte(ligne, contraintes, tables)

        predicat, params = self._predicat("owner")
        lignes = self._lire(erreurs, (
            "SELECT owner, table_name, index_name, uniqueness FROM ALL_INDEXES"
            f" WHERE 1 = 1{predicat} ORDER BY owner, table_name, index_name"
        ), params)
        for ligne in lignes:
            schema = _texte(_valeur(ligne, "owner", "table_schema", "schema")) or self.schema or ""
            table = _texte(_valeur(ligne, "table_name", "tablename", "table"))
            nom = _texte(_valeur(ligne, "index_name", "indexname", "name"))
            if not table:
                continue
            liste = _valeur(ligne, "colonnes", "columns")
            if not isinstance(liste, (list, tuple)):
                liste = [_texte(_valeur(ligne, "column_name", "column"))]
            cle = (schema, table, nom or f"{table}.INDEX")
            indexs.setdefault(cle, {
                "schema": schema, "table": table, "nom": cle[2],
                "colonnes": [_texte(colonne) for colonne in liste if _texte(colonne)],
                "unique": _unique(_valeur(ligne, "uniqueness", "unique", "is_unique"), False),
            })
            self._declarer_table(tables, schema, table, "sql_live_table")

        predicat, params = self._predicat("owner")
        lignes = self._lire(erreurs, (
            "SELECT owner, view_name FROM ALL_VIEWS"
            f" WHERE 1 = 1{predicat} ORDER BY owner, view_name"
        ), params)
        for ligne in lignes:
            schema = _texte(_valeur(ligne, "owner", "table_schema", "schema")) or self.schema or ""
            vue = _texte(_valeur(ligne, "view_name", "table_name", "name"))
            if vue:
                self._declarer_table(tables, schema, vue, "sql_live_view")

        predicat, params = self._predicat("owner")
        lignes = self._lire(erreurs, (
            "SELECT owner, object_name, procedure_name, object_type FROM ALL_PROCEDURES"
            f" WHERE 1 = 1{predicat} ORDER BY owner, object_name, procedure_name"
        ), params)
        for ligne in lignes:
            schema = _texte(_valeur(ligne, "owner", "table_schema", "schema")) or self.schema or ""
            objet = _texte(_valeur(ligne, "object_name", "procedure_name", "name"))
            procedure = _texte(_valeur(ligne, "procedure_name"))
            if not objet:
                continue
            if procedure.upper() == objet.upper():
                procedure = ""
            symbole = self._symbole(schema, objet, procedure)
            procedures.setdefault((schema, symbole), {
                "schema": schema, "objet": objet, "procedure": procedure,
                "type": _texte(_valeur(ligne, "object_type", "type")),
            })

    def _declarer_table(self, tables, schema: str, table: str, kind: str) -> None:
        cle = (schema, table)
        modele = tables.setdefault(cle, {"kind": kind, "colonnes": {}})
        if kind == "sql_live_view" or "kind" not in modele:
            modele["kind"] = kind

    def _ajouter_colonne(self, ligne: dict, colonnes, tables, ordinal_nom) -> None:
        schema = _texte(_valeur(ligne, "table_schema", "schema", "owner")) or self.schema or ""
        table = _texte(_valeur(ligne, "table_name", "table"))
        colonne = _texte(_valeur(ligne, "column_name", "column", "colonne"))
        if not table or not colonne:
            return
        ordinal = _entier(_valeur(
            ligne, ordinal_nom or "ordinal_position", "ordinal_position", "column_id",
            "position", "ordinal",
        ))
        cle = (schema, table, colonne)
        colonnes.setdefault(cle, {
            "schema": schema, "table": table, "column": colonne,
            "type": _texte(_valeur(ligne, "data_type", "type", "column_type")),
            "nullable": _booleen(_valeur(ligne, "is_nullable", "nullable"), True),
            "ordinal": ordinal,
        })
        self._declarer_table(tables, schema, table, "sql_live_table")
        tables[(schema, table)]["colonnes"].setdefault(colonne, ordinal)

    def _ajouter_contrainte(self, ligne: dict, contraintes, tables) -> None:
        schema = _texte(_valeur(ligne, "table_schema", "schema", "owner")) or self.schema or ""
        table = _texte(_valeur(ligne, "table_name", "table"))
        nom = _texte(_valeur(ligne, "constraint_name", "constraint", "name"))
        genre = _texte(_valeur(ligne, "constraint_type", "type")).upper()
        kind = _KINDS_CONTRAINTE.get(genre)
        if not table or kind is None:
            return
        cle = (schema, table, nom, kind)
        modele = contraintes.setdefault(cle, {
            "schema": schema, "table": table, "nom": nom, "kind": kind,
            "colonnes": {}, "references": "", "on_delete": "",
        })
        liste = _valeur(ligne, "colonnes", "columns")
        if isinstance(liste, (list, tuple)):
            for position, colonne in enumerate(liste, 1):
                if _texte(colonne):
                    modele["colonnes"].setdefault(position, _texte(colonne))
        else:
            colonne = _texte(_valeur(ligne, "column_name", "column", "colonne"))
            position = _entier(_valeur(
                ligne, "ordinal_position", "position", "ordinal", "column_id"))
            if colonne:
                modele["colonnes"].setdefault(position, colonne)
        reference = _valeur(ligne, "references", "referenced_table")
        if reference is not None:
            modele["references"] = _texte(reference)
        else:
            cible = _reference(
                _valeur(ligne, "ref_schema", "referenced_table_schema", "references_schema",
                        "r_owner", "target_schema"),
                _valeur(ligne, "ref_table", "referenced_table_name", "references_table",
                        "r_table_name", "target_table"),
            )
            if cible:
                modele["references"] = cible
        action = _valeur(ligne, "on_delete", "delete_rule")
        if action is not None:
            modele["on_delete"] = _texte(action)
        self._declarer_table(tables, schema, table, "sql_live_table")

    @staticmethod
    def _appliquer_references(colonnes, contraintes) -> None:
        for modele in contraintes.values():
            if modele["kind"] != "sql_live_fk":
                continue
            for colonne in modele["colonnes"].values():
                cle = (modele["schema"], modele["table"], colonne)
                if cle in colonnes:
                    if modele["references"]:
                        colonnes[cle]["references"] = modele["references"]
                    if modele["on_delete"]:
                        colonnes[cle]["on_delete"] = modele["on_delete"]

    @staticmethod
    def _symbole(schema: str, table: str, colonne: str = "") -> str:
        parties = [partie for partie in (schema, table, colonne) if partie]
        return ".".join(parties)

    def _observation(self, kind: str, symbole: str, schema: str, table: str,
                     attributs: dict) -> Observation:
        return Observation(
            provider=PROVIDER, parser=PARSER, parser_version=PARSER_VERSION,
            file=self._fichier(schema, table), language=LANGAGE, kind=kind,
            symbol=symbole, start=0, end=0, attributes=attributs,
        )

    def _observations(self, tables, colonnes, contraintes, indexs, procedures) -> list[Observation]:
        observations: list[Observation] = []
        for (schema, table), modele in sorted(tables.items()):
            noms = [
                nom for nom, _ in sorted(
                    modele["colonnes"].items(), key=lambda element: (element[1], element[0]))
            ]
            observations.append(self._observation(
                modele["kind"], self._symbole(schema, table), schema, table,
                {"schema": schema, "table": table, "colonnes": noms},
            ))
        for (schema, table, colonne), modele in sorted(
                colonnes.items(), key=lambda element: (
                    element[0][0], element[0][1], element[1]["ordinal"], element[0][2])):
            attributs = {
                "schema": schema, "table": table, "column": colonne,
                "type": modele["type"], "nullable": modele["nullable"],
                "ordinal": modele["ordinal"],
            }
            if modele.get("references"):
                attributs["references"] = modele["references"]
            if modele.get("on_delete"):
                attributs["on_delete"] = modele["on_delete"]
            observations.append(self._observation(
                "sql_live_column", self._symbole(schema, table, colonne), schema, table, attributs,
            ))
        for (schema, table, nom, kind), modele in sorted(contraintes.items()):
            colonnes_liste = [colonne for _, colonne in sorted(modele["colonnes"].items())]
            symbole = nom or (
                f"{self._symbole(schema, table)}."
                f"{_SUFFIXES_CONTRAINTE.get(kind, 'CONTRAINTE')}({','.join(colonnes_liste)})"
            )
            attributs = {"schema": schema, "table": table, "colonnes": colonnes_liste}
            if modele["references"]:
                attributs["references"] = modele["references"]
            if modele["on_delete"]:
                attributs["on_delete"] = modele["on_delete"]
            observations.append(self._observation(
                kind, symbole, schema, table, attributs,
            ))
        for (schema, table, _), modele in sorted(indexs.items()):
            observations.append(self._observation(
                "sql_live_index", modele["nom"], schema, table,
                {"schema": schema, "table": table, "colonnes": list(modele["colonnes"]),
                 "unique": modele["unique"]},
            ))
        for (schema, _), modele in sorted(procedures.items()):
            attributs = {"schema": schema, "table": modele["objet"]}
            if modele["procedure"]:
                attributs["procedure"] = modele["procedure"]
            if modele["type"]:
                attributs["type"] = modele["type"]
            observations.append(self._observation(
                "sql_live_procedure", self._symbole(
                    schema, modele["objet"], modele["procedure"]),
                schema, modele["objet"], attributs,
            ))
        uniques: dict[tuple, Observation] = {}
        for observation in observations:
            uniques.setdefault(observation.fingerprint, observation)
        return sorted(uniques.values(), key=lambda o: (o.file, o.start, o.kind, o.symbol))
