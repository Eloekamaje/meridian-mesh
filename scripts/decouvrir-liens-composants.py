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

from meridian.adapters.outbound.connectors.decouverte_composants import (  # noqa: E402
    extraire_depot,
    lire_fichiers,
)
from meridian.application.moteur_liens import moteur_liens  # noqa: E402
from meridian.domain.liens_composants import SourceDepot  # noqa: E402
from meridian.domain.politique_decouverte import PolitiqueSources  # noqa: E402


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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="decouvrir-liens-composants",
        description="Découvre les producteurs, consommateurs et liens probables.")
    parser.add_argument("--depot", action="append", type=_depot, required=True,
                        help="application:composant:chemin (répétable)")
    parser.add_argument("--environnement", default="prod")
    parser.add_argument("--niveau-sources", default="0",
                        help="niveaux de sources autorisés, séparés par des virgules "
                             "(0=code/config/contrats/Helm, 1=kubernetes/gateway/traces, "
                             "2=CMDB/portail API, 3=serveur/export WebSphere)")
    parser.add_argument("--source", action="append", default=[],
                        help="source explicite supplémentaire (répétable)")
    parser.add_argument("--approuve-par", default="",
                        help="approbation nommée, obligatoire pour le niveau 3")
    parser.add_argument("--max-fichiers", type=int, default=800)
    parser.add_argument("--max-octets", type=int, default=2_000_000)
    parser.add_argument("--sortie", help="écrit le rapport JSON dans ce fichier")
    args = parser.parse_args(argv)

    try:
        niveaux = tuple(int(x) for x in args.niveau_sources.split(",") if x.strip())
        politique = PolitiqueSources(
            tenant_id="cli", niveaux=niveaux,
            sources_explicites=tuple(args.source or ()),
            approuve_par=args.approuve_par)
    except ValueError as erreur:
        parser.error(str(erreur))

    extractions = []
    diagnostics: list[str] = []
    for application, composant, racine in args.depot:
        fichiers, problemes = lire_fichiers(
            racine, sources_autorisees=politique.sources_autorisees,
            max_fichiers=args.max_fichiers, max_octets=args.max_octets)
        diagnostics.extend(problemes)
        extraction = extraire_depot(SourceDepot(
            application_id=application, composant_id=composant,
            environment=args.environnement, fichiers=fichiers))
        extractions.append(extraction)
        diagnostics.extend(extraction.diagnostics)

    rapport = moteur_liens(extractions)
    donnees = rapport.as_dict()
    donnees["politique_sources"] = politique.as_dict()
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
