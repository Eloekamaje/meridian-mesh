"""Budget, forecast, réel et valeur : objets financiers séparés de l'effort."""
from __future__ import annotations

from typing import Any



def resume(store, conn, tenant: str, initiative_id: str | None = None) -> dict[str, Any]:
    budgets = store.budgets(conn, tenant, initiative_id)
    couts = store.couts(conn, tenant)
    valeurs = store.valeurs(conn, tenant, initiative_id)
    taux = store.taux(conn, tenant)
    temps = store.temps(conn, tenant)
    sortie = []
    for budget in budgets:
        lignes = [c for c in couts if c.get("budget_id") == budget["id"]]
        prevu = sum(float(c.get("prevu") or 0) for c in lignes)
        engage = sum(float(c.get("engage") or 0) for c in lignes)
        reel = sum(float(c.get("reel") or 0) for c in lignes)
        forecast = sum(float(c.get("forecast") or 0) for c in lignes)
        enveloppe = float(budget.get("enveloppe") or 0)
        sortie.append({
            "id": budget["id"], "libelle": budget["libelle"], "initiative_id": budget.get("initiative_id"),
            "devise": budget.get("devise") or "EUR", "enveloppe": enveloppe,
            "prevu": prevu, "engage": engage, "reel": reel, "forecast": forecast,
            "variance": enveloppe - forecast,
            "consomme_pct": round((reel / enveloppe) * 100, 2) if enveloppe else None,
            "source": budget.get("source"),
        })
    # Les devises ne sont jamais additionnées : la valeur est rendue par devise.
    par_devise: dict[str, float] = {}
    for ligne in sortie:
        par_devise[ligne["devise"]] = par_devise.get(ligne["devise"], 0.0) + ligne["enveloppe"]
    # Coût réel estimé : heures réelles × taux horaire de l'équipe (aucune conversion de devise implicite).
    cout_reel: dict[str, float] = {}
    for ligne in temps:
        heures = float(ligne.get("valeur") or 0)
        if (ligne.get("unite") or "heures") != "heures":
            continue
        candidats = [t for t in taux if t.get("equipe_id") == ligne.get("equipe_id")]
        if not candidats:
            continue
        tarif = candidats[0]
        devise = tarif.get("devise") or "EUR"
        cout_reel[devise] = cout_reel.get(devise, 0.0) + heures * float(tarif.get("cout_heure") or 0)
    return {"tenant": tenant, "budgets": sortie, "enveloppe_par_devise": par_devise,
            "valeurs": valeurs, "taux": taux, "cout_reel_estime": cout_reel}
