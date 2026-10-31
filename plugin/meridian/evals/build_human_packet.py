#!/usr/bin/env python3
"""Construit un packet de revue humaine aveugle depuis des résultats de benchmark.

Le script ne fabrique aucune revue : il copie les réponses, retire le nom du bras et génère
un formulaire vide conforme à ``human/review.schema.json``. Le mapping bras→label reste dans
``mapping.json`` pour l'administrateur.
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
from pathlib import Path

__all__ = ["construire"]


def _runs(racine: Path):
    for chemin in sorted(racine.rglob("run-*.json")):
        try:
            donnees = json.loads(chemin.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        texte = donnees.get("result")
        if not isinstance(texte, str) or not texte.strip():
            continue
        yield chemin, donnees


def construire(racines, sortie, *, seed=0, limite=20):
    """Écrit le packet ; retourne le résumé."""
    sortie = Path(sortie)
    if sortie.exists():
        shutil.rmtree(sortie)
    echantillons = sortie / "samples"
    echantillons.mkdir(parents=True)
    entrees = []
    for racine in racines:
        for chemin, donnees in _runs(Path(racine)):
            entrees.append((chemin, donnees))
    random.Random(seed).shuffle(entrees)
    mapping = {}
    for index, (chemin, donnees) in enumerate(entrees[:limite], 1):
        label = f"sample-{index:02d}"
        (echantillons / f"{label}.md").write_text(
            f"# Échantillon {index:02d}\n\n"
            f"Scénario : `{donnees.get('scenario', 'inconnu')}`\n\n"
            "## Réponse à évaluer\n\n"
            f"{(donnees.get('result') or '').strip()}\n",
            encoding="utf-8")
        mapping[label] = {
            "source": str(chemin),
            "scenario": donnees.get("scenario"),
            "condition": donnees.get("condition"),
            "cost_usd": donnees.get("cost_usd"),
            "duration_seconds": donnees.get("duration_seconds"),
        }
    (sortie / "mapping.json").write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    formulaire = {
        "reviewer_id": "",
        "scenario": "",
        "decision_accuracy": 0,
        "evidence_grounding": 0,
        "calibration": 0,
        "usefulness": 1,
        "trust": 1,
        "critical_errors": [],
        "would_approve": False,
        "time_seconds": 0,
        "comments": "",
    }
    (sortie / "review-form.json").write_text(
        json.dumps(formulaire, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (sortie / "README.md").write_text(
        "# Packet de revue humaine\n\n"
        "Chaque reviewer lit les échantillons sans connaître le bras, remplit un formulaire par\n"
        "échantillon selon `review.schema.json`, puis dépose les fichiers dans `reviews/`.\n"
        "Le mapping bras→label est réservé à l'administrateur.\n",
        encoding="utf-8")
    return {"echantillons": len(mapping), "sortie": str(sortie)}


def main(argv=None):
    parseur = argparse.ArgumentParser(description="Packet de revue humaine aveugle")
    parseur.add_argument("--runs-dir", action="append", required=True,
                         help="Répertoire de résultats du runner (répétable)")
    parseur.add_argument("--output", required=True)
    parseur.add_argument("--seed", type=int, default=0)
    parseur.add_argument("--limite", type=int, default=20)
    arguments = parseur.parse_args(argv)
    resultat = construire(arguments.runs_dir, arguments.output, seed=arguments.seed,
                          limite=arguments.limite)
    print(json.dumps(resultat, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
