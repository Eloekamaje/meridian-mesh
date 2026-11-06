"""API du jumeau réel (phase 0) : Claims prouvés, extraits vérifiés, revue humaine.

L'acteur vient de l'identité authentifiée (ou vaut ``demo``), jamais d'un en-tête client.
"""
import os
import re
from typing import Literal, Optional

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import acteur as acteur_courant
from meridian.adapters.outbound.postgres import carte
from meridian.adapters.outbound.postgres import connaissance
from meridian.adapters.outbound.postgres import depot
from meridian.adapters.outbound.postgres import partage
from meridian.domain.partage import Consommateur, PartageInvalide
from meridian.domain.roles import ROLES_PUBLICATION, role_canonique
from meridian.adapters.outbound.llm import flore
from meridian.adapters.outbound.llm import gardien
from meridian.adapters.outbound.connectors.source_git import lire_au_sha
from meridian.adapters.outbound.connectors.source_git import extrait

router = APIRouter(prefix="/v2", tags=["jumeau"])


def connexion():
    dsn = os.environ.get("JUMEAU_PG_DSN")
    if not dsn:
        raise HTTPException(503, "Couche cognitive non configurée (JUMEAU_PG_DSN)")
    with psycopg.connect(dsn, autocommit=True) as conn:
        yield conn


class Revue(BaseModel):
    decision: Literal["ACCEPTED", "CONTESTED"]
    motif: Optional[str] = Field(default=None, max_length=2000)


class NouvelleConsigne(BaseModel):
    portee: Literal["domaine", "equipe", "jumeau"]
    texte: str = Field(min_length=1, max_length=depot.MAX_TEXTE)
    pourquoi: str = Field(min_length=1, max_length=depot.MAX_POURQUOI)


class Tranche(BaseModel):
    verdict: Literal["a", "b", "aucune"]
    motif: Optional[str] = Field(default=None, max_length=2000)


class PublicationCarte(BaseModel):
    reviewed_by: Optional[str] = Field(default=None, max_length=200)
    # EXTERNAL reste connu du domaine mais n'est pas exposé par l'API : hors périmètre pour le moment.
    scope: Literal["TENANT", "TEAM", "PORTFOLIO"] = "TENANT"
    scope_id: Optional[str] = Field(default=None, max_length=200)


class RevueCarte(BaseModel):
    share_id: int
    decision: Literal["APPROVED", "REJECTED"]
    reason: Optional[str] = Field(default=None, max_length=2000)


@router.get("/jumeaux")
def lister_jumeaux(conn=Depends(connexion)):
    return depot.lister_jumeaux(conn)


@router.get("/jumeaux/{jumeau_id}/claims")
def lister_claims(jumeau_id: str, conn=Depends(connexion)):
    return depot.lister_claims(conn, jumeau_id)


@router.get("/preuves/{preuve_id}/extrait")
def lire_extrait(preuve_id: int, conn=Depends(connexion)):
    preuve = depot.preuve_par_id(conn, preuve_id)
    if not preuve:
        raise HTTPException(404, "Preuve introuvable")
    try:
        return {"chemin": preuve["chemin"], "sha": preuve["sha"], **extrait(preuve)}
    except ValueError:
        raise HTTPException(422, "Preuve invalide")


@router.post("/claims/{claim_id}/revue")
def reviser(claim_id: int, revue: Revue, request: Request, conn=Depends(connexion)):
    try:
        enonce = depot.reviser(conn, claim_id, acteur_courant(request), revue.decision, revue.motif)
    except LookupError:
        raise HTTPException(404, "Claim introuvable")
    if revue.decision == "CONTESTED" and depot.nettoyer_consigne(revue.motif):
        return {"ok": True, "consigne_proposee": depot.consigne_proposee(enonce, revue.motif)}
    return {"ok": True}


def _jumeau_ou_404(conn, jumeau_id):
    jumeau = depot.jumeau_par_id(conn, jumeau_id)
    if not jumeau:
        raise HTTPException(404, "Jumeau introuvable")
    return jumeau


@router.get("/jumeaux/{jumeau_id}/consignes")
def lister_consignes(jumeau_id: str, conn=Depends(connexion)):
    return depot.consignes_du_jumeau(conn, _jumeau_ou_404(conn, jumeau_id))


@router.post("/jumeaux/{jumeau_id}/consignes")
def ajouter_consigne(jumeau_id: str, consigne: NouvelleConsigne, request: Request, conn=Depends(connexion)):
    jumeau = _jumeau_ou_404(conn, jumeau_id)
    try:
        return {"id": depot.ajouter_consigne(conn, jumeau, consigne.portee, consigne.texte, consigne.pourquoi, acteur_courant(request))}
    except ValueError as e:  # obligatoires, trop longs, ou quota de la portée atteint
        raise HTTPException(422, str(e))


@router.post("/jumeaux/{jumeau_id}/consignes/{consigne_id}/retrait")
def retirer_consigne(jumeau_id: str, consigne_id: int, conn=Depends(connexion)):
    jumeau = _jumeau_ou_404(conn, jumeau_id)
    try:
        depot.retirer_consigne(conn, jumeau, consigne_id)
    except LookupError:
        raise HTTPException(404, "Consigne introuvable ou déjà retirée")
    return {"ok": True}


@router.post("/contradictions/{contradiction_id}/revue")
def trancher(contradiction_id: int, decision: Tranche, request: Request, conn=Depends(connexion)):
    c = depot.contradiction_par_id(conn, contradiction_id)
    try:
        if not c:
            raise LookupError(contradiction_id)
        depot.trancher_contradiction(conn, c["jumeau_id"], contradiction_id, acteur_courant(request), decision.verdict, decision.motif)
    except LookupError:
        raise HTTPException(404, "Contradiction introuvable ou déjà tranchée")
    return {"ok": True}


RE_DEPOT_LOCATOR = re.compile(r"git://([\w][\w.-]*)@[0-9a-f]+:")


def depot_du_locator(locator):
    """Le nom du dépôt d'une preuve de code (`git://depot@sha:chemin#La-Lb`), ou None."""
    m = RE_DEPOT_LOCATOR.match(locator or "")
    return m.group(1) if m else None


def extrait_preuve(conn, locator):
    """(jumeau, extrait) d'une preuve de code citée dans une réponse ; (None, None) si son dépôt est inconnu ou
    ambigu (un même nom chez deux jumeaux : on ne devine pas)."""
    nom = depot_du_locator(locator)
    lignes = conn.execute("SELECT DISTINCT jumeau_id FROM source WHERE nom = %s AND type = 'GIT'", (nom,)).fetchall() if nom else []
    if len(lignes) != 1:
        return None, None
    return lignes[0][0], _extrait_citation(conn, lignes[0][0], locator, "git")


def _extrait_citation(conn, jumeau_id, locator, systeme, contexte=3):
    """Lignes du code citées (et leur contexte) ; pour une autre source, locator et système seulement."""
    base = {"systeme": systeme, "locator": locator, "lignes": None}
    m = connaissance.RE_CITATION.fullmatch(locator) if systeme == "git" else None
    if not m:
        return base
    depot_nom, chemin, debut, fin = connaissance.decouper(m)
    try:
        source = connaissance.resoudre_source(depot.sources_du_jumeau(conn, jumeau_id), depot_nom, chemin)
        lignes = lire_au_sha(source.get("copie") or source["emplacement"], source["curseur"])(chemin)
    except (LookupError, ValueError):
        return base
    if lignes is None:
        return base
    de, a = max(1, debut - contexte), min(len(lignes), fin + contexte)
    return {**base, "lignes": [{"n": n, "texte": lignes[n - 1], "citee": debut <= n <= fin} for n in range(de, a + 1)]}


@router.get("/contradictions/{contradiction_id}/extraits")
def lire_extraits_contradiction(contradiction_id: int, conn=Depends(connexion)):
    c = depot.contradiction_par_id(conn, contradiction_id)
    if not c:
        raise HTTPException(404, "Contradiction introuvable")
    return [_extrait_citation(conn, c["jumeau_id"], c[f"preuve_{x}"], c[f"systeme_{x}"]) for x in "ab"]


@router.get("/jumeaux/{jumeau_id}/fiche")
def lire_fiche(jumeau_id: str, conn=Depends(connexion)):
    """Fiche vivante rédigée par le gardien : ce que le jumeau dit de l'application."""
    fiche, sources = gardien.fiche_courante(conn, jumeau_id), depot.sources_du_jumeau(conn, jumeau_id)
    if not fiche or not sources:
        raise HTTPException(404, "Pas encore de fiche vivante pour ce jumeau")
    return flore.fiche_affichable(fiche, sources)


def _consommateur_requete(request: Request) -> Consommateur | None:
    """Le périmètre authentifié (tenant + espace), jamais un en-tête client."""
    tenant = getattr(request.state, "tenant", None)
    if not tenant:
        return None
    return Consommateur(
        str(tenant),
        portfolio_id=str(getattr(request.state, "perimetre", "")
                         or getattr(request.state, "espace", "") or ""),
    )


def _peut_publier(request, jumeau) -> bool:
    """En démo, l'acteur peut publier ; hors démo, rôle, autorité ou équipe propriétaire."""
    if str(getattr(request.state, "auth_mode", "demo") or "demo") == "demo":
        return True
    if role_canonique(getattr(request.state, "role", "")) in ROLES_PUBLICATION:
        return True
    autorite = str(getattr(request.state, "autorite", "") or "").strip().lower()
    if autorite in {"decision", "approbation"}:
        return True
    equipes = {str(valeur).strip() for valeur in (getattr(request.state, "equipes", ()) or ())
               if str(valeur).strip()}
    equipe = str(getattr(request.state, "equipe", "") or "").strip()
    if equipe:
        equipes.add(equipe)
    return bool(equipes) and str(jumeau.get("equipe") or "").strip() in equipes


def _tenant_publication(conn, jumeau_id: str, request: Request) -> str:
    """Tenant du jumeau si l'acteur peut publier sa carte ; 403 ou 404 sinon."""
    tenant = getattr(request.state, "tenant", None)
    if not tenant:
        raise HTTPException(403, "Tenant authentifié requis")
    jumeau = depot.jumeau_carte(conn, jumeau_id)
    if not jumeau or jumeau.get("tenant_id") != tenant:
        raise HTTPException(404, "Jumeau introuvable")
    if not _peut_publier(request, jumeau):
        raise HTTPException(403, "Publication non autorisée")
    return tenant


@router.get("/jumeaux/{jumeau_id}/carte")
async def lire_carte(
    jumeau_id: str,
    request: Request,
    audience: Literal["business", "architecture", "audit"] = "business",
    technique: bool = False,
    conn=Depends(connexion),
):
    """Carte de catalogue : identité, owner, capacités, interfaces, dépendances, fraîcheur, criticité."""
    db = getattr(request.app.state, "db", None)
    if db is None:
        raise HTTPException(503, "Registre non configuré")
    tenant = getattr(request.state, "tenant", None)
    resultat = await carte.carte_du_jumeau(
        conn, db, jumeau_id, consommateur=_consommateur_requete(request), tenant_id=tenant,
        audience=audience, inclure_technique=technique)
    if not resultat:
        raise HTTPException(404, "Jumeau introuvable")
    return resultat


@router.post("/jumeaux/{jumeau_id}/carte/publier")
def publier_carte(
    jumeau_id: str,
    request: Request,
    publication: PublicationCarte | None = None,
    conn=Depends(connexion),
):
    """Publie la carte au tenant : Claims métier en SUMMARY, preuves non exposées."""
    tenant = getattr(request.state, "tenant", None)
    if not tenant:
        raise HTTPException(403, "Tenant authentifié requis")
    jumeau = depot.jumeau_carte(conn, jumeau_id)
    if not jumeau or jumeau.get("tenant_id") != tenant:
        raise HTTPException(404, "Jumeau introuvable")
    if not _peut_publier(request, jumeau):
        raise HTTPException(403, "Publication non autorisée")
    p = publication or PublicationCarte()
    try:
        return partage.publier_carte(
            conn, tenant, jumeau_id, granted_by=acteur_courant(request),
            scope_type=p.scope, scope_id=p.scope_id, reviewed_by=p.reviewed_by)
    except PartageInvalide as erreur:
        raise HTTPException(422, str(erreur))


@router.post("/jumeaux/{jumeau_id}/carte/depublier")
def depublier_carte(
    jumeau_id: str,
    request: Request,
    publication: PublicationCarte | None = None,
    conn=Depends(connexion),
):
    """Retire la carte du catalogue public ; les preuves restent dans le Twin."""
    tenant = getattr(request.state, "tenant", None)
    if not tenant:
        raise HTTPException(403, "Tenant authentifié requis")
    jumeau = depot.jumeau_carte(conn, jumeau_id)
    if not jumeau or jumeau.get("tenant_id") != tenant:
        raise HTTPException(404, "Jumeau introuvable")
    if not _peut_publier(request, jumeau):
        raise HTTPException(403, "Publication non autorisée")
    p = publication or PublicationCarte()
    try:
        return partage.depublier_carte(
            conn, tenant, jumeau_id, revoked_by=acteur_courant(request),
            scope_type=p.scope, scope_id=p.scope_id)
    except PartageInvalide as erreur:
        raise HTTPException(422, str(erreur))


@router.get("/jumeaux/{jumeau_id}/carte/a-reviser")
def lister_carte_a_reviser(jumeau_id: str, request: Request, conn=Depends(connexion)):
    """Partages de la carte en attente de revue de publication."""
    tenant = _tenant_publication(conn, jumeau_id, request)
    return partage.lister_a_reviser(conn, tenant, jumeau_id)


@router.post("/jumeaux/{jumeau_id}/carte/revue")
def decider_revue_carte(
    jumeau_id: str,
    revue: RevueCarte,
    request: Request,
    conn=Depends(connexion),
):
    """Approuve ou rejette une publication en attente et trace le reviewer."""
    tenant = _tenant_publication(conn, jumeau_id, request)
    try:
        return partage.decider_revue(
            conn, tenant, revue.share_id,
            reviewer=acteur_courant(request), decision=revue.decision, reason=revue.reason)
    except PartageInvalide as erreur:
        raise HTTPException(422, str(erreur))
    except LookupError:
        raise HTTPException(404, "Partage introuvable")
