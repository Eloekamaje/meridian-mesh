"""Gates d'un tour : un seul évaluateur pour les preuves, le cadre et les décisions.

Le module est pur : il lit un DossierRaisonnement et rend des Gate, sans appeler de modèle,
d'outil, de base ou de réseau.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Iterable

from meridian.domain import dossier_raisonnement as domaine

__all__ = ["evaluer", "statut"]


def _mapping(valeur) -> dict:
    return dict(valeur) if isinstance(valeur, Mapping) else {}


def _options_reponse(reponse: Mapping) -> list[dict]:
    decision = _mapping(reponse.get("decision_support") or reponse.get("decision"))
    options = reponse.get("options") or decision.get("options") or ()
    try:
        return [dict(o) for o in options if isinstance(o, Mapping)]
    except TypeError:
        return []


def evaluer(dossier: domaine.DossierRaisonnement) -> tuple[domaine.Gate, ...]:
    """Évalue les gates du tour et rend une trace stable."""
    gates: list[domaine.Gate] = []

    def ajouter(identifiant, condition, statut_gate, message=""):
        gates.append(domaine.Gate(identifiant, condition, statut_gate, message))

    cadre = dossier.cadre
    cadre_epistemique = getattr(dossier, "question_frame", None)
    if cadre_epistemique and cadre_epistemique.bloquantes:
        ajouter("G-PREM-01", "présupposés matériels vérifiés", "echec",
                "; ".join(p.texte for p in dossier.question_frame.bloquantes))
    if dossier.question_frame and any(
            p.statut == "CONTREDIT" for p in dossier.question_frame.presuppositions):
        ajouter("G-PREM-02", "présupposés non contredits", "echec",
                "un présupposé est contredit par le contexte")
    options = dossier.options or tuple(_options_reponse(dossier.reponse))
    critiques = dossier.critiques
    if cadre and cadre.questions_bloquantes:
        ajouter("G-KRN-01", "questions bloquantes résolues", "echec",
                "; ".join(cadre.questions_bloquantes))
    if dossier.niveau in {"N3", "N4"}:
        ajouter("G-KRN-02", "cadre présent", "ok" if cadre else "echec",
                "aucun cadre" if not cadre else "")
        ajouter("G-KRN-03", "au moins deux options", "ok" if len(options) >= 2 else "echec",
                f"{len(options)} option(s)")
        ajouter("G-KRN-04", "critique présente", "ok" if critiques else "echec",
                "aucune critique")
        if dossier.niveau == "N4":
            independante = any(c.independance in {"croisee", "humaine"} for c in critiques)
            ajouter("G-KRN-05", "revue indépendante", "ok" if independante else "echec",
                    "critique séparée insuffisante pour N4")
        bloquantes = [f.constat for c in critiques for f in c.findings
                      if f.severite in {"majeure", "critique"}]
        ajouter("G-KRN-06", "findings majeurs résolus", "echec" if bloquantes else "ok",
                "; ".join(bloquantes[:3]))
        validation = dossier.validation or (
            dossier.decision.plan_validation if dossier.decision else ())
        ajouter("G-KRN-10", "hypothèses validables", "ok" if validation else "avertissement",
                "aucun plan de validation")
    if dossier.demande and dossier.demande.but == "agir":
        irreversible = dossier.demande.reversibilite == "irreversible"
        autorise = dossier.demande.autorite in {"approbation", "decision", "action"}
        ajouter("G-KRN-07", "action autorisée",
                "ok" if (not irreversible or autorise) else "echec",
                "action irréversible sans approbation")
    if dossier.decision and not dossier.decision.plan_validation:
        ajouter("G-KRN-10B", "décision validable", "avertissement",
                "décision sans plan de validation")
    if not gates:
        ajouter("G-KRN-00", "aucun gate requis", "ok")
    return tuple(gates)


def statut(gates: Iterable[domaine.Gate], *, strict: bool = True) -> str:
    """Traduit les gates en statut de tour, sans masquer un échec."""
    valeurs = tuple(gates or ())
    if any(g.statut == "echec" and getattr(g, "bloquante", True) for g in valeurs):
        return "refus" if strict else "partiel"
    if any(g.statut == "avertissement" for g in valeurs):
        return "partiel"
    return "reponse"
