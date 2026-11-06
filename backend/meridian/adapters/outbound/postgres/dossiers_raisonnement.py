"""Persistance Postgres des dossiers de raisonnement.

Le dossier est écrit en JSONB et quelques colonnes de lecture sont dupliquées pour l'audit.
Aucune écriture canonique n'est faite ici : c'est une trace d'exécution, pas un Claim.
"""
from __future__ import annotations

from collections.abc import Mapping
import os
from typing import Any

from psycopg.types.json import Jsonb

__all__ = [
    "enregistrer",
    "enregistrer_dsn",
    "lire",
    "lire_dsn",
    "lister",
    "lister_dsn",
]


def _dossier_dict(dossier: Any) -> dict:
    if hasattr(dossier, "as_dict"):
        return dict(dossier.as_dict())
    return dict(dossier) if isinstance(dossier, Mapping) else {}


def _valeurs(tenant: str, dossier: Any, travail_id: str = "") -> tuple:
    vue = _dossier_dict(dossier)
    contexte = vue.get("contexte") or {}
    demande = vue.get("demande") or {}
    return (
        str(vue.get("id") or "")[:80],
        str(tenant or vue.get("tenant") or "local")[:128],
        str(travail_id or vue.get("travail_id") or "")[:128] or None,
        str(vue.get("question") or demande.get("question") or "")[:4000],
        str(vue.get("niveau") or demande.get("niveau") or "N0")[:4],
        str(vue.get("statut") or "reponse")[:30],
        str(contexte.get("fingerprint") or "")[:128] or None,
        str(vue.get("trace_id") or "")[:80] or None,
        Jsonb(vue),
    )


def enregistrer(conn, tenant: str, dossier: Any, travail_id: str = "") -> str:
    """Upsert idempotent d'un dossier ; rend son identifiant."""
    valeurs = _valeurs(tenant, dossier, travail_id)
    if not valeurs[0]:
        raise ValueError("dossier : id obligatoire")
    conn.execute(
        "INSERT INTO dossier_raisonnement "
        "(id, tenant_id, travail_id, question, niveau, statut, fingerprint, trace_id, dossier) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (id) DO UPDATE SET "
        "travail_id = coalesce(EXCLUDED.travail_id, dossier_raisonnement.travail_id), "
        "question = EXCLUDED.question, niveau = EXCLUDED.niveau, statut = EXCLUDED.statut, "
        "fingerprint = EXCLUDED.fingerprint, trace_id = EXCLUDED.trace_id, "
        "dossier = EXCLUDED.dossier, maj_le = now() "
        "WHERE dossier_raisonnement.tenant_id = EXCLUDED.tenant_id",
        valeurs,
    )
    return valeurs[0]


def enregistrer_dsn(dsn: str, tenant: str, dossier: Any, travail_id: str = "") -> str:
    """Écrit depuis un worker ou une route sans partager la connexion applicative."""
    import psycopg

    with psycopg.connect(dsn, connect_timeout=5) as conn:
        with conn.transaction():
            identifiant = enregistrer(conn, tenant, dossier, travail_id)
            try:
                from meridian.adapters.outbound.postgres import calibration_croyances
                calibration_croyances.enregistrer_dossier(
                    conn, tenant, identifiant, dossier)
            except Exception:
                pass
            return identifiant


def lire(conn, tenant: str, dossier_id: str) -> dict | None:
    ligne = conn.execute(
        "SELECT dossier, cree_le, maj_le FROM dossier_raisonnement WHERE tenant_id = %s AND id = %s",
        (tenant, dossier_id),
    ).fetchone()
    if not ligne:
        return None
    dossier = dict(ligne[0] or {})
    dossier.setdefault("cree_le", ligne[1].isoformat() if ligne[1] else None)
    dossier.setdefault("maj_le", ligne[2].isoformat() if ligne[2] else None)
    return dossier


def lire_dsn(dsn: str, tenant: str, dossier_id: str) -> dict | None:
    import psycopg

    with psycopg.connect(dsn, connect_timeout=5) as conn:
        return lire(conn, tenant, dossier_id)


def lister_dsn(dsn: str, tenant: str, *, travail_id: str | None = None, limite: int = 50) -> list[dict]:
    import psycopg

    with psycopg.connect(dsn, connect_timeout=5) as conn:
        return lister(conn, tenant, travail_id=travail_id, limite=limite)


def lister(conn, tenant: str, *, travail_id: str | None = None, limite: int = 50) -> list[dict]:
    try:
        borne = max(1, min(int(limite), 200))
    except (TypeError, ValueError):
        borne = 50
    if travail_id:
        lignes = conn.execute(
            "SELECT dossier, cree_le, maj_le FROM dossier_raisonnement "
            "WHERE tenant_id = %s AND travail_id = %s ORDER BY maj_le DESC LIMIT %s",
            (tenant, travail_id, borne),
        ).fetchall()
    else:
        lignes = conn.execute(
            "SELECT dossier, cree_le, maj_le FROM dossier_raisonnement "
            "WHERE tenant_id = %s ORDER BY maj_le DESC LIMIT %s",
            (tenant, borne),
        ).fetchall()
    resultat = []
    for dossier, cree, maj in lignes:
        vue = dict(dossier or {})
        vue.setdefault("cree_le", cree.isoformat() if cree else None)
        vue.setdefault("maj_le", maj.isoformat() if maj else None)
        resultat.append(vue)
    return resultat
