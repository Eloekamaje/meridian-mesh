#!/usr/bin/env python3
"""Compile un HTML design-diagram en artefact SVG pour le chat / Canvas.

Le compilateur de la skill (`export_svg.py`) est la source de vérité : il extrait le premier
SVG, embarque le CSS utile, préfixe les identifiants et vérifie que le document est du XML
valide. Ce script ne réimplémente pas cette logique ; il l'appelle avec les polices système
pour éviter toute requête réseau, puis construit l'artefact Meridian.

    python3 scripts/compiler-diagramme.py docs/diagrammes/architecture.html \
        --titre "Architecture Méridian" --sortie /tmp/architecture.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
EXPORTEUR_SKILL = RACINE / ".opencode/skills/diagram-design/scripts/export_svg.py"
EXPORTEUR_LOCAL = RACINE / "backend/meridian/adapters/outbound/diagram_export.py"


def _exporteur() -> Path:
    explicite = os.environ.get("DIAGRAM_EXPORT_SCRIPT")
    candidats = [Path(explicite)] if explicite else []
    candidats += [EXPORTEUR_LOCAL, EXPORTEUR_SKILL]
    for candidat in candidats:
        if candidat.is_file():
            return candidat
    raise SystemExit(
        "compilateur design-diagram introuvable : définir DIAGRAM_EXPORT_SCRIPT "
        "ou installer le fallback vendu dans backend/meridian/adapters/outbound/diagram_export.py")


def compiler(source: Path) -> str:
    if not source.is_file():
        raise SystemExit(f"source introuvable : {source}")
    script = _exporteur()
    with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as sortie:
        chemin = Path(sortie.name)
    try:
        resultat = subprocess.run(
            [sys.executable, str(script), str(source), str(chemin), "--system-fonts"],
            capture_output=True, text=True, timeout=60)
        if resultat.returncode != 0:
            raise SystemExit((resultat.stderr or resultat.stdout or "export SVG en échec").strip())
        return chemin.read_text(encoding="utf-8")
    finally:
        chemin.unlink(missing_ok=True)


def artefact(source: Path, titre: str, svg: str) -> dict:
    base = {"type": "svg", "titre": titre or source.stem, "version": "1.0",
            "source": "design-diagram", "fallback": "json", "svg": svg}
    empreinte = hashlib.sha256(json.dumps(base, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return {**base, "hash": empreinte, "artefact_id": empreinte[:24]}


def poster(artefact_: dict, url: str, tenant: str, jeton: str | None) -> dict:
    requete = urllib.request.Request(
        url.rstrip("/") + "/api/planification/artefacts",
        data=json.dumps(artefact_).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "X-Tenant": tenant,
                 **({"Authorization": f"Bearer {jeton}"} if jeton else {})})
    with urllib.request.urlopen(requete, timeout=30) as reponse:
        return json.loads(reponse.read().decode())


def main(argv=None) -> int:
    parseur = argparse.ArgumentParser(description="Compile un diagramme design-diagram en artefact SVG")
    parseur.add_argument("source", type=Path)
    parseur.add_argument("--titre", default=None)
    parseur.add_argument("--sortie", type=Path, default=None, help="écrit l'artefact JSON")
    parseur.add_argument("--api-url", default=None, help="POST /api/planification/artefacts")
    parseur.add_argument("--tenant", default=os.environ.get("JUMEAU_TENANT", "demo"))
    parseur.add_argument("--jeton", default=os.environ.get("JUMEAU_AUTH_TOKEN"))
    args = parseur.parse_args(argv)
    svg = compiler(args.source)
    artefact_ = artefact(args.source, args.titre, svg)
    if args.api_url:
        reponse = poster(artefact_, args.api_url, args.tenant, args.jeton)
        artefact_["artefact_id"] = reponse.get("artefact_id", artefact_["artefact_id"])
    if args.sortie:
        args.sortie.write_text(json.dumps(artefact_, ensure_ascii=False, indent=2), encoding="utf-8")
        print(args.sortie)
    else:
        print(json.dumps(artefact_, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
