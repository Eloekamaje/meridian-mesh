"""Outils read-only exposés au Harness pour le pilotage.

Ils ne portent aucun nom d'éditeur et appellent les services applicatifs, pas les connecteurs.
"""
from __future__ import annotations


from meridian.domain.capacites import ManifesteOutil

_SCHEMA_ENTREE = {
    "type": "object",
    "properties": {
        "equipe_id": {"type": "string"},
        "debut": {"type": "string", "format": "date"},
        "fin": {"type": "string", "format": "date"},
        "initiative_id": {"type": "string"},
        "date_depart": {"type": "string", "format": "date"},
        "seed": {"type": "integer"},
    },
    "additionalProperties": False,
}
_SCHEMA_SORTIE = {"type": "object"}


def manifestes() -> list[ManifesteOutil]:
    commun = dict(version="1.0.0", capacite="planifier", types_objets_lus=("Capacite", "Charge", "Prevision", "Budget"),
                  schema_entree=_SCHEMA_ENTREE, schema_sortie=_SCHEMA_SORTIE,
                  lecture_seule=True, cout=0.0, timeout_ms=5000, mode_preuve="DECLARED",
                  source="builtin", allowlist=("meridian.builtin",))
    return [
        ManifesteOutil(
            nom="planification_capacite",
            description="Lit la capacité et la charge agrégées d'une équipe ou du tenant, sans détail individuel.",
            **commun),
        ManifesteOutil(
            nom="planification_prevision",
            description="Calcule ou relit une prévision P50/P85/P95 ; s'abstient sans historique suffisant.",
            **commun),
        ManifesteOutil(
            nom="planification_budget",
            description="Lit budget, forecast, réel, variance et valeur d'une initiative.",
            **commun),
        ManifesteOutil(
            nom="planification_alertes",
            description="Liste les surcharges, éléments non estimés et dépassements budgétaires factuels.",
            **commun),
        ManifesteOutil(
            nom="planification_dependances",
            description="Lit le graphe de dépendances des éléments de travail, sans détail individuel.",
            **commun),
        ManifesteOutil(
            nom="planification_gantt",
            description="Lit le planning des cycles (sprints/itérations) et le rend en Gantt dans le chat.",
            **commun),
    ]
