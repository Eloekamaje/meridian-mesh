"""Identité serveur : demo explicite, proxy authentifiant ou OIDC.

En mode `proxy` ou `oidc`, le header `X-Persona` du client est ignoré : la persona est résolue depuis
l'identité vérifiée, puis réinjectée dans la requête pour les routes existantes.
"""
import json
import logging
import os
import re
import time

import requests
from fastapi import Request
from fastapi.responses import JSONResponse
from jose import jwk, jwt

from jumeau import tenant as tenant_context
from seed_data import PERSONAS

logger = logging.getLogger("meridian.auth")
PERSONA_IDS = {p["id"] for p in PERSONAS}
MODES = {"demo", "proxy", "oidc"}
_JWKS = {"url": None, "expire": 0, "cles": []}


class AuthError(Exception):
    def __init__(self, status, detail):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def mode():
    return os.getenv("AUTH_MODE", "demo").strip().lower()


def _mapping():
    brut = os.getenv("AUTH_PERSONA_MAP", "").strip()
    if not brut:
        return {}
    try:
        valeur = json.loads(brut)
        return valeur if isinstance(valeur, dict) else {}
    except ValueError:
        logger.error("AUTH_PERSONA_MAP n'est pas un JSON valide")
        return {}


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


def _choisir(candidats):
    correspondance = _mapping()
    for candidat in candidats:
        if candidat and correspondance.get(candidat) in PERSONA_IDS:
            return correspondance[candidat]
    for candidat in candidats:
        if candidat in PERSONA_IDS:
            return candidat
    return None


def _groupes(valeur):
    if isinstance(valeur, list):
        return [str(v).strip() for v in valeur if str(v).strip()]
    if isinstance(valeur, str):
        return [g for g in re.split(r"[\s,]+", valeur) if g]
    return []


def _persona_demo(request):
    persona = request.headers.get("x-persona") or "architecte"
    if persona not in PERSONA_IDS:
        raise AuthError(401, "Persona inconnu")
    return persona, None


def _persona_proxy(request):
    attendu = os.getenv("AUTH_PROXY_SECRET", "")
    if not attendu:
        raise AuthError(503, "AUTH_PROXY_SECRET n'est pas configuré")
    entete_secret = os.getenv("AUTH_PROXY_SECRET_HEADER", "X-Auth-Proxy-Secret")
    if request.headers.get(entete_secret) != attendu:
        raise AuthError(401, "Proxy non authentifié")
    utilisateur = request.headers.get(os.getenv("AUTH_USER_HEADER", "X-Auth-Request-User"), "").strip()
    groupes = _groupes(request.headers.get(os.getenv("AUTH_GROUPS_HEADER", "X-Auth-Request-Groups"), ""))
    persona = _choisir([utilisateur, *groupes])
    if not persona:
        raise AuthError(403, "Aucune persona autorisée pour cette identité")
    return persona, utilisateur or None


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


def _persona_oidc(request):
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
    persona_claim = claims.get(os.getenv("AUTH_PERSONA_CLAIM", "persona"))
    groupes = _groupes(claims.get(os.getenv("AUTH_GROUPS_CLAIM", "groups")))
    persona = _choisir([persona_claim, *groupes])
    if not persona:
        raise AuthError(403, "Aucune persona autorisée pour cette identité")
    return persona, utilisateur or None


def resoudre(request):
    mode_courant = mode()
    if mode_courant == "demo":
        persona, utilisateur = _persona_demo(request)
    elif mode_courant == "proxy":
        persona, utilisateur = _persona_proxy(request)
    elif mode_courant == "oidc":
        persona, utilisateur = _persona_oidc(request)
    else:
        raise AuthError(503, f"AUTH_MODE inconnu : {mode_courant}")
    return persona, utilisateur


async def middleware(request: Request, call_next):
    chemin = request.url.path
    if request.method == "OPTIONS" or chemin == "/api/health" or not chemin.startswith("/api"):
        return await call_next(request)
    mode_courant = mode()
    try:
        persona, utilisateur = resoudre(request)
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
        if nom.lower() != b"x-persona" and not (nom.lower() == b"x-tenant" and tenant is not None)
    ]
    entetes.append((b"x-persona", persona.encode("utf-8")))
    if tenant is not None:
        entetes.append((b"x-tenant", tenant.encode("utf-8")))
    request.scope["headers"] = entetes
    request.state.persona = persona
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
        logger.warning("AUTH_MODE=demo : X-Persona est accepté sans authentification ; interdit en production")
