#!/usr/bin/env python3
"""Synchronise l'ACL de configuration des sources vers document_chunk."""
import argparse
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "backend"))

from dotenv import load_dotenv


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", default="local")
    args = parser.parse_args()
    load_dotenv(RACINE / "backend" / ".env")
    from meridian.adapters.outbound.postgres import documentation
    print(f"{documentation.synchroniser_acl(args.tenant)} chunk(s) mis à jour")


if __name__ == "__main__":
    main()
