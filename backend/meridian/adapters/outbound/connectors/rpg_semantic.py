"""Sidecar RPGLE sémantique : parseur ANTLR rpgleparser exécuté hors processus.

Le runner par défaut lance ``tools/rpgle/Analyze`` (Java) sur chaque source et
lit un JSON contenant le parse tree simplifié et les symboles extraits. Un
runner injectable permet de tester le mapping sans JVM.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from meridian.domain.code_index import CouvertureFichier, Observation

__all__ = ["RpgSemanticSidecar"]

PROVIDER = "rpg-semantic"
PARSER = "rpgleparser-antlr"
VERSION = "1.0.0"
LANGAGE = "rpg"
SUFFIXES = frozenset({".rpg", ".rpgle", ".sqlrpgle"})
PARSER_VERSION = VERSION
EXTENSIONS = tuple(sorted(SUFFIXES))

_RACINE = Path(__file__).resolve().parents[5]
_OUTILS = _RACINE / "tools" / "rpgle"
_CLASSES = _OUTILS / "classes"
_LIB = _OUTILS / "lib"

_RULES = {
    "fspec": "rpg_file",
    "fspec_fixed": "rpg_file",
    "dcl_pr": "rpg_proc",
    "freeBeginProcedure": "rpg_proc",
    "psBegin": "rpg_proc",
    "dspec": "rpg_var",
    "dspec_fixed": "rpg_var",
    "dcl_ds": "rpg_data_structure",
    "dcl_ds_field": "rpg_var",
    "op_callp": "rpg_call",
    "op_exsr": "rpg_call",
    "csCALLP": "rpg_call",
    "csEXSR": "rpg_call",
    "csCALL": "rpg_call",
    "cspec_fixed_x2": "rpg_call",
    "exec_sql": "rpg_sql",
    "cspec_fixed_sql": "rpg_sql",
    "op_chain": "rpg_operation",
    "op_read": "rpg_operation",
    "op_readc": "rpg_operation",
    "op_reade": "rpg_operation",
    "op_readp": "rpg_operation",
    "op_readpe": "rpg_operation",
    "op_write": "rpg_operation",
    "op_update": "rpg_operation",
    "op_delete": "rpg_operation",
    "op_select": "rpg_operation",
    "csCHAIN": "rpg_operation",
    "csREAD": "rpg_operation",
    "csREADC": "rpg_operation",
    "csREADE": "rpg_operation",
    "csREADP": "rpg_operation",
    "csREADPE": "rpg_operation",
    "csWRITE": "rpg_operation",
    "csUPDATE": "rpg_operation",
    "csDELETE": "rpg_operation",
    "csSELECT": "rpg_operation",
}

_MAX_JETONS = 100
_MAX_TEXTE = 300


def _texte(valeur, maximum=_MAX_TEXTE) -> str:
    return " ".join(str(valeur or "").split())[:maximum]


def _java() -> str:
    return os.environ.get("JAVA", "java")


def _classpath() -> str:
    elements = [str(_CLASSES)]
    try:
        elements.extend(str(chemin) for chemin in sorted(_LIB.glob("*.jar")))
    except OSError:
        pass
    return os.pathsep.join(elements)


def _cle_fichier(racine: Path, chemin: Path) -> str:
    try:
        return chemin.resolve().relative_to(racine.resolve()).as_posix()
    except (OSError, ValueError, RuntimeError):
        try:
            return chemin.resolve().as_posix()
        except (OSError, RuntimeError):
            return str(chemin)


def _resultat_erreur(message: str) -> dict:
    return {"statut": "erreur", "symboles": [], "erreurs": [{"message": message}]}


class RpgSemanticSidecar:
    """Observations RPGLE issues d'un parse tree ANTLR, jamais d'exception de parse."""

    provider = PROVIDER
    extensions = EXTENSIONS
    parser = PARSER
    parser_version = PARSER_VERSION
    language = LANGAGE

    def __init__(
        self, runner=None, *, provider=None, java=None, classpath=None, timeout=60.0
    ):
        if runner is not None and not callable(runner):
            raise TypeError("le runner RPG sémantique doit être appelable")
        if provider:
            self.provider = str(provider)
        self._java = java or _java()
        self._classpath = classpath or _classpath()
        self._timeout = max(1.0, float(timeout))
        self._runner = runner or self._runner_java

    @classmethod
    def disponible(cls) -> bool:
        """Vrai si les jars, les classes compilées et java sont présents."""
        try:
            return (
                (_CLASSES / "Analyze.class").is_file()
                and any(_LIB.glob("*.jar"))
                and shutil.which(_java()) is not None
            )
        except OSError:
            return False

    @classmethod
    def available(cls) -> bool:
        """Alias anglais de :meth:`disponible`."""
        return cls.disponible()

    def index(self, racine: str, fichiers=()) -> list[Observation]:
        observations: list[Observation] = []
        for chemin in self._candidats(racine, fichiers):
            if chemin.suffix.lower() not in SUFFIXES or not chemin.is_file():
                continue
            try:
                fichier = _cle_fichier(Path(racine), chemin)
                resultat = self._analyser(chemin)
                for symbole in resultat.get("symboles") or ():
                    observation = self._observation(fichier, symbole)
                    if observation is not None:
                        observations.append(observation)
            except Exception:
                continue
        return observations

    def couverture(self, racine: str, fichiers=()) -> list[CouvertureFichier]:
        lignes: dict[str, CouvertureFichier] = {}
        for chemin in self._candidats(racine, fichiers):
            cle = _cle_fichier(Path(racine), chemin)
            if cle in lignes:
                continue
            if chemin.suffix.lower() not in SUFFIXES:
                lignes[cle] = CouvertureFichier(
                    file=cle,
                    parser=self.parser,
                    statut="non_supporte",
                    raison="extension non prise en charge",
                )
                continue
            if not chemin.is_file():
                lignes[cle] = CouvertureFichier(
                    file=cle,
                    language=self.language,
                    parser=self.parser,
                    statut="ignore",
                    raison="fichier introuvable ou illisible",
                )
                continue
            resultat = self._analyser(chemin)
            statut = str(resultat.get("statut") or "erreur")
            symboles = resultat.get("symboles") or ()
            if statut == "ok" and symboles:
                lignes[cle] = CouvertureFichier(
                    file=cle,
                    language=self.language,
                    parser=self.parser,
                    statut="indexe",
                )
            elif statut == "ok":
                lignes[cle] = CouvertureFichier(
                    file=cle,
                    language=self.language,
                    parser=self.parser,
                    statut="partiel",
                    raison="aucune structure RPG reconnue",
                )
            elif statut == "erreur":
                lignes[cle] = CouvertureFichier(
                    file=cle,
                    language=self.language,
                    parser=self.parser,
                    statut="partiel",
                    raison=self._raison(resultat) or "analyse RPGLE impossible",
                )
            else:
                lignes[cle] = CouvertureFichier(
                    file=cle,
                    language=self.language,
                    parser=self.parser,
                    statut="partiel",
                    raison=self._raison(resultat) or "parse RPGLE partiel",
                )
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

    def _runner_java(self, chemin: Path) -> dict:
        commande = [
            self._java,
            "-Xss8m",
            "-cp",
            self._classpath,
            "Analyze",
            str(chemin),
        ]
        try:
            processus = subprocess.run(
                commande,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self._timeout,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as erreur:
            return _resultat_erreur(f"{type(erreur).__name__}: {erreur}")
        sortie = (processus.stdout or "").strip()
        if sortie:
            try:
                resultat = json.loads(sortie)
            except (ValueError, TypeError):
                resultat = None
            if isinstance(resultat, dict):
                return resultat
        detail = (processus.stderr or processus.stdout or "").strip()
        return _resultat_erreur(
            detail[:500] or f"Analyze.java a échoué (code {processus.returncode})"
        )

    def _analyser(self, chemin: Path) -> dict:
        try:
            resultat = self._runner(chemin)
        except Exception as erreur:
            return _resultat_erreur(f"{type(erreur).__name__}: {erreur}")
        if isinstance(resultat, (bytes, bytearray)):
            resultat = resultat.decode("utf-8", errors="replace")
        if isinstance(resultat, str):
            try:
                resultat = json.loads(resultat)
            except (ValueError, TypeError) as erreur:
                return _resultat_erreur(f"JSON invalide : {erreur}")
        if not isinstance(resultat, dict):
            return _resultat_erreur("sortie d'analyse non exploitable")
        return resultat

    def _observation(self, fichier: str, symbole) -> Observation | None:
        if not isinstance(symbole, dict):
            return None
        regle = _texte(symbole.get("regle"), 80)
        kind = _RULES.get(regle)
        if kind is None:
            return None
        cible = _texte(symbole.get("cible"), 500)
        operation = _texte(symbole.get("operation"), 40).upper()
        table = _texte(symbole.get("table"), 500)
        proc = _texte(symbole.get("proc"), 500)
        jetons = self._jetons(symbole.get("tokens"))
        attributs = {"rule": regle, "tokens": jetons, "cible": cible}
        if kind == "rpg_sql":
            symbol = operation or table or cible
            if operation:
                attributs["operation"] = operation
            if table:
                attributs["table"] = table
            if proc:
                attributs["proc"] = proc
        elif kind == "rpg_operation":
            symbol = operation or cible
            if operation:
                attributs["operation"] = operation
            if cible:
                attributs["file"] = cible
            if proc:
                attributs["proc"] = proc
        elif kind == "rpg_call":
            symbol = cible
            attributs["target"] = cible
            if proc:
                attributs["proc"] = proc
        elif kind == "rpg_proc":
            symbol = cible or proc
            if symbol:
                attributs["proc"] = symbol
        elif kind == "rpg_file":
            symbol = cible
            attributs["file"] = cible
        else:
            symbol = cible
            if proc:
                attributs["proc"] = proc
        if not symbol:
            return None
        debut = self._entier(symbole.get("debut"))
        fin = max(debut, self._entier(symbole.get("fin")))
        return Observation(
            provider=self.provider,
            parser=self.parser,
            parser_version=self.parser_version,
            file=fichier,
            language=self.language,
            kind=kind,
            symbol=symbol,
            start=debut,
            end=fin,
            attributes=attributs,
        )

    @staticmethod
    def _jetons(valeur) -> list[str]:
        if not isinstance(valeur, (list, tuple)):
            return []
        resultat = []
        for jeton in valeur[:_MAX_JETONS]:
            texte = _texte(jeton, _MAX_TEXTE)
            if texte:
                resultat.append(texte)
        return resultat

    @staticmethod
    def _entier(valeur) -> int:
        try:
            return max(0, int(valeur or 0))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _raison(resultat: dict) -> str:
        erreurs = resultat.get("erreurs") or ()
        if isinstance(erreurs, (list, tuple)) and erreurs:
            premiere = erreurs[0]
            if isinstance(premiere, dict):
                return _texte(premiere.get("message"), 500)
            return _texte(premiere, 500)
        return ""
