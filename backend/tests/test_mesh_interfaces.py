"""Dérivation pure du Mesh d'interfaces : arêtes, impacts et vues publiques (sans base ni serveur)."""
from jumeau import interfaces_depot
from jumeau.interfaces import Assertion, Contract, InterfaceGraph, Operation

VISIBLES = ["facturation", "paiements"]


def _contrat(identifiant, application, environment="production"):
    return Contract(id=identifiant, format="openapi", version="1.0", digest=f"digest-{identifiant}",
                    locator="openapi.yaml", application_id=application, environment=environment)


def _operation(identifiant, contrat, method="GET", path="/paiements", environment="production"):
    return Operation(id=identifiant, contract_id=contrat, protocol="rest", method=method, path=path,
                     name=f"{method} {path}", version="1.0", environment=environment)


def _assertion(subject, predicate, objet, mode="declared", source="openapi", confidence=0.95,
               evidence="preuve", environment="production"):
    return Assertion(subject=subject, predicate=predicate, object=objet, mode=mode, source=source,
                     locator="openapi.yaml", environment=environment, confidence=confidence, evidence=evidence)


def _graphe(assertions):
    return InterfaceGraph(
        contracts=[_contrat("ctr-facturation", "facturation"), _contrat("ctr-paiements", "paiements")],
        operations=[_operation("op-get", "ctr-facturation", "GET", "/paiements"),
                    _operation("op-post", "ctr-facturation", "POST", "/paiements")],
        assertions=list(assertions),
    )


def test_une_consommation_par_id_designe_l_application_productrice():
    graph = _graphe([
        _assertion("paiements", "CONSOMME", "op-get", mode="observed", source="datadog",
                   confidence=0.9, evidence="trace-42"),
        _assertion("facturation", "EXPOSE", "GET /paiements"),
    ])
    assert interfaces_depot.deriver_aretes(graph, VISIBLES) == [{
        "source": "paiements",
        "target": "facturation",
        "operation_id": "op-get",
        "operation": "GET /paiements",
        "mode": "observed",
        "assertion_source": "datadog",
        "confidence": 0.9,
        "evidence": "trace-42",
    }]


def test_une_consommation_par_method_path_designe_la_bonne_operation():
    graph = _graphe([_assertion("paiements", "CONSOMME", "POST /paiements", source="config",
                                confidence=0.4, evidence="env")])
    aretes = interfaces_depot.deriver_aretes(graph, VISIBLES)
    assert len(aretes) == 1
    assert aretes[0]["operation_id"] == "op-post"
    assert aretes[0]["operation"] == "POST /paiements"


def test_une_operation_inconnue_ne_produit_aucune_arete():
    graph = _graphe([
        _assertion("paiements", "CONSOMME", "GET /inconnue"),
        _assertion("paiements", "CONSOMME", "https://api.example.test/paiements"),
        _assertion("paiements", "CONSOMME", "op-inexistante"),
    ])
    assert interfaces_depot.deriver_aretes(graph, VISIBLES) == []


def test_un_producteur_hors_perimetre_ne_est_pas_revele():
    graph = _graphe([_assertion("paiements", "CONSOMME", "op-get")])
    assert interfaces_depot.deriver_aretes(graph, ["paiements"]) == []
    assert interfaces_depot.operations_publiques(graph, ["paiements"]) == []


def test_un_consommateur_hors_perimetre_ne_produit_aucune_arete():
    graph = _graphe([_assertion("comptes", "CONSOMME", "op-get")])
    assert interfaces_depot.deriver_aretes(graph, VISIBLES) == []


def test_les_aretes_sont_dedupliquees_et_gardent_la_meilleure_preuve():
    graph = _graphe([
        _assertion("paiements", "CONSOMME", "op-get", mode="observed", source="datadog",
                   confidence=0.5, evidence="preuve-faible"),
        _assertion("paiements", "CONSOMME", "GET /paiements", mode="observed", source="datadog",
                   confidence=0.9, evidence="preuve-forte"),
    ])
    aretes = interfaces_depot.deriver_aretes(graph, VISIBLES)
    assert len(aretes) == 1
    assert aretes[0]["confidence"] == 0.9
    assert aretes[0]["evidence"] == "preuve-forte"


def test_les_impacts_hors_perimetre_sont_ecartes():
    runs = [
        {"id": "run-1", "application_id": "facturation", "status": "ok",
         "started_at": "2026-10-30T10:00:00+00:00", "stats": {"impacts": 2}, "impacts": [
             {"application": "paiements", "operation": "GET /paiements", "change_type": "operation_removed",
              "severity": "breaking", "raison": "rupture", "evidence": [{"type": "assertion"}]},
             {"application": "secret", "operation": "GET /secret", "change_type": "operation_removed",
              "severity": "breaking", "raison": "hors périmètre", "evidence": []},
         ]},
        {"id": "run-2", "application_id": "secret", "status": "ok",
         "started_at": "2026-10-30T11:00:00+00:00", "stats": {"impacts": 1}, "impacts": [
             {"application": "paiements", "operation": "GET /secret", "change_type": "operation_removed",
              "severity": "breaking", "raison": "run hors périmètre", "evidence": []},
         ]},
    ]
    impacts = interfaces_depot.impacts_des_runs(runs, VISIBLES)
    assert len(impacts) == 1
    assert impacts[0]["application"] == "paiements"
    assert impacts[0]["run_id"] == "run-1"
    assert impacts[0]["at"] == "2026-10-30T10:00:00+00:00"


def test_la_vue_des_runs_ne_revele_ni_changements_ni_runs_hors_perimetre():
    runs = [
        {"id": "run-1", "application_id": "paiements", "status": "ok",
         "started_at": "2026-10-30T10:00:00+00:00", "stats": {"operations": 3}, "changes": [{"secret": True}]},
        {"id": "run-2", "application_id": "secret", "status": "error",
         "started_at": "2026-10-30T11:00:00+00:00", "stats": {}},
    ]
    assert interfaces_depot.runs_publiques(runs, VISIBLES) == [{
        "id": "run-1", "application_id": "paiements", "status": "ok",
        "started_at": "2026-10-30T10:00:00+00:00", "stats": {"operations": 3},
    }]
