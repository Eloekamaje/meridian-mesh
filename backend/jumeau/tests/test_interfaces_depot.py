"""Persistance du graphe d'interfaces : idempotence, isolation par tenant, modes et secrets."""
import json

import pytest

from jumeau import depot, interfaces, interfaces_depot
from jumeau.tests.conftest import besoin_pg

OPENAPI = json.dumps({
    "openapi": "3.0.3",
    "info": {"title": "Comptes", "version": "1.4.2"},
    "servers": [{"url": "https://api.example.test/v1"}],
    "paths": {
        "/comptes": {"get": {"operationId": "listerComptes"}},
        "/comptes/{id}": {
            "get": {"operationId": "lireCompte"},
            "delete": {"operationId": "supprimerCompte"},
        },
    },
}, ensure_ascii=False)


def graphe(url="https://legacy.example.test/api", application_id="comptes", environment="prod"):
    return interfaces.merge([
        interfaces.parse_openapi(application_id, OPENAPI, "openapi.json", environment),
        interfaces.parse_config(application_id, f"legacy.url={url}\n", "application.properties", environment),
    ])


@besoin_pg
def test_enregistrer_puis_lire_retrouve_contrats_operations_et_assertions(conn):
    g = graphe()
    assert interfaces_depot.enregistrer(conn, "banque", g) == {
        "contracts": 1, "operations": 3, "bindings": 2, "assertions": 4}

    lu = interfaces_depot.lire(conn, "banque")
    assert {c["id"] for c in lu["contracts"]} == {c.id for c in g.contracts}
    assert {o["id"] for o in lu["operations"]} == {o.id for o in g.operations}
    assert {b["id"] for b in lu["bindings"]} == {b.id for b in g.bindings}
    assert len(lu["assertions"]) == len(g.assertions) == 4
    assert {a["mode"] for a in lu["assertions"]} == {"declared"}
    assert all(a["observed_at"] is None for a in lu["assertions"])
    contrat = lu["contracts"][0]
    assert (contrat["application_id"], contrat["format"], contrat["version"], contrat["environment"]) == (
        "comptes", "openapi", "1.4.2", "prod")
    assert contrat["digest"] == g.contracts[0].digest


@besoin_pg
def test_filtres_application_et_predicat(conn):
    interfaces_depot.enregistrer(conn, "banque", graphe())

    exposes = interfaces_depot.lire(conn, "banque", application_id="comptes", predicat="EXPOSE")
    assert len(exposes["assertions"]) == 3
    assert all(a["subject"] == "comptes" and a["predicate"] == "EXPOSE" for a in exposes["assertions"])
    assert {o["id"] for o in exposes["operations"]} == {o.id for o in graphe().operations}
    assert len(exposes["contracts"]) == 1
    assert "https://api.example.test/v1" in {b["url"] for b in exposes["bindings"]}

    consomme = interfaces_depot.lire(conn, "banque", predicat="CONSOMME")
    assert [(a["predicate"], a["object"]) for a in consomme["assertions"]] == [
        ("CONSOMME", "https://legacy.example.test/api")]
    assert "https://legacy.example.test/api" in {b["url"] for b in consomme["bindings"]}
    assert all(b["environment"] == "prod" for b in consomme["bindings"])


@besoin_pg
def test_double_enregistrement_sans_doublon(conn):
    g = graphe()
    interfaces_depot.enregistrer(conn, "banque", g)
    interfaces_depot.enregistrer(conn, "banque", g)

    assert interfaces_depot.compter(conn, "banque") == {
        "contracts": 1, "operations": 3, "bindings": 2, "assertions": 4}
    lu = interfaces_depot.lire(conn, "banque")
    assert len(lu["assertions"]) == 4 == len({a["id"] for a in lu["assertions"]})
    assert len(lu["operations"]) == 3 == len({o["id"] for o in lu["operations"]})
    assert len(lu["bindings"]) == 2 == len({b["id"] for b in lu["bindings"]})


@besoin_pg
def test_deux_tenants_ne_se_voient_pas(conn):
    interfaces_depot.enregistrer(conn, "banque", graphe(url="https://banque.example.test/api"))
    interfaces_depot.enregistrer(conn, "assurance", graphe(url="https://assurance.example.test/api"))

    banque = interfaces_depot.lire(conn, "banque")
    assurance = interfaces_depot.lire(conn, "assurance")
    urls_banque = {b["url"] for b in banque["bindings"]}
    urls_assurance = {b["url"] for b in assurance["bindings"]}
    assert "https://banque.example.test/api" in urls_banque
    assert "https://assurance.example.test/api" not in urls_banque
    assert "https://assurance.example.test/api" in urls_assurance
    assert "https://banque.example.test/api" not in urls_assurance
    assert {a["object"] for a in banque["assertions"]} & {"https://assurance.example.test/api"} == set()
    assert {a["object"] for a in assurance["assertions"]} & {"https://banque.example.test/api"} == set()
    assert interfaces_depot.compter(conn, "banque") == interfaces_depot.compter(conn, "assurance") == {
        "contracts": 1, "operations": 3, "bindings": 2, "assertions": 4}


@besoin_pg
def test_declared_reste_declared_et_observed_reste_distincte(conn):
    g = graphe()
    g.assertions.append(interfaces.Assertion(
        subject="comptes", predicate="EXPOSE", object="GET /comptes", mode="observed", source="datadog",
        locator="trace:abc", environment="prod", confidence=0.99, evidence="trace-abc",
        observed_at="2026-10-30T09:00:00+00:00"))
    interfaces_depot.enregistrer(conn, "banque", g)

    lu = interfaces_depot.lire(conn, "banque", predicat="EXPOSE")
    preuves = [a for a in lu["assertions"] if a["object"] == "GET /comptes"]
    assert [a["mode"] for a in preuves] == ["declared", "observed"]
    declaree = next(a for a in preuves if a["mode"] == "declared")
    observee = next(a for a in preuves if a["mode"] == "observed")
    assert declaree["source"] == "openapi" and declaree["observed_at"] is None
    assert observee["source"] == "datadog" and observee["observed_at"] == "2026-10-30T09:00:00+00:00"
    assert declaree["id"] != observee["id"]


@besoin_pg
@pytest.mark.parametrize("url", [
    "https://alice:s3cr3t@api.example.test/v1",
    "https://api.example.test/v1?token=abc123",
    "https://api.example.test/v1?password=hunter2",
])
def test_binding_avec_secret_refuse_sans_fuite(conn, url):
    g = interfaces.InterfaceGraph(bindings=[interfaces.Binding(
        id="bnd_secret", protocol="rest", url=url, environment="prod")])
    with pytest.raises(ValueError) as erreur:
        interfaces_depot.enregistrer(conn, "banque", g)
    message = str(erreur.value)
    for secret in ("alice", "s3cr3t", "abc123", "hunter2"):
        assert secret not in message
    assert interfaces_depot.compter(conn, "banque") == {
        "contracts": 0, "operations": 0, "bindings": 0, "assertions": 0}


@besoin_pg
def test_binding_assaini_avec_secret_masque_reste_acceptable(conn):
    g = interfaces.parse_config(
        "crm", "api.url=https://api.example.test/v1?token=abc123&name=public\n", "application.properties")
    interfaces_depot.enregistrer(conn, "banque", g)
    lu = interfaces_depot.lire(conn, "banque")
    assert [b["url"] for b in lu["bindings"]] == ["https://api.example.test/v1?token=***&name=public"]
    assert "abc123" not in json.dumps(lu, ensure_ascii=False)


@besoin_pg
def test_lire_est_serialisable_en_json_et_fidele_a_as_dict(conn):
    g = graphe()
    interfaces_depot.enregistrer(conn, "banque", g)
    rendu = json.loads(json.dumps(interfaces_depot.lire(conn, "banque"), ensure_ascii=False))

    assert rendu["contracts"][0]["application_id"] == "comptes"
    assert rendu["operations"][0]["contract_id"] == rendu["contracts"][0]["id"]
    assert isinstance(rendu["assertions"][0]["confidence"], float)
    assert rendu["assertions"][0]["cree_le"]
    attendues = {(a.subject, a.predicate, a.object, a.mode, a.source, a.locator, a.environment, a.evidence)
                 for a in g.assertions}
    assert {(a["subject"], a["predicate"], a["object"], a["mode"], a["source"], a["locator"], a["environment"],
             a["evidence"]) for a in rendu["assertions"]} == attendues
    json.dumps(g.as_dict(), ensure_ascii=False)


def test_tenant_vide_refuse_sans_base():
    with pytest.raises(ValueError):
        interfaces_depot.enregistrer(None, "   ", interfaces.InterfaceGraph())


@besoin_pg
def test_schema_rejoue_est_idempotent(conn):
    depot.appliquer_schema(conn)
    depot.appliquer_schema(conn)
    interfaces_depot.enregistrer(conn, "banque", graphe())
    assert interfaces_depot.compter(conn, "banque")["assertions"] == 4


@besoin_pg
def test_remplacer_retire_les_operations_et_assertions_de_la_meme_source(conn):
    g = graphe()
    interfaces_depot.enregistrer(conn, "banque", g, remplacer=True)
    vide = interfaces.InterfaceGraph(contracts=list(g.contracts))
    interfaces_depot.enregistrer(conn, "banque", vide, remplacer=True)
    lu = interfaces_depot.lire(conn, "banque", application_id="comptes")
    assert lu["operations"] == []
    assert [a for a in lu["assertions"] if a["predicate"] == "EXPOSE"] == []
    assert [a["predicate"] for a in lu["assertions"]] == ["CONSOMME"]  # la config n'est pas dans ce remplacement
    assert {c["id"] for c in lu["contracts"]} == {g.contracts[0].id}
