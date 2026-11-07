"""Tenant de la requête courante, pour les écritures qui n'ont pas de paramètre tenant.

Les routes historiques du Travail ne portent pas le tenant dans leur signature. Le middleware
le pose ici ; le proxy de double écriture le lit pour alimenter la colonne `travail.tenant_id`.
"""
from __future__ import annotations

from contextvars import ContextVar, Token
import os

from meridian.domain.tenant import TenantRequis

_COURANT: ContextVar[str | None] = ContextVar("meridian_tenant_courant", default=None)


def definir(tenant: str | None) -> Token:
    return _COURANT.set(str(tenant).strip() or None if tenant is not None else None)


def reinitialiser(token: Token) -> None:
    _COURANT.reset(token)


def courant(defaut: str = "local") -> str:
    return _COURANT.get() or defaut


def courant_explicite() -> str | None:
    return _COURANT.get()


def courant_requete(defaut: str = "local") -> str:
    """Tenant de la requête, sans repli implicite hors mode demo.

    Le contexte d'authentification est prioritaire ; ``JUMEAU_TENANT`` sert aux
    déploiements mono-tenant explicites. Hors demo (proxy, OIDC, production) et sans
    contexte, ``TenantRequis`` est levé au lieu de fabriquer ``local``.
    """
    explicite = _COURANT.get()
    if explicite:
        return explicite
    env = os.environ.get("JUMEAU_TENANT")
    if env:
        return env
    mode = str(os.environ.get("AUTH_MODE", "demo")).strip().lower()
    production = str(os.environ.get("APP_ENV", "")).strip().lower() in {"prod", "production"}
    if mode == "demo" and not production:
        return defaut
    raise TenantRequis("tenant requis hors du mode demo")


def courant_ou_env(defaut: str = "local") -> str:
    """Alias historique de :func:`courant_requete`."""
    return courant_requete(defaut)
