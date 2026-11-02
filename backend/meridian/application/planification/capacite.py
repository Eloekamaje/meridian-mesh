"""Capacité, charge, marges et non planifié, à partir des faits canoniques."""
from __future__ import annotations

from datetime import date
from typing import Any

from meridian.domain import planification as domaine


def _somme_capacites(lignes: list[dict]) -> dict[str, dict[str, Any]]:
    resultat: dict[str, dict[str, Any]] = {}
    for ligne in lignes:
        unite = str(ligne.get("unite") or "inconnue")
        courant = resultat.setdefault(unite, {"unite": unite, "valeur": 0.0, "confiance": 0.0,
                                               "sources": []})
        courant["valeur"] += float(ligne.get("valeur") or 0)
        courant["confiance"] = max(courant["confiance"], float(ligne.get("confiance") or 0))
        if ligne.get("source"):
            courant["sources"].append(ligne["source"])
    return resultat


def resume(store, conn, tenant: str, *, equipe_id: str | None = None,
           equipe_ids: set[str] | None = None, debut: date | None = None,
           fin: date | None = None) -> dict[str, Any]:
    equipes = {e["id"]: e for e in store.equipes(conn, tenant)}
    if equipe_ids is not None:
        equipes = {eid: equipe for eid, equipe in equipes.items() if eid in equipe_ids}
    if equipe_id:
        equipes = {equipe_id: equipes.get(equipe_id, {"id": equipe_id, "nom": equipe_id})}
    lignes_capacite = store.capacites(conn, tenant, equipe_id, debut, fin)
    lignes_absences = store.absences(conn, tenant, equipe_id, debut, fin)
    lignes_temps = store.temps(conn, tenant, equipe_id, debut, fin)
    elements = store.elements(conn, tenant, equipe_id=equipe_id, debut=debut, fin=fin)
    charges = domaine.agreger_charge([
        domaine.ElementTravail(
            id=e["id"], source=e["source_id"], external_id=e["external_id"],
            equipe_id=e.get("equipe_id") or "non_mappee", titre=e["titre"],
            statut=e.get("statut") or "inconnu", priorite=e.get("priorite") or "inconnue",
            type=e.get("type") or "item",
            estimation=(domaine.Estimation(e["estimation_valeur"], e["estimation_unite"],
                                           e.get("estimation_methode") or "declaree")
                        if e.get("estimation_valeur") is not None and e.get("estimation_unite") else None),
            categorie_charge=e.get("categorie_charge") or "planifiee",
            cycle_id=e.get("cycle_id"), release_id=e.get("release_id"),
            parent_id=e.get("parent_id"), assigne=e.get("assigne"), actif=bool(e.get("actif", True)),
        ) for e in elements])
    sortie = []
    for identifiant, equipe in sorted(equipes.items()):
        capacites = _somme_capacites([c for c in lignes_capacite if c["equipe_id"] == identifiant])
        absences_unite = _somme_capacites([{"unite": a.get("unite") or "jours",
                                            "valeur": a.get("valeur") or 0,
                                            "confiance": 1.0, "source": a.get("source")}
                                           for a in lignes_absences if a["equipe_id"] == identifiant])
        temps_unite = _somme_capacites([{"unite": t.get("unite") or "heures",
                                         "valeur": t.get("valeur") or 0,
                                         "confiance": 1.0, "source": t.get("source")}
                                        for t in lignes_temps if t.get("equipe_id") == identifiant])
        equipe_charges = []
        for (eid, unite), charge in sorted(charges.items(), key=lambda item: (item[0][0], item[0][1])):
            if eid != identifiant:
                continue
            capacite_brute = capacites.get(unite, {}).get("valeur")
            absence = absences_unite.get(unite, {}).get("valeur", 0)
            capacite = max(0.0, capacite_brute - absence) if capacite_brute is not None else None
            marge = domaine.marge(capacite, charge.connue)
            equipe_charges.append({
                "unite": unite, "engagee": charge.engagee, "planifiee": charge.planifiee,
                "non_planifiee": charge.non_planifiee, "inconnue": charge.inconnue,
                "total": charge.total, "connue": charge.connue,
                "capacite": capacite, "capacite_brute": capacite_brute,
                "absences": absence, "temps_reel": temps_unite.get(unite, {}).get("valeur", 0),
                "marge": marge, "elements_sans_estimation": charge.elements_sans_estimation,
            })
        for unite, capacite in capacites.items():
            if not any(c["unite"] == unite for c in equipe_charges):
                absence = absences_unite.get(unite, {}).get("valeur", 0)
                nette = max(0.0, capacite["valeur"] - absence)
                equipe_charges.append({"unite": unite, "engagee": 0.0, "planifiee": 0.0,
                                       "non_planifiee": 0.0, "inconnue": 0.0, "total": 0.0,
                                       "connue": 0.0, "capacite": nette,
                                       "capacite_brute": capacite["valeur"], "absences": absence,
                                       "temps_reel": temps_unite.get(unite, {}).get("valeur", 0),
                                       "marge": nette, "elements_sans_estimation": 0})
        sortie.append({
            "equipe_id": identifiant, "nom": equipe.get("nom") or identifiant,
            "domaine": equipe.get("domaine"), "capacites": list(capacites.values()),
            "charges": equipe_charges,
            "absences": [{"unite": u, "valeur": v["valeur"]} for u, v in absences_unite.items()],
            "temps_reel": [{"unite": u, "valeur": v["valeur"]} for u, v in temps_unite.items()],
            "elements_actifs": sum(1 for e in elements if (e.get("equipe_id") or "non_mappee") == identifiant),
        })
    return {"tenant": tenant, "debut": debut.isoformat() if debut else None,
            "fin": fin.isoformat() if fin else None, "equipes": sortie}
