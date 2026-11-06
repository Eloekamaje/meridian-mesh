"""Découverte locale déclenchée par `twin.born`.

Le handler ne fait pas de découverte globale : il ne persiste que les liens et
questions où le Twin naissant est impliqué.
"""
from __future__ import annotations

import os

import pytest

from meridian.adapters.outbound.postgres import code_index_store
from meridian.adapters.outbound.postgres import decouverte_liens as depot_liens
from meridian.adapters.outbound.postgres import memoire_prospective
from meridian.adapters.outbound.postgres import decouverte_naissance
from meridian.adapters.outbound.postgres import relations_naissance as depot_relations
from meridian.domain.code_index import Observation
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


def _observation(kind: str, symbol: str, attributes: dict, *, file="src/App.java"):
    return Observation(
        provider="cbm", parser="cbm-graph", parser_version="1",
        file=file, language="java", kind=kind, symbol=symbol,
        start=1, end=1, attributes=attributes,
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


def test_twin_born_utilise_les_observations_cbm(conn):
    a = _manifeste("app-a")  # aucune consommation déclarée : le code la porte
    b = _manifeste("app-b")  # aucune exposition déclarée : CBM porte la route
    depot_relations.enregistrer_manifeste(conn, a)
    depot_relations.enregistrer_manifeste(conn, b)
    for binding in _bindings():
        depot_liens.enregistrer_binding(conn, "banque", binding)
    code_index_store.remplacer(conn, "banque", "app-a", observations=[
        _observation("cbm_relation_http_calls", "demo.Client.get", {
            "target": "comptes-api", "method": "GET", "path": "/accounts/42",
        }),
    ])
    code_index_store.remplacer(conn, "banque", "app-b", observations=[
        _observation("cbm_route", "/accounts/{id}", {
            "method": "GET", "route": "/accounts/{id}",
        }),
    ])

    resultat = decouverte_naissance.traiter_twin_born(conn, b.as_dict())

    propositions = depot_relations.lister_propositions(conn, "banque")
    assert resultat["decouverte"] == 1
    assert resultat["liens_locaux"] == 1
    assert len(propositions) == 1
    assert propositions[0]["consumer_id"] == "app-a"
    assert propositions[0]["provider_id"] == "app-b"
    assert propositions[0]["object"] == "GET /accounts/{id}"


def test_lecture_des_observations_de_liens_filtre_et_borne(conn):
    code_index_store.remplacer(conn, "banque", "app-a", observations=[
        _observation("cbm_route", "/accounts", {"method": "GET", "route": "/accounts"}),
        _observation("cbm_route", "/soldes", {"method": "GET", "route": "/soldes"}),
        _observation("cbm_class", "demo.App", {"label": "Class"}),
    ])

    lignes, tronque = code_index_store.lire_observations_liens(
        conn, "banque", ("app-a",), limite=1)

    assert len(lignes) == 1
    assert lignes[0][0] == "app-a"
    assert lignes[0][1].kind == "cbm_route"
    assert tronque is True


def test_manifeste_et_cbm_ne_doublent_pas_l_exposition(conn):
    a = _manifeste("app-a", consomme=[("${comptes.base-url}", "GET /accounts/{id}")])
    b = _manifeste("app-b", exposes=["GET /accounts/{id}"])
    depot_relations.enregistrer_manifeste(conn, a)
    depot_relations.enregistrer_manifeste(conn, b)
    for binding in _bindings():
        depot_liens.enregistrer_binding(conn, "banque", binding)
    code_index_store.remplacer(conn, "banque", "app-a", observations=[
        _observation("cbm_relation_http_calls", "demo.Client.get", {
            "target": "comptes-api", "method": "GET", "path": "/accounts/42",
        }),
    ])
    code_index_store.remplacer(conn, "banque", "app-b", observations=[
        _observation("cbm_route", "/accounts/{id}", {
            "method": "GET", "route": "/accounts/{id}",
        }),
    ])

    resultat = decouverte_naissance.traiter_twin_born(conn, b.as_dict())

    propositions = depot_relations.lister_propositions(conn, "banque")
    assert resultat["decouverte"] == 1
    assert len(propositions) == 1


def test_reconcilier_twin_ignore_un_twin_sans_manifeste(conn):
    resultat = decouverte_naissance.reconcilier_twin(conn, "banque", "absent")

    assert resultat["statut"] == "ignore"
    assert "manifeste" in resultat["raison"]


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


def test_un_cas_ouvert_cree_une_intention_et_sa_resolution_la_clot(conn):
    e = _manifeste("app-e", consomme=[(
        "http://unknown-service/reports/42", "GET /reports/42")])
    depot_relations.enregistrer_manifeste(conn, e)

    decouverte_naissance.traiter_twin_born(conn, e.as_dict())

    cas = depot_liens.lister_resolution_cases(conn, "banque", twin_id="app-e")
    assert len(cas) == 1
    intentions = memoire_prospective.lister(
        conn, "banque", scope="twin", scope_id="app-e", source=f"case:{cas[0]['id']}")
    assert len(intentions) == 1
    assert intentions[0]["statut"] == "a_faire"
    assert intentions[0]["echeance"]

    depot_liens.resoudre_case(conn, "banque", cas[0]["id"])

    intentions = memoire_prospective.lister(
        conn, "banque", scope="twin", scope_id="app-e", source=f"case:{cas[0]['id']}")
    assert intentions[0]["statut"] == "fait"


def test_reconciliation_globale_dry_run_puis_apply(conn):
    a = _manifeste("app-a", consomme=[("${comptes.base-url}", "GET /accounts/{id}")])
    b = _manifeste("app-b", exposes=["GET /accounts/{id}"])
    c = _manifeste("app-c", consomme=[("GET /other", "GET /other")])
    d = _manifeste("app-d", exposes=["GET /other"])
    for manifeste in (a, b, c, d):
        depot_relations.enregistrer_manifeste(conn, manifeste)
    for binding in _bindings():
        depot_liens.enregistrer_binding(conn, "banque", binding)

    dry = decouverte_naissance.reconcilier(conn, "banque", appliquer=False)
    assert dry["dry_run"] is True
    assert dry["twins"] == 4
    assert dry["propositions"] == 2
    assert depot_relations.lister_propositions(conn, "banque") == []

    applied = decouverte_naissance.reconcilier(conn, "banque", appliquer=True)
    assert applied["propositions"] == 2
    propositions = depot_relations.lister_propositions(conn, "banque")
    assert len(propositions) == 2
    assert {p["consumer_id"] for p in propositions} == {"app-a", "app-c"}

    again = decouverte_naissance.reconcilier(conn, "banque", appliquer=True)
    assert again["propositions"] == 2
    assert len(depot_relations.lister_propositions(conn, "banque")) == 2


def test_reconciliation_globale_bornee_par_limite(conn):
    a = _manifeste("app-a", consomme=[("${comptes.base-url}", "GET /accounts/{id}")])
    b = _manifeste("app-b", exposes=["GET /accounts/{id}"])
    depot_relations.enregistrer_manifeste(conn, a)
    depot_relations.enregistrer_manifeste(conn, b)
    for binding in _bindings():
        depot_liens.enregistrer_binding(conn, "banque", binding)

    rapport = decouverte_naissance.reconcilier(conn, "banque", appliquer=False, limite=1)

    assert rapport["twins"] == 1
