"""Persistance d'un Learning proposé issu d'un dossier de raisonnement.

L'objet reste `PROPOSED` : il n'est pas promu dans la connaissance canonique. Il peut être relu par la
boucle et les spécialistes, puis approuvé par un humain comme n'importe quel Learning.
"""
from __future__ import annotations

import os

from meridian.adapters.outbound.postgres import entreprise_depot

__all__ = ["depuis_dossier", "persister", "persister_dsn", "promouvoir"]


def depuis_dossier(tenant: str, dossier_id: str, learning: dict) -> dict:
    source = dict(learning.get("source") or {})
    return {
        "id": f"learning-{dossier_id}-{source.get('trace_id') or 'sans-trace'}"[:128],
        "tenant_id": tenant,
        "famille": "resultat_apprentissage",
        "type": "LEARNING",
        "mode": "INFERRED",
        "titre": str(learning.get("titre") or "Learning de raisonnement")[:240],
        "donnees": {
            "enonce": learning.get("enonce") or "",
            "resume": learning.get("resume") or "",
            "statut": "PROPOSED",
            "scope": learning.get("scope") or tenant,
            "conditions_reutilisation": list(learning.get("conditions_reutilisation") or ()),
            "source": source,
            "evaluation": dict(learning.get("evaluation") or {}),
        },
    }


def persister(conn, tenant: str, dossier_id: str, learning: dict) -> dict:
    objet = depuis_dossier(tenant, dossier_id, learning)
    return entreprise_depot.enregistrer_objet(conn, tenant, objet)


def persister_dsn(dsn: str, tenant: str, dossier_id: str, learning: dict) -> dict:
    import psycopg

    with psycopg.connect(dsn, connect_timeout=5) as conn:
        with conn.transaction():
            return persister(conn, tenant, dossier_id, learning)


def promouvoir(conn, tenant: str, learning_id: str, acteur: str, motif: str = "") -> dict:
    """Promeut un Learning proposé en Learning accepté par un humain ; jamais automatique."""
    objet = entreprise_depot.lire_objet(conn, tenant, learning_id)
    if objet is None:
        raise LookupError("Learning introuvable")
    if str(objet.get("type") or "").upper() != "LEARNING":
        raise ValueError("l'objet n'est pas un LEARNING")
    donnees = dict(objet.get("donnees") or {})
    if str(donnees.get("statut") or "").upper() != "PROPOSED":
        raise ValueError("seul un Learning PROPOSED peut être promu")
    if not str(acteur or "").strip():
        raise ValueError("acteur obligatoire pour promouvoir un Learning")
    donnees.update({
        "statut": "ACCEPTED",
        "approuve_par": str(acteur)[:200],
        "approuve_le": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).isoformat(),
    })
    if motif:
        donnees["motif"] = str(motif)[:2000]
    return entreprise_depot.enregistrer_objet(conn, tenant, {
        **objet,
        "mode": "CONFIRMED",
        "donnees": donnees,
    })


def promouvoir_dsn(dsn: str, tenant: str, learning_id: str, acteur: str, motif: str = "") -> dict:
    import psycopg

    with psycopg.connect(dsn, connect_timeout=5) as conn:
        with conn.transaction():
            return promouvoir(conn, tenant, learning_id, acteur, motif)
