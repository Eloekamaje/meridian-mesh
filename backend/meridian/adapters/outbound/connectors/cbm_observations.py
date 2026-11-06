"""Provider CBM : traduit le graphe codebase-memory-mcp en observations fédérées."""
from __future__ import annotations

import json
import logging
import os
from collections.abc import Sequence
from pathlib import Path

from meridian.adapters.outbound.connectors import cbm
from meridian.domain.code_index import CouvertureFichier, Observation

__all__ = ["CbmObservations"]

PROVIDER = "cbm"
PARSER = "cbm-graph"
PARSER_VERSION = "1"
LIMITE = 100000
PAGE = 200
MAX_PAGES = 1000

journal = logging.getLogger(__name__)

LABELS = {
    "File": "cbm_file",
    "Module": "cbm_module",
    "Class": "cbm_class",
    "Function": "cbm_function",
    "Method": "cbm_method",
    "Variable": "cbm_variable",
    "Section": "cbm_section",
    "Table": "cbm_table",
    "Route": "cbm_route",
    "EnvVar": "cbm_env",
    "Package": "cbm_package",
    "Decorator": "cbm_decorator",
    "Process": "cbm_process",
    "Image": "cbm_image",
    "Resource": "cbm_resource",
}

RELATIONS = (
    "CALLS",
    "USAGE",
    "IMPORTS",
    "HTTP_CALLS",
    "WRITES",
    "TESTS",
    "DECORATES",
    "HANDLES",
    "REFERENCES_FILE",
    "DATA_FLOWS",
    "CONFIGURES",
    "DEPENDS_ON",
)

LANGAGES = {
    ".java": "java",
    ".jsp": "jsp",
    ".jspf": "jsp",
    ".tag": "jsp",
    ".cbl": "cobol",
    ".cob": "cobol",
    ".cobol": "cobol",
    ".cpy": "cobol",
    ".sql": "sql",
    ".ddl": "sql",
    ".pks": "sql",
    ".pkb": "sql",
    ".pls": "sql",
    ".prc": "sql",
    ".xml": "xml",
    ".xsd": "xml",
    ".xsl": "xml",
    ".xslt": "xml",
    ".wsdl": "xml",
    ".py": "python",
    ".pyi": "python",
    ".pyw": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".fs": "fsharp",
    ".vb": "vb",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".scala": "scala",
    ".rs": "rust",
    ".swift": "swift",
    ".dart": "dart",
    ".lua": "lua",
    ".pl": "perl",
    ".pm": "perl",
    ".r": "r",
    ".ex": "elixir",
    ".exs": "elixir",
    ".erl": "erlang",
    ".hrl": "erlang",
    ".clj": "clojure",
    ".hs": "haskell",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".ps1": "powershell",
    ".bat": "batch",
    ".cmd": "batch",
    ".env": "dotenv",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".json": "json",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "ini",
    ".conf": "config",
    ".properties": "properties",
    ".gradle": "groovy",
    ".groovy": "groovy",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".sass": "sass",
    ".less": "less",
    ".md": "markdown",
    ".rst": "restructuredtext",
    ".vue": "vue",
    ".svelte": "svelte",
    ".tf": "terraform",
    ".proto": "protobuf",
    ".graphql": "graphql",
    ".gql": "graphql",
    ".jcl": "jcl",
    ".asm": "assembly",
    ".s": "assembly",
}

LANGAGES_NOMS = {
    "dockerfile": "dockerfile",
    "makefile": "make",
    "jenkinsfile": "groovy",
    "gemfile": "ruby",
    "rakefile": "ruby",
}


def _liste_cypher(fichiers) -> str:
    return "[" + ", ".join(json.dumps(str(fichier)) for fichier in fichiers) + "]"


def _requete_noeuds(label: str, fichiers=(), skip: int = 0) -> str:
    filtre = f" WHERE n.file_path IN {_liste_cypher(fichiers)}" if fichiers else ""
    return (
        f"MATCH (n:{label}){filtre} "
        "RETURN n.name AS name, n.qualified_name AS qualified_name, "
        "n.file_path AS file_path, n.start_line AS start_line, "
        "n.end_line AS end_line, n.label AS label, "
        "n.method AS method, n.route AS route, n.path AS path, "
        "n.value AS value, n.url AS url, n.operation AS operation "
        f"ORDER BY n.file_path, n.start_line, n.name SKIP {int(skip)} LIMIT {LIMITE}"
    )


def _requete_relation(type_relation: str, fichiers=(), skip: int = 0) -> str:
    filtre = ""
    if fichiers:
        liste = _liste_cypher(fichiers)
        filtre = f" WHERE source.file_path IN {liste} OR target.file_path IN {liste}"
    return (
        f"MATCH (source)-[:{type_relation}]->(target){filtre} "
        "RETURN source.qualified_name AS source_qualified_name, source.name AS source_name, "
        "target.qualified_name AS target_qualified_name, target.name AS target_name, "
        "source.file_path AS source_file, target.file_path AS target_file, "
        "source.method AS source_method, source.route AS source_route, "
        "target.method AS target_method, target.route AS target_route, "
        "target.path AS target_path "
        f"ORDER BY source.file_path, source.qualified_name, target.file_path, "
        f"target.qualified_name SKIP {int(skip)} LIMIT {LIMITE}"
    )


def _pages(requete, runner, fichiers):
    """Pagine par 200 : CBM borne les résultats, le LIMIT seul en perdait les trois quarts."""
    skip = 0
    for _ in range(MAX_PAGES):
        lignes = list(runner(requete(fichiers=fichiers, skip=skip)) or ())
        yield from lignes
        if len(lignes) < PAGE:
            return
        skip += PAGE


def _runner_cbm(projet: str):
    def runner(requete: str) -> list[dict]:
        reponse = cbm._cli(
            "query_graph", "--project", projet, "--query", requete, "--format", "json"
        )
        if not isinstance(reponse, dict):
            return []
        colonnes = reponse.get("columns") or []
        lignes = reponse.get("rows") or []
        resultat = []
        for ligne in lignes:
            if isinstance(ligne, dict):
                resultat.append(dict(ligne))
            elif isinstance(ligne, (list, tuple)):
                resultat.append(dict(zip(colonnes, ligne)))
        return resultat

    return runner


def _fichiers_demandes(valeur) -> tuple:
    if valeur is None:
        return ()
    if isinstance(valeur, (str, os.PathLike)):
        return (valeur,)
    return tuple(valeur)


def _normaliser(racine: str, chemin) -> str:
    valeur = str(chemin or "").strip()
    if not valeur:
        return ""
    chemin = Path(valeur)
    if chemin.is_absolute():
        try:
            return chemin.resolve().relative_to(Path(racine).resolve()).as_posix()
        except (OSError, ValueError):
            return chemin.as_posix()
    return Path(os.path.normpath(valeur)).as_posix()


def _langage(fichier: str) -> str:
    if not fichier:
        return ""
    nom = Path(fichier).name.lower()
    if nom in LANGAGES_NOMS:
        return LANGAGES_NOMS[nom]
    return LANGAGES.get(Path(fichier).suffix.lower(), "")


def _premier(row: dict, *cles):
    for cle in cles:
        valeur = row.get(cle)
        if valeur is not None and str(valeur).strip():
            return valeur
    return ""


def _entier(valeur) -> int:
    try:
        return int(valeur)
    except (TypeError, ValueError):
        return 0


def _cibles(racine: str, fichiers) -> list[str]:
    return sorted({
        _normaliser(racine, fichier)
        for fichier in _fichiers_demandes(fichiers)
        if str(fichier).strip()
    })


def _observation_noeud(row: dict, label: str, racine: str, filtre) -> Observation | None:
    label_ligne = str(row.get("label") or "").strip()
    label_effectif = label_ligne if label_ligne in LABELS else label
    kind = LABELS.get(label_effectif)
    if kind is None:
        return None
    chemin_brut = _premier(row, "file_path", "file", "path")
    if not chemin_brut and label_effectif == "File":
        chemin_brut = _premier(row, "name", "qualified_name")
    chemin = _normaliser(racine, chemin_brut)
    if filtre is not None and chemin not in filtre:
        return None
    nom = str(_premier(row, "name"))
    qualifie = str(_premier(row, "qualified_name"))
    symbole = qualifie or nom or chemin
    if not symbole:
        return None
    attributs = {"label": label_effectif}
    if nom:
        attributs["name"] = nom
    if qualifie:
        attributs["qualified_name"] = qualifie
    for cle in ("method", "route", "path", "value", "url", "operation"):
        valeur = _premier(row, cle)
        if valeur:
            attributs[cle] = str(valeur)
    return Observation(
        provider=PROVIDER, parser=PARSER, parser_version=PARSER_VERSION,
        file=chemin, language=_langage(chemin), kind=kind, symbol=symbole,
        start=_entier(row.get("start_line")), end=_entier(row.get("end_line")),
        attributes=attributs, confidence=1.0, status="extracted",
    )


def _observation_relation(row: dict, type_attendu: str, racine: str, filtre) -> Observation | None:
    type_relation = str(_premier(row, "type", "relation") or type_attendu).upper()
    source = str(_premier(row, "source_qualified_name", "source", "source_name", "from", "from_name"))
    target = str(_premier(row, "target_qualified_name", "target", "target_name", "to", "to_name"))
    source_file = _normaliser(racine, _premier(row, "source_file", "source_path", "file", "path"))
    target_file = _normaliser(racine, _premier(row, "target_file", "target_path"))
    if filtre is not None:
        if source_file in filtre:
            fichier = source_file
        elif target_file in filtre:
            fichier = target_file
        else:
            return None
    else:
        fichier = source_file or target_file
    if not source and not target and not fichier:
        return None
    attributs = {
        "type": type_relation,
        "source": source,
        "target": target,
        "source_file": source_file,
        "target_file": target_file,
    }
    for cle, noms in (
        ("method", ("method", "source_method", "target_method")),
        ("route", ("route", "source_route", "target_route")),
        ("path", ("path", "target_path")),
    ):
        valeur = _premier(row, *noms)
        if valeur:
            attributs[cle] = str(valeur)
    return Observation(
        provider=PROVIDER, parser=PARSER, parser_version=PARSER_VERSION,
        file=fichier, language=_langage(fichier),
        kind=f"cbm_relation_{type_relation.lower()}", symbol=source,
        attributes=attributs, confidence=1.0, status="extracted",
    )


class CbmObservations:
    """Expose le graphe CBM local comme un provider d'indexation fédéré."""

    provider = PROVIDER
    parser = PARSER
    parser_version = PARSER_VERSION

    def __init__(self, projet: str, runner=None):
        projet = str(projet or "").strip()
        if not projet:
            raise ValueError("le projet CBM est requis")
        if runner is not None and not callable(runner):
            raise TypeError("le runner CBM doit être appelable")
        self.projet = projet
        self._runner = runner or _runner_cbm(projet)

    def _indexer(self, racine: str, fichiers) -> list[Observation]:
        demandes = _cibles(racine, fichiers)
        filtre = set(demandes) if demandes else None
        observations: list[Observation] = []
        vus: set[tuple] = set()
        for label in LABELS:
            for row in _pages(
                    lambda fichiers, skip, label=label: _requete_noeuds(label, fichiers, skip),
                    self._runner, demandes):
                if not isinstance(row, dict):
                    continue
                observation = _observation_noeud(row, label, racine, filtre)
                if observation is None or observation.fingerprint in vus:
                    continue
                vus.add(observation.fingerprint)
                observations.append(observation)
        for type_relation in RELATIONS:
            for row in _pages(
                    lambda fichiers, skip, type_relation=type_relation: _requete_relation(
                        type_relation, fichiers, skip),
                    self._runner, demandes):
                if not isinstance(row, dict):
                    continue
                observation = _observation_relation(row, type_relation, racine, filtre)
                if observation is not None:
                    observations.append(observation)
        return sorted(observations, key=lambda o: (o.file, o.start, o.kind, o.symbol))

    def index(self, racine: str, fichiers: Sequence[str] = ()) -> list[Observation]:
        """Observations des nœuds et relations CBM, filtrées par fichiers si demandé."""
        try:
            return self._indexer(racine, fichiers)
        except Exception as erreur:
            journal.warning("indexation CBM indisponible : %s", erreur, exc_info=True)
            return []

    def couverture(self, racine: str, fichiers: Sequence[str] = ()) -> list[CouvertureFichier]:
        """Une ligne par fichier demandé ; une panne CBM produit des lignes partielles."""
        demandes = _cibles(racine, fichiers)
        try:
            observations = self._indexer(racine, fichiers)
        except Exception as erreur:
            raison = f"échec CBM : {erreur}"
            journal.warning("couverture CBM indisponible : %s", erreur)
            return [
                CouvertureFichier(
                    file=fichier, language=_langage(fichier), parser=PARSER,
                    statut="partiel", raison=raison,
                )
                for fichier in demandes
            ]
        par_fichier: dict[str, Observation] = {}
        for observation in observations:
            if observation.file:
                par_fichier.setdefault(observation.file, observation)
        if not demandes:
            demandes = sorted(par_fichier)
        resultat = []
        for fichier in demandes:
            observation = par_fichier.get(fichier)
            resultat.append(CouvertureFichier(
                file=fichier,
                language=observation.language if observation else _langage(fichier),
                parser=PARSER,
                statut="indexe" if observation else "non_supporte",
                raison="" if observation else "aucun nœud CBM pour ce fichier",
            ))
        return resultat
