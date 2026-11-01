"""Composition dynamique bornée : profil → méthodes → compétences → spécialistes.

La composition est dynamique pour l'équipe de tâche, mais statique pour l'autorité. Le plan ne crée
ni méthode, ni compétence, ni spécialiste : il choisit uniquement dans les catalogues et laisse la
politique humaine décider. Un profil inconnu produit un plan de lecture, jamais une décision.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from meridian.domain import competences_cognitives, methodes_cognitives, packs_domaines, profils

__all__ = ["PlanComposition", "composer", "planifier", "valider_plan"]

_AUTORITES = ("lecture", "proposition", "approbation", "decision", "action")
_SPECIALISTES = frozenset({"decouverte", "preuve", "impact", "outcome"})


def _borne(valeur, maximum: int) -> int:
    try:
        nombre = int(valeur)
    except (TypeError, ValueError):
        return maximum
    return max(0, min(nombre, maximum))


def _ids(valeurs) -> tuple[str, ...]:
    resultat = []
    for valeur in valeurs or ():
        if isinstance(valeur, str):
            texte = valeur.strip()
        else:
            texte = str(getattr(valeur, "id", "") or "").strip()
        if texte and texte not in resultat:
            resultat.append(texte)
    return tuple(resultat)


def _autorite_bornee(autorite: str, maximum: str | None) -> str:
    if maximum is None:
        return autorite
    if maximum not in _AUTORITES:
        raise ValueError(f"autorité maximale inconnue : {maximum}")
    return _AUTORITES[min(_AUTORITES.index(autorite), _AUTORITES.index(maximum))]


@dataclass(frozen=True)
class PlanComposition:
    """Plan de tâche : une sélection traçable dans les catalogues, jamais une invention."""

    profil: profils.Profil
    methodes: tuple[methodes_cognitives.Methode, ...] = ()
    competences: tuple[competences_cognitives.Competence, ...] = ()
    specialistes: tuple[str, ...] = ()
    specialistes_socle: tuple[str, ...] = ("preuve", "impact")
    autorite: str = "lecture"
    budget: dict = field(default_factory=dict)
    justification: tuple[str, ...] = ()
    avertissements: tuple[str, ...] = ()
    pack: str | None = None

    def __post_init__(self):
        if not isinstance(self.profil, profils.Profil):
            raise TypeError("profil : Profil attendu")
        if self.autorite not in _AUTORITES:
            raise ValueError(f"autorité inconnue : {self.autorite}")
        if _AUTORITES.index(self.autorite) > _AUTORITES.index(self.profil.autorite):
            raise ValueError("le plan ne peut pas dépasser l'autorité du profil")
        if not isinstance(self.budget, dict):
            raise TypeError("budget : objet attendu")

    def as_dict(self) -> dict:
        return {
            "profil": self.profil.as_dict(),
            "methodes": [methode.as_dict() for methode in self.methodes],
            "competences": [competence.as_dict() for competence in self.competences],
            "specialistes": list(self.specialistes),
            "specialistes_socle": list(self.specialistes_socle),
            "autorite": self.autorite,
            "budget": dict(self.budget),
            "justification": list(self.justification),
            "avertissements": list(self.avertissements),
            "pack": self.pack,
        }


def planifier(
    profil: profils.Profil | str,
    question: str = "",
    *,
    autorite_max: str | None = None,
    limite_methodes: int = 3,
    limite_competences: int = 6,
    timeout_s: float = 8.0,
    application_id: str | None = None,
    situation_id: str | None = None,
    twin_ids: Any = (),
    pack: Any = None,
) -> PlanComposition:
    """Compose un plan borné à partir du profil, des catalogues et, si demandé, d'un pack de domaine.

    Le pack n'ajoute rien hors catalogues : il rend explicites des méthodes et compétences existantes.
    Son autorité plafonne le plan et reste en lecture seule.
    """
    if isinstance(profil, str):
        profil = profils.resoudre_profil(profil=profil, autorite_max=autorite_max)
    if not isinstance(profil, profils.Profil):
        raise TypeError("profil : Profil ou identifiant attendu")
    if not isinstance(question, str):
        raise ValueError("question : texte attendu")
    try:
        timeout = float(timeout_s)
    except (TypeError, ValueError) as exc:
        raise ValueError("timeout_s invalide") from exc
    if timeout <= 0:
        raise ValueError("timeout_s doit être positif")
    limite_methodes = _borne(limite_methodes, 20)
    limite_competences = _borne(limite_competences, 20)

    pack_fiche = None
    if pack is not None:
        try:
            pack_fiche = packs_domaines.resoudre_pack(pack)
        except packs_domaines.PackInvalide as erreur:
            raise ValueError(f"pack de domaine invalide : {erreur}") from erreur
        limite_methodes = max(limite_methodes, len(pack_fiche.methodes))
        limite_competences = max(limite_competences, len(pack_fiche.competences))

    methodes_ids = []
    if pack_fiche is not None:
        methodes_ids.extend(pack_fiche.methodes)
    methodes_ids.extend(
        methode.id for methode in methodes_cognitives.methodes_pour(
            profil, question, limite=limite_methodes))
    methodes = tuple(methodes_cognitives.valider_methodes(methodes_ids))[
        : _borne(limite_methodes, len(methodes_ids))]
    competences_ids = []
    if pack_fiche is not None:
        competences_ids.extend(pack_fiche.competences)
    for competence in methodes:
        competences_ids.extend(competence.competences)
    competences_ids.extend(profil.competences)
    competences_ids.extend(
        competence.id for competence in competences_cognitives.competences_pour(
            profil, question, limite=limite_competences))
    try:
        competences = competences_cognitives.valider_competences(competences_ids)
    except ValueError:
        competences = ()
    competences = competences[: _borne(limite_competences, len(competences))]

    specialistes = []
    if pack_fiche is not None:
        specialistes.extend(
            specialiste for specialiste in pack_fiche.specialistes
            if specialiste in _SPECIALISTES)
    for competence in competences:
        if competence.specialiste in _SPECIALISTES and competence.specialiste not in specialistes:
            specialistes.append(competence.specialiste)

    avertissements = []
    if profil.inconnu:
        avertissements.append("profil inconnu : plan en lecture seule, aucune décision implicite")
    if not methodes:
        avertissements.append("aucune méthode du catalogue ne correspond : plan minimal")
    if not competences:
        avertissements.append("aucune compétence du catalogue ne correspond : plan minimal")
    if not specialistes:
        avertissements.append("aucun spécialiste mobilisé par les compétences retenues")

    socle = ["preuve", "impact"]
    if application_id:
        socle.insert(0, "decouverte")
    if situation_id or twin_ids:
        socle.append("outcome")
    autorite = _autorite_bornee(profil.autorite, autorite_max or "proposition")
    if pack_fiche is not None:
        autorite = _autorite_bornee(autorite, pack_fiche.autorite.niveau_max)
    justification = [
        f"profil {profil.id} ({profil.source}, confiance {profil.confiance:.2f})",
        f"{len(methodes)} méthode(s), {len(competences)} compétence(s), "
        f"{len(specialistes)} spécialiste(s)",
    ]
    if pack_fiche is not None:
        justification.append(
            f"pack {pack_fiche.id} : {len(pack_fiche.evaluations)} évaluation(s), "
            f"autorité {pack_fiche.autorite.niveau_max}")
    return PlanComposition(
        profil=profil,
        methodes=methodes,
        competences=competences,
        specialistes=tuple(specialistes),
        specialistes_socle=tuple(dict.fromkeys(socle)),
        autorite=autorite,
        budget={
            "methodes_max": _borne(limite_methodes, 20),
            "competences_max": _borne(limite_competences, 20),
            "specialistes_max": 4,
            "timeout_s": timeout,
        },
        justification=tuple(justification),
        avertissements=tuple(avertissements),
        pack=pack_fiche.id if pack_fiche is not None else None,
    )


def composer(profil, question: str = "", **options) -> PlanComposition:
    """Alias explicite de :func:`planifier` pour l'orchestrateur."""
    return planifier(profil, question, **options)


def valider_plan(plan: PlanComposition) -> dict:
    """Vérifie qu'un plan ne sort ni des catalogues ni de l'autorité du profil."""
    if not isinstance(plan, PlanComposition):
        raise TypeError("plan : PlanComposition attendu")
    methode_ids = {methode.id for methode in methodes_cognitives.CATALOGUE_METHODES}
    competence_ids = {competence.id for competence in competences_cognitives.CATALOGUE_COMPETENCES}
    erreurs = []
    for methode in plan.methodes:
        if methode.id not in methode_ids:
            erreurs.append(f"méthode hors catalogue : {methode.id}")
    for competence in plan.competences:
        if competence.id not in competence_ids:
            erreurs.append(f"compétence hors catalogue : {competence.id}")
    for specialiste in (*plan.specialistes, *plan.specialistes_socle):
        if specialiste not in _SPECIALISTES:
            erreurs.append(f"spécialiste inconnu : {specialiste}")
    if _AUTORITES.index(plan.autorite) > _AUTORITES.index(plan.profil.autorite):
        erreurs.append("autorité du plan supérieure au profil")
    limites = {
        "methodes": plan.budget.get("methodes_max", 3),
        "competences": plan.budget.get("competences_max", 6),
        "specialistes": plan.budget.get("specialistes_max", 4),
    }
    if len(plan.methodes) > int(limites["methodes"]):
        erreurs.append("trop de méthodes")
    if len(plan.competences) > int(limites["competences"]):
        erreurs.append("trop de compétences")
    if len(plan.specialistes) > int(limites["specialistes"]):
        erreurs.append("trop de spécialistes")
    if len(plan.specialistes_socle) > 4:
        erreurs.append("trop de spécialistes de socle")
    return {"ok": not erreurs, "erreurs": erreurs, "plan": plan.as_dict()}
