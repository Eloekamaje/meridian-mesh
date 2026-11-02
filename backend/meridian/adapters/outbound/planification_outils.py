"""Adaptateurs exécutables des outils de pilotage pour le Harness."""
from __future__ import annotations

from typing import Any, Callable

import psycopg

from meridian.adapters.outbound.llm.harness import Harness
from meridian.adapters.outbound.postgres import planification as depot
from meridian.domain import artefacts
from meridian.application.planification import alertes, budget, capacite, outils, previsions
from meridian.domain.capacites import RegistreCapacites


def adaptateurs(dsn: str, tenant: str) -> dict[str, Callable[..., Any]]:
    def _conn():
        return psycopg.connect(dsn, autocommit=True)

    def lire_capacite(equipe_id=None, debut=None, fin=None):
        with _conn() as conn:
            return artefacts.envelopper(
                "planification.capacite", "Capacité & charge",
                capacite.resume(depot, conn, tenant, equipe_id=equipe_id, debut=debut, fin=fin),
                source="harness")

    def lire_prevision(equipe_id=None, date_depart=None, seed=42):
        if not equipe_id:
            return artefacts.envelopper(
                "planification.prevision", "Prévision",
                {"prevision": previsions.prevoir_explicite({}, date_depart=date_depart)},
                source="harness")
        with _conn() as conn:
            return artefacts.envelopper(
                "planification.prevision", "Prévision",
                {"prevision": previsions.prevoir_equipe(depot, conn, tenant, equipe_id,
                                                         date_depart=date_depart, seed=seed,
                                                         enregistrer=False)},
                source="harness")

    def lire_budget(initiative_id=None):
        with _conn() as conn:
            return artefacts.envelopper(
                "planification.budget", "Budget & valeur",
                budget.resume(depot, conn, tenant, initiative_id), source="harness")

    def lire_alertes():
        with _conn() as conn:
            return artefacts.envelopper(
                "planification.alertes", "Alertes de pilotage",
                {"alertes": alertes.lister(depot, conn, tenant)}, source="harness")

    def lire_gantt():
        with _conn() as conn:
            cycles = depot.cycles(conn, tenant)
            lignes = [{"id": c["id"], "label": c.get("nom") or c["id"],
                       "debut": c.get("debut"), "fin": c.get("fin"),
                       "statut": "termine" if c.get("termine") else "en_cours"}
                      for c in cycles if c.get("debut") and c.get("fin")]
            return artefacts.envelopper("planification.gantt", "Planning des cycles",
                                        {"lignes": lignes}, source="harness")

    def lire_dependances():
        with _conn() as conn:
            elements = depot.elements(conn, tenant)
            dependances = depot.dependances(conn, tenant)
            noeuds = [{"id": e["id"], "label": e.get("titre") or e["id"],
                       "equipe_id": e.get("equipe_id")} for e in elements]
            aretes = [{"source": d.get("source_element_id"), "cible": d.get("cible_element_id"),
                       "type": d.get("type")} for d in dependances]
            return artefacts.envelopper(
                "planification.dependances", "Dépendances du Travail",
                {"noeuds": noeuds, "aretes": aretes}, source="harness")

    return {"planification_capacite": lire_capacite,
            "planification_prevision": lire_prevision,
            "planification_budget": lire_budget,
            "planification_alertes": lire_alertes,
            "planification_dependances": lire_dependances,
            "planification_gantt": lire_gantt}


def construire(dsn: str, tenant: str, *, acteur: str = "flore",
               perimetre: str | None = None) -> Harness:
    registre = RegistreCapacites(outils.manifestes())
    return Harness(registre, adaptateurs(dsn, tenant), tenant=tenant, acteur=acteur,
                   perimetre=perimetre)
