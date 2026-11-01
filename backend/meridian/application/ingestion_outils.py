"""Ingestion de spécifications OpenAPI et de descripteurs MCP dans le registre capacitaire.

Aucun outil n'est exécuté : OpenAPI produit des manifestes par opération, MCP reprend `tools/list`.
Les fichiers sont lus en lecture seule, avec une taille bornée, et les erreurs sont rendues par entrée
pour qu'une spécification invalide n'empêche pas les autres de rejoindre le catalogue.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from meridian.application import interface_outils
from meridian.domain import interfaces
from meridian.application import mcp_outils
from meridian.application import openapi_outils
from meridian.application import protocoles_outils
from meridian.domain.capacites import RegistreCapacites

__all__ = [
    "ErreurIngestion", "ingerer_interface", "ingerer_mcp", "ingerer_openapi",
    "ingerer_protocoles",
]

_TAILLE_MAX = 5_000_000


class ErreurIngestion(ValueError):
    """Une entrée d'ingestion est invalide."""


def _lire(chemin) -> str:
    try:
        fichier = Path(chemin)
    except TypeError as exc:
        raise ErreurIngestion("chemin invalide") from exc
    if not fichier.is_file() or fichier.is_symlink():
        raise ErreurIngestion("fichier attendu")
    try:
        if fichier.stat().st_size > _TAILLE_MAX:
            raise ErreurIngestion("fichier trop volumineux")
        return fichier.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ErreurIngestion("fichier illisible") from exc


def _specifications(specifications):
    if isinstance(specifications, Mapping):
        specifications = [specifications]
    if not isinstance(specifications, (list, tuple)):
        raise ErreurIngestion("liste de spécifications attendue")
    for entree in specifications:
        if not isinstance(entree, Mapping):
            raise ErreurIngestion("spécification objet attendue")
        application = str(entree.get("application") or entree.get("application_id") or "").strip()
        chemin = entree.get("path") or entree.get("fichier")
        if not application or not chemin:
            raise ErreurIngestion("application et path obligatoires")
        yield {
            "application": application,
            "path": chemin,
            "version": str(entree.get("version") or "1.0.0"),
            "tenant": entree.get("tenant"),
            "acteur": entree.get("acteur"),
            "perimetre": entree.get("perimetre"),
            "type": str(entree.get("type") or "").strip().lower(),
        }


def ingerer_openapi(registre: RegistreCapacites, specifications) -> dict:
    """Charge des documents OpenAPI référencés ``{application, path, version?}``."""
    rapport = {"outils": [], "erreurs": []}
    for entree in _specifications(specifications):
        try:
            texte = _lire(entree["path"])
            noms = openapi_outils.charger_dans(
                registre,
                entree["application"],
                texte,
                locator=str(entree["path"]),
                version=entree["version"],
                tenant=entree["tenant"],
                acteur=entree["acteur"],
                perimetre=entree["perimetre"],
            )
            rapport["outils"].extend(noms)
        except Exception as exc:
            rapport["erreurs"].append({
                "application": entree["application"],
                "path": str(entree["path"]),
                "raison": str(exc)[:240],
            })
    return rapport


def ingerer_mcp(registre: RegistreCapacites, specifications) -> dict:
    """Charge des fichiers JSON de descripteurs MCP (``tools/list``) référencés comme OpenAPI."""
    rapport = {"outils": [], "erreurs": []}
    for entree in _specifications(specifications):
        try:
            charge = json.loads(_lire(entree["path"]))
            outils = charge.get("tools") if isinstance(charge, Mapping) else charge
            noms = mcp_outils.importer_outils(
                registre,
                entree["application"],
                outils,
                version=entree["version"],
                tenant=entree["tenant"],
                acteur=entree["acteur"],
                perimetre=entree["perimetre"],
            )
            rapport["outils"].extend(noms)
        except Exception as exc:
            rapport["erreurs"].append({
                "application": entree["application"],
                "path": str(entree["path"]),
                "raison": str(exc)[:240],
            })
    return rapport


def _detecter_type(chemin, texte: str) -> str:
    suffixe = str(chemin).lower().rsplit(".", 1)[-1] if "." in str(chemin) else ""
    debut = texte.lstrip()[:4096]
    if suffixe == "wsdl" or "<definitions" in debut or ":definitions" in debut:
        return "wsdl"
    if suffixe == "proto" or "syntax" in debut and "service" in debut:
        return "grpc"
    if suffixe in {"graphql", "gql"} or "type Query" in debut or "type Mutation" in debut:
        return "graphql"
    if "asyncapi" in debut.lower():
        return "asyncapi"
    return "openapi"


def _ingerer_une_interface(registre, entree):
    texte = _lire(entree["path"])
    type_ = entree["type"] or _detecter_type(entree["path"], texte)
    if type_ == "wsdl":
        graphe = interfaces.parse_wsdl(entree["application"], texte, str(entree["path"]))
        noms = interface_outils.charger_dans(
            registre, graphe, version=entree["version"], tenant=entree["tenant"],
            acteur=entree["acteur"], perimetre=entree["perimetre"])
        return noms
    if type_ == "openapi":
        return openapi_outils.charger_dans(
            registre, entree["application"], texte, locator=str(entree["path"]),
            version=entree["version"], tenant=entree["tenant"], acteur=entree["acteur"],
            perimetre=entree["perimetre"])
    return _ingerer_protocole(registre, entree, type_, texte)


def _ingerer_protocole(registre, entree, type_, texte):
    if type_ == "graphql":
        manifestes = protocoles_outils.manifests_graphql(
            entree["application"], texte, entree["version"], entree["tenant"],
            entree["acteur"], entree["perimetre"])
    elif type_ == "grpc":
        manifestes = protocoles_outils.manifests_grpc(
            entree["application"], texte, entree["version"], entree["tenant"],
            entree["acteur"], entree["perimetre"])
    elif type_ == "asyncapi":
        manifestes = protocoles_outils.manifests_asyncapi(
            entree["application"], texte, entree["version"], entree["tenant"],
            entree["acteur"], entree["perimetre"])
    else:
        raise ErreurIngestion(f"type d'outil inconnu : {type_}")
    return protocoles_outils.charger_dans(registre, manifestes)


def ingerer_interface(registre: RegistreCapacites, specifications) -> dict:
    """Charge OpenAPI ou WSDL déjà connus en manifestes (REST et SOAP)."""
    rapport = {"outils": [], "erreurs": []}
    for entree in _specifications(specifications):
        try:
            rapport["outils"].extend(_ingerer_une_interface(registre, entree))
        except Exception as exc:
            rapport["erreurs"].append({
                "application": entree["application"],
                "path": str(entree["path"]),
                "raison": str(exc)[:240],
            })
    return rapport


def ingerer_protocoles(registre: RegistreCapacites, specifications) -> dict:
    """Charge GraphQL, gRPC ou AsyncAPI selon le type détecté ou déclaré."""
    rapport = {"outils": [], "erreurs": []}
    for entree in _specifications(specifications):
        try:
            type_ = entree["type"] or _detecter_type(
                entree["path"], _lire(entree["path"]))
            rapport["outils"].extend(
                _ingerer_protocole(registre, entree, type_, _lire(entree["path"])))
        except Exception as exc:
            rapport["erreurs"].append({
                "application": entree["application"],
                "path": str(entree["path"]),
                "raison": str(exc)[:240],
            })
    return rapport


def main():
    import argparse

    parseur = argparse.ArgumentParser(description="Ingestion OpenAPI/MCP dans un registre capacitaire")
    parseur.add_argument("--openapi", action="append", default=[],
                         metavar="APPLICATION=PATH", help="spécification OpenAPI (répétable)")
    parseur.add_argument("--mcp", action="append", default=[],
                         metavar="APPLICATION=PATH", help="descripteurs tools/list JSON (répétable)")
    parseur.add_argument("--interface", action="append", default=[],
                         metavar="APPLICATION=PATH", help="OpenAPI ou WSDL (répétable)")
    parseur.add_argument("--graphql", action="append", default=[],
                         metavar="APPLICATION=PATH", help="SDL GraphQL (répétable)")
    parseur.add_argument("--grpc", action="append", default=[],
                         metavar="APPLICATION=PATH", help="fichier .proto (répétable)")
    parseur.add_argument("--asyncapi", action="append", default=[],
                         metavar="APPLICATION=PATH", help="document AsyncAPI (répétable)")
    arguments = parseur.parse_args()

    def spec(valeur):
        application, _, chemin = valeur.partition("=")
        return {"application": application, "path": chemin}

    registre = RegistreCapacites()
    rapport = {"outils": [], "erreurs": []}
    for type_, valeurs in (
        (None, arguments.openapi), ("mcp", arguments.mcp), (None, arguments.interface),
        ("graphql", arguments.graphql), ("grpc", arguments.grpc), ("asyncapi", arguments.asyncapi),
    ):
        entrees = [spec(v) for v in valeurs if "=" in v]
        if type_:
            entrees = [{**entree, "type": type_} for entree in entrees]
        resultat = (
            ingerer_mcp(registre, entrees) if type_ == "mcp"
            else ingerer_protocoles(registre, entrees) if type_ in {"graphql", "grpc", "asyncapi"}
            else ingerer_interface(registre, entrees)
        )
        rapport["outils"].extend(resultat["outils"])
        rapport["erreurs"].extend(resultat["erreurs"])
    print(json.dumps(rapport, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
