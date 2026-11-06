"""Découverte locale déclenchée par `twin.born`.

Le handler ne fait pas de découverte globale : il ne persiste que les liens et
questions où le Twin naissant est impliqué.
"""
from __future__ import annotations

import os

import pytest

from meridian.adapters.outbound.postgres import decouverte_liens as depot_liens
from meridian.adapters.outbound.postgres import decouverte_naissance
from meridian.adapters.outbound.postgres import relations_naissance as depot_relations
from meridian.domain.decouverte_liens import Binding
from meridian.domain.naissance_relationnelle import (
    Consommation,
    Exposition,
    ManifesteNaissance,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("JUMEAU_PG_DSN"), reason="JUMEAU_PG_DSN non défini")


def _manifeste(twin_id: str, *, exposes=(), consomme=(), portee="SERVICE"):
    return ManifesteNaissance(
        tenant_id="banque", twin_id=twin_id, birth_run_id=f"run-{twin_id}",
        application_id=twin_id, status="CONFIRMED", owner=f"Équipe {twin_id}",
        exposures=tuple(Exposition(
            kind="HTTP", operation=operation, environment="prod", portee=portee,
            evidence_ids=(f"code:{twin_id}:{operation}",)) for operation in exposes),
        consumptions=tuple(Consommation(
            kind="HTTP", logical_ref=reference, target_hint=hint, environment="prod",
            evidence_ids=(f"code:{twin_id}:{reference}",))
            for reference, hint in consomme),
    )


def _bindings():
    return [
        Binding(kind="PROPERTY", nom="comptes.base-url",
                valeur="http://gateway.internal/accounts", environment="prod",
                source="application.yml"),
        Binding(kind="GATEWAY_ROUTE", nom="/accounts", valeur="comptes-api",
                environment="prod", source="ingress.yaml"),
        Binding(kind="SERVICE", nom="comptes-api", valeur="app-b",
                environment="prod", source="service.yaml"),
    ]


def test_twin_born_decouvre_un_lien_par_configuration(conn):
    a = _manifeste("app-a", consomme=[("${comptes.base-url}", "GET /accounts/{id}")])
    b = _manifeste("app-b", exposes=["GET /accounts/{id}"])
    # Deux autres Twins produisent un lien qui ne concerne pas la naissance de b.
    c = _manifeste("app-c", consomme=[("GET /other", "GET /other")])
    d = _manifeste("app-d", exposes=["GET /other"])
    for manifeste in (a, b, c, d):
        depot_relations.enregistrer_manifeste(conn, manifeste)
    for binding in _bindings():
        depot_liens.enregistrer_binding(conn, "banque", binding)

    resultat = decouverte_naissance.traiter_twin_born(conn, b.as_dict())

    propositions = depot_relations.lister_propositions(conn, "banque")
    assert resultat["decouverte"] == 1
    assert resultat["liens_locaux"] == 1
    assert len(propositions) == 1
    proposition = propositions[0]
    assert proposition["consumer_id"] == "app-a"
    assert proposition["provider_id"] == "app-b"
    assert proposition["object"] == "GET /accounts/{id}"
    assert proposition["portee"] == "SERVICE"
    assert proposition["state"] == "supposee"
    # Le lien app-c → app-d existe dans le moteur global mais pas dans la passe locale.
    assert not any(p["consumer_id"] == "app-c" for p in propositions)


def test_twin_born_est_idempotent(conn):
    a = _manifeste("app-a", consomme=[("${comptes.base-url}", "GET /accounts/{id}")])
    b = _manifeste("app-b", exposes=["GET /accounts/{id}"])
    depot_relations.enregistrer_manifeste(conn, a)
    depot_relations.enregistrer_manifeste(conn, b)
    for binding in _bindings():
        depot_liens.enregistrer_binding(conn, "banque", binding)

    premier = decouverte_naissance.traiter_twin_born(conn, b.as_dict())
    second = decouverte_naissance.traiter_twin_born(conn, b.as_dict())

    assert premier["decouverte"] == 1 and second["decouverte"] == 1
    assert len(depot_relations.lister_propositions(conn, "banque")) == 1
    assert len(depot_liens.lister_resolution_cases(conn, "banque")) == 0


def test_une_portee_inconnue_ouvre_un_cas_de_frontiere(conn):
    a = _manifeste("app-a", consomme=[("${comptes.base-url}", "GET /accounts/{id}")])
    b = _manifeste("app-b", exposes=["GET /accounts/{id}"], portee="UNKNOWN")
    depot_relations.enregistrer_manifeste(conn, a)
    depot_relations.enregistrer_manifeste(conn, b)
    for binding in _bindings()[:2]:  # propriété + route, mais pas de service ingress
        depot_liens.enregistrer_binding(conn, "banque", binding)

    resultat = decouverte_naissance.traiter_twin_born(conn, b.as_dict())

    assert resultat["decouverte"] == 0
    assert resultat["non_eligibles"]
    cas = depot_liens.lister_resolution_cases(conn, "banque", twin_id="app-b")
    assert len(cas) == 1
    assert cas[0]["reference"].startswith("frontière:")
    assert "portée" in cas[0]["missing_evidence"]


def test_un_producteur_introuvable_ouvre_un_cas(conn):
    e = _manifeste("app-e", consomme=[(
        "http://unknown-service/reports/42", "GET /reports/42")])
    depot_relations.enregistrer_manifeste(conn, e)

    resultat = decouverte_naissance.traiter_twin_born(conn, e.as_dict())

    assert resultat["decouverte"] == 0
    assert resultat["questions_locales"] == 1
    cas = depot_liens.lister_resolution_cases(conn, "banque", twin_id="app-e")
    assert len(cas) == 1
    assert cas[0]["reference"] == "GET /reports/42"
    assert "aucun producteur" in cas[0]["missing_evidence"]
