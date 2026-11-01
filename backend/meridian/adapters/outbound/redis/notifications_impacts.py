"""Notifications d'impact d'interfaces, visibles par tout le tenant.

Une découverte d'interfaces ne notifie que si elle prouve un impact `breaking` ou `warning`. La notification
reste métier — opération, application impactée, sévérité — et ne recopie jamais la preuve brute, qui peut
contenir un secret ou une adresse interne.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from meridian.adapters.outbound.redis import evenements

__all__ = ["notification_depuis_run", "publier_notification"]

_SEVERITES_UTILES = ("breaking", "warning")
_RANG_SEVERITE = {"breaking": 0, "warning": 1}
_LIBELLES_SEVERITE = {"breaking": "rupture (haute)", "warning": "avertissement (normale)"}


def _champ(jumeau, nom):
    if isinstance(jumeau, dict):
        return jumeau.get(nom)
    if isinstance(jumeau, str):
        return jumeau if nom in ("id", "equipe") else None
    return getattr(jumeau, nom, None)


def _jumeau_id(jumeau) -> str:
    identifiant = _champ(jumeau, "id")
    if isinstance(jumeau, str):
        identifiant = jumeau
    identifiant = str(identifiant or "").strip()
    if not identifiant:
        raise ValueError("jumeau sans identifiant : notification refusée")
    return identifiant


def _run_effectif(run) -> dict:
    if not isinstance(run, dict):
        return {}
    if isinstance(run.get("run"), dict):
        effectif = dict(run["run"])
        if not effectif.get("impacts") and run.get("impacts"):
            effectif["impacts"] = run["impacts"]
        return effectif
    return run


def _impacts_significatifs(run: dict) -> list[dict]:
    return sorted(
        (impact for impact in (run.get("impacts") or [])
         if isinstance(impact, dict) and impact.get("severity") in _SEVERITES_UTILES),
        key=lambda impact: (_RANG_SEVERITE[impact["severity"]], str(impact.get("application") or ""),
                            str(impact.get("operation") or "")))


def _propre(valeur, defaut) -> str:
    texte = " ".join(str(valeur if valeur is not None else defaut).split())
    texte = re.sub(r"<[^>]*>", " ", texte).replace("<", "").replace(">", "")
    return " ".join(texte.split()) or defaut


def _texte(impacts: list[dict]) -> str:
    premier = impacts[0]
    application = _propre(premier.get("application"), "application non précisée")
    operation = _propre(premier.get("operation"), "opération non précisée")
    texte = (f"Interface : {_LIBELLES_SEVERITE[premier['severity']]} — "
             f"{application} est impactée par {operation}")
    if len(impacts) > 1:
        autres = len(impacts) - 1
        texte += f" (+{autres} autre{'s' if autres > 1 else ''} impact{'s' if autres > 1 else ''})"
    return texte + "."


def _quand(run: dict) -> str:
    quand = run.get("ended_at") or run.get("started_at")
    if not quand:
        return datetime.now(timezone.utc).isoformat()
    return quand.isoformat() if hasattr(quand, "isoformat") else str(quand)


def notification_depuis_run(run, jumeau, situation=None) -> dict | None:
    """Rend la notification d'un run, ou None si ses impacts ne sont que des informations.

    `jumeau` peut être le dictionnaire du jumeau ou son identifiant. Seuls les impacts `breaking` et `warning`
    comptent ; l'identifiant reste stable pour un même run, ce qui rend la publication idempotente.
    """
    run = _run_effectif(run)
    impacts = _impacts_significatifs(run)
    if not impacts:
        return None
    run_id = str(run.get("id") or "").strip()
    if not run_id:
        raise ValueError("run sans identifiant : notification refusée")
    jumeau_id = _jumeau_id(jumeau)
    return {
        "id": f"notif-interface-{jumeau_id}-{run_id}",
        "type": "interface_impact",
        "texte": _texte(impacts),
        "lien": f"/atlas?focus={jumeau_id}",
        "lu": False,
        "quand": _quand(run),
    }


async def publier_notification(db, jumeau, run, situation=None) -> dict | None:
    """Crée la notification une seule fois et prévient tous les flux du tenant par le canal SSE.

    L'identifiant du run sert de clé : une relance de la passe ne crée pas de doublon et ne republie pas
    l'événement. Les erreurs remontent à l'appelant, qui garde la passe best-effort.
    """
    doc = notification_depuis_run(run, jumeau, situation=situation)
    if not doc:
        return None
    resultat = await db.notifications.update_one({"id": doc["id"]}, {"$setOnInsert": doc}, upsert=True)
    cree = (getattr(resultat, "upserted_id", None) is not None
            or getattr(resultat, "matched_count", 1) == 0)
    if not cree:
        return None
    evenements.publier("*", "notification.creee", notification=doc)
    return doc
