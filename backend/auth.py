"""Identité serveur : demo explicite, proxy authentifiant ou OIDC.

Le backend ne connaît qu'un acteur (l'utilisateur authentifié, sinon ``demo``) et un tenant. Aucun en-tête
client ne choisit l'acteur : en mode proxy ou OIDC, il vient de l'identité vérifiée.
"""
import logging
import os
import time

import requests
from fastapi import Request
from fastapi.responses import JSONResponse
from jose import jwk, jwt

from meridian.domain import tenant as tenant_context

logger = logging.getLogger("meridian.auth")
MODES = {"demo", "proxy", "oidc"}
_JWKS = {"url": None, "expire": 0, "cles": []}


class AuthError(Exception):
    def __init__(self, status, detail):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def mode():
    return os.getenv("AUTH_MODE", "demo").strip().lower()


def acteur(request: Request) -> str:
    """L'acteur de la requête : utilisateur authentifié, sinon ``demo``."""
    return getattr(request.state, "utilisateur", None) or "demo"


def _tenant_entete(request):
    """Tenant posé par un proxy authentifiant, dans un en-tête de confiance."""
    nom = os.getenv("AUTH_TENANT_HEADER", "X-Auth-Request-Tenant")
    valeur = (request.headers.get(nom) or "").strip()
    if not valeur:
        return None
    try:
        return tenant_context.normaliser_slug(valeur)
    except tenant_context.TenantInvalide:
        raise AuthError(403, "Tenant de l'identité invalide")


def _tenant_oidc(request):
    """Claim tenant du jeton OIDC, après vérification de la signature."""
    claims = getattr(request.state, "oidc_claims", None) or {}
    valeur = claims.get(os.getenv("AUTH_TENANT_CLAIM", "tenant"))
    if valeur is None:
        return None
    try:
        return tenant_context.normaliser_slug(str(valeur))
    except tenant_context.TenantInvalide:
        raise AuthError(403, "Tenant de l'identité invalide")


def _tenant_identite(request, mode_courant):
    if mode_courant == "proxy":
        return _tenant_entete(request)
    if mode_courant == "oidc":
        return _tenant_oidc(request)
    return None


def _acteur_demo(request):
    return "demo", None


def _acteur_proxy(request):
    attendu = os.getenv("AUTH_PROXY_SECRET", "")
    if not attendu:
        raise AuthError(503, "AUTH_PROXY_SECRET n'est pas configuré")
    entete_secret = os.getenv("AUTH_PROXY_SECRET_HEADER", "X-Auth-Proxy-Secret")
    if request.headers.get(entete_secret) != attendu:
        raise AuthError(401, "Proxy non authentifié")
    utilisateur = request.headers.get(os.getenv("AUTH_USER_HEADER", "X-Auth-Request-User"), "").strip()
    if not utilisateur:
        raise AuthError(403, "Identité absente de l'authentification proxy")
    return utilisateur, utilisateur


def _cle_oidc(entete):
    url = os.getenv("AUTH_OIDC_JWKS_URL", "").strip()
    if not url:
        raise AuthError(503, "AUTH_OIDC_JWKS_URL n'est pas configuré")
    maintenant = time.time()
    if _JWKS["url"] != url or _JWKS["expire"] < maintenant:
        try:
            reponse = requests.get(url, timeout=5)
            reponse.raise_for_status()
            _JWKS["cles"] = reponse.json().get("keys", [])
            _JWKS["url"] = url
            _JWKS["expire"] = maintenant + 300
        except Exception:
            raise AuthError(503, "JWKS OIDC injoignable")
    kid = entete.get("kid")
    cle = next((k for k in _JWKS["cles"] if k.get("kid") == kid), None)
    if cle is None and len(_JWKS["cles"]) == 1:
        cle = _JWKS["cles"][0]
    if cle is None:
        raise AuthError(401, "Clé de signature OIDC inconnue")
    return jwk.construct(cle, algorithm=entete.get("alg"))


def _acteur_oidc(request):
    entete_nom = os.getenv("AUTH_TOKEN_HEADER", "Authorization")
    prefixe = os.getenv("AUTH_TOKEN_PREFIX", "Bearer ")
    jeton = (request.headers.get(entete_nom) or "").strip()
    if prefixe and jeton.startswith(prefixe):
        jeton = jeton[len(prefixe):].strip()
    if not jeton:
        raise AuthError(401, "Jeton OIDC absent")
    try:
        entete = jwt.get_unverified_header(jeton)
        alg = entete.get("alg", "")
        secret = os.getenv("AUTH_OIDC_SECRET", "")
        if secret and alg.startswith("HS"):
            cle = secret
        else:
            cle = _cle_oidc(entete)
        claims = jwt.decode(
            jeton, cle, algorithms=[alg] if alg else None,
            audience=os.getenv("AUTH_AUDIENCE") or None,
            issuer=os.getenv("AUTH_ISSUER") or None,
        )
        request.state.oidc_claims = claims
    except AuthError:
        raise
    except Exception:
        raise AuthError(401, "Jeton OIDC invalide")
    utilisateur = claims.get("name") or claims.get("preferred_username") or claims.get("email") or claims.get("sub")
    if not utilisateur:
        raise AuthError(403, "Identité absente du jeton OIDC")
    return str(utilisateur), str(utilisateur)


def resoudre(request):
    mode_courant = mode()
    if mode_courant == "demo":
        acteur_courant, utilisateur = _acteur_demo(request)
    elif mode_courant == "proxy":
        acteur_courant, utilisateur = _acteur_proxy(request)
    elif mode_courant == "oidc":
        acteur_courant, utilisateur = _acteur_oidc(request)
    else:
        raise AuthError(503, f"AUTH_MODE inconnu : {mode_courant}")
    return acteur_courant, utilisateur


async def middleware(request: Request, call_next):
    chemin = request.url.path
    if request.method == "OPTIONS" or chemin == "/api/health" or not chemin.startswith("/api"):
        return await call_next(request)
    mode_courant = mode()
    try:
        acteur_courant, utilisateur = resoudre(request)
        tenant = _tenant_identite(request, mode_courant)
        if mode_courant in ("proxy", "oidc") and tenant is None:
            raise AuthError(403, "Tenant absent de l'identité authentifiée")
        entete_tenant = request.headers.get("x-tenant")
        if tenant is not None and entete_tenant is not None:
            try:
                entete_normalise = tenant_context.normaliser_slug(entete_tenant)
            except tenant_context.TenantInvalide:
                raise AuthError(403, "Tenant invalide")
            if entete_normalise != tenant:
                raise AuthError(403, "Tenant différent de l'identité authentifiée")
    except AuthError as exc:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status)
    entetes = [
        (nom, valeur) for nom, valeur in request.scope["headers"]
        if not (nom.lower() == b"x-tenant" and tenant is not None)
    ]
    if tenant is not None:
        entetes.append((b"x-tenant", tenant.encode("utf-8")))
    request.scope["headers"] = entetes
    request.state.acteur = acteur_courant
    request.state.auth_mode = mode_courant
    request.state.utilisateur = utilisateur
    if tenant is not None:
        request.state.tenant = tenant
        request.state.auth_tenant = tenant
    return await call_next(request)


def installer(app):
    app.middleware("http")(middleware)


def verifier_config():
    mode_courant = mode()
    if mode_courant not in MODES:
        raise RuntimeError(f"AUTH_MODE inconnu : {mode_courant}")
    if mode_courant == "proxy" and not os.getenv("AUTH_PROXY_SECRET"):
        raise RuntimeError("AUTH_PROXY_SECRET est requis en mode proxy")
    if mode_courant == "oidc" and not (os.getenv("AUTH_OIDC_SECRET") or os.getenv("AUTH_OIDC_JWKS_URL")):
        raise RuntimeError("AUTH_OIDC_SECRET ou AUTH_OIDC_JWKS_URL est requis en mode oidc")
    if mode_courant == "demo":
        if os.getenv("APP_ENV", "").strip().lower() in {"prod", "production"}:
            raise RuntimeError("AUTH_MODE=demo est interdit en production (APP_ENV=production)")
        logger.warning("AUTH_MODE=demo : aucun utilisateur authentifié, l'acteur vaut demo")
