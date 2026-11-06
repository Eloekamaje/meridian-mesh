#!/usr/bin/env python3
"""Migration idempotente des colonnes d'embedding de `document_chunk`.

Les bases créées avant l'ADR-0024 n'ont pas `embedding_dim` : l'indexation
documentaire échouait alors silencieusement. Ce script ajoute les colonnes
manquantes sans toucher aux données.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "backend"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(RACINE / "backend" / ".env")


def main() -> int:
    import psycopg

    dsn = os.environ.get("JUMEAU_PG_DSN")
    if not dsn:
        raise SystemExit("JUMEAU_PG_DSN absent")
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("ALTER TABLE document_chunk ADD COLUMN IF NOT EXISTS embedding double precision[]")
        conn.execute("ALTER TABLE document_chunk ADD COLUMN IF NOT EXISTS embedding_model text")
        conn.execute("ALTER TABLE document_chunk ADD COLUMN IF NOT EXISTS embedding_dim int")
        colonnes = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'document_chunk' "
            "AND column_name IN ('embedding', 'embedding_model', 'embedding_dim') "
            "ORDER BY column_name").fetchall()
    print("colonnes d'embedding présentes :", ", ".join(ligne[0] for ligne in colonnes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
