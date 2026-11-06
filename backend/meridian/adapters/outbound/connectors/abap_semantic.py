"""Sidecar ABAP sémantique : AST réel via abaplint, sans parsing regex."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Mapping

from meridian.domain.code_index import CouvertureFichier, Observation

__all__ = ["AbapSemanticSidecar", "ANALYZE_JS"]

PROVIDER = "abap-semantic"
PARSER = "abaplint"
VERSION = "2.120.92"
LANGAGE = "abap"
SUFFIXES = frozenset({".abap", ".abapinclude"})
PARSER_VERSION = VERSION
EXTENSIONS = tuple(sorted(SUFFIXES))

ANALYZE_JS = Path(__file__).resolve().parents[5] / "tools" / "abaplint" / "analyze.js"

_KINDS = {
    "Report": "abap_program",
    "Program": "abap_program",
    "ClassDefinition": "abap_class",
    "ClassImplementation": "abap_class",
    "MethodDef": "abap_method",
    "MethodImplementation": "abap_method",
    "Form": "abap_form",
    "FunctionModule": "abap_function_module",
    "CallFunction": "abap_call",
    "CallMethod": "abap_call",
    "Call": "abap_call",
    "Perform": "abap_call",
    "Select": "abap_sql",
    "Insert": "abap_sql",
    "InsertDatabase": "abap_sql",
    "Update": "abap_sql",
    "UpdateDatabase": "abap_sql",
    "Delete": "abap_sql",
    "DeleteDatabase": "abap_sql",
    "Modify": "abap_sql",
    "ModifyDatabase": "abap_sql",
    "Types": "abap_type",
    "Type": "abap_type",
    "Data": "abap_data",
    "Parameters": "abap_parameter",
    "Parameter": "abap_parameter",
    "Include": "abap_include",
}

_SQL_SYMBOLS = {
    "Select": "SELECT",
    "Insert": "INSERT",
    "InsertDatabase": "INSERT",
    "Update": "UPDATE",
    "UpdateDatabase": "UPDATE",
    "Delete": "DELETE",
    "DeleteDatabase": "DELETE",
    "Modify": "MODIFY",
    "ModifyDatabase": "MODIFY",
}

_STATUTS_EXACTS = {
    "ok": "indexe",
    "indexe": "indexe",
    "complete": "indexe",
    "complet": "indexe",
    "partial": "partiel",
    "partiel": "partiel",
    "unsupported": "non_supporte",
    "non_supporte": "non_supporte",
    "ignore": "ignore",
    "ignoree": "ignore",
}


def _texte(valeur, maximum=1000) -> str:
    return " ".join(str(valeur or "").split())[:maximum]


def _entier(valeur) -> int:
    try:
        return max(0, int(valeur or 0))
    except (TypeError, ValueError):
        return 0


def _cle_fichier(racine: Path, chemin: Path) -> str:
    """Chemin stable : relatif à la racine quand il y est, absolu sinon."""
    try:
        return chemin.resolve().relative_to(racine.resolve()).as_posix()
    except (OSError, ValueError, RuntimeError):
        try:
            return chemin.resolve().as_posix()
        except (OSError, RuntimeError):
            return str(chemin)


class AbapSemanticSidecar:
    """Indexe l'ABAP depuis l'AST abaplint ; le runner Node est injectable."""

    provider = PROVIDER
    extensions = EXTENSIONS
    parser = PARSER
    parser_version = PARSER_VERSION
    language = LANGAGE

    @classmethod
    def disponible(cls) -> bool:
        """Vrai si Node, le script et le paquet abaplint sont présents."""
        try:
            return (ANALYZE_JS.is_file()
                    and shutil.which("node") is not None
                    and (ANALYZE_JS.parent / "node_modules" / "@abaplint" / "core").is_dir())
        except OSError:
            return False

    def __init__(
        self,
        provider: str = PROVIDER,
        *,
        runner: Callable[[str], Mapping] | None = None,
        analyze_js: str | Path | None = None,
        node: str | None = None,
        timeout: float = 60.0,
    ):
        self.provider = _texte(provider, 40) or PROVIDER
        self.extensions = EXTENSIONS
        self.parser = PARSER
        self.parser_version = VERSION
        self.language = LANGAGE
        self.analyze_js = Path(
            analyze_js or os.environ.get("MERIDIAN_ABAPLINT_ANALYZE") or ANALYZE_JS)
        self.node = str(node or os.environ.get("MERIDIAN_NODE") or "node")
        self.timeout = float(timeout)
        self.runner = runner or self._lancer_node

    def index(self, racine: str, fichiers=()) -> list[Observation]:
        observations = []
        for fichier, resultat in self._analyses(racine, fichiers):
            if self._statut(resultat) not in ("indexe", "partiel"):
                continue
            observations.extend(self._observations(fichier, resultat))
        return observations

    def couverture(self, racine: str, fichiers=()) -> list[CouvertureFichier]:
        lignes = {}
        for fichier, resultat in self._analyses(racine, fichiers):
            supporte = Path(fichier).suffix.lower() in SUFFIXES
            lignes[fichier] = CouvertureFichier(
                file=fichier,
                language=LANGAGE if supporte else "",
                parser=PARSER,
                statut=self._statut(resultat),
                raison=self._raison(resultat),
            )
        return [lignes[cle] for cle in sorted(lignes)]

    def _analyses(self, racine: str, fichiers=()):
        base = Path(racine)
        vus = set()
        for chemin in self._candidats(base, fichiers):
            fichier = _cle_fichier(base, chemin)
            if fichier in vus:
                continue
            vus.add(fichier)
            suffixe = chemin.suffix.lower()
            if suffixe not in SUFFIXES:
                yield fichier, {
                    "file": fichier, "status": "unsupported",
                    "errors": [{"message": "extension non prise en charge"}],
                }
                continue
            if not chemin.is_file():
                yield fichier, {
                    "file": fichier, "status": "ignore",
                    "errors": [{"message": "fichier introuvable ou illisible"}],
                }
                continue
            try:
                resultat = self.runner(str(chemin))
            except Exception as erreur:
                yield fichier, {
                    "file": fichier, "status": "error",
                    "errors": [{"message": f"runner sémantique indisponible : {erreur}"}],
                }
                continue
            if not isinstance(resultat, Mapping):
                yield fichier, {
                    "file": fichier, "status": "error",
                    "errors": [{"message": "sortie du runner non interprétable"}],
                }
                continue
            yield fichier, resultat

    @staticmethod
    def _candidats(racine: Path, fichiers):
        if fichiers:
            for nom in fichiers:
                chemin = Path(nom)
                yield chemin if chemin.is_absolute() else racine / chemin
            return
        try:
            for chemin in sorted(racine.rglob("*")):
                if chemin.is_file() and chemin.suffix.lower() in SUFFIXES:
                    yield chemin
        except OSError:
            return

    def _observations(self, fichier: str, resultat: Mapping) -> list[Observation]:
        statements = resultat.get("statements")
        if not isinstance(statements, list):
            return []
        version = _texte(resultat.get("parser_version") or VERSION, 40)
        observations = []
        for statement in statements:
            if not isinstance(statement, Mapping):
                continue
            ast_type = _texte(statement.get("type"), 80)
            kind = _KINDS.get(ast_type)
            if not kind:
                continue
            tokens = statement.get("tokens")
            if not isinstance(tokens, list):
                tokens = []
            tokens = [str(jeton) for jeton in tokens]
            attributs = {"type": ast_type, "tokens": tokens}
            for nom, cle in (("owner", "owner"), ("target", "target"), ("table", "table")):
                valeur = _texte(statement.get(nom), 500)
                if valeur:
                    attributs[cle] = valeur
            ligne = _entier(statement.get("line"))
            fin = _entier(statement.get("end_line")) or ligne
            symbole = _texte(statement.get("symbol"), 500) or self._symbole(
                ast_type, tokens)
            observations.append(Observation(
                provider=self.provider, parser=PARSER, parser_version=version,
                file=fichier, language=LANGAGE, kind=kind, symbol=symbole,
                start=ligne, end=fin, attributes=attributs))
        return observations

    @staticmethod
    def _symbole(ast_type: str, tokens) -> str:
        if ast_type in _SQL_SYMBOLS:
            return _SQL_SYMBOLS[ast_type]
        if not tokens:
            return ""
        if ast_type == "Data" and len(tokens) > 2 and tokens[1] == "(":
            return tokens[2]
        return tokens[1] if len(tokens) > 1 else ""

    @staticmethod
    def _statut(resultat: Mapping) -> str:
        statut = _texte(resultat.get("status"), 40).lower()
        resolu = _STATUTS_EXACTS.get(statut, "ignore")
        if resolu == "indexe" and resultat.get("errors"):
            return "partiel"
        return resolu

    @staticmethod
    def _raison(resultat: Mapping) -> str:
        messages = []
        erreurs = resultat.get("errors")
        if isinstance(erreurs, list):
            for erreur in erreurs:
                if isinstance(erreur, Mapping):
                    message = erreur.get("message") or erreur.get("key") or ""
                else:
                    message = erreur
                message = _texte(message, 500)
                if message and message not in messages:
                    messages.append(message)
        if not messages:
            message = _texte(resultat.get("error"), 500)
            if message:
                messages.append(message)
        return " ; ".join(messages)[:500]

    def _lancer_node(self, chemin: str) -> dict:
        commande = [self.node, str(self.analyze_js), str(chemin)]
        try:
            termine = subprocess.run(
                commande, capture_output=True, encoding="utf-8", errors="replace",
                timeout=self.timeout, check=False)
        except (OSError, subprocess.SubprocessError) as erreur:
            return {
                "file": chemin, "status": "error",
                "errors": [{"message": f"runner Node indisponible : {erreur}"}],
            }
        if termine.returncode != 0:
            detail = (termine.stderr or termine.stdout or "").strip()
            return {
                "file": chemin, "status": "error",
                "errors": [{"message": (
                    f"abaplint a échoué ({termine.returncode}) : {detail}")[:500]}],
            }
        try:
            resultat = json.loads(termine.stdout)
        except (TypeError, ValueError) as erreur:
            return {
                "file": chemin, "status": "error",
                "errors": [{"message": f"JSON abaplint invalide : {erreur}"}],
            }
        if not isinstance(resultat, dict):
            return {
                "file": chemin, "status": "error",
                "errors": [{"message": "sortie abaplint inattendue"}],
            }
        return resultat
