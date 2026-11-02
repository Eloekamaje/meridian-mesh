"""Synchronisation canonique des sources de travail, people et finance."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from meridian.domain import planification as domaine


def _tenant(source: dict[str, Any]) -> str:
    return str(source.get("tenant_id") or "").strip()


def _maj_source(element: dict[str, Any]) -> str | None:
    valeur = element.get("maj_source") or element.get("updated")
    return str(valeur) if valeur else None


def _identifiant(source_id: str, external: Any) -> str:
    return f"{source_id}:{external}"


def _equipe_mapping(store, conn, tenant: str, source: dict[str, Any], adapter) -> dict[str, str]:
    mapping = {}
    for equipe in adapter.lister_equipes() or []:
        externe = str(equipe.get("id") or equipe.get("externe_id") or "").strip()
        if not externe:
            continue
        canonique = str(equipe.get("canonique_id") or equipe.get("equipe_id") or externe)
        store.enregistrer_equipe(conn, tenant, {
            "id": canonique, "nom": equipe.get("nom") or canonique,
            "domaine": equipe.get("domaine"), "parent_id": equipe.get("parent_id"),
            "source_id": source["id"], "externe_id": externe,
        })
        mapping[externe] = canonique
    return mapping


def synchroniser_travail(store, conn, source: dict[str, Any], adapter) -> dict[str, Any]:
    """Synchronise une source de travail ; idempotent, avec curseur et run durable."""
    tenant = _tenant(source)
    if not tenant:
        raise ValueError("source sans tenant")
    run_id = store.creer_sync_run(conn, tenant, source["id"])
    lus = ecrits = 0
    try:
        equipes = _equipe_mapping(store, conn, tenant, source, adapter)
        elements = adapter.lister_elements(source.get("curseur"), 500)
        curseur = source.get("curseur")
        for element in elements:
            lus += 1
            externe = str(element.get("external_id") or element.get("id") or "").strip()
            if not externe:
                continue
            equipe_externe = str(element.get("equipe_id") or "").strip()
            element["equipe_id"] = equipes.get(equipe_externe, equipe_externe or None)
            element["source_id"] = source["id"]
            element["external_id"] = externe
            element["id"] = _identifiant(source["id"], externe)
            store.enregistrer_element(conn, tenant, element)
            ecrits += 1
            if _maj_source(element):
                candidat = f"{_maj_source(element)}|{externe}"
                if not curseur or candidat > curseur:
                    curseur = candidat
        for cycle in adapter.lister_cycles() or []:
            cycle = dict(cycle)
            cycle["source_id"] = source["id"]
            equipe = str(cycle.get("equipe_id") or "")
            cycle["equipe_id"] = equipes.get(equipe, equipe or None)
            store.enregistrer_cycle(conn, tenant, cycle)
        for release in adapter.lister_releases() or []:
            release = dict(release)
            release["source_id"] = source["id"]
            store.enregistrer_release(conn, tenant, release)
        if not source.get("curseur"):
            store.desactiver_absents(conn, tenant, source["id"],
                                     [str(e.get("external_id")) for e in elements if e.get("external_id")])
        for temps in adapter.lister_temps() or []:
            temps = dict(temps)
            temps["source_id"] = source["id"]
            if temps.get("element_id"):
                temps["element_id"] = _identifiant(source["id"], temps["element_id"])
            temps.setdefault("source", adapter.provider)
            store.enregistrer_temps(conn, tenant, temps)
        for dependance in adapter.lister_dependances() or []:
            dependance = dict(dependance)
            dependance["source_id"] = source["id"]
            dependance["source_element_id"] = _identifiant(source["id"], dependance.get("source_element_id"))
            dependance["cible_element_id"] = _identifiant(source["id"], dependance.get("cible_element_id"))
            store.enregistrer_dependance(conn, tenant, dependance)
        store.maj_source(conn, tenant, source["id"], curseur=curseur,
                         capacites=adapter.capacites(), etat="active", derniere_erreur=None)
        store.terminer_sync_run(conn, tenant, run_id, etat="SUCCEEDED", lus=lus, ecrits=ecrits,
                               metriques={"provider": adapter.provider, "equipes": len(equipes)})
        return {"ok": True, "run_id": run_id, "lus": lus, "ecrits": ecrits,
                "curseur": curseur, "capacites": adapter.capacites()}
    except Exception as erreur:  # noqa: BLE001 - le run doit rester visible
        store.maj_source(conn, tenant, source["id"], etat="erreur",
                         derniere_erreur=str(erreur)[:500])
        store.terminer_sync_run(conn, tenant, run_id, etat="FAILED", lus=lus, ecrits=ecrits,
                               erreur=str(erreur), metriques={"provider": adapter.provider})
        raise


def synchroniser_people(store, conn, source: dict[str, Any], adapter) -> dict[str, Any]:
    tenant = _tenant(source)
    equipes = _equipe_mapping(store, conn, tenant, source, adapter)
    for membre in adapter.lister_membres() or []:
        equipe_externe = str(membre.get("equipe_id") or "")
        store.enregistrer_membre(conn, tenant, {
            "equipe_id": equipes.get(equipe_externe, equipe_externe),
            "acteur": membre.get("acteur"), "fte": membre.get("fte") or 1,
            "role": membre.get("role"), "source": "people"})
    for competence in adapter.lister_competences() or []:
        equipe_externe = str(competence.get("equipe_id") or "")
        store.enregistrer_competence(conn, tenant, {
            "equipe_id": equipes.get(equipe_externe, equipe_externe),
            "competence": competence.get("competence"),
            "niveau": int(competence.get("niveau") or 0), "source": "people"})
    for capacite in adapter.lister_capacites() or []:
        capacite = dict(capacite)
        equipe_externe = str(capacite.get("equipe_id") or "")
        capacite["equipe_id"] = equipes.get(equipe_externe, equipe_externe)
        store.enregistrer_capacite(conn, tenant, capacite)
    for allocation in adapter.lister_allocations() or []:
        allocation = dict(allocation)
        equipe_externe = str(allocation.get("equipe_id") or "")
        allocation["equipe_id"] = equipes.get(equipe_externe, equipe_externe)
        store.enregistrer_allocation(conn, tenant, allocation)
    for absence in adapter.lister_absences() or []:
        absence = dict(absence)
        equipe_externe = str(absence.get("equipe_id") or "")
        absence["equipe_id"] = equipes.get(equipe_externe, equipe_externe)
        store.enregistrer_absence(conn, tenant, absence)
    store.maj_source(conn, tenant, source["id"], etat="active", derniere_erreur=None,
                     capacites={"people": True})
    return {"ok": True, "equipes": len(equipes)}


def synchroniser_incidents(store, conn, source: dict[str, Any], adapter) -> dict[str, Any]:
    tenant = _tenant(source)
    equipes = _equipe_mapping(store, conn, tenant, source, adapter)
    lus = 0
    for element in adapter.lister_charge_non_planifiee() or []:
        lus += 1
        element = dict(element)
        externe = str(element.get("external_id") or "")
        if not externe:
            continue
        equipe = str(element.get("equipe_id") or "")
        element.update({"source_id": source["id"], "external_id": externe,
                        "id": _identifiant(source["id"], externe),
                        "equipe_id": equipes.get(equipe, equipe), "categorie_charge": "non_planifiee"})
        store.enregistrer_element(conn, tenant, element)
    store.maj_source(conn, tenant, source["id"], etat="active", derniere_erreur=None)
    return {"ok": True, "incidents": lus}


def synchroniser_finance(store, conn, source: dict[str, Any], adapter) -> dict[str, Any]:
    tenant = _tenant(source)
    budgets = adapter.lister_budgets() or []
    for budget in budgets:
        store.enregistrer_budget(conn, tenant, budget)
    for cout in adapter.lister_couts() or []:
        store.enregistrer_cout(conn, tenant, cout)
    for taux in adapter.lister_taux() or []:
        store.enregistrer_taux(conn, tenant, taux)
    store.maj_source(conn, tenant, source["id"], etat="active", derniere_erreur=None,
                     capacites={"finance": True})
    return {"ok": True, "budgets": len(budgets)}


def synchroniser(store, conn, source: dict[str, Any], adapter=None) -> dict[str, Any]:
    usage = str(source.get("usage") or "travail")
    if usage == "travail":
        return synchroniser_travail(store, conn, source, adapter)
    if usage == "people":
        return synchroniser_people(store, conn, source, adapter)
    if usage == "incidents":
        return synchroniser_incidents(store, conn, source, adapter)
    if usage == "finance":
        return synchroniser_finance(store, conn, source, adapter)
    raise ValueError(f"usage de source inconnu : {usage!r}")
