"""Ingestion de spécifications OpenAPI et de descripteurs MCP dans le registre capacitaire.

Aucun outil n'est exécuté : OpenAPI produit des manifestes par opération, MCP reprend `tools/list`.
Les fichiers sont lus en lecture seule, avec une taille bornée, et les erreurs sont rendues par entrée
pour qu'une spécification invalide n'empêche pas les autres de rejoindre le catalogue.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from jumeau import mcp_outils, openapi_outils
from jumeau.capacites import RegistreCapacites

__all__ = ["ErreurIngestion", "ingerer_mcp", "ingerer_openapi"]

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
            "persona": entree.get("persona"),
            "perimetre": entree.get("perimetre"),
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
                persona=entree["persona"],
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
                persona=entree["persona"],
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


def main():
    import argparse

    parseur = argparse.ArgumentParser(description="Ingestion OpenAPI/MCP dans un registre capacitaire")
    parseur.add_argument("--openapi", action="append", default=[],
                         metavar="APPLICATION=PATH", help="spécification OpenAPI (répétable)")
    parseur.add_argument("--mcp", action="append", default=[],
                         metavar="APPLICATION=PATH", help="descripteurs tools/list JSON (répétable)")
    arguments = parseur.parse_args()

    def spec(valeur):
        application, _, chemin = valeur.partition("=")
        return {"application": application, "path": chemin}

    registre = RegistreCapacites()
    rapport = ingerer_openapi(registre, [spec(v) for v in arguments.openapi if "=" in v])
    mcp = ingerer_mcp(registre, [spec(v) for v in arguments.mcp if "=" in v])
    rapport["outils"].extend(mcp["outils"])
    rapport["erreurs"].extend(mcp["erreurs"])
    print(json.dumps(rapport, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
