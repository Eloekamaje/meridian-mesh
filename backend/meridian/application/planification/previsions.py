"""Application de la prévision aux faits canoniques d'une équipe."""
from __future__ import annotations

from datetime import date
from statistics import mean
from typing import Any

from meridian.application.planification import prevision as moteur
from meridian.domain import planification as domaine


def _jours_cycle(cycle: dict) -> float:
    try:
        if cycle.get("debut") and cycle.get("fin"):
            debut = date.fromisoformat(str(cycle["debut"])[:10])
            fin = date.fromisoformat(str(cycle["fin"])[:10])
            return max(1.0, float((fin - debut).days))
    except (TypeError, ValueError):
        pass
    return 10.0


def _historique(store, conn, tenant: str, equipe_id: str) -> tuple[tuple[float, ...], tuple[float, ...], float]:
    cycles = store.cycles(conn, tenant, equipe_id, termines=True)
    elements = store.elements_historique(conn, tenant, equipe_id)
    par_cycle: dict[str, list[dict]] = {}
    for element in elements:
        if element.get("cycle_id"):
            par_cycle.setdefault(element["cycle_id"], []).append(element)
    velocites, debits, durees = [], [], []
    for cycle in cycles:
        lignes = par_cycle.get(cycle["id"], [])
        termines = [e for e in lignes if e.get("statut") == "termine"]
        if not termines:
            continue
        points = sum(float(e.get("estimation_valeur") or 0) for e in termines
                     if e.get("estimation_unite") == "points")
        if points > 0:
            velocites.append(points)
        duree = _jours_cycle(cycle)
        if duree > 0:
            durees.append(duree)
            debits.append(len(termines) / max(1.0, duree / 7))
    return tuple(velocites), tuple(debits), (mean(durees) if durees else 10.0)


def prevoir_equipe(store, conn, tenant: str, equipe_id: str, *, date_depart: date | None = None,
                   seed: int = 42, simulations: int = 2000,
                   enregistrer: bool = True) -> dict[str, Any]:
    elements = store.elements(conn, tenant, equipe_id=equipe_id)
    restant_points = sum(float(e["estimation_valeur"] or 0) for e in elements
                         if e.get("estimation_unite") == "points")
    restant_items = len(elements)
    velocites, debits, duree = _historique(store, conn, tenant, equipe_id)
    entree = moteur.EntreePrevision(
        date_depart=date_depart or date.today(), restant_items=restant_items,
        restant_points=restant_points if restant_points > 0 else None,
        historique_velocite=velocites, historique_debit=debits,
        duree_cycle_jours=duree, seed=seed, simulations=simulations,
    )
    resultat = moteur.prevoir(entree)
    prevision = {
        "perimetre_type": "equipe", "perimetre_id": equipe_id, "equipe_id": equipe_id,
        "horizon": f"{resultat.get('p50') or 'inconnu'}",
        "methode": resultat.get("methode"), "version": resultat.get("version"),
        "entree_hash": resultat.get("entree_hash"), "seed": resultat.get("seed"),
        "p50": resultat.get("p50"), "p85": resultat.get("p85"), "p95": resultat.get("p95"),
        "confiance": resultat.get("confiance") or 0,
        "hypotheses": resultat.get("hypotheses") or [],
        "exclusions": resultat.get("exclusions") or [],
        "resultat": resultat,
    }
    if enregistrer:
        prevision["id"] = store.enregistrer_prevision(conn, tenant, prevision)
    return prevision


def prevoir_explicite(entree: dict[str, Any], *, date_depart: date | None = None,
                      enregistrer=None) -> dict[str, Any]:
    """Calcule une prévision fournie par un appelant (tests, scénario, CLI) sans source tracker."""
    entree = dict(entree or {})
    modele = moteur.EntreePrevision(
        date_depart=date_depart or date.today(),
        restant_items=entree.get("restant_items"),
        restant_points=entree.get("restant_points"),
        historique_debit=tuple(entree.get("historique_debit") or ()),
        historique_velocite=tuple(entree.get("historique_velocite") or ()),
        duree_cycle_jours=float(entree.get("duree_cycle_jours") or 10),
        historique_cycle=tuple(entree.get("historique_cycle") or ()),
        delai_fixe_jours=float(entree.get("delai_fixe_jours") or 0),
        seed=int(entree.get("seed") or 42),
        simulations=int(entree.get("simulations") or 2000),
    )
    resultat = moteur.prevoir(modele)
    if enregistrer is not None:
        resultat["id"] = enregistrer(resultat)
    return resultat
