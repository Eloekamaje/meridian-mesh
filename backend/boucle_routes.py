"""API de lecture de la boucle canonique d'entreprise.

Lecture seule : les objets sont lus dans ``objet_entreprise`` (Postgres) via
:mod:`jumeau.entreprise_depot` et :mod:`jumeau.boucle`. Aucune route n'écrit.

Le tenant est résolu par :mod:`jumeau.tenant`. En mode demo seulement, l'absence de ``X-Tenant`` vaut ``local`` ;
hors demo (proxy, OIDC, production), l'en-tête est obligatoire et un en-tête vide ou invalide est refusé. Aucun repli
silencieux n'est fait en production. Si un tenant authentifié est déjà posé sur ``request.state.tenant``, il fait foi
et un ``X-Tenant`` différent est refusé. Les en-têtes ``X-Persona`` / ``X-Espace`` restent les contextes d'usage de la
démonstration.
"""
from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
import math
import os
import re
import unicodedata
from urllib.parse import parse_qsl, unquote_plus, urlsplit

import psycopg
from fastapi import APIRouter, Header, HTTPException, Query, Request
from psycopg.rows import dict_row

from jumeau import boucle, entreprise_depot, modele_entreprise
from jumeau.tenant import TenantError, exiger_tenant, normaliser_slug, resoudre_tenant
from seed_data import ESPACES, PERSONAS

router = APIRouter(prefix="/boucle", tags=["boucle"])

_DSN_MANQUANT = "Couche cognitive non configurée (JUMEAU_PG_DSN)"
_DSN_INDISPONIBLE = "Couche cognitive indisponible"
_FAMILLES = frozenset(modele_entreprise.FAMILLES)
_MODES = frozenset(modele_entreprise.MODES)
_TYPES = frozenset(modele_entreprise.TYPES_OBJET)

_MARQUEURS_SECRETS = ("password", "passwd", "secret", "token", "credential", "authorization")
_CLES_SECRETES = frozenset({
    "pwd", "pass", "auth", "key", "apikey", "api_key", "api-key", "access_key", "accesskey",
    "private_key", "privatekey", "client_secret", "clientsecret", "bearer", "password", "passwd",
})
_JETON_SENSIBLE = re.compile(
    r"(?i)(?:\bbearer\s+[A-Za-z0-9_.~+/=-]{12,}|\bsk-[A-Za-z0-9_-]{8,}|"
    r"\bgh[pousr]_[A-Za-z0-9]{10,}|\bxox[baprs]-[A-Za-z0-9-]{10,})"
)


def _normaliser(valeur, *, minuscule: bool = False) -> str:
    texte = unicodedata.normalize("NFKD", str(valeur or ""))
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    texte = "".join(c if c.isalnum() else "_" for c in texte).strip("_")
    while "__" in texte:
        texte = texte.replace("__", "_")
    return texte.lower() if minuscule else texte.upper()


def _tenant(request: Request, x_tenant: str | None) -> str:
    """Résout le tenant de la requête, sans repli implicite hors demo."""
    mode = getattr(request.state, "auth_mode", None)
    authentifie = getattr(request.state, "tenant", None)
    try:
        if authentifie is not None:
            contexte = resoudre_tenant(authentifie, auth_mode=mode)
            if x_tenant is not None and normaliser_slug(x_tenant) != contexte.id:
                raise HTTPException(403, "Tenant différent de l'identité authentifiée")
        else:
            contexte = resoudre_tenant(x_tenant, auth_mode=mode)
        tenant = exiger_tenant(contexte).id
    except TenantError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    request.state.tenant = tenant
    return tenant


def _verifier_contexte(x_persona: str, x_espace: str | None) -> None:
    persona = next((p for p in PERSONAS if p["id"] == x_persona), PERSONAS[0])
    if not x_espace or x_espace not in persona["espaces"]:
        espace_id = persona["par_defaut"]
    else:
        espace_id = x_espace
    if not any(e["id"] == espace_id for e in ESPACES):
        raise HTTPException(400, "Espace inconnu")


def _filtres(famille: str | None, type_: str | None, mode: str | None, limite: int) -> dict:
    filtres: dict = {}
    if famille is not None:
        valeur = _normaliser(famille, minuscule=True)
        if valeur not in _FAMILLES:
            raise HTTPException(400, f"Famille inconnue : {famille!r}")
        filtres["famille"] = valeur
    if type_ is not None:
        valeur = _normaliser(type_)
        if valeur not in _TYPES:
            raise HTTPException(400, f"Type inconnu : {type_!r}")
        filtres["type_"] = valeur
    if mode is not None:
        valeur = _normaliser(mode)
        if valeur not in _MODES:
            raise HTTPException(400, f"Mode inconnu : {mode!r}")
        filtres["mode"] = valeur
    filtres["limite"] = max(1, min(int(limite), 1000))
    return filtres


def _dsn() -> str:
    dsn = os.environ.get("JUMEAU_PG_DSN")
    if not dsn:
        raise HTTPException(503, _DSN_MANQUANT)
    return dsn


def _cle_sensible(cle) -> bool:
    normalisee = unquote_plus(str(cle)).strip().lower()
    if normalisee.endswith(("_ref", "-ref", "_reference", "-reference")):
        return False
    compacte = normalisee.replace("-", "_")
    if compacte in _CLES_SECRETES:
        return True
    if compacte.endswith("_key"):
        return True
    return any(marque in compacte for marque in _MARQUEURS_SECRETS)


def _url_porte_un_secret(url: str) -> bool:
    try:
        parties = urlsplit(url)
    except (ValueError, UnicodeError):
        return True
    if parties.username is not None or parties.password is not None or "@" in parties.netloc:
        return True
    return any(
        _cle_sensible(cle) and valeur not in ("", "***")
        for cle, valeur in parse_qsl(parties.query, keep_blank_values=True)
    )


def _assainir(valeur):
    if isinstance(valeur, Mapping):
        resultat = {}
        for cle, contenu in valeur.items():
            nom = str(cle)
            resultat[nom] = "***" if _cle_sensible(nom) else _assainir(contenu)
        return resultat
    if isinstance(valeur, (list, tuple, set, frozenset)):
        return [_assainir(element) for element in valeur]
    if isinstance(valeur, Decimal):
        return float(valeur)
    if isinstance(valeur, (datetime, date)):
        return valeur.isoformat()
    if isinstance(valeur, str):
        if _JETON_SENSIBLE.search(valeur) or _url_porte_un_secret(valeur):
            return "***"
        return valeur
    if isinstance(valeur, float) and not math.isfinite(valeur):
        return str(valeur)
    if valeur is None or isinstance(valeur, (bool, int, float)):
        return valeur
    return _assainir(str(valeur))


def _objet_public(ligne: Mapping) -> dict:
    objet = dict(ligne)
    donnees = objet.get("donnees")
    if isinstance(donnees, Mapping):
        objet["donnees"] = {
            str(cle): valeur for cle, valeur in donnees.items() if str(cle) != "_historique"
        }
    return _assainir(objet)


async def _dans_le_thread(action):
    try:
        return await asyncio.to_thread(action)
    except HTTPException:
        raise
    except entreprise_depot.ObjetInvalide as exc:
        raise HTTPException(400, str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(503, _DSN_INDISPONIBLE) from exc


@router.get("/objets")
async def lister_objets(
    request: Request,
    famille: str | None = Query(None, max_length=64),
    type_: str | None = Query(None, alias="type", max_length=64),
    mode: str | None = Query(None, max_length=32),
    limite: int = Query(100, ge=1, le=1000),
    x_persona: str = Header("architecte", max_length=64),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Liste les objets canoniques du tenant, filtrés par famille, type, mode et bornés par ``limite``."""
    _verifier_contexte(x_persona, x_espace)
    tenant = _tenant(request, x_tenant)
    filtres = _filtres(famille, type_, mode, limite)
    dsn = _dsn()

    def lire():
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            return entreprise_depot.lister_objets(conn, tenant, **filtres)

    objets = await _dans_le_thread(lire)
    return {"tenant": tenant, "objets": _assainir(objets)}


@router.get("/objets/{objet_id}")
async def lire_objet(
    objet_id: str,
    request: Request,
    historique: bool = Query(False),
    x_persona: str = Header("architecte", max_length=64),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Lit un objet du tenant ; ``historique=true`` ajoute sa chaîne canonique et ses versions conservées."""
    _verifier_contexte(x_persona, x_espace)
    tenant = _tenant(request, x_tenant)
    dsn = _dsn()

    def lire():
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            return boucle.lire_boucle(conn, tenant, objet_id, historique=historique, as_dict=True)

    resultat = await _dans_le_thread(lire)
    if resultat is None:
        raise HTTPException(404, "Objet introuvable")

    objet = {cle: valeur for cle, valeur in resultat.items() if cle not in ("chaine", "historique")}
    reponse = {"tenant": tenant, "objet": _objet_public(objet)}
    if historique:
        reponse["chaine"] = [_objet_public(element) for element in resultat.get("chaine") or []]
        reponse["historique"] = _assainir(resultat.get("historique") or [])
    return reponse


@router.get("/synthese")
async def synthese(
    request: Request,
    x_persona: str = Header("architecte", max_length=64),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Compte les objets du tenant par famille, type et mode, sans exposer leur contenu."""
    _verifier_contexte(x_persona, x_espace)
    tenant = _tenant(request, x_tenant)
    dsn = _dsn()

    def lire():
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                return cur.execute(
                    "SELECT famille, type, mode, count(*) AS nombre FROM objet_entreprise "
                    "WHERE tenant_id = %s GROUP BY famille, type, mode ORDER BY famille, type, mode",
                    (tenant,),
                ).fetchall()

    lignes = await _dans_le_thread(lire)
    familles: dict[str, int] = {}
    types: dict[str, int] = {}
    modes: dict[str, int] = {}
    total = 0
    for ligne in lignes:
        nombre = int(ligne.get("nombre") or 0)
        if nombre <= 0:
            continue
        total += nombre
        for compteur, cle in ((familles, ligne.get("famille")), (types, ligne.get("type")),
                              (modes, ligne.get("mode"))):
            if cle:
                compteur[str(cle)] = compteur.get(str(cle), 0) + nombre
    return {
        "tenant": tenant,
        "total": total,
        "familles": {cle: familles[cle] for cle in sorted(familles)},
        "types": {cle: types[cle] for cle in sorted(types)},
        "modes": {cle: modes[cle] for cle in sorted(modes)},
    }
