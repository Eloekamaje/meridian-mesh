#!/usr/bin/env python3
"""Évalue le moteur de liens contre un corpus labellisé.

Exemple :

    python scripts/evaluer-liens.py --corpus backend/meridian/tests/fixtures/liens_corpus/corpus.json

Le script ne lit que les sources autorisées par la politique du corpus, ne contacte
aucun serveur et n'écrit rien sans `--sortie`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "backend"))

from meridian.adapters.outbound.connectors.corpus_liens import charger_corpus  # noqa: E402
from meridian.application.evaluation_liens import evaluer_liens  # noqa: E402
from meridian.application.moteur_liens import moteur_liens  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="evaluer-liens",
        description="Évalue le moteur de liens contre un corpus JSON labellisé.")
    parser.add_argument("--corpus", required=True, help="fichier JSON du corpus")
    parser.add_argument("--sortie", help="écrit le rapport JSON dans ce fichier")
    parser.add_argument("--strict", action="store_true",
                        help="échoue si une fausse certitude est détectée")
    args = parser.parse_args(argv)

    try:
        corpus = charger_corpus(args.corpus)
    except ValueError as erreur:
        parser.error(str(erreur))

    rapport = moteur_liens(corpus.extractions)
    resultat = evaluer_liens(rapport, corpus.jeu)
    donnees = {
        "corpus": corpus.chemin,
        "politique_sources": corpus.politique.as_dict(),
        "evaluation": resultat.as_dict(),
        "resume": resultat.resume(),
        "rapport": rapport.as_dict(),
        "diagnostics": list(corpus.diagnostics),
    }
    texte = json.dumps(donnees, ensure_ascii=False, indent=2)
    if args.sortie:
        Path(args.sortie).write_text(texte + "\n", encoding="utf-8")
        print(f"rapport écrit : {args.sortie}")
    else:
        print(texte)
    if args.strict and resultat.fausses_certitudes:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
