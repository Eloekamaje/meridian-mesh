"""Modèle de valeur : types, statuts, attribution et écart attendu/observé.

Ce module ne calcule pas de ROI et n'invente pas de causalité. Il valide une hypothèse de valeur et
calcule seulement un écart lorsque les nombres, l'unité et la devise sont comparables.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
import math

from jumeau import valeur_depot

__all__ = [
    "ATTRIBUTIONS", "STATUTS", "TYPES_VALEUR", "ValeurInvalide",
    "creer", "ecart", "lire", "lister", "mettre_a_jour", "resume", "valider",
]

TYPES_VALEUR = (
    "revenu", "cout_evite", "cout_reduit", "temps", "qualite", "sla", "risque",
    "conformite", "client", "connaissance", "strategie", "autre",
)
STATUTS = ("hypothese", "mesuree", "validee", "realisee", "deplacee", "detruite", "abandonnee")
ATTRIBUTIONS = ("directe", "contribution", "activation", "inconnue")


class ValeurInvalide(valeur_depot.ValeurInvalide):
    """Une valeur, son écart ou sa provenance ne respecte pas le contrat."""


def _texte(valeur, champ, obligatoire=True):
    if valeur is None:
        if obligatoire:
            raise ValeurInvalide(f"{champ} obligatoire")
        return None
    texte = str(valeur).strip()
    if not texte and obligatoire:
        raise ValeurInvalide(f"{champ} obligatoire")
    return texte or None


def _nombre(valeur):
    if isinstance(valeur, Mapping):
        valeur = valeur.get("valeur")
    if isinstance(valeur, bool):
        return None
    try:
        nombre = float(valeur)
    except (TypeError, ValueError):
        return None
    return nombre if math.isfinite(nombre) else None


def _date(valeur, champ):
    if valeur is None:
        return None
    if isinstance(valeur, (date, datetime)):
        return valeur.isoformat()
    texte = _texte(valeur, champ)
    try:
        return datetime.fromisoformat(texte.replace("Z", "+00:00")).date().isoformat()
    except ValueError as exc:
        raise ValeurInvalide(f"{champ} invalide") from exc


def valider(valeur: Mapping) -> dict:
    """Valide et normalise une ligne de valeur, sans calculer d'attribution."""
    if not isinstance(valeur, Mapping):
        raise ValeurInvalide("valeur : objet attendu")
    resultat = dict(valeur)
    resultat["tenant_id"] = _texte(valeur.get("tenant_id"), "tenant_id")
    resultat["id"] = _texte(valeur.get("id"), "id")
    resultat["libelle"] = _texte(valeur.get("libelle"), "libelle")
    resultat["proprietaire"] = _texte(valeur.get("proprietaire"), "proprietaire")
    type_ = _texte(valeur.get("type"), "type").lower()
    if type_ not in TYPES_VALEUR:
        raise ValeurInvalide(f"type de valeur inconnu : {type_}")
    statut = (_texte(valeur.get("statut") or "hypothese", "statut")).lower()
    if statut not in STATUTS:
        raise ValeurInvalide(f"statut inconnu : {statut}")
    attribution = (_texte(valeur.get("attribution") or "inconnue", "attribution")).lower()
    if attribution not in ATTRIBUTIONS:
        raise ValeurInvalide(f"attribution inconnue : {attribution}")
    try:
        confiance = float(valeur.get("confiance", 0.5))
    except (TypeError, ValueError) as exc:
        raise ValeurInvalide("confiance invalide") from exc
    if not 0 <= confiance <= 1:
        raise ValeurInvalide("confiance hors bornes")
    for champ in ("baseline", "cible", "observe", "cout", "risque"):
        if valeur.get(champ) is not None and not isinstance(valeur[champ], (Mapping, int, float)):
            raise ValeurInvalide(f"{champ} : nombre ou objet attendu")
    resultat.update({
        "type": type_, "statut": statut, "attribution": attribution,
        "confiance": confiance, "date_revue": _date(valeur.get("date_revue"), "date_revue"),
    })
    return resultat


def ecart(valeur: Mapping) -> dict:
    """Écart observé/cible, seulement si les nombres, l'unité et la devise sont comparables."""
    if not isinstance(valeur, Mapping):
        raise ValeurInvalide("valeur : objet attendu")
    cible = _nombre(valeur.get("cible"))
    observe = _nombre(valeur.get("observe"))
    if cible is None or observe is None:
        return {"comparable": False, "raison": "cible ou observe numérique absent"}

    def _attribut(bloc, cle):
        if isinstance(bloc, Mapping) and bloc.get(cle):
            return _texte(bloc.get(cle), cle, False)
        return _texte(valeur.get(cle), cle, False)

    unite_cible = _attribut(valeur.get("cible"), "unite")
    unite_observe = _attribut(valeur.get("observe"), "unite")
    if unite_cible and unite_observe and unite_cible != unite_observe:
        return {"comparable": False, "raison": "unités différentes"}
    devise_cible = _attribut(valeur.get("cible"), "devise")
    devise_observe = _attribut(valeur.get("observe"), "devise")
    if devise_cible and devise_observe and devise_cible != devise_observe:
        return {"comparable": False, "raison": "devises différentes"}
    delta = observe - cible
    return {
        "comparable": True,
        "cible": cible,
        "observe": observe,
        "delta": round(delta, 4),
        "ecart_relatif": round(delta / cible, 4) if cible else None,
        "unite": unite_observe or unite_cible,
        "devise": devise_observe or devise_cible,
        "statut": "atteint" if delta >= 0 else "en_ecart",
    }


def creer(conn, tenant_id, valeur: Mapping) -> dict:
    donnees = valider({**dict(valeur), "tenant_id": tenant_id})
    try:
        resultat = valeur_depot.enregistrer(conn, tenant_id, donnees)
    except valeur_depot.ValeurInvalide as exc:
        raise ValeurInvalide(str(exc)) from exc
    return {**resultat, "ecart": ecart(resultat)}


def lire(conn, tenant_id, valeur_id) -> dict | None:
    resultat = valeur_depot.lire(conn, tenant_id, valeur_id)
    return {**resultat, "ecart": ecart(resultat)} if resultat is not None else None


def lister(conn, tenant_id, **filtres) -> list[dict]:
    return [{**ligne, "ecart": ecart(ligne)}
            for ligne in valeur_depot.lister(conn, tenant_id, **filtres)]


def mettre_a_jour(conn, tenant_id, valeur_id, changements: Mapping) -> dict:
    try:
        resultat = valeur_depot.mettre_a_jour(conn, tenant_id, valeur_id, changements)
    except valeur_depot.ValeurInvalide as exc:
        raise ValeurInvalide(str(exc)) from exc
    return {**resultat, "ecart": ecart(resultat)}


def resume(conn, tenant_id, **filtres) -> dict:
    return valeur_depot.resume(conn, tenant_id, **filtres)
