#!/usr/bin/env python3
"""Re-embedde les chunks documentaires avec le provider sémantique configuré.

Usage :
    backend/.venv/bin/python scripts/reembedder-documentation.py --tenant demo

Le script ne journalise aucun secret. Il s'arrête quand il n'y a plus de chunk à
ré-embedder ou après `--passe-max` passes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "backend"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(RACINE / "backend" / ".env")

from meridian.adapters.outbound.postgres import chunk_store  # noqa: E402


def main(argv=None) -> int:
    analyseur = argparse.ArgumentParser(description="Ré-embedding des chunks documentaires.")
    analyseur.add_argument("--tenant", required=True)
    analyseur.add_argument("--limite", type=int, default=500)
    analyseur.add_argument("--passe-max", type=int, default=20)
    args = analyseur.parse_args(argv)
    total = 0
    passes = 0
    for passe in range(1, max(1, args.passe_max) + 1):
        resultat = chunk_store.reembedder(args.tenant, limite=args.limite)
        print(json.dumps({"passe": passe, **resultat}, ensure_ascii=False))
        if not resultat.get("ok") or not resultat.get("reembedes"):
            break
        total += int(resultat.get("reembedes") or 0)
        passes = passe
        if not resultat.get("restants"):
            break
    print(json.dumps({"tenant": args.tenant, "passes": passes, "reembedes": total},
                     ensure_ascii=False))
    return 0 if total or passes else 1


if __name__ == "__main__":
    raise SystemExit(main())
