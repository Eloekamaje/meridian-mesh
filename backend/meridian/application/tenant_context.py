"""Tenant de la requête courante, pour les écritures qui n'ont pas de paramètre tenant.

Les routes historiques du Travail ne portent pas le tenant dans leur signature. Le middleware
le pose ici ; le proxy de double écriture le lit pour alimenter la colonne `travail.tenant_id`.
"""
from __future__ import annotations

from contextvars import ContextVar, Token

_COURANT: ContextVar[str | None] = ContextVar("meridian_tenant_courant", default=None)


def definir(tenant: str | None) -> Token:
    return _COURANT.set(str(tenant).strip() or None if tenant is not None else None)


def reinitialiser(token: Token) -> None:
    _COURANT.reset(token)


def courant(defaut: str = "local") -> str:
    return _COURANT.get() or defaut


def courant_explicite() -> str | None:
    return _COURANT.get()
