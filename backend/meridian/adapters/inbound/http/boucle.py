"""API de lecture et de transition de la boucle canonique d'entreprise.

Les objets sont lus dans ``objet_entreprise`` (Postgres) via
:mod:`meridian.adapters.outbound.postgres.entreprise_depot` et
:mod:`meridian.adapters.outbound.postgres.boucle`.
Les six transitions canoniques sont exposées en POST : Situation → Investigation → Decision →
Initiative → Outcome → Learning. Une transition charge sa source, applique la règle pure,
persiste avec historique et renvoie l'objet créé avec sa chaîne. Les Scénarios canoniques
disposent en plus d'une création (`POST /boucle/scenarios`), d'une liste filtrée
(`GET /boucle/scenarios`) et d'une comparaison déterministe (`POST /boucle/scenarios/comparer`).
Le stade « Exprimer » dispose de sa création (`POST /boucle/situations/{id}/expressions`) :
une Expression canonique unique par Situation, lisible dans la chaîne.

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
import json
import logging
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
import math
import os
from typing import Annotated, Any
import unicodedata
from urllib.parse import parse_qsl, unquote_plus, urlsplit

import psycopg
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from psycopg.rows import dict_row
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

from auth import acteur as acteur_courant
from meridian.adapters.outbound.postgres import boucle
from meridian.adapters.outbound.postgres import entreprise_depot
from meridian.adapters.outbound.neo4j import graph_store
from meridian.application import commandes_boucle
from meridian.application.pont_securite import jeton_sensible
from meridian.domain import modele_entreprise
from meridian.domain.mesure import mesure_renseignee as _mesure_renseignee
from meridian.domain.objets_exploitation import TYPES_EXPRESSION, TYPES_SIGNAL
from meridian.adapters.outbound.postgres import rls
from meridian.domain.tenant import (
    TenantError,
    exiger_tenant,
    normaliser_tenant_canonique,
    resoudre_tenant,
)
from meridian.ports.boucle import ObjetExistant, ObjetInvalide, VersionRefusee
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


def _type_expression_canonique(valeur: str) -> str:
    texte = str(valeur or "").strip().upper()
    if texte not in TYPES_EXPRESSION:
        raise ValueError(
            f"type_expression inconnu : {valeur!r} "
            f"(attendus : {', '.join(TYPES_EXPRESSION)})"
        )
    return texte


def _type_signal_canonique(valeur: str) -> str:
    texte = str(valeur or "").strip().upper()
    if texte not in TYPES_SIGNAL:
        raise ValueError(
            f"type_signal inconnu : {valeur!r} "
            f"(attendus : {', '.join(TYPES_SIGNAL)})"
        )
    return texte


ModeCanonique = Annotated[str, AfterValidator(_mode_canonique)]
TypeExpression = Annotated[str, AfterValidator(_type_expression_canonique)]
TypeSignal = Annotated[str, AfterValidator(_type_signal_canonique)]
TexteNonVide = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
TexteNettoye = Annotated[str, StringConstraints(strip_whitespace=True)]
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
    400: {"description": "Objet invalide (secret ou données non sérialisables)"},
    404: {"description": "Source absente du tenant"},
    409: {"description": "Transition refusée (état, choix, doublon, version périmée)"},
    422: {"description": "Corps invalide"},
    501: {"description": "Idempotency-Key non pris en charge"},
    503: {"description": "Postgres indisponible"},
}


def _refuser_idempotence(
    idempotency_key: str | None = Header(None, alias="Idempotency-Key", max_length=200),
) -> None:
    """Aucun stockage d'idempotence durable : refus explicite, même pour une valeur blanche."""
    if idempotency_key is not None:
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
    description: str | None = Field(None, max_length=10000)
    resume: str | None = Field(None, max_length=5000)
    statut: str | None = Field(None, max_length=64)
    priorite: str | None = Field(None, max_length=64)
    twin_ids: list[str] | None = None
    signal_ids: list[str] | None = None
    claim_ids: list[str] | None = None
    opportunite_ids: list[str] | None = None
    risk_ids: list[str] | None = None
    inconnues: list[str] | None = None
    mode: ModeCanonique | None = None
    preuves: list[Any] | None = Field(None, max_length=100)
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
    question: str | None = Field(None, max_length=2000)
    resume: str | None = Field(None, max_length=5000)
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
    incertitudes: list[str] | None = Field(None, max_length=50)
    preuves: list[Any] | None = Field(None, max_length=100)
    mode: ModeCanonique | None = None


class PropositionDecision(_CorpsTransition):
    id: TexteIdentifiant | None = None
    titre: str | None = Field(None, max_length=500)
    resume: str | None = Field(None, max_length=5000)
    options: list[TexteNonVide] = Field(..., min_length=1, max_length=50)
    criteres: list[TexteNonVide] | None = Field(None, max_length=50)
    incertitudes: list[TexteNonVide] | None = Field(None, max_length=50)
    rationale: str | None = None
    preuves: list[Any] | None = Field(None, max_length=100)
    mode: ModeCanonique | None = None


class TranchementDecision(_CorpsTransition):
    # ``acteur``/``acteur_declare`` restent acceptés pour les clients existants mais ne
    # sont jamais utilisés : l'acteur enregistré vient de l'identité authentifiée
    # (``Depends(acteur_courant)``). Le type est volontairement tolérant pour ne pas
    # casser une UI encore porteuse du champ.
    acteur: Any = None
    acteur_declare: Any = None
    choix: TexteNonVide
    motif: str | None = None
    rationale: str | None = None
    decide_le: DateIso | None = None
    preuves: list[Any] | None = Field(None, max_length=100)
    mode: ModeCanonique | None = None


class LancementInitiative(_CorpsTransition):
    id: TexteIdentifiant | None = None
    titre: str | None = Field(None, max_length=500)
    resume: str | None = Field(None, max_length=5000)
    statut: str | None = Field(None, max_length=64)
    proprietaire: str | None = None
    perimetre: str | None = None
    outcome_attendu_ids: list[str] | None = None
    debut_le: DateIso | None = None
    fin_prevue_le: DateIso | None = None
    preuves: list[Any] | None = Field(None, max_length=100)
    mode: ModeCanonique | None = None


class MesureOutcome(_CorpsTransition):
    id: TexteIdentifiant | None = None
    titre: str | None = Field(None, max_length=500)
    resume: str | None = Field(None, max_length=5000)
    mesure: Any
    metrique: str | None = Field(None, max_length=200)
    valeur_attendue: Any = None
    interpretation: str | None = Field(None, max_length=5000)
    mesure_le: DateIso | None = None
    periode: str | None = Field(None, max_length=100)
    statut: str | None = Field(None, max_length=64)
    preuves: list[Any] | None = Field(None, max_length=100)
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
    resume: str | None = Field(None, max_length=5000)
    enonce: TexteNonVide = Field(..., max_length=5000)
    scope: str | None = Field(None, max_length=200)
    conditions_applicabilite: list[TexteNonVide] | None = Field(None, max_length=50)
    related_claim_ids: list[str] | None = None
    preuves: list[Any] | None = Field(None, max_length=100)
    # Acceptés pour compatibilité mais ignorés : le flux force PROPOSED / INFERRED.
    statut: str | None = Field(None, max_length=64)
    mode: ModeCanonique | None = None


class CreationScenario(_CorpsTransition):
    titre: TexteNonVide = Field(..., max_length=500)
    description: str | None = Field(None, max_length=10000)
    investigation_id: TexteIdentifiant | None = None
    decision_id: TexteIdentifiant | None = None
    hypothesis_ids: list[TexteNonVide] | None = Field(None, max_length=100)
    actions: list[TexteNonVide] | None = Field(None, max_length=100)
    valeur_estimee: float | None = Field(None, ge=0)
    cout_estime: float | None = Field(None, ge=0)
    complexite: float | None = Field(None, ge=0, le=1)
    risque: float | None = Field(None, ge=0, le=1)
    dependances: list[TexteNonVide] | None = Field(None, max_length=100)
    delai_jours: int | None = Field(None, ge=0)
    impacts: dict[str, str] | None = None
    reversibilite: str | None = Field(None, max_length=32)
    statut: str | None = Field(None, max_length=64)
    preuves: list[Any] | None = Field(None, max_length=100)
    confiance: float | None = Field(None, ge=0, le=1)

    @model_validator(mode="after")
    def _parent_obligatoire(self):
        if not (self.investigation_id or self.decision_id):
            raise ValueError("investigation_id ou decision_id obligatoire")
        return self


class CreationExpression(_CorpsTransition):
    """Corps C5a strict : ``statut`` n'est pas admis, le serveur force ``PROPOSED``."""

    type_expression: TypeExpression = "IDEE"
    formulation: TexteNonVide = Field(..., max_length=10000)
    canal: str | None = Field(None, max_length=200)
    auteur: str | None = Field(None, max_length=200)
    exprime_le: DateIso | None = None
    claim_ids: list[TexteNonVide] | None = Field(None, max_length=100)
    hypothesis_ids: list[TexteNonVide] | None = Field(None, max_length=100)
    inconnues: list[TexteNonVide] | None = Field(None, max_length=100)
    preuves: list[Any] | None = Field(None, max_length=100)
    confiance: float | None = Field(None, ge=0, le=1)
    mode: ModeCanonique = "DECLARED"


class _CreationObjetExpression(_CorpsTransition):
    """Corps C5b commun : ``statut``, ``id`` et les liens sont serveur uniquement."""

    titre: TexteNonVide = Field(..., max_length=500)
    description: str | None = Field(None, max_length=10000)
    valeur_potentielle: float | None = Field(None, ge=0)
    probabilite: float | None = Field(None, ge=0, le=1)
    impact: str | None = Field(None, max_length=2000)
    horizon: str | None = Field(None, max_length=200)
    criteres: list[TexteNonVide] | None = Field(None, max_length=100)
    preuves: list[Any] | None = Field(None, max_length=100)
    confiance: float | None = Field(None, ge=0, le=1)
    mode: ModeCanonique = "INFERRED"


class CreationOpportunite(_CreationObjetExpression):
    type_opportunite: str | None = Field(None, max_length=64)


class CreationRisque(_CreationObjetExpression):
    type_risque: str | None = Field(None, max_length=64)
    severite: str | None = Field(None, max_length=32)


class ChangementStatutObjet(_CorpsTransition):
    statut: TexteNonVide = Field(..., max_length=64)
    motif: TexteNettoye | None = Field(None, max_length=5000)
    preuves: list[Any] | None = Field(None, max_length=100)


class CreationHypothese(_CorpsTransition):
    """Corps C5c strict : statut, mode, id et liens sont serveur uniquement.

    ``expert_id`` reste porté par le domaine pour C5e, mais n'est pas exposé tant
    qu'aucune route EXPERT n'existe : le client qui l'envoie est refusé par
    ``extra="forbid"`` (422).
    """

    enonce: TexteNonVide = Field(..., max_length=5000)
    conditions_test: list[TexteNonVide] | None = Field(None, max_length=100)
    claim_ids_soutenants: list[TexteNonVide] | None = Field(None, max_length=100)
    claim_ids_opposants: list[TexteNonVide] | None = Field(None, max_length=100)
    preuves: list[Any] | None = Field(None, max_length=100)
    confiance: float | None = Field(None, ge=0, le=1)


class ChangementStatutHypothese(_CorpsTransition):
    vers: TexteNonVide = Field(..., max_length=64)
    motif: TexteNettoye | None = Field(None, max_length=5000)
    preuves: list[Any] | None = Field(None, max_length=100)


class CreationSignal(_CorpsTransition):
    """Corps C5d strict : statut, mode, id, tenant et empreinte sont serveur.

    ``situation_ids`` est optionnel en global ; depuis
    ``POST /situations/{sid}/signals`` la commande exige qu'il soit absent ou
    exactement ``[sid]``. Aucun champ de statut n'est exposé : C5d ne fournit pas
    de route de changement de statut.
    """

    libelle: TexteNonVide = Field(..., max_length=1000)
    source: TexteNonVide = Field(..., max_length=2000)
    type_signal: TypeSignal = "OBSERVATION"
    description: str | None = Field(None, max_length=10000)
    intensite: float | None = Field(None, ge=0, le=1)
    detecte_le: DateIso | None = None
    situation_ids: list[TexteIdentifiant] | None = Field(None, max_length=100)
    entite_ids: list[TexteIdentifiant] | None = Field(None, max_length=100)
    liens: dict[str, list[TexteIdentifiant]] | None = None
    preuves: list[Any] | None = Field(None, max_length=100)
    confiance: float | None = Field(None, ge=0, le=1)


async def _corps_signal(request: Request) -> CreationSignal:
    """Valide le JSON Signal en distinguant un corps malformé (400) d'un champ invalide (422)."""
    corps = await request.body()
    try:
        donnees = json.loads(corps)
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(400, "Corps JSON invalide") from exc
    if not isinstance(donnees, dict):
        raise HTTPException(400, "Corps JSON invalide : objet attendu")
    try:
        return CreationSignal.model_validate(donnees)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc


_OPENAPI_CORPS_SIGNAL = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {"schema": CreationSignal.model_json_schema()},
        },
    },
}


class ComparaisonScenarios(_CorpsTransition):
    scenario_ids: list[TexteIdentifiant] = Field(..., min_length=2, max_length=50)
    reference_id: TexteIdentifiant | None = None

    @model_validator(mode="after")
    def _ids_coherents(self):
        if len(set(self.scenario_ids)) != len(self.scenario_ids):
            raise ValueError("scenario_ids ne doit pas contenir de doublon")
        if self.reference_id is not None and self.reference_id not in self.scenario_ids:
            raise ValueError("reference_id doit appartenir à scenario_ids")
        return self


_MARQUEURS_SECRETS = ("password", "passwd", "secret", "token", "credential", "authorization")
_CLES_SECRETES = frozenset({
    "pwd", "pass", "auth", "key", "apikey", "api_key", "api-key", "access_key", "accesskey",
    "private_key", "privatekey", "client_secret", "clientsecret", "bearer", "password", "passwd",
})


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
            if (x_tenant is not None
                    and normaliser_tenant_canonique(x_tenant)
                    != normaliser_tenant_canonique(contexte.id)):
                raise HTTPException(403, "Tenant différent de l'identité authentifiée")
        else:
            contexte = resoudre_tenant(x_tenant, auth_mode=mode)
        tenant = normaliser_tenant_canonique(exiger_tenant(contexte).id)
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
        if jeton_sensible(valeur) or _url_porte_un_secret(valeur):
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
    except ObjetInvalide as exc:
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


def _detail_unique_violation(exc: psycopg.errors.UniqueViolation) -> str:
    """Message 409 dédié quand l'index 1:1 Situation → Expression est heurté."""
    contrainte = getattr(getattr(exc, "diag", None), "constraint_name", None)
    if contrainte == "objet_entreprise_expression_situation_unique":
        return "Situation déjà exprimée : une Expression existe déjà pour cette Situation"
    return "objet déjà existant"


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
    except ObjetExistant as exc:
        raise HTTPException(409, str(exc)) from exc
    except (commandes_boucle.TransitionRefusee, boucle.BoucleInvalide,
            VersionRefusee) as exc:
        raise HTTPException(409, str(exc)) from exc
    except psycopg.errors.UniqueViolation as exc:
        raise HTTPException(409, _detail_unique_violation(exc)) from exc
    except modele_entreprise.ModeleInvalide as exc:
        raise HTTPException(422, str(exc)) from exc
    except ObjetInvalide as exc:
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


@router.post("/situations/{sid}/expressions", status_code=201,
             response_model=ReponseTransition, responses=_REPONSES_TRANSITION)
async def creer_expression(
    sid: str,
    payload: CreationExpression,
    request: Request,
    idempotence: None = Depends(_refuser_idempotence),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Formule l'unique Expression canonique d'une Situation du tenant.

    ``statut`` est absent du corps : un client qui l'envoie est refusé en 422 et le
    serveur persiste toujours ``PROPOSED``. Une Situation déjà exprimée répond 409.
    """
    _verifier_espace(x_espace)
    tenant = _tenant(request, x_tenant)
    resultat = await _executer_transition(
        tenant,
        lambda conn: commandes_boucle.creer_expression(
            boucle, conn, tenant, sid, **payload.model_dump(exclude_none=True)),
        request=request,
    )
    return _reponse_transition(tenant, resultat, "expression")


@router.post("/expressions/{eid}/opportunities", status_code=201,
             response_model=ReponseTransition, responses=_REPONSES_TRANSITION)
async def creer_opportunite(
    eid: str,
    payload: CreationOpportunite,
    request: Request,
    idempotence: None = Depends(_refuser_idempotence),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Qualifie une Expression en Opportunité du tenant, statut initial ``DETECTED``.

    ``statut`` est absent du corps : le serveur le force et un client qui l'envoie est
    refusé en 422. L'Expression doit être ``PROPOSED`` ou ``CONFIRMED`` (sinon 409) ; elle
    est verrouillée pendant la création, et son lien inverse ``opportunity_ids`` est écrit
    dans la même transaction.
    """
    _verifier_espace(x_espace)
    tenant = _tenant(request, x_tenant)
    resultat = await _executer_transition(
        tenant,
        lambda conn: commandes_boucle.creer_opportunite(
            boucle, conn, tenant, eid, **payload.model_dump(exclude_none=True)),
        request=request,
    )
    return _reponse_transition(tenant, resultat, "opportunite")


@router.post("/expressions/{eid}/risks", status_code=201,
             response_model=ReponseTransition, responses=_REPONSES_TRANSITION)
async def creer_risque(
    eid: str,
    payload: CreationRisque,
    request: Request,
    idempotence: None = Depends(_refuser_idempotence),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Qualifie une Expression en Risque du tenant, statut initial ``DETECTED``.

    Même règle que l'opportunité : Expression ``PROPOSED``/``CONFIRMED`` seulement.
    """
    _verifier_espace(x_espace)
    tenant = _tenant(request, x_tenant)
    resultat = await _executer_transition(
        tenant,
        lambda conn: commandes_boucle.creer_risque(
            boucle, conn, tenant, eid, **payload.model_dump(exclude_none=True)),
        request=request,
    )
    return _reponse_transition(tenant, resultat, "risque")


@router.get("/expressions/{eid}/opportunities")
async def lister_opportunites(
    eid: str,
    request: Request,
    limite: int = Query(100, ge=1, le=1000),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Liste les Opportunités d'une Expression du tenant, bornées par ``limite``."""
    _verifier_espace(x_espace)
    tenant = _tenant(request, x_tenant)
    opportunites = await _executer_transition(
        tenant,
        lambda conn: commandes_boucle.lister_opportunites(
            boucle, conn, tenant, eid, limite=limite),
        request=request,
    )
    return {"tenant": tenant, "opportunites": _assainir(opportunites)}


@router.get("/expressions/{eid}/risks")
async def lister_risques(
    eid: str,
    request: Request,
    limite: int = Query(100, ge=1, le=1000),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Liste les Risques d'une Expression du tenant, bornés par ``limite``."""
    _verifier_espace(x_espace)
    tenant = _tenant(request, x_tenant)
    risques = await _executer_transition(
        tenant,
        lambda conn: commandes_boucle.lister_risques(
            boucle, conn, tenant, eid, limite=limite),
        request=request,
    )
    return {"tenant": tenant, "risques": _assainir(risques)}


@router.post("/opportunities/{oid}/statut", response_model=ReponseTransition,
             responses=_REPONSES_TRANSITION)
async def changer_statut_opportunite(
    oid: str,
    payload: ChangementStatutObjet,
    request: Request,
    idempotence: None = Depends(_refuser_idempotence),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Fait évoluer une Opportunité selon le cycle canonique C5b.

    Une transition non autorisée est un 409, un statut inconnu ou un identifiant d'un autre
    type un 422, une source absente ou hors tenant un 404. ``maj_le`` est posé par le
    serveur et la version précédente reste dans ``historique``.
    """
    _verifier_espace(x_espace)
    tenant = _tenant(request, x_tenant)
    champs = payload.model_dump(exclude_none=True)
    statut = champs.pop("statut")
    resultat = await _executer_transition(
        tenant,
        lambda conn: commandes_boucle.changer_statut_opportunite(
            boucle, conn, tenant, oid, statut, **champs),
        request=request,
    )
    return _reponse_transition(tenant, resultat, "opportunite")


@router.post("/risks/{rid}/statut", response_model=ReponseTransition,
             responses=_REPONSES_TRANSITION)
async def changer_statut_risque(
    rid: str,
    payload: ChangementStatutObjet,
    request: Request,
    idempotence: None = Depends(_refuser_idempotence),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Fait évoluer un Risque selon le même cycle et les mêmes erreurs que l'opportunité."""
    _verifier_espace(x_espace)
    tenant = _tenant(request, x_tenant)
    champs = payload.model_dump(exclude_none=True)
    statut = champs.pop("statut")
    resultat = await _executer_transition(
        tenant,
        lambda conn: commandes_boucle.changer_statut_risque(
            boucle, conn, tenant, rid, statut, **champs),
        request=request,
    )
    return _reponse_transition(tenant, resultat, "risque")


@router.post("/investigations/{iid}/hypotheses", status_code=201,
             response_model=ReponseTransition, responses=_REPONSES_TRANSITION)
async def creer_hypothese(
    iid: str,
    payload: CreationHypothese,
    request: Request,
    idempotence: None = Depends(_refuser_idempotence),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Formule une Hypothèse initiale sur une Investigation du tenant.

    ``statut``, ``mode``, ``id`` et ``investigation_id`` sont absents du corps : le
    serveur force ``OPEN``/``PROPOSED`` et un client qui les envoie est refusé en 422.
    ``expert_id`` est également refusé tant que C5e n'expose pas les Experts.
    L'Investigation doit être ouverte (sinon 409), est verrouillée et son lien inverse
    ``hypothesis_ids`` est écrit dans la même transaction.
    """
    _verifier_espace(x_espace)
    tenant = _tenant(request, x_tenant)
    resultat = await _executer_transition(
        tenant,
        lambda conn: commandes_boucle.creer_hypothese(
            boucle, conn, tenant, iid, **payload.model_dump(exclude_none=True)),
        request=request,
    )
    return _reponse_transition(tenant, resultat, "hypothese")


@router.get("/hypotheses")
async def lister_hypotheses(
    request: Request,
    investigation_id: str | None = Query(None, max_length=128),
    statut: str | None = Query(None, max_length=64),
    limite: int = Query(100, ge=1, le=1000),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Liste les Hypothèses du tenant, filtrées par Investigation et statut."""
    _verifier_espace(x_espace)
    tenant = _tenant(request, x_tenant)
    hypotheses = await _executer_transition(
        tenant,
        lambda conn: commandes_boucle.lister_hypotheses(
            boucle, conn, tenant, investigation_id=investigation_id,
            statut=statut, limite=limite),
        request=request,
    )
    return {"tenant": tenant, "hypotheses": _assainir(hypotheses)}


@router.post("/hypotheses/{hid}/statut", response_model=ReponseTransition,
             responses=_REPONSES_TRANSITION)
async def changer_statut_hypothese(
    hid: str,
    payload: ChangementStatutHypothese,
    request: Request,
    idempotence: None = Depends(_refuser_idempotence),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Fait évoluer une Hypothèse selon le cycle canonique C5c.

    Une transition non autorisée est un 409, un statut inconnu ou un ``CONFIRMED`` sans
    preuve un 422, une cible absente ou hors tenant un 404, un identifiant d'un autre
    type un 422. ``maj_le`` est posé par le serveur et la version précédente reste dans
    ``historique``.
    """
    _verifier_espace(x_espace)
    tenant = _tenant(request, x_tenant)
    champs = payload.model_dump(exclude_none=True)
    vers = champs.pop("vers")
    resultat = await _executer_transition(
        tenant,
        lambda conn: commandes_boucle.changer_statut_hypothese(
            boucle, conn, tenant, hid, vers, **champs),
        request=request,
    )
    return _reponse_transition(tenant, resultat, "hypothese")


@router.post("/signals", status_code=201,
             response_model=ReponseTransition, responses=_REPONSES_TRANSITION,
             openapi_extra=_OPENAPI_CORPS_SIGNAL)
async def creer_signal(
    request: Request,
    payload: CreationSignal = Depends(_corps_signal),
    idempotence: None = Depends(_refuser_idempotence),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Enregistre un Signal global, éventuellement rattaché à plusieurs Situations.

    ``statut`` (``DETECTED``), ``mode`` (``OBSERVED``), ``id``, ``tenant_id`` et
    ``fingerprint`` sont serveur : un client qui les envoie est refusé en 422.
    L'empreinte est calculée avant écriture ; un doublon répond 409. Une Situation
    absente ou hors tenant répond 404. Aucune route de changement de statut n'existe
    en C5d.
    """
    _verifier_espace(x_espace)
    tenant = _tenant(request, x_tenant)
    resultat = await _executer_transition(
        tenant,
        lambda conn: commandes_boucle.creer_signal(
            boucle, conn, tenant, **payload.model_dump(exclude_none=True)),
        request=request,
    )
    return _reponse_transition(tenant, resultat, "signal")


@router.post("/situations/{sid}/signals", status_code=201,
             response_model=ReponseTransition, responses=_REPONSES_TRANSITION,
             openapi_extra=_OPENAPI_CORPS_SIGNAL)
async def creer_signal_depuis_situation(
    sid: str,
    request: Request,
    payload: CreationSignal = Depends(_corps_signal),
    idempotence: None = Depends(_refuser_idempotence),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Enregistre un Signal rattaché à une Situation du tenant.

    La Situation est forcée par la route ; un corps qui porte ``situation_ids`` doit
    contenir exactement ``sid`` (sinon 422). Une Situation absente ou hors tenant
    répond 404 avant toute écriture.
    """
    _verifier_espace(x_espace)
    tenant = _tenant(request, x_tenant)
    resultat = await _executer_transition(
        tenant,
        lambda conn: commandes_boucle.creer_signal(
            boucle, conn, tenant, situation_id=sid,
            **payload.model_dump(exclude_none=True)),
        request=request,
    )
    return _reponse_transition(tenant, resultat, "signal")


@router.get("/signals")
async def lister_signaux(
    request: Request,
    situation_id: str | None = Query(None, max_length=128),
    type_signal: TypeSignal | None = Query(None),
    statut: str | None = Query(None, max_length=64),
    limite: int = Query(100, ge=1, le=1000),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Liste les Signaux du tenant, filtrés par Situation, type et statut."""
    _verifier_espace(x_espace)
    tenant = _tenant(request, x_tenant)
    signaux = await _executer_transition(
        tenant,
        lambda conn: commandes_boucle.lister_signaux(
            boucle, conn, tenant, situation_id=situation_id,
            type_signal=type_signal, statut=statut, limite=limite),
        request=request,
    )
    return {"tenant": tenant, "signaux": _assainir(signaux)}


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


@router.post("/scenarios", status_code=201, response_model=ReponseTransition,
             responses=_REPONSES_TRANSITION)
async def creer_scenario(
    payload: CreationScenario,
    request: Request,
    idempotence: None = Depends(_refuser_idempotence),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Crée un Scénario rattaché à une Investigation et/ou une Decision du tenant."""
    _verifier_espace(x_espace)
    tenant = _tenant(request, x_tenant)
    resultat = await _executer_transition(
        tenant,
        lambda conn: commandes_boucle.creer_scenario(
            boucle, conn, tenant, **payload.model_dump(exclude_none=True)),
        request=request,
    )
    return _reponse_transition(tenant, resultat, "scenario")


@router.get("/scenarios")
async def lister_scenarios(
    request: Request,
    investigation_id: str | None = Query(None, max_length=128),
    decision_id: str | None = Query(None, max_length=128),
    limite: int = Query(100, ge=1, le=1000),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Liste les Scénarios du tenant, filtrés par Investigation et/ou Decision."""
    _verifier_espace(x_espace)
    tenant = _tenant(request, x_tenant)
    scenarios = await _executer_transition(
        tenant,
        lambda conn: commandes_boucle.lister_scenarios(
            boucle, conn, tenant, investigation_id=investigation_id,
            decision_id=decision_id, limite=limite),
        request=request,
    )
    return {"tenant": tenant, "scenarios": _assainir(scenarios)}


@router.post("/scenarios/comparer")
async def comparer_scenarios(
    payload: ComparaisonScenarios,
    request: Request,
    idempotence: None = Depends(_refuser_idempotence),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Compare des Scénarios du tenant à une référence et rend les écarts canoniques."""
    _verifier_espace(x_espace)
    tenant = _tenant(request, x_tenant)
    resultat = await _executer_transition(
        tenant,
        lambda conn: commandes_boucle.comparer_scenarios(
            boucle, conn, tenant, payload.scenario_ids, payload.reference_id),
        request=request,
    )
    return {"tenant": tenant, **_assainir(resultat)}
