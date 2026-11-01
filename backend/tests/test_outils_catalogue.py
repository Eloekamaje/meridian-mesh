"""Catalogue read-only /api/outils et audit persistant d'un tour d'orchestrateur, sans base réelle."""
import asyncio
import json
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def serveur():
    os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
    os.environ.setdefault("DB_NAME", "meridian_tests")
    import server
    return server


def _client(serveur):
    app = FastAPI()
    app.include_router(serveur.api_router)
    return TestClient(app)


def _manifeste(nom, tenant="banque", acteur="demo", perimetre="mesh-global", **autres):
    return {
        "nom": nom,
        "version": "1.0.0",
        "description": "Lit les traces d'observabilité d'une application",
        "capacite": "observer",
        "schema_entree": {
            "type": "object",
            "properties": {"application": {"type": "string"}},
            "required": ["application"],
            "additionalProperties": False,
        },
        "schema_sortie": {
            "type": "object",
            "properties": {"traces": {"type": "array", "items": {"type": "object"}}},
            "required": ["traces"],
            "additionalProperties": False,
        },
        "tenant": tenant,
        "acteur": acteur,
        "perimetre": perimetre,
        "lecture_seule": True,
        "timeout_ms": 2000,
        "mode_preuve": "OBSERVED",
        "source": "manifeste",
        **autres,
    }


def test_le_catalogue_expose_les_manifestes_integres_sans_dsn(serveur, monkeypatch):
    monkeypatch.delenv("JUMEAU_PG_DSN", raising=False)
    monkeypatch.delenv("JUMEAU_MANIFESTES", raising=False)
    monkeypatch.delenv("JUMEAU_TENANT", raising=False)

    reponse = _client(serveur).get("/api/outils", headers={"X-Tenant": "banque"})

    assert reponse.status_code == 200
    donnees = reponse.json()
    assert donnees["tenant"] == "banque"
    noms = {outil["nom"] for outil in donnees["outils"]}
    assert {"resoudre_application", "mobiliser_jumeaux", "concevoir_architecture"} <= noms
    assert all(outil["lecture_seule"] is True for outil in donnees["outils"])
    texte = reponse.text.lower()
    assert "sk-" not in texte and "bearer " not in texte and "password=" not in texte


def test_le_catalogue_charge_jumeau_manifestes_et_filtre_la_portee(serveur, monkeypatch, tmp_path):
    fichier = tmp_path / "outils.json"
    fichier.write_text(json.dumps([
        _manifeste("lire_traces"),
        _manifeste("lire_traces_autre", tenant="autre"),
    ]), encoding="utf-8")
    monkeypatch.setenv("JUMEAU_MANIFESTES", str(fichier))
    client = _client(serveur)

    local = client.get("/api/outils", headers={"X-Tenant": "local"}).json()
    assert all(outil["nom"] != "lire_traces" for outil in local["outils"])

    banque = client.get("/api/outils", headers={
        "X-Tenant": "banque", "X-Espace": "mesh-global"}).json()
    noms = {outil["nom"] for outil in banque["outils"]}
    assert "lire_traces" in noms
    assert "lire_traces_autre" not in noms
    assert {"resoudre_application", "mobiliser_jumeaux", "concevoir_architecture"} <= noms

    par_query = client.get("/api/outils", params={
        "tenant": "banque", "perimetre": "mesh-global"}).json()
    assert "lire_traces" in {outil["nom"] for outil in par_query["outils"]}


def test_le_catalogue_expurge_un_jeton_dans_un_manifeste_valide(serveur, monkeypatch, tmp_path):
    fichier = tmp_path / "jeton.json"
    manifeste = _manifeste("lire_traces_jeton")
    manifeste["description"] = "Lit les traces sk-secret-123456 sans les exposer"
    manifeste["signature"] = "sk-secret-123456"
    fichier.write_text(json.dumps(manifeste), encoding="utf-8")
    monkeypatch.setenv("JUMEAU_MANIFESTES", str(fichier))

    reponse = _client(serveur).get("/api/outils", headers={"X-Tenant": "banque"})

    assert reponse.status_code == 200
    assert "lire_traces_jeton" in {outil["nom"] for outil in reponse.json()["outils"]}
    assert "sk-secret-123456" not in reponse.text


def test_un_manifeste_externe_porteur_de_secret_est_ignore(serveur, monkeypatch, tmp_path):
    fichier = tmp_path / "fuite.json"
    fichier.write_text(json.dumps({
        "nom": "fuite",
        "version": "1.0.0",
        "description": "password=hunter2",
        "capacite": "observer",
        "schema_entree": {"type": "object"},
        "schema_sortie": {"type": "object"},
        "lecture_seule": True,
        "api_key": "sk-secret-123456",
    }), encoding="utf-8")
    monkeypatch.setenv("JUMEAU_MANIFESTES", str(fichier))

    reponse = _client(serveur).get("/api/outils")

    assert reponse.status_code == 200
    assert "fuite" not in {outil["nom"] for outil in reponse.json()["outils"]}
    assert "sk-secret-123456" not in reponse.text
    assert "hunter2" not in reponse.text


def test_le_catalogue_n_execute_aucun_outil(serveur, monkeypatch):
    async def interdit(*_arguments, **_options):
        raise AssertionError("aucune exécution attendue")

    monkeypatch.setattr(serveur.jumeau_orchestrateur, "executer", interdit)
    monkeypatch.setattr(serveur.jumeau_harness.Harness, "appeler", interdit)

    reponse = _client(serveur).get("/api/outils")

    assert reponse.status_code == 200


class _JumeauxVides:
    def find(self, *_arguments, **_options):
        return self

    async def to_list(self, _limite):
        return []


class _DbVide:
    jumeaux = _JumeauxVides()


def _preparer_tour(serveur, monkeypatch, audit, tenant="banque"):
    async def faux_executer(*_arguments, **_options):
        return {
            "comportement": "expliquer",
            "reponse": "Réponse de l'orchestrateur.",
            "preuves": [],
            "orchestration": {"outils": [{"outil": "resoudre_application"}], "audit": audit, "erreurs": []},
        }

    async def autoriser(*_arguments, **_options):
        return True

    monkeypatch.setattr(serveur.jumeau_orchestrateur, "executer", faux_executer)
    monkeypatch.setattr(serveur, "db", _DbVide())
    monkeypatch.setattr(serveur.limites, "autoriser", autoriser)
    monkeypatch.setattr(serveur, "autorisations", lambda *_: {})
    monkeypatch.setattr(serveur, "resoudre_perimetre",
                        lambda *_: ({"id": "architecte"}, {"id": "mesh-global"}))
    return asyncio.run(serveur.generer_reponse_flore(
        "global", "Que fait Alpha ?", [], None, "architecte", None, tenant=tenant))


def test_un_tour_d_orchestrateur_transmet_son_audit_au_serveur(serveur, monkeypatch):
    audit = [{"nom": "resoudre_application", "capacite": "situer",
              "arguments": {"terme": "alpha"}, "duree_ms": 1.0, "statut": "ok"}]
    vus = []
    monkeypatch.setenv("JUMEAU_PG_DSN", "postgresql://test/test")
    monkeypatch.setattr(serveur, "enregistrer_lignes",
                        lambda *arguments: vus.append(arguments) or {"ecrits": 1, "erreurs": 0})

    class FauxThread:
        def __init__(self, target, args=(), kwargs=None, **_options):
            self.target, self.args, self.kwargs = target, args, kwargs or {}

        def start(self):
            self.target(*self.args, **self.kwargs)

    monkeypatch.setattr(serveur.threading, "Thread", FauxThread)

    reponse = _preparer_tour(serveur, monkeypatch, audit)

    assert reponse["reponse"] == "Réponse de l'orchestrateur."
    assert vus == [("postgresql://test/test", "banque", "architecte", audit)]


def test_un_audit_en_echec_ne_casse_pas_le_tour(serveur, monkeypatch):
    monkeypatch.setenv("JUMEAU_PG_DSN", "postgresql://test/test")

    def casse(*_arguments):
        raise RuntimeError("base indisponible")

    monkeypatch.setattr(serveur, "enregistrer_lignes", casse)

    class FauxThread:
        def __init__(self, target, **_options):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(serveur.threading, "Thread", FauxThread)

    reponse = _preparer_tour(serveur, monkeypatch, [{"nom": "resoudre_application", "statut": "ok"}])

    assert reponse["reponse"] == "Réponse de l'orchestrateur."
    assert reponse["orchestration"]["audit"][0]["nom"] == "resoudre_application"


def test_sans_dsn_l_audit_n_est_pas_tente(serveur, monkeypatch):
    monkeypatch.delenv("JUMEAU_PG_DSN", raising=False)
    vus = []
    monkeypatch.setattr(serveur, "enregistrer_lignes", lambda *arguments: vus.append(arguments))

    reponse = _preparer_tour(serveur, monkeypatch, [{"nom": "resoudre_application", "statut": "ok"}])

    assert reponse["reponse"] == "Réponse de l'orchestrateur."
    assert vus == []
