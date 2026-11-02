"""Rôles projet, périmètres et autorisations du pilotage.

Un rôle est une autorisation réelle ; une lentille ne donne jamais de droit. Les rôles sont lus dans
Postgres et les actions sont vérifiées avant l'agrégation.
"""
from __future__ import annotations

from meridian.domain import planification as domaine

PRIORITE_ROLES = {
    "observateur": 0, "audit": 1, "membre": 2, "ops": 3, "architecte": 4,
    "sponsor": 5, "finance": 6, "scrum_master": 7, "pmo": 8,
    "engineering_manager": 9, "po": 10, "admin": 11,
}


class AccesRefuse(PermissionError):
    """Le rôle ou le périmètre ne permet pas l'action demandée."""


def role_effectif(store, conn, tenant: str, acteur: str, *, perimetre_type: str = "tenant",
                  perimetre_id: str | None = None) -> str:
    affectations = store.roles(conn, tenant, acteur)
    retenues = []
    for affectation in affectations:
        meme_type = affectation.get("perimetre_type") == perimetre_type
        if perimetre_type == "tenant" and perimetre_id is None:
            meme_type = True  # une affectation équipe/portefeuille est une autorisation réelle
        meme_id = perimetre_id is None or affectation.get("perimetre_id") in (None, perimetre_id)
        if meme_type and meme_id:
            retenues.append(affectation)
    if not retenues:
        return "observateur"
    return max((a["role"] for a in retenues), key=lambda r: PRIORITE_ROLES.get(r, 0))


def exiger(role: str, action: str) -> None:
    if not domaine.role_autorise(role, action):
        raise AccesRefuse(f"rôle {role} : action {action} refusée")


def perimetres_visibles(store, conn, tenant: str, acteur: str) -> list[dict]:
    return store.roles(conn, tenant, acteur)


def affecter(store, conn, tenant: str, acteur: str, role: str, *, perimetre_type: str = "tenant",
             perimetre_id: str | None = None, debut=None, fin=None,
             source: str = "admin") -> dict:
    domaine.normaliser_role(role)
    identifiant = store.affecter_role(conn, tenant, {
        "acteur": acteur, "role": role, "perimetre_type": perimetre_type,
        "perimetre_id": perimetre_id, "debut": debut, "fin": fin, "source": source,
    })
    return {"id": identifiant, "acteur": acteur, "role": role,
            "perimetre_type": perimetre_type, "perimetre_id": perimetre_id}
