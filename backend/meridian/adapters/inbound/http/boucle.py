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
from meridian.adapters.outbound.postgres import calibration
from meridian.adapters.outbound.postgres import entreprise_depot
from meridian.adapters.outbound.postgres import journal_episodes
from meridian.adapters.outbound.postgres import metriques_revue
from meridian.adapters.outbound.postgres import revue_graduee
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
    except modele_entreprise.ModeleInvalide as exc:
        raise HTTPException(422, str(exc)) from exc
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


# --- B1 : écriture canonique (création + transitions) ---

import inspect as _inspect
from pydantic import BaseModel as _BaseModel, Field as _Field

_PREFIXES_ID = {
    "SITUATION": "sit-", "INVESTIGATION": "inv-", "DECISION": "dec-",
    "INITIATIVE": "ini-", "OUTCOME": "out-", "LEARNING": "ler-",
    "UNKNOWN": "unk-", "HYPOTHESIS": "hyp-", "NEED": "need-",
}
_TYPES_CREATION = (
    "SITUATION", "INVESTIGATION", "DECISION", "INITIATIVE",
    "UNKNOWN", "HYPOTHESIS", "NEED",
)
_MODES_CREATION = {"SITUATION": "OBSERVED"}

_ACTIONS_TRANSITION = {
    "ouvrir_investigation": ("SITUATION", boucle.ouvrir_investigation),
    "proposer_decision": ("INVESTIGATION", boucle.proposer_decision),
    "trancher": ("DECISION", boucle.trancher_decision),
    "lancer_initiative": ("DECISION", boucle.lancer_initiative),
    "mesurer_outcome": ("INITIATIVE", boucle.mesurer_outcome),
    "transiter_need": ("NEED", boucle.transiter_need),
}


class _ObjetCree(_BaseModel):
    type: str
    titre: str = ""
    donnees: dict = _Field(default_factory=dict)
    mode: str | None = None


class _TransitionDemande(_BaseModel):
    action: str
    donnees: dict = _Field(default_factory=dict)


@router.post("/objets", status_code=201)
async def creer_objet(
    request: Request,
    payload: _ObjetCree,
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Crée un objet canonique de la boucle (Situation, Investigation, Decision, Initiative)
    ou un objet complémentaire (Unknown, Hypothesis, Need)."""
    _verifier_espace(x_espace)
    tenant = _tenant(request, x_tenant)
    type_objet = str(payload.type or "").strip().upper()
    if type_objet not in _TYPES_CREATION:
        raise HTTPException(
            422, f"type non créable : {type_objet!r} (créables : {list(_TYPES_CREATION)})")
    mode = (payload.mode or _MODES_CREATION.get(type_objet, "PROPOSED")).upper()
    if mode not in _MODES:
        raise HTTPException(422, f"mode inconnu : {mode!r}")
    dsn = _dsn()

    def ecrire():
        classe = boucle._CLASSES[type_objet]
        params = set(_inspect.signature(classe).parameters)
        valeurs = {
            cle: valeur
            for cle, valeur in {"titre": payload.titre, "mode": mode, **dict(payload.donnees)}.items()
            if cle in params
        }
        if "tenant_id" in params:
            valeurs["tenant_id"] = tenant
        objet = classe(id=boucle._nouvel_id(_PREFIXES_ID[type_objet]), **valeurs)
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            if rls.est_actif():
                with rls.contexte_tenant(conn, tenant):
                    return boucle.enregistrer_boucle(conn, tenant, objet)
            return boucle.enregistrer_boucle(conn, tenant, objet)

    resultat = await _dans_le_thread(ecrire)
    return _assainir(resultat)


@router.post("/objets/{objet_id}/transition", status_code=201)
async def transition_objet(
    objet_id: str,
    request: Request,
    payload: _TransitionDemande,
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Fait transiter un objet : ouvrir_investigation, proposer_decision, trancher,
    lancer_initiative, mesurer_outcome, transiter_need — la chaîne est validée par le dépôt."""
    _verifier_espace(x_espace)
    tenant = _tenant(request, x_tenant)
    entree = _ACTIONS_TRANSITION.get(str(payload.action or "").strip())
    if entree is None:
        raise HTTPException(
            422, f"action inconnue : {payload.action!r} (connues : {list(_ACTIONS_TRANSITION)})")
    type_attendu, fonction = entree
    dsn = _dsn()

    def ecrire():
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            if rls.est_actif():
                with rls.contexte_tenant(conn, tenant):
                    return _transiter(conn)
            return _transiter(conn)

    def _transiter(conn):
        source = boucle.lire_boucle(conn, tenant, objet_id, as_dict=True)
        if source is None:
            raise HTTPException(404, "Objet introuvable")
        nouvel = fonction(source, tenant_id=tenant, **dict(payload.donnees))
        return boucle.enregistrer_boucle(conn, tenant, nouvel)

    resultat = await _dans_le_thread(ecrire)
    return _assainir(resultat)


# --- D1 : journal d'épisodes (lecture du journal append-only) ---


@router.get("/episodes")
async def lister_episodes(
    request: Request,
    limite: int = Query(50, ge=1, le=500),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Liste les derniers épisodes du tenant, groupés par ``episode_id``, du plus récent au plus ancien."""
    _verifier_espace(x_espace)
    tenant = _tenant(request, x_tenant)
    dsn = _dsn()

    def lire():
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            if rls.est_actif():
                with rls.contexte_tenant(conn, tenant):
                    return journal_episodes.episodes(conn, tenant, limite)
            return journal_episodes.episodes(conn, tenant, limite)

    resultat = await _dans_le_thread(lire)
    return {"tenant": tenant, "episodes": _assainir(resultat)}


@router.get("/episodes/{episode_id}")
async def lire_episode(
    episode_id: str,
    request: Request,
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Rend les événements d'un épisode du tenant, dans l'ordre d'écriture ; 404 s'il est inconnu."""
    _verifier_espace(x_espace)
    tenant = _tenant(request, x_tenant)
    episode = episode_id.strip()
    if not episode or len(episode) > 256:
        raise HTTPException(400, "episode_id invalide")
    dsn = _dsn()

    def lire():
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            if rls.est_actif():
                with rls.contexte_tenant(conn, tenant):
                    return journal_episodes.lire_episode(conn, tenant, episode)
            return journal_episodes.lire_episode(conn, tenant, episode)

    evenements = await _dans_le_thread(lire)
    if not evenements:
        raise HTTPException(404, "Épisode introuvable")
    return {"tenant": tenant, "episode": episode, "evenements": _assainir(evenements)}


# --- C4 : calibration des prédictions (Brier + IC de Wilson) ---


@router.get("/calibration")
async def boucle_calibration(
    request: Request,
    minimum: int = Query(10, ge=1, le=1000),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Brier des prédictions résolues + IC de Wilson du taux observé, tenant-scopé.

    ``brier``, ``taux`` et ``ic95`` sont ``null`` tant que ``n`` est sous
    ``minimum`` : jamais un nombre sans effectif. ``par_source`` décline la
    même mesure par source de prédiction.
    """
    _verifier_espace(x_espace)
    tenant = _tenant(request, x_tenant)
    dsn = _dsn()

    def lire():
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            if rls.est_actif():
                with rls.contexte_tenant(conn, tenant):
                    return calibration.score_brier(conn, tenant, minimum=minimum)
            return calibration.score_brier(conn, tenant, minimum=minimum)

    resultat = await _dans_le_thread(lire)
    return {"tenant": tenant, **_assainir(resultat)}


# --- C3 : métriques de la revue humaine (taux + délai, jamais sans n) ---


@router.get("/revue/metriques")
async def revue_metriques(
    request: Request,
    jours: int = Query(30, ge=1, le=366),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Taux accepté/corrigé/refusé et délai médian de la revue humaine, tenant-scopés.

    ``n`` = claims décidés dans la fenêtre ; ``taux_*`` et ``ic95`` sont ``null``
    tant que ``n`` est sous ``minimum`` — jamais un ratio sans effectif. Revue
    vide : comptes à 0, mesures à ``null``, jamais de 500.
    """
    _verifier_espace(x_espace)
    tenant = _tenant(request, x_tenant)
    dsn = _dsn()

    def lire():
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            if rls.est_actif():
                with rls.contexte_tenant(conn, tenant):
                    return metriques_revue.metriques(conn, tenant, jours=jours)
            return metriques_revue.metriques(conn, tenant, jours=jours)

    resultat = await _dans_le_thread(lire)
    return {"tenant": tenant, **_assainir(resultat)}


# --- D3 : revue graduée par risque (répartition des niveaux, lecture seule) ---


@router.get("/revue/niveaux")
async def revue_niveaux(
    request: Request,
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Répartition des niveaux de revue du tenant : ``AUTO_VISIBLE`` /
    ``ATTENTION`` / ``BLOQUANT``, auto-acceptés encore révocables et révoqués,
    pour les claims et les propositions. Comptes seuls — jamais de ratio.
    """
    _verifier_espace(x_espace)
    tenant = _tenant(request, x_tenant)
    dsn = _dsn()

    def lire():
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            if rls.est_actif():
                with rls.contexte_tenant(conn, tenant):
                    return revue_graduee.niveaux(conn, tenant)
            return revue_graduee.niveaux(conn, tenant)

    resultat = await _dans_le_thread(lire)
    return {"tenant": tenant, **_assainir(resultat)}


# --- D8 : Twin comme projection des claims ---

from meridian.adapters.outbound.postgres import projection_twin as _projection_twin


@router.get("/twins/{twin_id}/projection")
async def twin_projection(
    twin_id: str,
    request: Request,
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Projection calculée du twin : capacités, dépendances, dépendants, couverture,
    fraîcheur et état épistémique — tout se déduit des claims ; la ligne ``jumeau``
    ne fournit que l'identité (nom, équipe, type). ``None`` → 404 tenant-scopé.
    """
    _verifier_espace(x_espace)
    tenant = _tenant(request, x_tenant)
    if not twin_id.strip() or len(twin_id) > 128:
        raise HTTPException(400, "twin_id invalide")
    dsn = _dsn()

    def lire():
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            if rls.est_actif():
                with rls.contexte_tenant(conn, tenant):
                    return _projection_twin.projeter(conn, tenant, twin_id.strip())
            return _projection_twin.projeter(conn, tenant, twin_id.strip())

    resultat = await _dans_le_thread(lire)
    if resultat is None:
        raise HTTPException(404, "Twin introuvable")
    return {"tenant": tenant, "twin": twin_id.strip(),
            "projection": _assainir(resultat)}


@router.get("/twins/{twin_id}/projection/ecarts")
async def twin_projection_ecarts(
    twin_id: str,
    request: Request,
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Écarts entre la ligne ``jumeau`` stockée et la projection des claims :
    ``stocke``, ``calcule`` et la liste des champs qui divergent."""
    _verifier_espace(x_espace)
    tenant = _tenant(request, x_tenant)
    if not twin_id.strip() or len(twin_id) > 128:
        raise HTTPException(400, "twin_id invalide")
    dsn = _dsn()

    def lire():
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            if rls.est_actif():
                with rls.contexte_tenant(conn, tenant):
                    return _projection_twin.ecarts(conn, tenant, twin_id.strip())
            return _projection_twin.ecarts(conn, tenant, twin_id.strip())

    resultat = await _dans_le_thread(lire)
    if resultat is None:
        raise HTTPException(404, "Twin introuvable")
    return {"tenant": tenant, "twin": twin_id.strip(), **_assainir(resultat)}
