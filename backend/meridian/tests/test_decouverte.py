"""Le moteur de changement : diff déterministe, ruptures et consommateurs prouvés."""
import json

from meridian.application import decouverte
from meridian.domain import interfaces
from meridian.domain.interfaces import Assertion, Binding, InterfaceGraph, Operation


def _spec(version, chemins, titre="Comptes", serveur="https://api.example.test/v1"):
    return json.dumps({
        "openapi": "3.0.3",
        "info": {"title": titre, "version": version},
        "servers": [{"url": serveur}],
        "paths": chemins,
    }, ensure_ascii=False)


COMPTES = {"/comptes": {"get": {"operationId": "listerComptes"}}}
PAIEMENTS = {"/paiements": {"post": {"operationId": "creerPaiement"}}}
LES_DEUX = {
    "/comptes": {"get": {"operationId": "listerComptes"}},
    "/paiements": {"post": {"operationId": "creerPaiement"}},
}


def _operation(identifiant="op_1", chemin="/comptes", nom="listerComptes", methode="GET",
               contrat="ctr_1", version="1.0.0", environnement="prod"):
    return Operation(id=identifiant, contract_id=contrat, protocol="rest", method=methode, path=chemin,
                     name=nom, version=version, environment=environnement)


def _consommation(application, operation, mode="declared", locator="application.properties",
                  source="config", evidence="digest-config"):
    return Assertion(subject=application, predicate="CONSOMME", object=operation, mode=mode, source=source,
                     locator=locator, environment="prod", confidence=0.6, evidence=evidence)


def _types(changements):
    return [change.type for change in changements]


def test_operation_ajoutee_est_un_changement_non_breaking():
    avant = interfaces.parse_openapi("comptes", _spec("1.0.0", COMPTES), "openapi.json", "prod")
    apres = interfaces.parse_openapi("comptes", _spec("1.0.0", LES_DEUX), "openapi.json", "prod")

    changements = decouverte.diff_graphs(avant, apres)
    ajouts = [c for c in changements if c.type == "operation_added"]

    assert len(ajouts) == 1
    assert ajouts[0].after["path"] == "/paiements"
    assert ajouts[0].severity == "info"
    assert "operation_removed" not in _types(changements)
    assert ajouts[0].evidence


def test_operation_supprimee_est_breaking_et_garde_sa_preuve():
    avant = interfaces.parse_openapi("comptes", _spec("1.0.0", LES_DEUX), "openapi.json", "prod")
    apres = interfaces.parse_openapi("comptes", _spec("1.0.0", COMPTES), "openapi.json", "prod")

    changements = decouverte.diff_graphs(avant, apres)
    suppressions = [c for c in changements if c.type == "operation_removed"]

    assert len(suppressions) == 1
    assert suppressions[0].severity == "breaking"
    assert suppressions[0].before["path"] == "/paiements"
    assert suppressions[0].after is None
    assert any(preuve.get("source") == "openapi" for preuve in suppressions[0].evidence)


def test_operation_changee_par_identifiant_stable():
    avant = InterfaceGraph(operations=[_operation(nom="listerComptes")])
    apres = InterfaceGraph(operations=[_operation(nom="listerTousLesComptes")])

    changements = decouverte.diff_graphs(avant, apres)
    changes = [c for c in changements if c.type == "operation_changed"]

    assert len(changes) == 1
    assert changes[0].severity == "warning"
    assert changes[0].subject == "op_1"
    assert changes[0].before["name"] == "listerComptes"
    assert changes[0].after["name"] == "listerTousLesComptes"
    assert any(preuve.get("changed") == ["name"] for preuve in changes[0].evidence)


def test_operation_changee_de_chemin_est_breaking():
    avant = InterfaceGraph(operations=[_operation(chemin="/comptes")])
    apres = InterfaceGraph(operations=[_operation(chemin="/comptes/v2")])

    changes = [c for c in decouverte.diff_graphs(avant, apres) if c.type == "operation_changed"]

    assert len(changes) == 1
    assert changes[0].severity == "breaking"


def test_contrat_version_et_digest_sans_cascade_sur_les_operations():
    avant = interfaces.parse_openapi("comptes", _spec("1.4.0", COMPTES), "openapi.json", "prod")
    apres = interfaces.parse_openapi("comptes", _spec("1.5.0", COMPTES), "openapi.json", "prod")

    changements = decouverte.diff_graphs(avant, apres)

    assert "contract_version" in _types(changements)
    assert "contract_digest" in _types(changements)
    assert [c.severity for c in changements if c.type == "contract_version"] == ["warning"]
    assert "operation_added" not in _types(changements)
    assert "operation_removed" not in _types(changements)
    assert "operation_changed" not in _types(changements)


def test_contrat_version_majeure_est_breaking():
    avant = interfaces.parse_openapi("comptes", _spec("1.9.0", COMPTES), "openapi.json", "prod")
    apres = interfaces.parse_openapi("comptes", _spec("2.0.0", COMPTES), "openapi.json", "prod")

    versions = [c for c in decouverte.diff_graphs(avant, apres) if c.type == "contract_version"]

    assert len(versions) == 1
    assert versions[0].before == "1.9.0" and versions[0].after == "2.0.0"
    assert versions[0].severity == "breaking"


def test_digest_change_seul_reste_un_avertissement():
    avant = interfaces.parse_openapi("comptes", _spec("1.0.0", COMPTES, titre="Comptes"), "openapi.json", "prod")
    apres = interfaces.parse_openapi("comptes", _spec("1.0.0", COMPTES, titre="Comptes v2"), "openapi.json", "prod")

    changements = decouverte.diff_graphs(avant, apres)

    assert _types(changements) == ["contract_digest"]
    assert changements[0].severity == "warning"
    assert changements[0].before != changements[0].after


def test_consommateur_declare_impacte_par_une_suppression_breaking():
    avant = interfaces.parse_openapi("comptes", _spec("1.0.0", COMPTES), "openapi.json", "prod")
    apres = interfaces.parse_openapi("comptes", _spec("1.0.0", {}), "openapi.json", "prod")
    supprimee = avant.operations[0]
    apres.assertions.append(_consommation("crm", supprimee.id))

    changements = decouverte.diff_graphs(avant, apres)
    constats = decouverte.impacts(changements, apres)

    assert len(constats) == 1
    assert constats[0].application == "crm"
    assert constats[0].operation == supprimee.id
    assert constats[0].change_type == "operation_removed"
    assert constats[0].severity == "breaking"
    assert any(preuve.get("predicate") == "CONSOMME" and preuve.get("mode") == "declared"
               for preuve in constats[0].evidence)


def test_consommation_observee_et_declaree_conservee_dans_la_preuve():
    avant = interfaces.parse_openapi("comptes", _spec("1.0.0", COMPTES), "openapi.json", "prod")
    apres = interfaces.parse_openapi("comptes", _spec("1.0.0", {}), "openapi.json", "prod")
    supprimee = avant.operations[0]
    apres.assertions.append(_consommation("crm", supprimee.id, mode="declared", locator="application.properties"))
    apres.assertions.append(_consommation("crm", supprimee.id, mode="observed", locator="traces.json",
                                         source="datadog", evidence="trace-42"))

    constats = decouverte.impacts(decouverte.diff_graphs(avant, apres), apres)

    assert len(constats) == 1
    modes = {preuve["mode"] for preuve in constats[0].evidence}
    sources = {preuve["source"] for preuve in constats[0].evidence}
    assert modes == {"declared", "observed"}
    assert sources == {"config", "datadog"}


def test_aucun_consommateur_n_est_invente():
    avant = interfaces.parse_openapi("comptes", _spec("1.0.0", COMPTES), "openapi.json", "prod")
    apres = interfaces.parse_openapi("comptes", _spec("1.0.0", {}), "openapi.json", "prod")
    apres.assertions.append(_consommation("crm", "GET /autre"))

    constats = decouverte.impacts(decouverte.diff_graphs(avant, apres), apres)

    assert constats == []


def test_changements_non_breaking_ne_sont_jamais_classes_breaking():
    op1 = _operation()
    op2 = _operation("op_2", chemin="/paiements", nom="creerPaiement", methode="POST")
    binding = Binding(id="bnd_1", protocol="rest", url="https://api.example.test/v1", environment="prod")
    expose = Assertion(subject="comptes", predicate="EXPOSE", object=op1.id, mode="declared", source="openapi",
                       locator="openapi.json", environment="prod", confidence=0.95, evidence="digest")
    observe = Assertion(subject="comptes", predicate="EXPOSE", object=op1.id, mode="observed", source="openapi",
                        locator="openapi.json", environment="prod", confidence=0.95, evidence="digest")

    avant = InterfaceGraph(operations=[op1], assertions=[expose])
    apres = InterfaceGraph(operations=[op1, op2], bindings=[binding], assertions=[observe])

    changements = decouverte.diff_graphs(avant, apres)

    assert {"operation_added", "binding_added", "assertion_mode_changed"} <= set(_types(changements))
    assert all(change.severity != "breaking" for change in changements)


def test_changement_de_locator_est_garde_mais_non_breaking():
    expose = Assertion(subject="comptes", predicate="EXPOSE", object="op_1", mode="declared", source="openapi",
                       locator="openapi.json", environment="prod", confidence=0.95, evidence="digest")
    deplace = Assertion(subject="comptes", predicate="EXPOSE", object="op_1", mode="declared", source="openapi",
                        locator="openapi-v2.json", environment="prod", confidence=0.95, evidence="digest")

    changements = decouverte.diff_graphs(
        InterfaceGraph(operations=[_operation()], assertions=[expose]),
        InterfaceGraph(operations=[_operation()], assertions=[deplace]))

    assert {"assertion_removed", "assertion_added"} <= set(_types(changements))
    assert all(change.severity == "info" for change in changements)


def test_binding_retire_reste_un_avertissement():
    binding = Binding(id="bnd_1", protocol="rest", url="https://api.example.test/v1", environment="prod")

    changements = decouverte.diff_graphs(InterfaceGraph(bindings=[binding]), InterfaceGraph())

    assert _types(changements) == ["binding_removed"]
    assert changements[0].severity == "warning"


def test_diff_et_impacts_sont_deterministes():
    avant = interfaces.parse_openapi("comptes", _spec("1.0.0", COMPTES), "openapi.json", "prod")
    apres = interfaces.parse_openapi("comptes", _spec("1.0.0", {}), "openapi.json", "prod")
    supprimee = avant.operations[0]
    apres.assertions.append(_consommation("crm", supprimee.id))

    premier = decouverte.diff_graphs(avant, apres)
    second = decouverte.diff_graphs(avant, apres)
    impremier = decouverte.impacts(premier, apres)
    impsecond = decouverte.impacts(second, apres)

    assert premier == second
    assert impremier == impsecond
    assert decouverte.resume(premier, impremier) == decouverte.resume(second, impsecond)


def test_resume_compte_les_severites_et_liste_les_ruptures():
    avant = interfaces.parse_openapi("comptes", _spec("1.0.0", LES_DEUX), "openapi.json", "prod")
    apres = interfaces.parse_openapi("comptes", _spec("1.0.0", COMPTES), "openapi.json", "prod")
    supprimee = next(o for o in avant.operations if o.path == "/paiements")
    apres.assertions.append(_consommation("crm", supprimee.id))
    changements = decouverte.diff_graphs(avant, apres)
    constats = decouverte.impacts(changements, apres)

    resultat = decouverte.resume(changements, constats)

    assert resultat["total"] == len(changements)
    assert resultat["par_severite"]["breaking"] == 1
    assert len(resultat["breaking"]) == 1
    assert resultat["breaking"][0]["type"] == "operation_removed"
    assert resultat["impacts"] == 1
    assert resultat["applications_impactees"] == ["crm"]
    assert "breaking" in resultat["texte"] and "crm" not in resultat["texte"]


def test_changements_impacts_et_resume_sont_serialisables_en_json():
    avant = interfaces.parse_openapi("comptes", _spec("1.0.0", COMPTES), "openapi.json", "prod")
    apres = interfaces.parse_openapi("comptes", _spec("1.0.0", {}), "openapi.json", "prod")
    supprimee = avant.operations[0]
    apres.assertions.append(_consommation("crm", supprimee.id))
    changements = decouverte.diff_graphs(avant, apres)
    constats = decouverte.impacts(changements, apres)

    rendu = json.dumps({
        "changements": [change.as_dict() for change in changements],
        "impacts": [impact.as_dict() for impact in constats],
        "resume": decouverte.resume(changements, constats),
    }, ensure_ascii=False)
    relu = json.loads(rendu)

    assert relu["changements"][0]["type"] in decouverte.TYPES_CHANGE
    assert relu["impacts"][0]["application"] == "crm"
    assert relu["resume"]["par_severite"]["breaking"] == 1
