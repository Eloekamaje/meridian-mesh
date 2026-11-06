"""Identité serveur : demo explicite, proxy authentifiant ou OIDC.

Le backend ne connaît qu'un acteur (l'utilisateur authentifié, sinon ``demo``) et un tenant. Aucun en-tête
client ne choisit l'acteur : en mode proxy ou OIDC, il vient de l'identité vérifiée.
"""
import hashlib
import logging
import os
import secrets
import time
from datetime import datetime, timedelta, timezone

import requests
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from jose import jwk, jwt
from motor.motor_asyncio import AsyncIOMotorClient
from passlib.context import CryptContext
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from limites import autoriser as autoriser_debit
from meridian.domain import tenant as tenant_context
from meridian.application import tenant_context as contexte_ecriture

logger = logging.getLogger("meridian.auth")
MODES = {"demo", "local", "proxy", "oidc"}
_JWKS = {"url": None, "expire": 0, "cles": []}
_MONGO = {"client": None, "db": None}
_COOKIE = "meridian_session"
_POSTES = (
    ("analyste", "Analyste", "analyste_fonctionnel", "proposition"),
    ("architecte", "Architecte", "architecte", "proposition"),
    ("product_owner", "Product Owner", "product_owner", "proposition"),
    ("developpeur", "Développeur", "developpeur", "proposition"),
    ("scrum_master", "Scrum Master", "scrum_master", "proposition"),
    ("chef_projet", "Chef de projet / PMO", "chef_projet", "proposition"),
    ("directeur", "Directeur", "directeur", "proposition"),
    ("finance", "Finance", "directeur", "proposition"),
    ("support", "Ops / Support", "support", "proposition"),
    ("risque", "Risque / Conformité", "risque", "proposition"),
    ("data_steward", "Data Steward", "data_steward", "proposition"),
    ("administrateur", "Administrateur", "generaliste", "lecture"),
)
_POSTES_PAR_ID = {ident: (libelle, profil, autorite) for ident, libelle, profil, autorite in _POSTES}
_MDP = CryptContext(schemes=["bcrypt"], deprecated="auto")


class Inscription(BaseModel):
    nom: str = Field(min_length=1, max_length=240)
    email: str = Field(min_length=3, max_length=320)
    mot_de_passe: str = Field(min_length=8, max_length=200)
    poste: str = Field(min_length=1, max_length=40)
    invitation: str | None = Field(None, max_length=200)


class Connexion(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    mot_de_passe: str = Field(min_length=1, max_length=200)


router = APIRouter(prefix="/auth", tags=["auth"])


def _db():
    if _MONGO["db"] is None:
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        _MONGO["client"] = client
        _MONGO["db"] = client[os.environ["DB_NAME"]]
    return _MONGO["db"]


async def initialiser():
    """Crée les index d'identité locaux (idempotent)."""
    db = _db()
    await db.utilisateurs.create_index("email", unique=True)
    await db.utilisateurs.create_index("id", unique=True)
    await db.sessions.create_index("id", unique=True)
    await db.invitations.create_index("code", unique=True)


def _email(valeur) -> str:
    return str(valeur or "").strip().lower()


def _hash_jeton(jeton: str) -> str:
    return hashlib.sha256(jeton.encode("utf-8")).hexdigest()


def _maintenant():
    return datetime.now(timezone.utc)


def _moi(user: dict) -> dict:
    return {
        "acteur": user.get("id"),
        "utilisateur": user.get("nom") or user.get("email"),
        "nom": user.get("nom"),
        "email": user.get("email"),
        "poste": user.get("poste"),
        "poste_libelle": user.get("poste_libelle"),
        "profil": user.get("profil_id"),
        "autorite": user.get("autorite") or "proposition",
        "tenant": user.get("tenant_id"),
        "espace": user.get("espace_defaut"),
        "auth_mode": "local",
    }


async def _creer_session(reponse: Response, user: dict):
    jeton = secrets.token_urlsafe(40)
    expire = _maintenant() + timedelta(hours=int(os.getenv("AUTH_SESSION_HEURES", "168")))
    await _db().sessions.insert_one({
        "id": _hash_jeton(jeton), "user_id": user["id"], "tenant_id": user["tenant_id"],
        "cree_le": _maintenant().isoformat(), "expire_le": expire.isoformat(),
    })
    reponse.set_cookie(
        _COOKIE, jeton, max_age=int((expire - _maintenant()).total_seconds()),
        httponly=True, samesite="lax",
        secure=os.getenv("AUTH_COOKIE_SECURE", "0").strip().lower() in {"1", "true", "oui", "yes"},
        path="/",
    )
    return user


async def contexte_acteur(identifiant: str) -> dict:
    """Contexte stable d'un acteur local ; vide en mode démo ou si le compte est inconnu."""
    if not identifiant or identifiant == "demo":
        return {}
    user = await _db().utilisateurs.find_one({"id": identifiant}, {"_id": 0})
    if not user or user.get("statut") != "actif":
        return {}
    return {
        "acteur": user.get("id"), "nom": user.get("nom"),
        "poste": user.get("poste_libelle") or user.get("poste"),
        "profil": user.get("profil_id"), "autorite": user.get("autorite") or "proposition",
        "espace": user.get("espace_defaut"), "tenant": user.get("tenant_id"),
    }


async def _session(request: Request) -> dict | None:
    jeton = request.cookies.get(_COOKIE)
    if not jeton:
        return None
    session = await _db().sessions.find_one({"id": _hash_jeton(jeton)})
    if not session:
        return None
    try:
        expire = datetime.fromisoformat(str(session.get("expire_le")))
        if expire.tzinfo is None:
            expire = expire.replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    if expire <= _maintenant():
        await _db().sessions.delete_one({"id": session["id"]})
        return None
    user = await _db().utilisateurs.find_one({"id": session["user_id"]}, {"_id": 0})
    if not user or user.get("statut") != "actif":
        return None
    return user


async def _acteur_local(request: Request):
    user = await _session(request)
    if not user:
        raise AuthError(401, "Authentification requise")
    request.state.utilisateur_local = user
    return user["id"], user.get("nom") or user.get("email")


@router.get("/postes")
def postes():
    return [{"id": ident, "libelle": libelle, "profil": profil}
            for ident, libelle, profil, _ in _POSTES]


@router.post("/signup")
async def signup(payload: Inscription, response: Response, request: Request):
    if not await autoriser_debit(f"auth-signup:{request.client.host if request.client else 'inconnu'}",
                                 int(os.getenv("AUTH_RATE_MAX", "10")),
                                 int(os.getenv("AUTH_RATE_FENETRE", "60"))):
        raise HTTPException(429, "Trop de tentatives, réessayez plus tard")
    email = _email(payload.email)
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(400, "Adresse électronique invalide")
    if payload.poste not in _POSTES_PAR_ID:
        raise HTTPException(400, "Poste inconnu")
    db = _db()
    if await db.utilisateurs.find_one({"email": email}):
        raise HTTPException(409, "Un compte existe déjà pour cette adresse")
    libelle_poste, profil_id, autorite = _POSTES_PAR_ID[payload.poste]
    user_id = "usr-" + secrets.token_hex(12)
    tenant = os.getenv("AUTH_LOCAL_TENANT", "demo").strip() or "demo"
    espace = os.getenv("AUTH_LOCAL_ESPACE", "mesh-global").strip() or "mesh-global"
    equipes = []
    if payload.invitation:
        invitation = await db.invitations.find_one({"code": _hash_jeton(payload.invitation), "utilise_le": None})
        if not invitation:
            raise HTTPException(403, "Invitation invalide ou déjà utilisée")
        expire = invitation.get("expire_le")
        if expire:
            try:
                date_expire = datetime.fromisoformat(str(expire))
                if date_expire.tzinfo is None:
                    date_expire = date_expire.replace(tzinfo=timezone.utc)
                if date_expire <= _maintenant():
                    raise HTTPException(403, "Invitation expirée")
            except ValueError:
                raise HTTPException(403, "Invitation invalide")
        if invitation.get("email") and invitation["email"] != email:
            raise HTTPException(403, "Cette invitation est réservée à une autre adresse")
        tenant = invitation.get("tenant_id") or tenant
        espace = invitation.get("espace_id") or espace
        equipes = list(invitation.get("equipes") or ())
        for valeur in (invitation.get("equipe_id"), invitation.get("equipe")):
            if valeur and valeur not in equipes:
                equipes.append(valeur)
    user = {
        "id": user_id, "tenant_id": tenant, "email": email, "nom": " ".join(payload.nom.split())[:240],
        "poste": payload.poste, "poste_libelle": libelle_poste, "profil_id": profil_id,
        "autorite": autorite, "espace_defaut": espace, "equipes": equipes, "auth_provider": "local",
        "external_subject": None, "statut": "actif",
        "mot_de_passe_hash": _MDP.hash(payload.mot_de_passe),
        "cree_le": _maintenant().isoformat(), "maj_le": _maintenant().isoformat(),
    }
    try:
        await db.utilisateurs.insert_one(dict(user))
    except DuplicateKeyError:
        raise HTTPException(409, "Un compte existe déjà pour cette adresse")
    if payload.invitation:
        await db.invitations.update_one(
            {"code": _hash_jeton(payload.invitation)},
            {"$set": {"utilise_le": _maintenant().isoformat(), "utilise_par": user_id}})
    await _creer_session(response, user)
    return _moi(user)


@router.post("/login")
async def login(payload: Connexion, response: Response, request: Request):
    if not await autoriser_debit(f"auth-login:{request.client.host if request.client else 'inconnu'}",
                                 int(os.getenv("AUTH_RATE_MAX", "10")),
                                 int(os.getenv("AUTH_RATE_FENETRE", "60"))):
        raise HTTPException(429, "Trop de tentatives, réessayez plus tard")
    user = await _db().utilisateurs.find_one({"email": _email(payload.email)})
    if not user or not _MDP.verify(payload.mot_de_passe, user.get("mot_de_passe_hash", "")):
        raise HTTPException(401, "Identifiants invalides")
    if user.get("statut") != "actif":
        raise HTTPException(403, "Compte désactivé")
    await _creer_session(response, user)
    return _moi(user)


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response):
    jeton = request.cookies.get(_COOKIE)
    if jeton:
        await _db().sessions.delete_one({"id": _hash_jeton(jeton)})
    response.delete_cookie(_COOKIE, path="/")
    response.status_code = 204
    return response


class AuthError(Exception):
    def __init__(self, status, detail):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def mode():
    return os.getenv("AUTH_MODE", "demo").strip().lower()


def acteur(request: Request) -> str:
    """L'acteur de la requête : identifiant stable authentifié, sinon ``demo``."""
    return getattr(request.state, "acteur", None) or getattr(request.state, "utilisateur", None) or "demo"


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
        request.state.role = claims.get("role") or (claims.get("roles") or [None])[0]
        request.state.equipe = claims.get("equipe") or claims.get("team")
        equipes_oidc = claims.get("equipes") or claims.get("groups") or claims.get("teams") or []
        request.state.equipes = list(equipes_oidc) if isinstance(equipes_oidc, (list, tuple)) else [equipes_oidc]
        request.state.perimetre = claims.get("perimetre") or claims.get("perimeter") or claims.get("espace")
    except AuthError:
        raise
    except Exception:
        raise AuthError(401, "Jeton OIDC invalide")
    utilisateur = claims.get("name") or claims.get("preferred_username") or claims.get("email") or claims.get("sub")
    if not utilisateur:
        raise AuthError(403, "Identité absente du jeton OIDC")
    return str(utilisateur), str(utilisateur)


async def resoudre(request):
    mode_courant = mode()
    if mode_courant == "demo":
        acteur_courant, utilisateur = _acteur_demo(request)
    elif mode_courant == "local":
        acteur_courant, utilisateur = await _acteur_local(request)
    elif mode_courant == "proxy":
        acteur_courant, utilisateur = _acteur_proxy(request)
    elif mode_courant == "oidc":
        acteur_courant, utilisateur = _acteur_oidc(request)
    else:
        raise AuthError(503, f"AUTH_MODE inconnu : {mode_courant}")
    return acteur_courant, utilisateur


async def middleware(request: Request, call_next):
    chemin = request.url.path
    if (request.method == "OPTIONS" or chemin == "/api/health"
            or chemin.startswith("/api/auth/") or not chemin.startswith("/api")):
        return await call_next(request)
    mode_courant = mode()
    try:
        acteur_courant, utilisateur = await resoudre(request)
        local_user = getattr(request.state, "utilisateur_local", None)
        tenant = local_user.get("tenant_id") if local_user else _tenant_identite(request, mode_courant)
        if mode_courant in ("proxy", "oidc") and tenant is None:
            raise AuthError(403, "Tenant absent de l'identité authentifiée")
        entete_tenant = request.headers.get("x-tenant")
        if mode_courant != "local" and tenant is not None and entete_tenant is not None:
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
    local_user = getattr(request.state, "utilisateur_local", None)
    if local_user:
        request.state.poste = local_user.get("poste")
        request.state.poste_libelle = local_user.get("poste_libelle")
        request.state.profil_id = local_user.get("profil_id")
        request.state.autorite = local_user.get("autorite") or "proposition"
        request.state.role = local_user.get("role") or local_user.get("poste")
        request.state.equipe = local_user.get("equipe") or local_user.get("equipe_id")
        equipes_locales = list(local_user.get("equipes") or ())
        for valeur in (local_user.get("equipe"), local_user.get("equipe_id")):
            if valeur and valeur not in equipes_locales:
                equipes_locales.append(valeur)
        request.state.equipes = equipes_locales
        request.state.perimetre = (local_user.get("perimetre_id") or local_user.get("perimetre")
                                   or local_user.get("espace_defaut"))
        request.state.espace = local_user.get("espace_defaut")
        request.state.tenant = local_user.get("tenant_id")
        request.state.auth_tenant = local_user.get("tenant_id")
    if tenant is not None:
        request.state.tenant = tenant
        request.state.auth_tenant = tenant
    contexte = tenant
    if contexte is None:
        entete_demo = (request.headers.get("x-tenant") or "").strip()
        if entete_demo:
            try:
                contexte = tenant_context.normaliser_slug(entete_demo)
            except tenant_context.TenantInvalide:
                contexte = None
    jeton = contexte_ecriture.definir(contexte or "local")
    try:
        return await call_next(request)
    finally:
        contexte_ecriture.reinitialiser(jeton)


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
