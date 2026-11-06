"""Passerelle entre le contexte, les spécialistes et le dossier de raisonnement.

Le contexte existant (Context Pack, Twins, Claims, preuves) ne devient pas un prompt : il devient
des `Constat` typés, avec provenance, confiance, fraîcheur et limites. C'est le point qui évite
au dossier de raisonnement d'être un simple texte à côté du vrai contexte.
"""
from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from typing import Any

from meridian.domain import dossier_raisonnement as domaine

__all__ = [
    "attacher",
    "constats_depuis_pack",
    "constats_depuis_specialistes",
    "depuis_pack",
    "depuis_scope",
]


def _lire(objet: Any, nom: str, defaut=None):
    if isinstance(objet, Mapping):
        return objet.get(nom, defaut)
    return getattr(objet, nom, defaut)


def _mapping(valeur) -> dict:
    return dict(valeur) if isinstance(valeur, Mapping) else {}


def _liste(valeur) -> list:
    if valeur is None:
        return []
    if isinstance(valeur, (list, tuple)):
        return list(valeur)
    return [valeur]


def _texte(valeur, maximum=1000) -> str:
    return " ".join(str(valeur or "").split())[:maximum]


def _ids(valeurs) -> tuple[str, ...]:
    resultat: list[str] = []
    for valeur in _liste(valeurs):
        if isinstance(valeur, Mapping):
            valeur = valeur.get("id") or valeur.get("locator") or valeur.get("hash")
        texte = _texte(valeur, 200)
        if texte and texte not in resultat:
            resultat.append(texte)
    return tuple(resultat)


def _premier(mapping: Mapping, *cles) -> str:
    for cle in cles:
        valeur = mapping.get(cle)
        if isinstance(valeur, (list, tuple)):
            valeur = valeur[0] if valeur else None
        texte = _texte(valeur, 200)
        if texte:
            return texte
    return ""


def depuis_pack(pack: Any, *, twin_ids=(), source_ids=(), limites=()) -> domaine.ContexteRaisonnement:
    """Transforme un Context Pack en empreinte de contexte, sans recopier le prompt."""
    if pack is None:
        return domaine.ContexteRaisonnement(
            twin_ids=tuple(twin_ids), source_ids=tuple(source_ids), limites=tuple(limites))
    faits = _liste(_lire(pack, "faits", ()))
    entites = _ids(_lire(pack, "entites", ()))
    preuves = _ids(_lire(pack, "preuves", ()))
    twins = list(twin_ids)
    sources = list(source_ids)
    claims = []
    for fait in faits:
        if not isinstance(fait, Mapping):
            continue
        donnees = _mapping(fait.get("donnees"))
        for valeur in _liste(donnees.get("twin_id") or donnees.get("twin_ids")
                             or donnees.get("application_id") or donnees.get("application_ids")):
            if _texte(valeur, 160) and _texte(valeur, 160) not in twins:
                twins.append(_texte(valeur, 160))
        for valeur in _liste(donnees.get("source_id") or donnees.get("source")):
            if _texte(valeur, 200) and _texte(valeur, 200) not in sources:
                sources.append(_texte(valeur, 200))
        if _texte(fait.get("type"), 40).upper() == "CLAIM":
            identifiant = _texte(fait.get("id"), 160)
            if identifiant and identifiant not in claims:
                claims.append(identifiant)
    toutes_limites = list(_liste(_lire(pack, "limites", ()))) + list(limites)
    return domaine.ContexteRaisonnement(
        fingerprint=_texte(_lire(pack, "fingerprint", ""), 128),
        entites=entites,
        twin_ids=tuple(twins),
        claim_ids=tuple(claims),
        preuve_ids=preuves,
        source_ids=tuple(sources),
        completude=_texte(_lire(pack, "completude", "complet"), 40) or "complet",
        fraicheur=_premier(faits[0], "fraicheur", "observe_le", "maj_le") if faits else "",
        limites=tuple(dict.fromkeys(_texte(v, 500) for v in toutes_limites if _texte(v, 500))),
    )


def _constat_depuis_fait(fait: Mapping, *, provenance="contexte") -> domaine.Constat | None:
    donnees = _mapping(fait.get("donnees"))
    texte = _texte(fait.get("titre") or fait.get("resume") or fait.get("texte"))
    if not texte:
        return None
    preuves = _ids(fait.get("preuves"))
    contradictions = tuple(_texte(v, 500) for v in _liste(donnees.get("contradictions")) if _texte(v, 500))
    return domaine.Constat(
        texte=texte,
        type=_texte(fait.get("type"), 40).upper() or "CONSTAT",
        provenance=_texte(fait.get("specialiste") or fait.get("provenance") or provenance, 240),
        twin_id=_premier(donnees, "twin_id", "application_id"),
        claim_id=_texte(fait.get("claim_id") or (fait.get("id") if _texte(fait.get("type"), 40).upper() == "CLAIM" else ""), 160),
        preuve_id=preuves[0] if preuves else "",
        source_id=_premier(donnees, "source_id", "source"),
        confiance=fait.get("confiance", 0.5),
        fraicheur=_texte(fait.get("fraicheur") or _premier(donnees, "observe_le", "maj_le", "date"), 80),
        contradictions=contradictions,
        limites=tuple(_texte(v, 500) for v in _liste(fait.get("limites")) if _texte(v, 500)),
        donnees=donnees,
        id=_texte(fait.get("id"), 80),
    )


def constats_depuis_pack(pack: Any) -> tuple[domaine.Constat, ...]:
    """Un fait de Context Pack devient un constat ; aucun fait n'est inventé."""
    resultat = []
    for fait in _liste(_lire(pack, "faits", ())):
        if isinstance(fait, Mapping):
            constat = _constat_depuis_fait(fait)
            if constat is not None:
                resultat.append(constat)
    return tuple(resultat)


def constats_depuis_specialistes(dossier: Any) -> tuple[domaine.Constat, ...]:
    """Les propositions des spécialistes deviennent des constats contextualisés."""
    resultat = []
    for proposition in _liste(_lire(dossier, "propositions", ())):
        if isinstance(proposition, Mapping):
            constat = _constat_depuis_fait(proposition, provenance="specialiste")
            if constat is not None:
                resultat.append(constat)
    return tuple(resultat)


def _empreinte_scope(scope: Mapping) -> str:
    charge = json.dumps({
        "twin_ids": sorted(scope.get("twin_ids") or ()),
        "claim_ids": sorted(scope.get("claim_ids") or ()),
        "situation_id": scope.get("situation_id"),
        "application_id": scope.get("application_id"),
        "question": scope.get("question"),
        "acteur": scope.get("acteur"),
        "poste": scope.get("poste"),
        "espace": scope.get("espace"),
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "ctx-" + hashlib.sha256(charge.encode("utf-8")).hexdigest()[:16]


def depuis_scope(contexte: Mapping | None = None) -> domaine.ContexteRaisonnement:
    """Contexte minimal pour le chat : périmètre et identifiants, sans prétendre à un Context Pack."""
    contexte = _mapping(contexte)
    twins = list(_ids(contexte.get("twin_ids") or contexte.get("jumeaux") or ()))
    claims = list(_ids(contexte.get("claim_ids") or ()))
    sources = list(_ids(contexte.get("source_ids") or contexte.get("sources") or ()))
    return domaine.ContexteRaisonnement(
        fingerprint=_empreinte_scope(contexte),
        acteur=_texte(contexte.get("acteur"), 128),
        poste=_texte(contexte.get("poste"), 160),
        profil=_texte(contexte.get("profil"), 80),
        autorite=_texte(contexte.get("autorite"), 20),
        espace=_texte(contexte.get("espace"), 160),
        twin_ids=tuple(twins),
        claim_ids=tuple(claims),
        source_ids=tuple(sources),
        completude=_texte(contexte.get("completude") or ("partiel" if contexte.get("partiel") else "complet"), 40),
        limites=tuple(_texte(v, 500) for v in _liste(contexte.get("limites")) if _texte(v, 500)),
    )


def attacher(
    dossier: domaine.DossierRaisonnement,
    *,
    pack=None,
    specialistes=None,
    contexte: Mapping | None = None,
    trace_id: str = "",
) -> domaine.DossierRaisonnement:
    """Attache contexte, constats et trace à un dossier existant."""
    if pack is not None:
        dossier.contexte = depuis_pack(pack, twin_ids=(dossier.contexte.twin_ids if dossier.contexte else ()))
        constats = constats_depuis_pack(pack)
    else:
        dossier.contexte = depuis_scope(contexte)
        constats = ()
    if specialistes is not None:
        constats = (*constats, *constats_depuis_specialistes(specialistes))
    uniques = []
    vus = set()
    for constat in constats:
        cle = constat.id or constat.texte
        if cle and cle not in vus:
            vus.add(cle)
            uniques.append(constat)
    dossier.constats = tuple(uniques)
    if trace_id:
        dossier.trace_id = _texte(trace_id, 80)
    dossier.maj_le = domaine.maintenant()
    return dossier
