"""Tirage OTLP d'arrière-plan : fusion runtime, runs observés, erreurs isolées et impacts publiés."""
import asyncio
import json

from jumeau import (connecteurs_runtime_pull, decouverte_interfaces, interfaces, interfaces_depot,
                    pulls_runtime)
from jumeau.tests.conftest import besoin_pg

URL = "https://collecteur.exemple.fr/v1/traces"
SECRET_REF = "env:MERIDIAN_OTLP_TOKEN"
SECRET = "jeton-tres-secret-123"
JUMEAU = {"id": "comptes", "tenant_id": "banque", "nom": "Comptes", "equipe": "equipe-paiements"}


def _graph(path="/comptes", environment="prod", application_id="comptes"):
    contrat = interfaces.Contract(
        id=f"ctr-runtime-{path}", format="runtime", version=None, digest="sha256:test",
        locator=f"otlp:{environment}", application_id=application_id, environment=environment)
    operation = interfaces.Operation(
        id=f"op-runtime-{path}", contract_id=contrat.id, protocol="http", method="GET", path=path,
        name=f"GET {path}", version=None, environment=environment)
    assertion = interfaces.Assertion(
        subject=application_id, predicate="EXPOSE", object=f"GET {path}", mode="observed", source="otlp",
        locator=f"otlp:{environment}", environment=environment, confidence=0.9,
        evidence='{"trace_id":"0af7651916cd43dd8448eb211c80319c"}',
        observed_at="2026-10-30T10:00:00+00:00")
    return interfaces.InterfaceGraph(contracts=[contrat], operations=[operation], assertions=[assertion])


def _claims():
    return [{"id": "c1", "predicat": "EXPOSE", "objet": "GET /sante", "preuve": "server.py#L10",
             "confiance": 0.7}]


@besoin_pg
def test_executer_graph_fusionne_sans_supprimer_le_declare(conn):
    decouverte_interfaces.executer(
        conn, "banque", "comptes", claims=_claims(), environment="prod", source="code")

    premier = decouverte_interfaces.executer(
        conn, "banque", "comptes", graph=_graph(), environment="prod", source="otlp")
    lu = interfaces_depot.lire_graph(conn, "banque", "comptes")

    assert premier["run"]["source"] == "otlp" and premier["run"]["status"] == "ok"
    assert {(o.method, o.path) for o in lu.operations} == {("GET", "/sante"), ("GET", "/comptes")}
    assert any(a.mode == "declared" and a.source == "code" for a in lu.assertions)
    assert any(a.mode == "observed" and a.source == "otlp" for a in lu.assertions)

    # Un second tirage remplace le périmètre runtime sans toucher au code déclaré.
    decouverte_interfaces.executer(
        conn, "banque", "comptes", graph=_graph("/nouveau"), environment="prod", source="otlp")
    lu = interfaces_depot.lire_graph(conn, "banque", "comptes")

    assert {(o.method, o.path) for o in lu.operations} == {("GET", "/sante"), ("GET", "/nouveau")}
    assert any(a.mode == "declared" and a.source == "code" for a in lu.assertions)
    assert {a.object for a in lu.assertions if a.mode == "observed"} == {"GET /nouveau"}


@besoin_pg
def test_tirer_avec_pull_mocke_produit_un_run_observe(conn, monkeypatch):
    appels = []

    def depuis_url(application_id, url, secret_ref, environment, source, hotes_autorises=None):
        appels.append((application_id, url, secret_ref, environment, source, hotes_autorises))
        return _graph()

    monkeypatch.setattr(pulls_runtime.connecteurs_runtime_pull, "depuis_url", depuis_url)
    source = {"nom": "collecteur-comptes", "url": URL, "secret_ref": SECRET_REF, "environment": "prod"}

    resultat = pulls_runtime.tirer(conn, JUMEAU, source)

    assert resultat["run"]["source"] == "otlp" and resultat["run"]["status"] == "ok"
    assert resultat["run"]["application_id"] == "comptes"
    assert resultat["run"]["stats"]["operations"] == 1
    assert resultat["source"] == {"id": None, "nom": "collecteur-comptes", "environment": "prod",
                                  "frequence": None, "derniere_pull": None, "derniere_tentative": None,
                                  "derniere_erreur": None}
    assert all(a["mode"] == "observed" for a in resultat["graphe"]["assertions"])
    assert appels == [("comptes", URL, SECRET_REF, "prod", "otlp", None)]

    ligne = conn.execute("SELECT status, source, environment FROM discovery_run WHERE id = %s",
                         (resultat["run"]["id"],)).fetchone()
    assert ligne == ("ok", "otlp", "prod")
    lu = interfaces_depot.lire_graph(conn, "banque", "comptes")
    assert {(o.method, o.path) for o in lu.operations} == {("GET", "/comptes")}


@besoin_pg
def test_erreur_d_une_source_n_empeche_pas_les_autres(conn, monkeypatch):
    def depuis_url(application_id, url, *args, **kwargs):
        if "panne" in url:
            raise connecteurs_runtime_pull.HoteRefuse("URL OTLP : hôte non autorisé")
        return _graph()

    monkeypatch.setattr(pulls_runtime.connecteurs_runtime_pull, "depuis_url", depuis_url)
    sources = [
        {"nom": "panne", "url": "https://panne.exemple.fr/v1/traces", "environment": "prod"},
        {"nom": "sain", "url": URL, "environment": "prod"},
    ]

    runs = asyncio.run(pulls_runtime.tirer_et_publier(None, conn, JUMEAU, sources))

    assert len(runs) == 1 and runs[0]["source"] == "otlp" and runs[0]["status"] == "ok"
    assert conn.execute("SELECT count(*) FROM discovery_run WHERE tenant_id = %s",
                        ("banque",)).fetchone()[0] == 1


class _Situations:
    def __init__(self):
        self.docs = {}

    async def update_many(self, filtre, mise_a_jour):
        for doc in self.docs.values():
            if doc.get("statut") == "active":
                doc["statut"] = "archivee"

    async def replace_one(self, filtre, doc, upsert=False):
        self.docs[doc["id"]] = dict(doc)


class _Notifications:
    def __init__(self):
        self.docs = {}

    async def update_one(self, filtre, mise_a_jour, upsert=False):
        if filtre["id"] in self.docs:
            return type("Resultat", (), {"upserted_id": None, "matched_count": 1})()
        self.docs[filtre["id"]] = dict(mise_a_jour["$setOnInsert"])
        return type("Resultat", (), {"upserted_id": filtre["id"], "matched_count": 0})()


class _Db:
    def __init__(self):
        self.situations = _Situations()
        self.notifications = _Notifications()


def _run_avec_impact():
    return {
        "id": "run-impact", "application_id": "comptes", "source": "otlp", "environment": "prod",
        "status": "ok", "stats": {"changements": 1, "impacts": 1}, "changes": [],
        "impacts": [{"application": "portail", "operation": "DELETE /comptes/{id}",
                     "change_type": "operation_removed", "severity": "breaking", "evidence": []}],
        "started_at": "2026-10-30T10:00:00+00:00", "ended_at": "2026-10-30T10:01:00+00:00",
        "error": None,
    }


def test_tirer_et_publier_cree_situation_et_notification_sur_impact(monkeypatch):
    run = _run_avec_impact()
    monkeypatch.setattr(
        pulls_runtime, "tirer",
        lambda conn, jumeau, source: {"source": {"nom": source["nom"]}, "run": run,
                                      "changements": [], "impacts": run["impacts"], "graphe": {}})
    db = _Db()

    runs = asyncio.run(pulls_runtime.tirer_et_publier(
        db, None, JUMEAU, [{"nom": "collecteur-comptes", "environment": "prod"}]))

    assert runs == [run]
    situation = db.situations.docs["sit-interfaces-comptes-run-impact"]
    assert situation["priorite"] == "haute" and situation["type"] == "interface"
    assert "portail" in situation["titre"] and "DELETE /comptes/{id}" in situation["titre"]
    notification = db.notifications.docs["notif-interface-comptes-run-impact"]
    assert notification["persona"] == "paiements"
    assert "rupture" in notification["texte"] and "portail" in notification["texte"]


class _Curseur:
    def __init__(self, lignes):
        self.lignes = lignes

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, requete, parametres=None):
        return self

    def fetchall(self):
        return self.lignes


class _Connexion:
    def __init__(self, lignes):
        self.lignes = lignes

    def cursor(self, row_factory=None):
        return _Curseur(self.lignes)


def test_sources_otlp_lit_la_configuration_sans_resoudre_le_secret():
    source = {
        "id": 7, "nom": "collecteur-comptes", "type": "OTLP", "emplacement": URL,
        "url": "https://ancien.exemple.fr/v1/traces", "secret_ref": "env:ANCIEN",
        "configuration": {"url": URL, "secret_ref": SECRET_REF, "environnement": "prod",
                          "frequence": "*/5 * * * *"},
    }

    sources = pulls_runtime.sources_otlp(_Connexion([source]), "comptes")

    assert len(sources) == 1 and sources[0]["url"] == URL
    assert sources[0]["secret_ref"] == SECRET_REF
    assert sources[0]["environment"] == "prod" and sources[0]["frequence"] == "*/5 * * * *"
    assert sources[0]["configuration"]["url"] == URL
    assert SECRET not in json.dumps(sources)


@besoin_pg
def test_aucun_url_ni_secret_dans_le_retour_du_tirage(conn, monkeypatch):
    monkeypatch.setenv("MERIDIAN_OTLP_TOKEN", SECRET)
    monkeypatch.setattr(pulls_runtime.connecteurs_runtime_pull, "depuis_url",
                        lambda *args, **kwargs: _graph())
    source = {"nom": "collecteur-comptes", "url": URL, "secret_ref": SECRET_REF, "environment": "prod"}

    resultat = pulls_runtime.tirer(conn, JUMEAU, source)
    texte = json.dumps(resultat, ensure_ascii=False, default=str)

    assert URL not in texte and SECRET not in texte and SECRET_REF not in texte
    assert "secret_ref" not in json.dumps(resultat["source"])


def test_frequence_et_derniere_pull():
    from datetime import datetime, timedelta, timezone as tz
    from jumeau import pulls_runtime
    maintenant = datetime(2026, 10, 30, 12, 0, tzinfo=tz.utc)
    assert pulls_runtime.due({"configuration": {"frequence": "horaire"}}, maintenant) is True
    assert pulls_runtime.due({"configuration": {"frequence": "horaire",
                                               "derniere_pull": (maintenant - timedelta(minutes=30)).isoformat()}},
                             maintenant) is False
    assert pulls_runtime.due({"configuration": {"frequence": "horaire",
                                               "derniere_pull": (maintenant - timedelta(hours=2)).isoformat()}},
                             maintenant) is True
    assert pulls_runtime.intervalle({"configuration": {"frequence": "quotidienne"}}) == 86400
    assert pulls_runtime.intervalle({"configuration": {"frequence": "inconnue"}}) == 3600
