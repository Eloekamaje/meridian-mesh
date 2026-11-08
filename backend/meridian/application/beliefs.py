"""Beliefs persistés : érosion de confiance et conversion dossier → objets BELIEF (C2/D2).

Module pur : aucun accès base, réseau ou adaptateur. La persistance passe par
``adapters.outbound.postgres.boucle.enregistrer_boucle`` ; ce module calcule la
confiance effective d'un belief — qui s'érode par demi-vie depuis sa dernière
revalidation — et prépare les objets canoniques à partir d'un dossier de
raisonnement.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import hashlib
import math

from meridian.domain import modele_entreprise as modele

__all__ = [
    "DEMI_VIE_JOURS",
    "STATUTS_TENUS",
    "beliefs_persistables",
    "confiance_effective",
]

# Demi-vie de confiance d'un belief non revalidé : passé ce délai depuis
# `revalide_le`, la confiance effective est divisée par deux.
DEMI_VIE_JOURS = 90.0

# Seules les croyances « tenues » d'un dossier deviennent des BELIEF canoniques ;
# INCONNU, CONTREDIT ou PERIME ne sont pas des conclusions.
STATUTS_TENUS = ("CONNU", "SUPPOSE")
_STATUTS_ETEINTS = ("REVISE", "CADUC")


def _texte(valeur, maximum=4000) -> str:
    return " ".join(str(valeur or "").split())[:maximum]


def _textes(valeurs) -> list[str]:
    if valeurs is None:
        return []
    if isinstance(valeurs, str):
        valeurs = [valeurs]
    resultat: list[str] = []
    for valeur in valeurs:
        texte = _texte(valeur, 240)
        if texte and texte not in resultat:
            resultat.append(texte)
    return resultat


def _vue(valeur) -> dict:
    if hasattr(valeur, "as_dict"):
        valeur = valeur.as_dict()
    elif hasattr(valeur, "to_dict"):
        valeur = valeur.to_dict()
    return dict(valeur) if isinstance(valeur, Mapping) else {}


def _valeur(objet, nom: str, defaut=None):
    """Lit un champ sur une ligne `objet_entreprise` (donnees) ou un objet canonique."""
    if objet is None:
        return defaut
    if hasattr(objet, "as_dict") or hasattr(objet, "to_dict"):
        objet = _vue(objet)
    if isinstance(objet, Mapping):
        if nom in objet:
            return objet[nom]
        donnees = objet.get("donnees")
        if isinstance(donnees, Mapping) and nom in donnees:
            return donnees[nom]
        return defaut
    return getattr(objet, nom, defaut)


def _instant(valeur) -> datetime | None:
    if valeur is None:
        return None
    if isinstance(valeur, datetime):
        instant = valeur
    elif isinstance(valeur, str):
        try:
            instant = datetime.fromisoformat(valeur.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant


def confiance_effective(
    belief, maintenant=None, *, demi_vie_jours: float = DEMI_VIE_JOURS,
) -> float:
    """Confiance d'un belief à `maintenant`, érodée depuis `revalide_le`.

    ``confiance × 2 ** (-âge / demi_vie)``, bornée dans ``[0, confiance]`` :
    l'érosion ne dépasse jamais la confiance initiale et ne devient pas
    négative. Un belief REVISE ou CADUC a une confiance effective nulle — la
    révision n'érode pas, elle éteint.
    """
    statut = _texte(_valeur(belief, "statut"), 40).upper()
    if statut in _STATUTS_ETEINTS:
        return 0.0
    try:
        confiance = float(_valeur(belief, "confiance", 0.0) or 0.0)
    except (TypeError, ValueError):
        confiance = 0.0
    if not math.isfinite(confiance):
        confiance = 0.0
    confiance = max(0.0, min(1.0, confiance))
    if confiance <= 0.0:
        return 0.0
    reference = _instant(_valeur(belief, "revalide_le")) or _instant(
        _valeur(belief, "cree_le"))
    pivot = _instant(maintenant) or datetime.now(timezone.utc)
    if reference is None:
        return confiance
    try:
        age_jours = (pivot - reference).total_seconds() / 86400.0
    except TypeError:
        return confiance
    if age_jours <= 0.0:
        return confiance
    try:
        demi_vie = float(demi_vie_jours)
    except (TypeError, ValueError):
        demi_vie = DEMI_VIE_JOURS
    if demi_vie <= 0.0:
        return confiance
    return max(0.0, min(confiance, confiance * math.pow(0.5, age_jours / demi_vie)))


def _constat_id_claim(constat: Mapping) -> str:
    claim = _texte(constat.get("claim_id"), 240)
    if claim:
        return claim
    donnees = constat.get("donnees")
    if isinstance(donnees, Mapping):
        return _texte(donnees.get("claim_id"), 240)
    return ""


def _constat_id_twin(constat: Mapping) -> str:
    twin = _texte(constat.get("twin_id"), 160)
    if twin:
        return twin
    donnees = constat.get("donnees")
    if isinstance(donnees, Mapping):
        return _texte(donnees.get("twin_id"), 160)
    return ""


def beliefs_persistables(dossier, tenant: str = "", *, maintenant=None) -> list[modele.Belief]:
    """Convertit les croyances « tenues » d'un dossier en objets BELIEF canoniques.

    Chaque belief produit est adossé au claim cité par le constat dont il est
    issu : le texte du constat et l'objet du belief coïncident (même troncature
    que `beliefs_depuis_constats`). Une croyance sans claim résoluble — ou non
    tenue (INCONNU, CONTREDIT, PERIME) — n'est pas persistée : un BELIEF
    RAISONNEMENT sans appui enfreindrait l'invariant du modèle.
    """
    vue = _vue(dossier)
    if not vue:
        return []
    tenant_id = _texte(tenant, 128) or _texte(vue.get("tenant"), 128) or "local"
    pivot = _instant(maintenant) or datetime.now(timezone.utc)
    instant = pivot.isoformat()
    dossier_id = _texte(vue.get("id"), 80)

    # Les constats sont l'ancrage : texte tronqué → (claim, twin).
    appuis: dict[str, Mapping] = {}
    for constat in vue.get("constats") or ():
        if not isinstance(constat, Mapping):
            continue
        texte = _texte(constat.get("texte"), 240)
        if texte and texte not in appuis:
            appuis[texte] = constat
    contexte = vue.get("contexte") or {}
    twins_contexte = _textes(contexte.get("twin_ids"))

    resultat: list[modele.Belief] = []
    vus: set[str] = set()
    for belief in vue.get("beliefs") or ():
        vue_belief = _vue(belief)
        if not vue_belief:
            continue
        if _texte(vue_belief.get("statut"), 20).upper() not in STATUTS_TENUS:
            continue
        constat = appuis.get(_texte(vue_belief.get("objet"), 240))
        claim_ids: list[str] = []
        if constat is not None:
            claim_id = _constat_id_claim(constat)
            if claim_id:
                claim_ids.append(claim_id)
        if not claim_ids:
            continue
        twins = _textes(vue_belief.get("twins"))
        sujet_id = (
            _constat_id_twin(constat) if constat is not None else ""
        ) or (twins[0] if twins else "") or (
            twins_contexte[0] if twins_contexte else ""
        ) or claim_ids[0]
        enonce = " · ".join(
            partie
            for partie in (
                _texte(vue_belief.get("sujet"), 240),
                _texte(vue_belief.get("predicat"), 240),
                _texte(vue_belief.get("objet"), 240),
            )
            if partie
        )
        if not enonce:
            continue
        identifiant = "belief-" + hashlib.sha256(
            f"{tenant_id}:{dossier_id}:{_texte(vue_belief.get('id'), 80)}".encode("utf-8")
        ).hexdigest()[:12]
        if identifiant in vus:
            continue
        try:
            resultat.append(modele.Belief(
                id=identifiant,
                tenant_id=tenant_id,
                mode="INFERRED",
                enonce=enonce,
                sujet_id=sujet_id,
                confiance=vue_belief.get("confiance", 0.5),
                source="RAISONNEMENT",
                claim_ids=claim_ids,
                statut="ACTIF",
                dossier_id=dossier_id or None,
                cree_le=instant,
                observe_le=instant,
                valide_depuis=instant,
                revalide_le=instant,
            ))
            vus.add(identifiant)
        except modele.ModeleInvalide:
            continue
    return resultat
