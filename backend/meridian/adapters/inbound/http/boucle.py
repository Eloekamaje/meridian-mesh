"""API de lecture et de transition de la boucle canonique d'entreprise.

Les objets sont lus dans ``objet_entreprise`` (Postgres) via
:mod:`meridian.adapters.outbound.postgres.entreprise_depot` et
:mod:`meridian.adapters.outbound.postgres.boucle`.
Les six transitions canoniques sont exposées en POST : Situation → Investigation → Decision →
Initiative → Outcome → Learning. Une transition charge sa source, applique la règle pure,
persiste avec historique et renvoie l'objet créé avec sa chaîne.

``Idempotency-Key`` n'est pas accepté silencieusement : aucun stockage d'idempotence durable
n'étant branché, toute requête qui fournit cet en-tête est refusée en 501. Les transitions
d'état déjà consommées restent refusées en 409.

Le tenant est résolu par :mod:`meridian.domain.tenant`. En mode demo seulement, l'absence de
``X-Tenant`` vaut ``local`` ; hors demo (proxy, OIDC, production), l'en-tête est obligatoire et un
en-tête vide ou invalide est refusé. Aucun repli silencieux n'est fait en production. Si un tenant
authentifié est déjà posé sur ``request.state.tenant``, il fait foi et un ``X-Tenant`` différent est
refusé. ``X-Espace`` reste un contexte de lecture, jamais une identité.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
import math
import os
import re
from typing import Annotated, Any
import unicodedata
from urllib.parse import parse_qsl, unquote_plus, urlsplit

import psycopg
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from psycopg.rows import dict_row
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from auth import acteur as acteur_courant
from meridian.adapters.outbound.postgres import boucle
from meridian.adapters.outbound.postgres import entreprise_depot
from meridian.adapters.outbound.neo4j import graph_store
from meridian.application import commandes_boucle
from meridian.domain import modele_entreprise
from meridian.adapters.outbound.postgres import rls
from meridian.domain.tenant import TenantError, exiger_tenant, normaliser_slug, resoudre_tenant
from seed_data import ESPACES

router = APIRouter(prefix="/boucle", tags=["boucle"])
journal = logging.getLogger("meridian")

_DSN_MANQUANT = "Couche cognitive non configurée (JUMEAU_PG_DSN)"
_DSN_INDISPONIBLE = "Couche cognitive indisponible"
_FAMILLES = frozenset(modele_entreprise.FAMILLES)
_MODES = frozenset(modele_entreprise.MODES)
_TYPES = frozenset(modele_entreprise.TYPES_OBJET)


def _mode_canonique(valeur: str) -> str:
    texte = str(valeur or "").strip().upper()
    if texte not in _MODES:
        raise ValueError(f"mode inconnu : {valeur!r} (attendus : {', '.join(sorted(_MODES))})")
    return texte


ModeCanonique = Annotated[str, AfterValidator(_mode_canonique)]
TexteNonVide = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
TexteIdentifiant = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)
]


def _date_iso(valeur: str) -> str:
    texte = str(valeur).strip()
    try:
        datetime.fromisoformat(texte.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("date ISO 8601 attendue") from exc
    return texte


DateIso = Annotated[str, AfterValidator(_date_iso)]


class ReponseTransition(BaseModel):
    """Contrat stable des POST de transition ; ``objet`` et ``chaine`` restent l'interface UI."""

    tenant: str
    objet: dict[str, Any]
    type: str
    role: str
    chaine: list[dict[str, Any]]
    historique: list[dict[str, Any]] = Field(default_factory=list)
    idempotency_key: str | None = None


_REPONSES_TRANSITION = {
    404: {"description": "Source absente du tenant"},
    409: {"description": "Transition refusée (état, choix, doublon, version périmée)"},
    422: {"description": "Corps invalide"},
    501: {"description": "Idempotency-Key non pris en charge"},
    503: {"description": "Postgres indisponible"},
}


def _refuser_idempotence(
    idempotency_key: str | None = Header(None, alias="Idempotency-Key", max_length=200),
) -> None:
    """Aucun stockage d'idempotence durable : refus explicite plutôt qu'un écho trompeur."""
    if idempotency_key and idempotency_key.strip():
        raise HTTPException(
            501,
            "Idempotency-Key non pris en charge : aucun stockage d'idempotence durable "
            "n'est configuré",
        )


class _CorpsTransition(BaseModel):
    """Corps JSON strict : un champ inconnu est une erreur de contrat (422)."""

    model_config = ConfigDict(extra="forbid")


class CreationSituation(_CorpsTransition):
    id: TexteIdentifiant | None = None
    titre: str | None = Field(None, max_length=500)
    description: str | None = None
    resume: str | None = None
    statut: str | None = Field(None, max_length=64)
    priorite: str | None = Field(None, max_length=64)
    twin_ids: list[str] | None = None
    signal_ids: list[str] | None = None
    claim_ids: list[str] | None = None
    opportunite_ids: list[str] | None = None
    risk_ids: list[str] | None = None
    expression_id: str | None = None
    inconnues: list[str] | None = None
    mode: ModeCanonique | None = None
    preuves: list[Any] | None = None
    confiance: float | None = Field(None, ge=0, le=1)

    @model_validator(mode="after")
    def _texte_racine(self):
        textes = (self.titre, self.description, self.resume)
        if not any(texte and texte.strip() for texte in textes):
            raise ValueError("titre, description ou resume obligatoire")
        return self


class OuvertureInvestigation(_CorpsTransition):
    id: TexteIdentifiant | None = None
    titre: str | None = Field(None, max_length=500)
    question: str | None = None
    resume: str | None = None
    statut: str | None = Field(None, max_length=64)
    perimetre: str | None = None
    proprietaire: str | None = None
    twin_ids: list[str] | None = None
    hypothesis_ids: list[str] | None = None
    expert_ids: list[str] | None = None
    scenario_ids: list[str] | None = None
    ouverte_le: DateIso | None = None
    close_le: DateIso | None = None
    synthese: str | None = None
    incertitudes: list[str] | None = None
    preuves: list[Any] | None = None
    mode: ModeCanonique | None = None


class PropositionDecision(_CorpsTransition):
    id: TexteIdentifiant | None = None
    titre: str | None = Field(None, max_length=500)
    resume: str | None = None
    options: list[TexteNonVide] = Field(..., min_length=1, max_length=50)
    criteres: list[TexteNonVide] | None = None
    incertitudes: list[TexteNonVide] | None = None
    rationale: str | None = None
    preuves: list[Any] | None = None
    mode: ModeCanonique | None = None


class TranchementDecision(_CorpsTransition):
    # ``acteur`` reste accepté pour les clients existants mais n'est jamais utilisé :
    # l'acteur enregistré vient de l'identité authentifiée (``Depends(acteur_courant)``).
    acteur: TexteNonVide | None = None
    acteur_declare: TexteNonVide | None = None
    choix: TexteNonVide
    motif: str | None = None
    rationale: str | None = None
    decide_le: DateIso | None = None
    preuves: list[Any] | None = None
    mode: ModeCanonique | None = None


class LancementInitiative(_CorpsTransition):
    id: TexteIdentifiant | None = None
    titre: str | None = Field(None, max_length=500)
    resume: str | None = None
    statut: str | None = Field(None, max_length=64)
    proprietaire: str | None = None
    perimetre: str | None = None
    outcome_attendu_ids: list[str] | None = None
    debut_le: DateIso | None = None
    fin_prevue_le: DateIso | None = None
    preuves: list[Any] | None = None
    mode: ModeCanonique | None = None


def _mesure_renseignee(valeur: Any) -> bool:
    """Même règle que le domaine : une mesure vide n'est pas une mesure."""
    if valeur is None or isinstance(valeur, bool):
        return False
    if isinstance(valeur, str):
        return bool(valeur.strip())
    if isinstance(valeur, Mapping):
        return any(_mesure_renseignee(element) for element in valeur.values())
    if isinstance(valeur, (list, tuple, set, frozenset)):
        return bool(valeur)
    return True


class MesureOutcome(_CorpsTransition):
    id: TexteIdentifiant | None = None
    titre: str | None = Field(None, max_length=500)
    resume: str | None = None
    mesure: Any
    metrique: str | None = None
    valeur_attendue: Any = None
    interpretation: str | None = None
    mesure_le: DateIso | None = None
    periode: str | None = None
    statut: str | None = Field(None, max_length=64)
    preuves: list[Any] | None = None
    mode: ModeCanonique | None = None

    @field_validator("mesure")
    @classmethod
    def _mesure_non_vide(cls, valeur: Any) -> Any:
        if not _mesure_renseignee(valeur):
            raise ValueError("une mesure non vide est obligatoire")
        return valeur


class CapitalisationLearning(_CorpsTransition):
    id: TexteIdentifiant | None = None
    titre: str | None = Field(None, max_length=500)
    resume: str | None = None
    enonce: TexteNonVide
    scope: str | None = None
    conditions_applicabilite: list[TexteNonVide] | None = None
    related_claim_ids: list[str] | None = None
    preuves: list[Any] | None = None
    # Acceptés pour compatibilité mais ignorés : le flux force PROPOSED / INFERRED.
    statut: str | None = Field(None, max_length=64)
    mode: ModeCanonique | None = None


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


# --------------------------------------------------------------------------- #
# Transitions canoniques : Situation → Investigation → Decision → Initiative →
# Outcome → Learning. La règle vit dans le domaine ; l'API orchestre et traduit
# les erreurs (404 source absente, 409 transition refusée, 422 corps invalide).
# --------------------------------------------------------------------------- #


async def _executer_transition(tenant: str, action, *, request: Request | None = None):
    """Ouvre une connexion tenant-scoped et traduit les erreurs métier en HTTP."""
    dsn = _dsn()

    def executer():
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            if rls.est_actif():
                with rls.contexte_tenant(conn, tenant):
                    return action(conn)
            return action(conn)

    try:
        return await asyncio.to_thread(executer)
    except HTTPException:
        raise
    except commandes_boucle.SourceIntrouvable as exc:
        raise HTTPException(404, str(exc)) from exc
    except entreprise_depot.ObjetExistant as exc:
        raise HTTPException(409, str(exc)) from exc
    except (commandes_boucle.TransitionRefusee, boucle.BoucleInvalide,
            entreprise_depot.VersionRefusee) as exc:
        raise HTTPException(409, str(exc)) from exc
    except psycopg.errors.UniqueViolation as exc:
        raise HTTPException(409, "objet déjà existant") from exc
    except modele_entreprise.ModeleInvalide as exc:
        raise HTTPException(422, str(exc)) from exc
    except entreprise_depot.ObjetInvalide as exc:
        raise HTTPException(400, str(exc)) from exc
    except psycopg.Error as exc:
        correlation = None
        if request is not None:
            correlation = (getattr(request.state, "request_id", None)
                           or getattr(request.state, "correlation_id", None))
        journal.warning(
            "boucle transition indisponible tenant=%s correlation=%s: %s",
            tenant, correlation or "-", exc.__class__.__name__)
        raise HTTPException(503, _DSN_INDISPONIBLE) from exc


def _reponse_transition(
    tenant: str, resultat: commandes_boucle.ResultatTransition, role: str,
) -> dict:
    """Rend l'objet créé avec son type, sa chaîne et son historique."""
    objet = _objet_public(resultat.objet)
    return {
        "tenant": tenant,
        "objet": objet,
        "type": str(objet.get("type") or role.upper()),
        "role": role,
        "chaine": [_objet_public(element) for element in resultat.chaine],
        "historique": _assainir(resultat.historique),
        "idempotency_key": None,
    }


@router.post("/situations", status_code=201, response_model=ReponseTransition,
             responses=_REPONSES_TRANSITION)
async def creer_situation(
    payload: CreationSituation,
    request: Request,
    idempotence: None = Depends(_refuser_idempotence),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Crée une Situation racine ; un identifiant existant est refusé en 409.

    ``X-Espace`` reste un contexte de lecture : il est validé puis ignoré sur les POST.
    """
    _verifier_espace(x_espace)
    tenant = _tenant(request, x_tenant)
    resultat = await _executer_transition(
        tenant,
        lambda conn: commandes_boucle.creer_situation(
            boucle, conn, tenant, **payload.model_dump(exclude_none=True)),
        request=request,
    )
    return _reponse_transition(tenant, resultat, "situation")


@router.post("/situations/{sid}/investigations", status_code=201,
             response_model=ReponseTransition, responses=_REPONSES_TRANSITION)
async def ouvrir_investigation(
    sid: str,
    payload: OuvertureInvestigation,
    request: Request,
    idempotence: None = Depends(_refuser_idempotence),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Ouvre une Investigation sur une Situation du tenant ; ``X-Espace`` est ignoré."""
    _verifier_espace(x_espace)
    tenant = _tenant(request, x_tenant)
    resultat = await _executer_transition(
        tenant,
        lambda conn: commandes_boucle.ouvrir_investigation(
            boucle, conn, tenant, sid, **payload.model_dump(exclude_none=True)),
        request=request,
    )
    return _reponse_transition(tenant, resultat, "investigation")


@router.post("/investigations/{iid}/decisions", status_code=201,
             response_model=ReponseTransition, responses=_REPONSES_TRANSITION)
async def proposer_decision(
    iid: str,
    payload: PropositionDecision,
    request: Request,
    idempotence: None = Depends(_refuser_idempotence),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Propose une Decision non tranchée sur une Investigation du tenant."""
    _verifier_espace(x_espace)
    tenant = _tenant(request, x_tenant)
    champs = payload.model_dump(exclude_none=True)
    options = champs.pop("options")

    def proposer(conn):
        return commandes_boucle.proposer_decision(boucle, conn, tenant, iid, options, **champs)

    resultat = await _executer_transition(tenant, proposer, request=request)
    return _reponse_transition(tenant, resultat, "decision")


@router.post("/decisions/{did}/trancher", response_model=ReponseTransition,
             responses=_REPONSES_TRANSITION)
async def trancher_decision(
    did: str,
    payload: TranchementDecision,
    request: Request,
    acteur: str = Depends(acteur_courant),
    idempotence: None = Depends(_refuser_idempotence),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Tranche une Decision proposée ; l'acteur vient de l'identité, jamais du corps.

    L'ancienne version reste dans ``historique``. Un ``acteur`` ou ``acteur_declare`` fourni
    par le client est accepté pour compatibilité mais ignoré.
    """
    _verifier_espace(x_espace)
    tenant = _tenant(request, x_tenant)
    champs = payload.model_dump(exclude_none=True)
    champs.pop("acteur", None)
    champs.pop("acteur_declare", None)
    choix = champs.pop("choix")

    def trancher(conn):
        return commandes_boucle.trancher_decision(
            boucle, conn, tenant, did, acteur=acteur, choix=choix, **champs)

    resultat = await _executer_transition(tenant, trancher, request=request)
    return _reponse_transition(tenant, resultat, "decision")


@router.post("/decisions/{did}/initiatives", status_code=201,
             response_model=ReponseTransition, responses=_REPONSES_TRANSITION)
async def lancer_initiative(
    did: str,
    payload: LancementInitiative,
    request: Request,
    idempotence: None = Depends(_refuser_idempotence),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Lance une Initiative depuis une Decision tranchée du tenant."""
    _verifier_espace(x_espace)
    tenant = _tenant(request, x_tenant)
    resultat = await _executer_transition(
        tenant,
        lambda conn: commandes_boucle.lancer_initiative(
            boucle, conn, tenant, did, **payload.model_dump(exclude_none=True)),
        request=request,
    )
    return _reponse_transition(tenant, resultat, "initiative")


@router.post("/initiatives/{iid}/outcomes", status_code=201,
             response_model=ReponseTransition, responses=_REPONSES_TRANSITION)
async def mesurer_outcome(
    iid: str,
    payload: MesureOutcome,
    request: Request,
    idempotence: None = Depends(_refuser_idempotence),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Mesure un Outcome sur une Initiative du tenant ; une mesure vide est refusée en 422."""
    _verifier_espace(x_espace)
    tenant = _tenant(request, x_tenant)
    champs = payload.model_dump(exclude_none=True)
    mesure = champs.pop("mesure")

    def mesurer(conn):
        return commandes_boucle.mesurer_outcome(boucle, conn, tenant, iid, mesure, **champs)

    resultat = await _executer_transition(tenant, mesurer, request=request)
    return _reponse_transition(tenant, resultat, "outcome")


@router.post("/outcomes/{oid}/learnings", status_code=201,
             response_model=ReponseTransition, responses=_REPONSES_TRANSITION)
async def capitaliser_learning_depuis_outcome(
    oid: str,
    payload: CapitalisationLearning,
    request: Request,
    idempotence: None = Depends(_refuser_idempotence),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Capitalise un Learning depuis un Outcome mesuré ; statut/mode sont forcés côté serveur."""
    _verifier_espace(x_espace)
    tenant = _tenant(request, x_tenant)
    resultat = await _executer_transition(
        tenant,
        lambda conn: commandes_boucle.capitaliser_learning_depuis_outcome(
            boucle, conn, tenant, oid, **payload.model_dump(exclude_none=True)),
        request=request,
    )
    return _reponse_transition(tenant, resultat, "learning")


@router.post("/investigations/{iid}/learnings", status_code=201,
             response_model=ReponseTransition, responses=_REPONSES_TRANSITION)
async def capitaliser_learning_depuis_investigation(
    iid: str,
    payload: CapitalisationLearning,
    request: Request,
    idempotence: None = Depends(_refuser_idempotence),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Capitalise un Learning depuis une Investigation ; statut/mode sont forcés côté serveur."""
    _verifier_espace(x_espace)
    tenant = _tenant(request, x_tenant)
    resultat = await _executer_transition(
        tenant,
        lambda conn: commandes_boucle.capitaliser_learning_depuis_investigation(
            boucle, conn, tenant, iid, **payload.model_dump(exclude_none=True)),
        request=request,
    )
    return _reponse_transition(tenant, resultat, "learning")
