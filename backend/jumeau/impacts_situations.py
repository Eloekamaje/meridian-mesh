"""Situations issues des impacts d'une découverte d'interfaces.

Une découverte ne mérite une situation que si elle prouve un impact `breaking` ou `warning`. Le texte reste
métier — application, opération, type de changement — et ne recopie jamais la preuve brute, qui peut contenir
un secret ou une adresse interne.
"""
from __future__ import annotations

from datetime import datetime, timezone

__all__ = ["situation_depuis_run"]

SCORES = {"haute": 82, "normale": 64}
_SEVERITES_UTILES = ("breaking", "warning")
_RANG_SEVERITE = {"breaking": 0, "warning": 1}
_LIBELLES_CHANGE = {
    "contract_version": "version de contrat modifiée",
    "contract_digest": "contenu de contrat modifié",
    "operation_added": "opération ajoutée",
    "operation_removed": "opération retirée",
    "operation_changed": "opération modifiée",
    "binding_added": "liaison ajoutée",
    "binding_removed": "liaison retirée",
    "assertion_added": "assertion ajoutée",
    "assertion_removed": "assertion retirée",
    "assertion_mode_changed": "mode d'assertion modifié",
}
_LIBELLES_SEVERITE = {"breaking": "rupture", "warning": "avertissement"}


def _jumeau_id(jumeau) -> str:
    identifiant = jumeau if isinstance(jumeau, str) else (
        jumeau.get("id") if isinstance(jumeau, dict) else getattr(jumeau, "id", None))
    if not identifiant:
        raise ValueError("jumeau sans identifiant : situation refusée")
    return str(identifiant)


def _run_effectif(run) -> dict:
    if not isinstance(run, dict):
        return {}
    if isinstance(run.get("run"), dict):
        effectif = dict(run["run"])
        if not effectif.get("impacts") and run.get("impacts"):
            effectif["impacts"] = run["impacts"]
        return effectif
    return run


def _impacts_significatifs(run: dict) -> list[dict]:
    return sorted(
        (impact for impact in (run.get("impacts") or [])
         if isinstance(impact, dict) and impact.get("severity") in _SEVERITES_UTILES),
        key=lambda impact: (_RANG_SEVERITE[impact["severity"]], str(impact.get("application") or ""),
                            str(impact.get("operation") or "")))


def _libelle_change(type_change) -> str:
    type_change = str(type_change or "")
    return _LIBELLES_CHANGE.get(type_change, type_change.replace("_", " ") or "changement d'interface")


def _application(impact: dict) -> str:
    return str(impact.get("application") or "application non précisée")


def _operation(impact: dict) -> str:
    return str(impact.get("operation") or "opération non précisée")


def _titre(impacts: list[dict]) -> str:
    premier = impacts[0]
    titre = (f"Interface : {_operation(premier)} — {_libelle_change(premier.get('change_type'))}, "
             f"impact sur {_application(premier)}")
    if len(impacts) > 1:
        titre += f" (+{len(impacts) - 1} autre{'s' if len(impacts) > 2 else ''} impact{'s' if len(impacts) > 2 else ''})"
    return titre


def _resume(impacts: list[dict]) -> str:
    details = "; ".join(
        f"{_application(impact)} consomme {_operation(impact)} ({_libelle_change(impact.get('change_type'))}, "
        f"{_LIBELLES_SEVERITE[impact['severity']]})" for impact in impacts)
    return f"La découverte d'interfaces a relevé {len(impacts)} impact(s) : {details}."


def _question(impacts: list[dict], priorite: str) -> str:
    premier = impacts[0]
    application, operation = _application(premier), _operation(premier)
    if priorite == "haute":
        return f"Qui doit adapter {application} à la rupture sur {operation} avant la mise en production ?"
    return f"Quel effet la modification de {operation} a-t-elle sur {application}, et faut-il l'anticiper ?"


def _decouverte_quoi(impacts: list[dict]) -> str:
    details = "; ".join(
        f"{_application(impact)} sur {_operation(impact)} : {_libelle_change(impact.get('change_type'))} "
        f"({impact.get('change_type')})" for impact in impacts)
    return f"{len(impacts)} impact(s) d'interface : {details}."


def _score(run: dict, impacts: list[dict], priorite: str):
    for impact in impacts:
        score = impact.get("score")
        if isinstance(score, (int, float)) and not isinstance(score, bool):
            return score
    statistiques = run.get("stats") if isinstance(run.get("stats"), dict) else {}
    for source in (statistiques, run):
        score = source.get("score") if isinstance(source, dict) else None
        if isinstance(score, (int, float)) and not isinstance(score, bool):
            return score
    return SCORES[priorite]


def _detectee(run: dict):
    detectee = run.get("ended_at") or run.get("started_at")
    if not detectee:
        return datetime.now(timezone.utc).isoformat()
    return detectee.isoformat() if hasattr(detectee, "isoformat") else str(detectee)


def situation_depuis_run(run, jumeau) -> dict | None:
    """Rend la situation d'interface d'un run, ou None si ses impacts ne sont que des informations.

    `jumeau` peut être le dictionnaire du jumeau ou son identifiant. Seuls les impacts `breaking` et `warning`
    comptent ; la priorité suit la gravité la plus forte et l'identifiant reste stable pour un même run.
    """
    run = _run_effectif(run)
    impacts = _impacts_significatifs(run)
    if not impacts:
        return None
    run_id = str(run.get("id") or "").strip()
    if not run_id:
        raise ValueError("run sans identifiant : situation refusée")
    jumeau_id = _jumeau_id(jumeau)
    priorite = "haute" if any(impact["severity"] == "breaking" for impact in impacts) else "normale"
    return {
        "id": f"sit-interfaces-{jumeau_id}-{run_id}",
        "verbe": "a_comprendre",
        "nature": "changement",
        "type": "interface",
        "titre": _titre(impacts),
        "resume": _resume(impacts),
        "priorite": priorite,
        "statut": "active",
        "score": _score(run, impacts, priorite),
        "detectee": _detectee(run),
        "question": _question(impacts, priorite),
        "jumeaux": [jumeau_id],
        "decouverte_quoi": _decouverte_quoi(impacts),
    }
