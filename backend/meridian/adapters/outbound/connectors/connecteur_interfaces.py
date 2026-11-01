"""Connecteur de fichiers : une racine Git ou locale devient un graphe d'interfaces.

Adaptateur de système source, sans agent, sans modèle et sans réseau : le parcours est trié, les documents
OpenAPI/Swagger et WSDL sont reconnus par leur contenu, la configuration par son nom, puis `interfaces.py` fait la
lecture. Les secrets ne sont jamais rendus : la configuration n'est lue que pour ses URLs, que le parseur assainit. Un
fichier trop gros, illisible ou au-delà de la limite rend le graphe `partial` et laisse un diagnostic localisé par un
chemin relatif à la racine.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
from fnmatch import fnmatch
from pathlib import Path
from typing import Iterator, Optional

from meridian.domain import interfaces
from meridian.application import interfaces_protocoles

DOSSIERS_IGNORES = frozenset({
    ".git", "node_modules", "vendor", "build", "dist", ".venv", "__pycache__", ".cache",
    "test", "tests", "__tests__",
})
EXTENSIONS_OPENAPI = frozenset({".json", ".yaml", ".yml"})
EXTENSIONS_WSDL = frozenset({".wsdl", ".xml"})
EXTENSIONS_PROTOCOLES = frozenset({".graphql", ".gql", ".proto"})
MOTIFS_CONFIG = ("application*.properties", "application*.yml", "application*.yaml",
                 ".env", ".env.*", "*.conf", "*.config")
MOTIF_OPENAPI_JSON = re.compile(r'"\s*(?:openapi|swagger)\s*"\s*:', re.IGNORECASE)
MOTIF_OPENAPI_YAML = re.compile(r"(?m)^[\"']?(?:openapi|swagger)[\"']?\s*:", re.IGNORECASE)
MOTIF_WSDL = re.compile(r"<(?:\w+:)?definitions(?=[\s/>])", re.IGNORECASE)
MOTIF_GRAPHQL = re.compile(r"(?m)^\s*(?:extend\s+)?type\s+(?:Query|Mutation|Subscription)\b")
MOTIF_PROTO = re.compile(r"(?m)^\s*(?:syntax\s*=|service\s+\w+\s*\{)")
MOTIF_ASYNCAPI = re.compile(r"(?im)^\s*[\"']?asyncapi[\"']?\s*:")


def _nom_config(nom: str) -> bool:
    minuscule = nom.lower()
    return any(fnmatch(minuscule, motif) for motif in MOTIFS_CONFIG)


def _est_openapi(texte: str) -> bool:
    """Le contenu décide, pas le nom : une clé racine JSON ou YAML `openapi`/`swagger`."""
    texte = texte.lstrip("\ufeff")
    return bool(MOTIF_OPENAPI_JSON.search(texte) or MOTIF_OPENAPI_YAML.search(texte))


def _est_wsdl(texte: str) -> bool:
    """Un WSDL est reconnu par son élément racine, avec ou sans préfixe de namespace."""
    texte = texte.lstrip("\ufeff")
    return bool(MOTIF_WSDL.search(texte))


def _est_graphql(texte: str) -> bool:
    return bool(MOTIF_GRAPHQL.search(texte.lstrip("\ufeff")))


def _est_proto(texte: str) -> bool:
    return bool(MOTIF_PROTO.search(texte.lstrip("\ufeff")))


def _est_asyncapi(texte: str) -> bool:
    return bool(MOTIF_ASYNCAPI.search(texte.lstrip("\ufeff")))


def _est_candidat(chemin: Path) -> bool:
    suffixe = chemin.suffix.lower()
    return (suffixe in EXTENSIONS_OPENAPI or suffixe in EXTENSIONS_WSDL
            or suffixe in EXTENSIONS_PROTOCOLES or _nom_config(chemin.name))


def _est_binaire(donnees: bytes) -> bool:
    if b"\x00" in donnees:
        return True
    echantillon = donnees[:4096]
    if not echantillon:
        return False
    controles = sum(1 for octet in echantillon if octet < 9 or 13 < octet < 32)
    return controles / len(echantillon) > 0.3


def _decoder(donnees: bytes) -> Optional[str]:
    try:
        return donnees.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            return donnees.decode("latin-1")
        except UnicodeDecodeError:
            return None


def _fichiers(racine: Path) -> Iterator[Path]:
    for dossier, sous_dossiers, noms in os.walk(racine, followlinks=False):
        sous_dossiers[:] = sorted(
            nom for nom in sous_dossiers
            if nom.lower() not in DOSSIERS_IGNORES and not (Path(dossier) / nom).is_symlink()
        )
        for nom in sorted(noms):
            yield Path(dossier) / nom


def _locator(chemin: Path, racine: Path) -> str:
    return chemin.relative_to(racine).as_posix()


def _diagnostic(locator: str, message: str, partial: bool = False) -> interfaces.InterfaceGraph:
    return interfaces.InterfaceGraph(diagnostics=[f"{locator} : {message}"], partial=partial)


def _avec_locator(graph: interfaces.InterfaceGraph, locator: str) -> interfaces.InterfaceGraph:
    graph.diagnostics = [f"{locator} : {diagnostic}" for diagnostic in graph.diagnostics]
    return graph


def _lire(chemin: Path, locator: str, max_octets: int) -> tuple[Optional[str], Optional[interfaces.InterfaceGraph]]:
    """Texte du fichier, ou le diagnostic qui explique pourquoi il n'a pas été lu (jamais son contenu)."""
    try:
        attributs = chemin.stat()
    except OSError as erreur:
        return None, _diagnostic(locator, f"fichier illisible ({type(erreur).__name__})", partial=True)
    if not stat.S_ISREG(attributs.st_mode):
        return None, _diagnostic(locator, "fichier spécial ignoré")
    taille = attributs.st_size
    if taille > max_octets:
        return None, _diagnostic(
            locator, f"fichier ignoré (taille {taille} octets > {max_octets})", partial=True)
    try:
        with chemin.open("rb") as flux:
            donnees = flux.read(max_octets + 1)
    except OSError as erreur:
        return None, _diagnostic(locator, f"fichier illisible ({type(erreur).__name__})", partial=True)
    if len(donnees) > max_octets:
        return None, _diagnostic(
            locator, f"fichier ignoré (taille > {max_octets} octets)", partial=True)
    if _est_binaire(donnees):
        return None, _diagnostic(locator, "fichier binaire ignoré")
    texte = _decoder(donnees)
    if texte is None:
        return None, _diagnostic(locator, "fichier illisible (encodage non textuel)", partial=True)
    return texte, None


def collecter(racine, application_id, environment: str = "inconnu", max_fichiers: int = 500,
              max_octets: int = 2_000_000) -> interfaces.InterfaceGraph:
    """Scanne `racine` (au plus `max_fichiers` candidats, chacun au plus `max_octets`) et rend un `InterfaceGraph`.

    OpenAPI/Swagger et WSDL sont reconnus par leur contenu ; la configuration par son nom. Le parcours est trié et
    relatif à la racine ; `.git`, `node_modules`, `vendor`, `build`, `dist`, `.venv`, `__pycache__`, `.cache` et les
    dossiers de tests sont ignorés. Une erreur, un binaire ou un dépassement laisse un diagnostic, sans jamais
    recopier une valeur de secret ni un chemin absolu.
    """
    base = Path(racine)
    if not base.is_dir():
        raise ValueError("racine introuvable ou n'est pas un dossier")
    if not application_id or not str(application_id).strip():
        raise ValueError("application_id requis")
    if max_fichiers < 0 or max_octets < 0:
        raise ValueError("les limites doivent être positives ou nulles")

    morceaux: list[interfaces.InterfaceGraph] = []
    candidats = 0
    for chemin in _fichiers(base):
        if not _est_candidat(chemin):
            continue
        locator = _locator(chemin, base)
        if chemin.is_symlink():
            morceaux.append(_diagnostic(locator, "lien symbolique ignoré"))
            continue
        if candidats >= max_fichiers:
            morceaux.append(_diagnostic(
                locator, f"limite de {max_fichiers} fichiers candidats atteinte : parcours tronqué", partial=True))
            break
        candidats += 1
        texte, probleme = _lire(chemin, locator, max_octets)
        if probleme is not None:
            morceaux.append(probleme)
            continue
        suffixe = chemin.suffix.lower()
        if suffixe in EXTENSIONS_OPENAPI and _est_openapi(texte):
            morceaux.append(_avec_locator(
                interfaces.parse_openapi(application_id, texte, locator, environment), locator))
        elif suffixe in EXTENSIONS_WSDL and _est_wsdl(texte):
            morceaux.append(_avec_locator(
                interfaces.parse_wsdl(application_id, texte, locator, environment), locator))
        elif suffixe in (".graphql", ".gql") or _est_graphql(texte):
            morceaux.append(_avec_locator(
                interfaces_protocoles.parse_graphql(application_id, texte, locator, environment), locator))
        elif suffixe == ".proto" or _est_proto(texte):
            morceaux.append(_avec_locator(
                interfaces_protocoles.parse_proto(application_id, texte, locator, environment), locator))
        elif _est_asyncapi(texte):
            morceaux.append(_avec_locator(
                interfaces_protocoles.parse_asyncapi(application_id, texte, locator, environment), locator))
        elif _nom_config(chemin.name):
            morceaux.append(_avec_locator(
                interfaces.parse_config(application_id, texte, locator, environment), locator))
    return interfaces.merge(morceaux)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m meridian.adapters.outbound.connectors.connecteur_interfaces",
                                description="Scanner une racine et imprimer le graphe d'interfaces en JSON.")
    p.add_argument("racine")
    p.add_argument("application_id")
    p.add_argument("--environment", default="inconnu")
    p.add_argument("--max-fichiers", type=int, default=500)
    p.add_argument("--max-octets", type=int, default=2_000_000)
    args = p.parse_args(argv)
    try:
        graph = collecter(args.racine, args.application_id, args.environment,
                          max_fichiers=args.max_fichiers, max_octets=args.max_octets)
    except (ValueError, OSError) as erreur:
        print(f"collecte impossible : {erreur}", file=sys.stderr)
        return 2
    print(json.dumps(graph.as_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
