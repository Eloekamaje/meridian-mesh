#!/usr/bin/env python3
"""Découvre les liens entre composants à partir de dépôts locaux.

Exemple :

    python scripts/decouvrir-liens-composants.py \
        --depot comptes:comptes-api:/chemin/vers/comptes \
        --depot antifraude:antifraude-backend:/chemin/vers/antifraude \
        --environnement prod

Le script ne contacte aucun serveur, ne lit aucun secret et n'écrit rien sans `--sortie`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "backend"))

from meridian.adapters.outbound.connectors.decouverte_composants import extraire_depot  # noqa: E402
from meridian.application.moteur_liens import moteur_liens  # noqa: E402
from meridian.domain.liens_composants import SourceDepot  # noqa: E402

DOSSIERS_IGNORES = frozenset({
    ".git", ".hg", ".svn", "node_modules", "vendor", "target", "build", "dist",
    ".venv", "venv", "__pycache__", ".cache", ".idea", ".mypy_cache", ".pytest_cache",
})
EXTENSIONS = frozenset({
    ".java", ".js", ".jsx", ".ts", ".tsx", ".yaml", ".yml", ".json", ".xml",
    ".wsdl", ".graphql", ".gql", ".proto", ".properties", ".env", ".conf", ".config",
})


def _depot(valeur: str) -> tuple[str, str, Path]:
    morceaux = valeur.split(":", 2)
    if len(morceaux) != 3 or not all(morceaux):
        raise argparse.ArgumentTypeError(
            "format attendu : application:composant:chemin")
    application, composant, chemin = morceaux
    racine = Path(chemin).expanduser().resolve()
    if not racine.is_dir():
        raise argparse.ArgumentTypeError(f"dossier introuvable : {racine}")
    return application, composant, racine


def _lire_fichiers(racine: Path, max_fichiers: int, max_octets: int) -> tuple[dict[str, str], list[str]]:
    fichiers: dict[str, str] = {}
    diagnostics: list[str] = []
    for chemin in sorted(racine.rglob("*")):
        if len(fichiers) >= max_fichiers:
            diagnostics.append(f"{racine} : limite de {max_fichiers} fichiers atteinte")
            break
        if not chemin.is_file() or any(partie in DOSSIERS_IGNORES for partie in chemin.parts):
            continue
        if chemin.suffix.lower() not in EXTENSIONS:
            continue
        try:
            if chemin.stat().st_size > max_octets:
                diagnostics.append(f"{chemin.relative_to(racine)} : fichier trop gros, ignoré")
                continue
            donnees = chemin.read_bytes()
        except OSError as erreur:
            diagnostics.append(f"{chemin.relative_to(racine)} : illisible ({type(erreur).__name__})")
            continue
        if b"\x00" in donnees[:4096]:
            continue
        try:
            texte = donnees.decode("utf-8-sig")
        except UnicodeDecodeError:
            diagnostics.append(f"{chemin.relative_to(racine)} : encodage non UTF-8, ignoré")
            continue
        fichiers[chemin.relative_to(racine).as_posix()] = texte
    return fichiers, diagnostics


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="decouvrir-liens-composants",
        description="Découvre les producteurs, consommateurs et liens probables.")
    parser.add_argument("--depot", action="append", type=_depot, required=True,
                        help="application:composant:chemin (répétable)")
    parser.add_argument("--environnement", default="prod")
    parser.add_argument("--max-fichiers", type=int, default=800)
    parser.add_argument("--max-octets", type=int, default=2_000_000)
    parser.add_argument("--sortie", help="écrit le rapport JSON dans ce fichier")
    args = parser.parse_args(argv)

    extractions = []
    diagnostics: list[str] = []
    for application, composant, racine in args.depot:
        fichiers, problemes = _lire_fichiers(racine, args.max_fichiers, args.max_octets)
        diagnostics.extend(problemes)
        extraction = extraire_depot(SourceDepot(
            application_id=application, composant_id=composant,
            environment=args.environnement, fichiers=fichiers))
        extractions.append(extraction)
        diagnostics.extend(extraction.diagnostics)

    rapport = moteur_liens(extractions)
    donnees = rapport.as_dict()
    donnees["diagnostics"] = [*diagnostics, *donnees["diagnostics"]]
    texte = json.dumps(donnees, ensure_ascii=False, indent=2)
    if args.sortie:
        Path(args.sortie).write_text(texte + "\n", encoding="utf-8")
        print(f"rapport écrit : {args.sortie}")
    else:
        print(texte)
    return 0


if __name__ == "__main__":
    sys.exit(main())
