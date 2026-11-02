"""Alertes factuelles de pilotage : surcharge, non estimé, budget."""
from __future__ import annotations

from meridian.application.planification import budget, capacite


def lister(store, conn, tenant: str, *, equipe_ids: set[str] | None = None) -> list[dict]:
    resultat = []
    resume = capacite.resume(store, conn, tenant, equipe_ids=equipe_ids)
    for equipe in resume["equipes"]:
        for charge in equipe["charges"]:
            if charge["marge"] is not None and charge["marge"] < 0:
                resultat.append({"type": "surcharge", "equipe_id": equipe["equipe_id"],
                                 "unite": charge["unite"], "valeur": charge["marge"],
                                 "message": f"{equipe['nom']} dépasse sa capacité de "
                                            f"{abs(charge['marge']):g} {charge['unite']}"})
            if charge["elements_sans_estimation"]:
                resultat.append({"type": "non_estime", "equipe_id": equipe["equipe_id"],
                                 "valeur": charge["elements_sans_estimation"],
                                 "message": f"{charge['elements_sans_estimation']} élément(s) sans estimation"})
    for ligne in budget.resume(store, conn, tenant)["budgets"]:
        if ligne["variance"] < 0:
            resultat.append({"type": "budget", "budget_id": ligne["id"], "valeur": ligne["variance"],
                             "message": f"Forecast {ligne['forecast']:g} au-delà de l'enveloppe "
                                        f"{ligne['enveloppe']:g} {ligne['devise']}"})
    return resultat
