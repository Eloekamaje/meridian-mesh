"""Connecteur runtime APM/gateway : assertions observées, mode ombre, preuves, secrets et bornes."""
import json
import os
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from jumeau import connecteurs_runtime as runtime
from jumeau import interfaces

TS = "2026-10-30T12:00:00Z"
TS2 = "2026-10-30T12:00:05Z"
TS_NS = int(datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc).timestamp()) * 1_000_000_000
TRACE_OTLP = "0af7651916cd43dd8448eb211c80319c"


def observation(**champs):
    base = {
        "ts": TS, "caller": "app-a", "callee": "app-b", "protocol": "rest",
        "method": "GET", "path": "/comptes", "operation_id": "listerComptes",
        "status": 200, "duration_ms": 12, "trace_id": "trace-1", "gateway": "kong",
    }
    base.update(champs)
    return base


def attribut_otlp(cle, valeur):
    if isinstance(valeur, bool):
        contenu = {"boolValue": valeur}
    elif isinstance(valeur, int):
        contenu = {"intValue": str(valeur)}
    elif isinstance(valeur, float):
        contenu = {"doubleValue": valeur}
    else:
        contenu = {"stringValue": str(valeur)}
    return {"key": cle, "value": contenu}


def span_otlp(kind=3, span_id="b7ad6b7169203331", trace_id=TRACE_OTLP, debut=TS_NS,
              fin=TS_NS + 12_000_000, attributs=None, sans=()):
    valeurs = {
        "http.method": "GET", "http.route": "/comptes", "http.status_code": 200,
        "peer.service": "app-b",
    }
    valeurs.update(dict(attributs or {}))
    for cle in sans:
        valeurs.pop(cle, None)
    return {
        "traceId": trace_id, "spanId": span_id, "name": "GET /comptes", "kind": kind,
        "startTimeUnixNano": str(debut), "endTimeUnixNano": str(fin),
        "attributes": [attribut_otlp(cle, valeur) for cle, valeur in valeurs.items()],
    }


def payload_otlp(spans, service="app-a"):
    return {
        "resourceSpans": [{
            "resource": {"attributes": [attribut_otlp("service.name", service)]},
            "scopeSpans": [{"scope": {"name": "test"}, "spans": spans}],
        }],
    }


def test_observation_caller_produit_consomme_observee():
    g = runtime.depuis_observations("app-a", [observation()], environment="prod", source="apm")

    contrat = g.contracts[0]
    assert contrat.format == "runtime" and contrat.application_id == "app-a"
    assert contrat.environment == "prod" and len(contrat.digest) == 64
    assert [(o.protocol, o.method, o.path, o.name, o.environment) for o in g.operations] == [
        ("rest", "GET", "/comptes", "listerComptes", "prod")]
    assert len(g.assertions) == 1
    a = g.assertions[0]
    assert (a.subject, a.predicate, a.object) == ("app-a", "CONSOMME", "app-b : GET /comptes")
    assert (a.mode, a.source, a.environment) == ("observed", "apm", "prod")
    assert a.observed_at == TS and a.confidence == 0.95
    assert "trace-1" in a.evidence and "kong" in a.evidence
    assert g.partial is False and g.diagnostics == []


def test_observation_callee_produit_expose_observee():
    g = runtime.depuis_observations("app-b", [observation()], environment="prod")

    assert [(o.method, o.path) for o in g.operations] == [("GET", "/comptes")]
    a = g.assertions[0]
    assert (a.subject, a.predicate, a.object) == ("app-b", "EXPOSE", "GET /comptes")
    assert a.mode == "observed" and a.source == "apm"
    assert "trace-1" in a.evidence


def test_appels_hors_application_ignores():
    g = runtime.depuis_observations("app-x", [observation()])

    assert g.assertions == [] and g.operations == []
    assert g.partial is True
    assert any("aucune observation" in diagnostic for diagnostic in g.diagnostics)


def test_caller_ou_callee_absent_reste_attribuable():
    sortant = runtime.depuis_observations("app-a", [observation(callee=None)])
    entrant = runtime.depuis_observations("app-a", [observation(caller=None, callee="app-a")])

    assert [(a.predicate, a.object) for a in sortant.assertions] == [("CONSOMME", "GET /comptes")]
    assert [(a.predicate, a.object) for a in entrant.assertions] == [("EXPOSE", "GET /comptes")]


def test_auto_appel_compte_une_seule_fois_dans_resume():
    g = runtime.depuis_observations("app-a", [observation(callee="app-a")])

    assert {a.predicate for a in g.assertions} == {"CONSOMME", "EXPOSE"}
    assert len(g.operations) == 1
    assert runtime.resume(g)["appels"] == 1


def test_trace_status_duree_et_confiance_conserves():
    complet = runtime.depuis_observations("app-a", [observation()]).assertions[0]
    sans_trace = runtime.depuis_observations(
        "app-a", [observation(trace_id=None)]).assertions[0]
    minimal = runtime.depuis_observations(
        "app-a", [observation(trace_id=None, duration_ms=None, status=None)]).assertions[0]

    assert complet.confidence == 0.95
    assert sans_trace.confidence == 0.8
    assert minimal.confidence == 0.4
    meta = json.loads(complet.evidence)
    assert (meta["trace_id"], meta["gateway"], meta["status"], meta["duration_ms"]) == (
        "trace-1", "kong", 200, 12.0)


def test_observations_identiques_dedupliquees_et_digest_stable():
    une = runtime.depuis_observations("app-a", [observation()])
    deux = runtime.depuis_observations("app-a", [observation(), observation()])
    inversees = runtime.depuis_observations(
        "app-a", [observation(path="/paiements", method="POST", operation_id="payer"), observation()])

    assert une.as_dict() == deux.as_dict()
    assert len(deux.assertions) == 1 and len(deux.operations) == 1
    assert une.contracts[0].digest == deux.contracts[0].digest
    assert inversees.as_dict() == runtime.depuis_observations(
        "app-a", [observation(), observation(path="/paiements", method="POST", operation_id="payer")]
    ).as_dict()


def test_operations_stables_quand_une_autre_observation_arrive():
    seul = runtime.depuis_observations("app-a", [observation()])
    avec_autre = runtime.depuis_observations(
        "app-a", [observation(), observation(path="/paiements", method="POST", operation_id="payer")])

    assert seul.contracts[0].digest != avec_autre.contracts[0].digest
    identifiants = {o.id for o in seul.operations}
    assert identifiants <= {o.id for o in avec_autre.operations}


def test_aucune_assertion_declared_et_fusion_en_ombre_preserve_le_declare():
    openapi = json.dumps({
        "openapi": "3.0.3", "info": {"title": "Comptes", "version": "1"},
        "paths": {"/comptes": {"get": {"operationId": "listerComptes"}}},
    })
    declare = interfaces.parse_openapi("app-a", openapi, "openapi.json", "prod")
    observe = runtime.depuis_observations("app-a", [observation(callee="app-a")], environment="prod")
    fusion = interfaces.merge([declare, observe])

    assert all(a.mode == "observed" for a in observe.assertions)
    assert all(a.mode != "observed" or a.source == "apm" for a in fusion.assertions)
    assert any(a.mode == "declared" and a.source == "openapi" for a in fusion.assertions)
    assert any(a.mode == "observed" and a.source == "apm" for a in fusion.assertions)
    assert {a.object for a in fusion.assertions if a.mode == "declared"} == {"GET /comptes"}


def test_resume_compteurs_par_protocole_erreurs_et_applications():
    observations = [
        observation(),
        observation(ts=TS2, caller="app-b", callee="app-a", method="POST", path="/paiements",
                    operation_id="payer", status=500, duration_ms=30, trace_id="trace-2"),
        observation(ts=TS2, caller="app-c", callee="app-d", protocol="grpc", path="/x", trace_id="trace-3"),
    ]
    g = runtime.depuis_observations("app-a", observations)

    attendu = {
        "appels": 2, "erreurs": 1, "protocoles": {"rest": 2},
        "applications": {"caller": {"app-a": 1, "app-b": 1}, "callee": {"app-a": 1, "app-b": 1}},
    }
    assert runtime.resume(g) == attendu
    assert runtime.resume_observations(observations, "app-a") == attendu
    global_ = runtime.resume_observations(observations)
    assert global_["appels"] == 3 and global_["erreurs"] == 1
    assert global_["protocoles"] == {"grpc": 1, "rest": 2}


def test_lecteur_json_fichier_texte_et_objet_enveloppe(tmp_path):
    chemin = tmp_path / "export.json"
    chemin.write_text(json.dumps([observation()]), encoding="utf-8")

    assert runtime.lire_export(chemin) == [observation()]
    assert runtime.lire_export(json.dumps([observation()])) == [observation()]
    assert runtime.lire_export(json.dumps({"observations": [observation()]})) == [observation()]
    assert runtime.depuis_fichier(chemin, "app-a").assertions[0].predicate == "CONSOMME"


def test_export_invalide_trop_gros_ou_hors_schema_erreur_claire(tmp_path):
    secret = "s3cr3t-interdit"
    with pytest.raises(ValueError, match="JSON invalide") as invalide:
        runtime.lire_export('{"document": "' + secret + '"')
    assert secret not in str(invalide.value)

    with pytest.raises(ValueError, match="trop volumineux"):
        runtime.lire_export(json.dumps([observation()]), max_octets=10)

    chemin = tmp_path / "gros.json"
    chemin.write_text(json.dumps([observation()]), encoding="utf-8")
    with pytest.raises(ValueError, match="trop volumineux"):
        runtime.lire_export(chemin, max_octets=10)

    with pytest.raises(ValueError, match="liste d'observations"):
        runtime.lire_export(json.dumps({"pas": "une liste"}))
    with pytest.raises(ValueError, match="ts manquant"):
        runtime.lire_export(json.dumps([{"caller": "app-a"}]))
    with pytest.raises(ValueError, match="status"):
        runtime.lire_export(json.dumps([observation(status="200")]))
    assert secret not in json.dumps(runtime.lire_export(json.dumps([observation()])))


def test_export_avec_userinfo_ou_secret_refuse_sans_fuite():
    userinfo = observation(path="https://alice:s3cr3t@api.example.test/comptes")
    secret = observation(path="/comptes?token=abc123&name=public")

    for donnees, interdit in (([userinfo], ("alice", "s3cr3t")), ([secret], ("abc123",))):
        with pytest.raises(ValueError) as erreur:
            runtime.lire_export(json.dumps(donnees))
        message = str(erreur.value)
        assert "identifiants ou un secret" in message
        assert all(valeur not in message for valeur in interdit)


def test_transformation_masque_userinfo_et_secret_sans_fuite():
    g = runtime.depuis_observations("app-a", [observation(
        path="https://alice:s3cr3t@api.example.test/comptes?token=abc123&name=public",
        gateway="https://bob:hunter2@gateway.example.test")])

    a = g.assertions[0]
    assert a.object == "app-b : GET /comptes?token=***&name=public"
    rendu = json.dumps(g.as_dict(), ensure_ascii=False)
    for interdit in ("alice", "s3cr3t", "abc123", "bob", "hunter2", "api.example.test",
                     "gateway.example.test"):
        assert interdit not in rendu
    assert g.operations[0].path == "/comptes?token=***&name=public"


def test_aucun_acces_reseau_pendant_la_lecture(tmp_path, monkeypatch):
    chemin = tmp_path / "export.json"
    chemin.write_text(json.dumps([observation()]), encoding="utf-8")

    def interdit(*args, **kwargs):
        raise AssertionError("accès réseau interdit")

    monkeypatch.setattr(socket, "socket", interdit)
    monkeypatch.setattr(socket, "create_connection", interdit)
    monkeypatch.setattr(socket, "getaddrinfo", interdit)

    assert runtime.depuis_fichier(chemin, "app-a").assertions[0].predicate == "CONSOMME"


def test_cli_imprime_le_graphe_et_erreur_sans_stdout(tmp_path):
    chemin = tmp_path / "export.json"
    chemin.write_text(json.dumps([observation()]), encoding="utf-8")
    backend = Path(__file__).resolve().parents[2]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(backend) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")

    reussi = subprocess.run(
        [sys.executable, "-m", "jumeau.connecteurs_runtime", str(chemin), "app-a",
         "--environment", "prod"], cwd=backend, env=env, capture_output=True, text=True, timeout=60)
    assert reussi.returncode == 0
    rendu = json.loads(reussi.stdout)
    assert rendu["contracts"][0]["format"] == "runtime"
    assert rendu["contracts"][0]["environment"] == "prod"
    assert rendu["assertions"][0]["mode"] == "observed"

    invalide = tmp_path / "invalide.json"
    invalide.write_text('{"secret": "s3cr3t"', encoding="utf-8")
    echec = subprocess.run(
        [sys.executable, "-m", "jumeau.connecteurs_runtime", str(invalide), "app-a"],
        cwd=backend, env=env, capture_output=True, text=True, timeout=60)
    assert echec.returncode == 2 and echec.stdout == ""
    assert "s3cr3t" not in echec.stderr


def test_otlp_client_et_serveur_produisent_consomme_et_expose_observed():
    client = span_otlp(span_id="client-1")
    g = runtime.depuis_otlp("app-a", payload_otlp([client], service="app-a"), environment="prod")

    assert [(a.subject, a.predicate, a.object, a.mode) for a in g.assertions] == [
        ("app-a", "CONSOMME", "app-b : GET /comptes", "observed")]
    assert g.partial is False and g.diagnostics == []
    assert g.contracts[0].environment == "prod" and g.contracts[0].application_id == "app-a"

    serveur = span_otlp(
        kind=2, span_id="serveur-1",
        attributs={"http.method": "POST", "http.route": "/paiements", "http.status_code": 201,
                   "peer.service": "app-c"})
    g = runtime.depuis_otlp("app-b", payload_otlp([serveur], service="app-b"), environment="prod")

    assert [(a.subject, a.predicate, a.object, a.mode) for a in g.assertions] == [
        ("app-b", "EXPOSE", "POST /paiements", "observed")]
    assert g.partial is False and g.diagnostics == []


def test_lire_export_auto_detecte_otlp_et_garde_le_normalise():
    charge = json.dumps(payload_otlp([span_otlp()]))

    otlp = runtime.lire_export(charge)
    assert [(o["caller"], o["callee"], o["trace_id"], o["path"]) for o in otlp] == [
        ("app-a", "app-b", TRACE_OTLP, "/comptes")]
    assert runtime.lire_export(charge, format="otlp") == otlp
    assert runtime.lire_export(charge.encode("utf-8")) == otlp
    assert runtime.depuis_otlp("app-a", charge.encode("utf-8")).assertions[0].predicate == "CONSOMME"
    assert runtime.lire_export(json.dumps([observation()])) == [observation()]
    assert runtime.lire_export(json.dumps({"observations": [observation()]})) == [observation()]


def test_otlp_http_trace_status_duree_et_route():
    g = runtime.depuis_otlp(
        "app-a", payload_otlp([span_otlp(attributs={"http.route": "/comptes/{id}",
                                                    "http.status_code": 204})]))
    a = g.assertions[0]
    meta = json.loads(a.evidence)

    assert (meta["trace_id"], meta["status"], meta["duration_ms"]) == (TRACE_OTLP, 204, 12.0)
    assert (g.operations[0].method, g.operations[0].path) == ("GET", "/comptes/{id}")
    assert a.confidence == 0.95


def test_otlp_grpc_method_service_statut_et_duree():
    span = span_otlp(
        kind=2, span_id="grpc-1", fin=TS_NS + 5_000_000,
        attributs={"rpc.system": "grpc", "rpc.service": "comptes.Comptes", "rpc.method": "Lister",
                   "rpc.grpc.status_code": 0, "peer.service": "app-a"},
        sans=("http.method", "http.route", "http.status_code"))
    g = runtime.depuis_otlp("app-b", payload_otlp([span], service="app-b"))

    assert [(o.protocol, o.method, o.path) for o in g.operations] == [
        ("grpc", "LISTER", "/comptes.Comptes/Lister")]
    a = g.assertions[0]
    assert (a.predicate, a.object, a.mode) == ("EXPOSE", "LISTER /comptes.Comptes/Lister", "observed")
    meta = json.loads(a.evidence)
    assert (meta["status"], meta["duration_ms"], meta["trace_id"]) == (200, 5.0, TRACE_OTLP)


def test_otlp_spans_incomplets_ignores_avec_compteur_de_diagnostics():
    sans_ts = span_otlp(span_id="sans-ts")
    sans_ts.pop("startTimeUnixNano")
    sans_methode = span_otlp(span_id="sans-methode", sans=("http.method",))
    sans_chemin = span_otlp(span_id="sans-chemin", sans=("http.route",))
    valide = span_otlp(span_id="valide")

    g = runtime.depuis_otlp(
        "app-a", payload_otlp([sans_ts, sans_methode, sans_chemin, valide]))

    assert [(a.predicate, a.object, a.mode) for a in g.assertions] == [
        ("CONSOMME", "app-b : GET /comptes", "observed")]
    assert g.partial is True
    texte = " | ".join(g.diagnostics)
    assert "startTimeUnixNano" in texte and "méthode manquante" in texte and "chemin manquant" in texte
    assert "3 span(s) ignoré(s) sur 4" in texte


def test_otlp_sens_indetermine_reste_partiel_sans_inventer():
    ambigu = span_otlp(kind=0, span_id="ambigu", sans=("peer.service",))
    g = runtime.depuis_otlp("app-a", payload_otlp([ambigu]))

    assert [(a.predicate, a.object, a.mode) for a in g.assertions] == [
        ("CONSOMME", "GET /comptes", "observed")]
    assert g.partial is True
    assert any("callee indéterminé" in diagnostic for diagnostic in g.diagnostics)

    avec_pair = span_otlp(kind=0, span_id="ambigu-avec-pair")
    g = runtime.depuis_otlp("app-a", payload_otlp([avec_pair]))

    assert [(a.predicate, a.object) for a in g.assertions] == [("CONSOMME", "app-b : GET /comptes")]
    assert any("sens caller/callee indéterminé" in diagnostic for diagnostic in g.diagnostics)


def test_otlp_deduplique_les_spans_identiques():
    span = span_otlp()

    g = runtime.depuis_otlp("app-a", payload_otlp([span, dict(span)]))

    assert len(g.assertions) == 1 and len(g.operations) == 1


def test_otlp_json_invalide_taille_et_secret_sans_fuite(tmp_path):
    secret = "s3cr3t-otlp"
    with pytest.raises(ValueError, match="JSON invalide") as invalide:
        runtime.depuis_otlp("app-a", '{"resourceSpans": "' + secret)
    assert secret not in str(invalide.value)

    charge = json.dumps(payload_otlp([span_otlp()]))
    with pytest.raises(ValueError, match="trop volumineux"):
        runtime.lire_otlp(charge, max_octets=10)
    with pytest.raises(ValueError, match="trop volumineux"):
        runtime.lire_otlp(json.dumps(payload_otlp([span_otlp(span_id=str(i)) for i in range(3)])),
                          max_spans=2)
    chemin = tmp_path / "otlp.json"
    chemin.write_text(charge, encoding="utf-8")
    with pytest.raises(ValueError, match="trop volumineux"):
        runtime.lire_otlp(chemin, max_octets=10)

    avec_secret = span_otlp(
        attributs={"http.url": "https://alice:s3cr3t@api.example.test/comptes?token=abc123"},
        sans=("http.route",))
    for lecture in (lambda: runtime.depuis_otlp("app-a", payload_otlp([avec_secret])),
                    lambda: runtime.lire_export(json.dumps(payload_otlp([avec_secret])))):
        with pytest.raises(ValueError) as erreur:
            lecture()
        message = str(erreur.value)
        assert all(interdit not in message for interdit in ("alice", "s3cr3t", "abc123"))

    observations = runtime.lire_otlp(payload_otlp([avec_secret]), strict=False)
    assert observations[0]["path"] == "/comptes?token=***"
    rendu = json.dumps(observations)
    assert all(interdit not in rendu for interdit in
               ("alice", "s3cr3t", "abc123", "api.example.test"))


def test_otlp_ne_produit_aucune_assertion_declared():
    spans = [span_otlp(span_id="client"), span_otlp(kind=2, span_id="serveur")]
    g = runtime.depuis_otlp("app-a", payload_otlp(spans, service="app-a"), environment="prod")

    assert g.assertions
    assert {a.predicate for a in g.assertions} == {"CONSOMME", "EXPOSE"}
    assert all(a.mode == "observed" for a in g.assertions)
    assert not any(a.mode == "declared" for a in g.assertions)


def test_cli_format_otlp(tmp_path):
    chemin = tmp_path / "otlp.json"
    chemin.write_text(json.dumps(payload_otlp([span_otlp()])), encoding="utf-8")
    backend = Path(__file__).resolve().parents[2]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(backend) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")

    resultat = subprocess.run(
        [sys.executable, "-m", "jumeau.connecteurs_runtime", str(chemin), "app-a",
         "--format", "otlp", "--environment", "prod"],
        cwd=backend, env=env, capture_output=True, text=True, timeout=60)

    assert resultat.returncode == 0
    rendu = json.loads(resultat.stdout)
    assert rendu["assertions"][0]["mode"] == "observed"
    assert rendu["assertions"][0]["object"] == "app-b : GET /comptes"
