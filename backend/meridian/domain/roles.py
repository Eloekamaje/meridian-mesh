"""Rôles ADR-0001 : rôles du tenant et mapping des postes vers ces rôles.

Le poste reste un libellé d'identité (``product_owner``, ``Architecte``…) ; le rôle est la
valeur canonique utilisée par les règles d'autorisation. Aucun poste inconnu ne devient un rôle.
"""
from __future__ import annotations

import unicodedata

__all__ = ["ROLES", "ROLE_PAR_POSTE", "ROLES_PUBLICATION", "role_canonique"]

ROLES = (
    "TENANT_ADMIN",
    "PORTFOLIO_OWNER",
    "APPLICATION_OWNER",
    "MAINTAINER",
    "MEMBER",
    "VIEWER",
    "AUDITOR",
)

ROLE_PAR_POSTE = {
    "product_owner": "APPLICATION_OWNER",
    "application_owner": "APPLICATION_OWNER",
    "architecte": "PORTFOLIO_OWNER",
    "portfolio_owner": "PORTFOLIO_OWNER",
    "admin": "TENANT_ADMIN",
    "administrateur": "TENANT_ADMIN",
    "tenant_admin": "TENANT_ADMIN",
    "developpeur": "MAINTAINER",
    "mainteneur": "MAINTAINER",
    "lecteur": "VIEWER",
    "auditeur": "AUDITOR",
}

ROLES_PUBLICATION = {"APPLICATION_OWNER", "PORTFOLIO_OWNER", "TENANT_ADMIN"}

_ROLES_CANONIQUES = {role.casefold(): role for role in ROLES}


def _normaliser(valeur) -> str:
    texte = unicodedata.normalize("NFKD", str(valeur or "").strip())
    texte = "".join(c for c in texte if not unicodedata.combining(c)).casefold()
    return "_".join(texte.replace("-", " ").split())


def role_canonique(valeur) -> str:
    """Rôle ADR-0001 correspondant à un poste ou à un rôle, sinon ``""``.

    La casse, les accents et les séparateurs (espace, tiret) sont normalisés.
    """
    poste = _normaliser(valeur)
    if not poste:
        return ""
    if poste in ROLE_PAR_POSTE:
        return ROLE_PAR_POSTE[poste]
    return _ROLES_CANONIQUES.get(poste, "")
