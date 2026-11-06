#!/usr/bin/env python3
"""Backfill des sources documentaires (Confluence/SharePoint) dans document_chunk."""
import argparse
import asyncio
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "backend"))

from dotenv import load_dotenv


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", default="local")
    parser.add_argument("--limite", type=int, default=500)
    args = parser.parse_args()
    load_dotenv(RACINE / "backend" / ".env")
    from meridian.adapters.outbound.postgres import documentation
    total = await documentation.indexer_toutes(args.tenant, limite=args.limite)
    print(f"{total} document(s) indexé(s)")


if __name__ == "__main__":
    asyncio.run(main())
