#!/usr/bin/env python3
"""Crée une invitation locale Méridian (code affiché une seule fois)."""
import argparse
import asyncio
import hashlib
import os
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "backend"))

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient


def hacher(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


async def creer(tenant: str, espace: str, email: str | None, jours: int) -> str:
    code = secrets.token_urlsafe(24)
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    await db.invitations.insert_one({
        "code": hacher(code),
        "tenant_id": tenant,
        "espace_id": espace,
        "email": (email or "").strip().lower() or None,
        "cree_le": datetime.now(timezone.utc).isoformat(),
        "expire_le": (datetime.now(timezone.utc) + timedelta(days=jours)).isoformat(),
        "utilise_le": None,
    })
    client.close()
    return code


def main() -> None:
    load_dotenv(RACINE / "backend" / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", default=os.getenv("AUTH_LOCAL_TENANT", "demo"))
    parser.add_argument("--espace", default=os.getenv("AUTH_LOCAL_ESPACE", "mesh-global"))
    parser.add_argument("--email", default=None)
    parser.add_argument("--jours", type=int, default=7)
    args = parser.parse_args()
    print(asyncio.run(creer(args.tenant, args.espace, args.email, args.jours)))


if __name__ == "__main__":
    main()
