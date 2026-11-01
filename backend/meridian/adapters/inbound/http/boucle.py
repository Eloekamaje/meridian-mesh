"""API de lecture de la boucle canonique d'entreprise.

Lecture seule : les objets sont lus dans ``objet_entreprise`` (Postgres) via
:mod:`meridian.adapters.outbound.postgres.entreprise_depot` et :mod:`meridian.adapters.outbound.postgres.boucle`. Aucune route n'écrit.

Le tenant est résolu par :mod:`meridian.domain.tenant`. En mode demo seulement, l'absence de ``X-Tenant`` vaut ``local`` ;
hors demo (proxy, OIDC, production), l'en-tête est obligatoire et un en-tête vide ou invalide est refusé. Aucun repli
silencieux n'est fait en production. Si un tenant authentifié est déjà posé sur ``request.state.tenant``, il fait foi
et un ``X-Tenant`` différent est refusé. ``X-Espace`` reste un contexte de lecture, jamais une identité.
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

from meridian.adapters.outbound.postgres import boucle
from meridian.adapters.outbound.postgres import entreprise_depot
from meridian.adapters.outbound.neo4j import graph_store
from meridian.domain import modele_entreprise
from meridian.adapters.outbound.postgres import rls
from meridian.domain.tenant import TenantError, exiger_tenant, normaliser_slug, resoudre_tenant
from seed_data import ESPACES

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


def _verifier_espace(x_espace: str | None) -> str:
    """Valide un espace ; l'espace reste un contexte de lecture."""
    if not x_espace:
        return "mesh-global"
    if not any(e["id"] == x_espace for e in ESPACES):
        raise HTTPException(400, "Espace inconnu")
    return x_espace


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


def _executer_graphe(action):
    """Ouvre le graphe, exécute une lecture tenant-scoped et ferme toujours la session."""
    try:
        contexte = graph_store.ouvrir()
    except ValueError as exc:
        raise HTTPException(503, "Graphe non configuré (GRAPH_STORE=neo4j)") from exc
    except RuntimeError as exc:
        raise HTTPException(503, "Graphe indisponible") from exc
    try:
        return action(contexte["store"]), contexte["mode"]
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, "Graphe indisponible") from exc
    finally:
        contexte["fermer"]()


def _cle_sensible(cle) -> bool:
    normalisee = unquote_plus(str(cle)).strip().lower()
    if normalisee.endswith(("_ref", "-ref", "_reference", "-reference")):
        return False
    compacte = normalisee.replace("-", "_")
    # Budgets de contexte : « tokens » est une mesure, pas un secret.
    if compacte in {"tokens", "tokens_estimes", "tokens_utilises", "tokens_memoire",
                    "token_budget", "budget_tokens", "nb_tokens"}:
        return False
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
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Liste les objets canoniques du tenant, filtrés par famille, type, mode et bornés par ``limite``."""
    _verifier_espace(x_espace)
    tenant = _tenant(request, x_tenant)
    filtres = _filtres(famille, type_, mode, limite)
    dsn = _dsn()

    def lire():
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            if rls.est_actif():
                with rls.contexte_tenant(conn, tenant):
                    return entreprise_depot.lister_objets(conn, tenant, **filtres)
            return entreprise_depot.lister_objets(conn, tenant, **filtres)

    objets = await _dans_le_thread(lire)
    return {"tenant": tenant, "objets": _assainir(objets)}


@router.get("/objets/{objet_id}")
async def lire_objet(
    objet_id: str,
    request: Request,
    historique: bool = Query(False),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Lit un objet du tenant ; ``historique=true`` ajoute sa chaîne canonique et ses versions conservées."""
    _verifier_espace(x_espace)
    tenant = _tenant(request, x_tenant)
    dsn = _dsn()

    def lire():
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            if rls.est_actif():
                with rls.contexte_tenant(conn, tenant):
                    return boucle.lire_boucle(conn, tenant, objet_id, historique=historique, as_dict=True)
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
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Compte les objets du tenant par famille, type et mode, sans exposer leur contenu."""
    _verifier_espace(x_espace)
    tenant = _tenant(request, x_tenant)
    dsn = _dsn()

    def lire():
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            if rls.est_actif():
                with rls.contexte_tenant(conn, tenant):
                    with conn.cursor(row_factory=dict_row) as cur:
                        return cur.execute(
                            "SELECT famille, type, mode, count(*) AS nombre FROM objet_entreprise "
                            "WHERE tenant_id = %s GROUP BY famille, type, mode ORDER BY famille, type, mode",
                            (tenant,),
                        ).fetchall()
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


@router.get("/graphe/resume")
async def graphe_resume(
    request: Request,
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Compte les Twins et relations du tenant dans le graph store, sans exposer leur contenu."""
    _verifier_espace(x_espace)
    tenant = _tenant(request, x_tenant)

    def compter(store):
        try:
            etat = store.as_dict(tenant)
        except TypeError:
            etat = store.as_dict()
        if not isinstance(etat, Mapping):
            return {"twins": 0, "relations": 0}
        return {"twins": len(etat.get("noeuds") or []), "relations": len(etat.get("aretes") or [])}

    comptes, mode = await asyncio.to_thread(_executer_graphe, compter)
    return {"tenant": tenant, "mode": mode, **comptes}


@router.get("/graphe/{twin_id}/voisins")
async def graphe_voisins(
    twin_id: str,
    request: Request,
    profondeur: int = Query(1, ge=1, le=8),
    sens: str = Query("sortant", pattern="^(sortant|entrant|les_deux)$"),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Voisinage topologique du twin dans le graph store, borné au tenant authentifié."""
    _verifier_espace(x_espace)
    tenant = _tenant(request, x_tenant)
    if not twin_id.strip() or len(twin_id) > 128:
        raise HTTPException(400, "twin_id invalide")
    voisins, mode = await asyncio.to_thread(
        _executer_graphe,
        lambda store: store.voisins(tenant, twin_id.strip(), profondeur, sens),
    )
    return {"tenant": tenant, "twin": twin_id.strip(), "profondeur": profondeur,
            "sens": sens, "mode": mode, "voisins": _assainir(voisins)}


@router.get("/graphe/{twin_id}/impact")
async def graphe_impact(
    twin_id: str,
    request: Request,
    profondeur: int = Query(3, ge=1, le=8),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Impact amont/aval du twin, sans jamais dépasser le tenant."""
    _verifier_espace(x_espace)
    tenant = _tenant(request, x_tenant)
    if not twin_id.strip() or len(twin_id) > 128:
        raise HTTPException(400, "twin_id invalide")
    impact, mode = await asyncio.to_thread(
        _executer_graphe,
        lambda store: store.impact(tenant, twin_id.strip(), profondeur),
    )
    return {"tenant": tenant, "twin": twin_id.strip(), "profondeur": profondeur,
            "mode": mode, "impact": _assainir(impact)}


@router.get("/graphe/chemins")
async def graphe_chemins(
    request: Request,
    source: str = Query(..., min_length=1, max_length=128),
    cible: str = Query(..., min_length=1, max_length=128),
    profondeur: int = Query(6, ge=1, le=8),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Chemins orientés source → cible, bornés et tenant-scoped."""
    _verifier_espace(x_espace)
    tenant = _tenant(request, x_tenant)
    chemins, mode = await asyncio.to_thread(
        _executer_graphe,
        lambda store: store.chemins(tenant, source.strip(), cible.strip(), profondeur),
    )
    return {"tenant": tenant, "source": source.strip(), "cible": cible.strip(),
            "profondeur": profondeur, "mode": mode, "chemins": _assainir(chemins)}
