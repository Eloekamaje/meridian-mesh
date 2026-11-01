"""Proposer une initiative à partir d'une situation de source à forte priorité.

L'ingestion ne décide jamais : elle dépose une proposition `en_attente` dans l'inbox des
initiatives, que l'équipe peut suivre, ignorer ou transformer en travail. Les situations
de priorité basse/normale restent dans le fil sans créer de proposition.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

SEUIL = "haute"


def _identifiant(situation: dict[str, Any]) -> str:
    return f"init-{situation['id']}"


def proposition_depuis_situation(situation: dict[str, Any]) -> dict[str, Any] | None:
    if situation.get("priorite") != SEUIL:
        return None
    jumeaux = [str(j) for j in (situation.get("jumeaux") or []) if j]
    if not jumeaux:
        return None
    return {
        "id": _identifiant(situation),
        "titre": f"Traiter : {situation.get('titre') or 'changement de source'}"[:200],
        "raison": (situation.get("resume") or situation.get("question") or "")[:1000],
        "jumeaux": jumeaux,
        "statut": "en_attente",
        "urgence": "haute",
        "genre": "a_confirmer",
        "confiance": 70,
        "quand": datetime.now(timezone.utc).isoformat(),
        "source": "gardien",
        "situation_id": situation.get("id"),
        "declencheur": str(situation.get("type") or "changement"),
        **({"tenant_id": situation["tenant_id"]} if situation.get("tenant_id") else {}),
    }


async def proposer(db, situation: dict[str, Any]) -> dict[str, Any] | None:
    """Crée la proposition une seule fois ; ne lève jamais vers l'appelant de la veille."""
    doc = proposition_depuis_situation(situation)
    if doc is None:
        return None
    collection = getattr(db, "initiatives", None)
    if collection is None:
        return None
    await collection.update_one({"id": doc["id"]}, {"$setOnInsert": doc}, upsert=True)
    return doc
