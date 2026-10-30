"""API de lecture de la boucle canonique : DSN, filtres, tenant, sérialisation et secrets.

La base Postgres est remplacée par une connexion factice : ces tests ne dépendent ni d'un serveur lancé ni d'un
``JUMEAU_PG_DSN`` réel.
"""
from datetime import date, datetime, timezone
import json

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

import boucle_routes


def _objet(identifiant, tenant="local", famille="emergence", type_="SITUATION", mode="OBSERVED",
           titre="", **donnees):
    return {
        "id": identifiant,
        "tenant_id": tenant,
        "famille": famille,
        "type": type_,
        "mode": mode,
        "titre": titre or identifiant,
        "donnees": donnees,
        "version": 1,
        "observe_le": datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc),
        "valide_depuis": datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc),
        "valide_jusqua": None,
        "cree_le": datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc),
        "maj_le": datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc),
    }


class _Curseur:
    def __init__(self, conn):
        self.conn = conn
        self.lignes = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=()):
        self.conn.requetes.append((" ".join(sql.split()), tuple(params)))
        self.lignes = self.conn.repondre(" ".join(sql.split()), tuple(params))
        return self

    def fetchall(self):
        return list(self.lignes)

    def fetchone(self):
        return self.lignes[0] if self.lignes else None


class _Connexion:
    def __init__(self, objets):
        self.objets = [dict(objet) for objet in objets]
        self.requetes = []
        self.ferme = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.ferme = True
        return False

    def cursor(self, row_factory=None):
        return _Curseur(self)

    def repondre(self, sql, params):
        if "GROUP BY famille, type, mode" in sql:
            tenant = params[0]
            comptes = {}
            for objet in self.objets:
                if objet["tenant_id"] != tenant:
                    continue
                cle = (objet["famille"], objet["type"], objet["mode"])
                comptes[cle] = comptes.get(cle, 0) + 1
            return [
                {"famille": famille, "type": type_, "mode": mode, "nombre": nombre}
                for (famille, type_, mode), nombre in sorted(comptes.items())
            ]
        if "WHERE tenant_id = %s AND id = %s" in sql:
            tenant, identifiant = params
            return [objet for objet in self.objets
                    if objet["tenant_id"] == tenant and objet["id"] == identifiant][:1]
        if "FROM objet_entreprise WHERE" in sql:
            tenant = params[0]
            lignes = [objet for objet in self.objets if objet["tenant_id"] == tenant]
            rang = 1
            for colonne in ("famille", "type", "mode"):
                if f"{colonne} = %s" in sql:
                    valeur = params[rang]
                    rang += 1
                    lignes = [objet for objet in lignes if objet[colonne] == valeur]
            lignes.sort(key=lambda objet: (objet["famille"], objet["type"], objet["id"]))
            return lignes[:params[-1]]
        return []


def _app():
    app = FastAPI()
    api = APIRouter(prefix="/api")
    api.include_router(boucle_routes.router)
    app.include_router(api)
    return TestClient(app)


def _client(monkeypatch, objets):
    connexion = _Connexion(objets)
    monkeypatch.setenv("JUMEAU_PG_DSN", "postgresql://test/test")
    monkeypatch.setattr(boucle_routes.psycopg, "connect", lambda *_, **__: connexion)
    return _app(), connexion


@pytest.mark.parametrize("chemin", ["/api/boucle/objets", "/api/boucle/objets/sit-1", "/api/boucle/synthese"])
def test_sans_dsn_les_routes_repondent_503(monkeypatch, chemin):
    monkeypatch.delenv("JUMEAU_PG_DSN", raising=False)
    reponse = _app().get(chemin)
    assert reponse.status_code == 503
    assert "JUMEAU_PG_DSN" in reponse.json()["detail"]


@pytest.mark.parametrize("params", [
    {"famille": "famille_inconnue"},
    {"mode": "MAGIQUE"},
    {"type": "TYPE_INCONNU"},
])
def test_un_filtre_invalide_repond_400_avant_le_dsn(monkeypatch, params):
    monkeypatch.delenv("JUMEAU_PG_DSN", raising=False)
    reponse = _app().get("/api/boucle/objets", params=params)
    assert reponse.status_code == 400


def test_un_tenant_vide_est_refuse(monkeypatch):
    monkeypatch.delenv("JUMEAU_PG_DSN", raising=False)
    reponse = _app().get("/api/boucle/objets", headers={"X-Tenant": "   "})
    assert reponse.status_code == 400


def test_la_liste_est_filtree_par_le_tenant_par_defaut_et_l_entete(monkeypatch):
    objets = [
        _objet("sit-local", tenant="local"),
        _objet("sit-banque", tenant="banque"),
        _objet("dec-local", tenant="local", famille="decision", type_="DECISION", mode="DECLARED"),
    ]
    client, connexion = _client(monkeypatch, objets)

    reponse = client.get("/api/boucle/objets")
    assert reponse.status_code == 200
    assert reponse.json()["tenant"] == "local"
    assert {objet["id"] for objet in reponse.json()["objets"]} == {"sit-local", "dec-local"}
    assert connexion.requetes[-1][1][0] == "local"
    assert connexion.ferme is True

    reponse = client.get("/api/boucle/objets", headers={"X-Tenant": "banque"})
    assert reponse.status_code == 200
    assert reponse.json()["tenant"] == "banque"
    assert [objet["id"] for objet in reponse.json()["objets"]] == ["sit-banque"]
    assert connexion.requetes[-1][1][0] == "banque"


def test_les_filtres_et_la_limite_sont_appliques(monkeypatch):
    objets = [
        _objet("sit-1", famille="emergence", type_="SITUATION", mode="OBSERVED"),
        _objet("sit-2", famille="emergence", type_="SITUATION", mode="OBSERVED"),
        _objet("dec-1", famille="decision", type_="DECISION", mode="DECLARED"),
    ]
    client, _ = _client(monkeypatch, objets)

    reponse = client.get("/api/boucle/objets", params={
        "famille": "ÉMERGENCE", "type": "situation", "mode": "observed", "limite": 1})
    assert reponse.status_code == 200
    assert [objet["id"] for objet in reponse.json()["objets"]] == ["sit-1"]


def test_la_reponse_est_json_serialisable_et_sans_secret(monkeypatch):
    objet = _objet(
        "sit-secret",
        titre="Situation avec secret",
        password="hunter2",
        token="Bearer abcdefghijklmnop",
        url="https://alice:s3cr3t@api.example.test",
        secret_ref="vault/banque/situation",
        quand=date(2026, 10, 2),
    )
    client, _ = _client(monkeypatch, [objet])

    reponse = client.get("/api/boucle/objets")
    assert reponse.status_code == 200
    texte = json.dumps(reponse.json())
    assert "hunter2" not in texte
    assert "s3cr3t" not in texte
    assert "abcdefghijklmnop" not in texte
    assert reponse.json()["objets"][0]["donnees"]["secret_ref"] == "vault/banque/situation"


def test_un_objet_hors_tenant_est_404_et_l_historique_ajoute_la_chaine(monkeypatch):
    situation = _objet("sit-1", tenant="banque")
    investigation = _objet("inv-1", tenant="banque", famille="investigation", type_="INVESTIGATION",
                           mode="DECLARED", situation_id="sit-1")
    decision = _objet("dec-1", tenant="banque", famille="decision", type_="DECISION", mode="DECLARED",
                      investigation_id="inv-1", _historique=[{"version": 1, "titre": "Décision v1"}])
    client, _ = _client(monkeypatch, [situation, investigation, decision])

    assert client.get("/api/boucle/objets/dec-1").status_code == 404

    reponse = client.get("/api/boucle/objets/dec-1", headers={"X-Tenant": "banque"})
    assert reponse.status_code == 200
    assert reponse.json()["objet"]["id"] == "dec-1"
    assert "_historique" not in reponse.json()["objet"]["donnees"]
    assert "chaine" not in reponse.json() and "historique" not in reponse.json()

    reponse = client.get("/api/boucle/objets/dec-1", params={"historique": "true"},
                         headers={"X-Tenant": "banque"})
    assert reponse.status_code == 200
    assert [objet["type"] for objet in reponse.json()["chaine"]] == [
        "SITUATION", "INVESTIGATION", "DECISION"]
    assert reponse.json()["historique"] == [{"version": 1, "titre": "Décision v1"}]
    json.dumps(reponse.json())


def test_la_synthese_compte_par_famille_type_et_mode_sans_contenu(monkeypatch):
    objets = [
        _objet("sit-1", tenant="local", password="hunter2"),
        _objet("sit-2", tenant="local"),
        _objet("dec-1", tenant="local", famille="decision", type_="DECISION", mode="DECLARED"),
        _objet("sit-banque", tenant="banque"),
    ]
    client, _ = _client(monkeypatch, objets)

    reponse = client.get("/api/boucle/synthese")
    assert reponse.status_code == 200
    resultat = reponse.json()
    assert resultat["tenant"] == "local" and resultat["total"] == 3
    assert resultat["familles"] == {"decision": 1, "emergence": 2}
    assert resultat["types"] == {"DECISION": 1, "SITUATION": 2}
    assert resultat["modes"] == {"DECLARED": 1, "OBSERVED": 2}
    assert "hunter2" not in json.dumps(resultat)
