"""Routes génériques des connexions « e-mail + jeton » : un jeu de routes, un registre de systèmes."""
import asyncio
import os
import types

import pytest
from fastapi import HTTPException

ENV = {"MONGO_URL": "mongodb://127.0.0.1:1", "DB_NAME": "test_connexions"}  # client paresseux : pas de connexion
avant = {k: os.environ.get(k) for k in ENV}
os.environ.update({k: v for k, v in ENV.items() if avant[k] is None})
try:
    server = pytest.importorskip("server")
finally:
    for k, v in avant.items():
        if v is None:
            os.environ.pop(k, None)


class Collection:
    def __init__(self):
        self.docs = {}

    async def find_one(self, filtre, _projection=None):
        return self.docs.get(filtre["id"])

    async def update_one(self, filtre, maj, upsert=False):
        self.docs[filtre["id"]] = maj["$set"]


class FausseBase(dict):
    def __missing__(self, nom):
        self[nom] = Collection()
        return self[nom]


def systeme_factice(prefixe="zz-"):
    return types.SimpleNamespace(
        PREFIXE=prefixe, SERVICE="Zed", identifiants=lambda e, j: f"{e}:{j}",
        compte_du_jeton=lambda secret: {"login": "Ana@Banque.fr", "compte": "5f1a", "nom": "Ana"},
        perimetres=lambda reference, q: [{"cle": "P", "nom": reference + q}])


@pytest.fixture
def monde(monkeypatch):
    base, deposes = FausseBase(), {}
    monkeypatch.setattr(server, "db", base)
    monkeypatch.setitem(server.SYSTEMES, "zed", systeme_factice())
    monkeypatch.setattr(server.jumeau_naissance, "deposer_jeton", lambda chemin, secret: deposes.setdefault(chemin, "vault:" + chemin))
    return base, deposes


def test_systemes_inscrits_avec_leur_prefixe_et_leur_contrat():
    assert {n: m.PREFIXE for n, m in server.SYSTEMES.items()} == {"confluence": "cf-", "jira": "jr-", "servicenow": "sn-", "datadog": "dd-"}
    assert server.PREFIXES_CONNEXION == {"github": "gh-", "confluence": "cf-", "jira": "jr-", "servicenow": "sn-", "datadog": "dd-"}
    for m in server.SYSTEMES.values():
        assert all(callable(getattr(m, f)) for f in ("identifiants", "compte_du_jeton", "perimetres", "tester", "source_de"))


def test_systeme_inconnu_refuse(monde):
    for appel in (server.lister_connexions("inconnu"),
                  server.declarer_connexion("inconnu", server.JetonAtlassian(email="a@b.fr", jeton="t")),
                  server.perimetres_connexion("inconnu", "x", ""), server.perimetres_connexion("github", "gh-x", "")):
        with pytest.raises(HTTPException) as e:
            asyncio.run(appel)
        assert e.value.status_code == 404


def test_declarer_lister_et_chercher_le_perimetre(monde):
    base, deposes = monde
    doc = asyncio.run(server.declarer_connexion("zed", server.JetonAtlassian(email="ana@banque.fr", jeton="t")))
    assert doc["id"].startswith("zz-ana-banque-fr-") and "reference" not in doc
    assert list(deposes) == [f"connexions/zed/{doc['id']}"]  # une collection et un chemin Vault par système
    assert base["connexions_zed"].docs[doc["id"]]["reference"] == f"vault:connexions/zed/{doc['id']}"
    assert not base["connexions_confluence"].docs
    assert asyncio.run(server.perimetres_connexion("zed", doc["id"], "?")) == [{"cle": "P", "nom": f"vault:connexions/zed/{doc['id']}?"}]
    with pytest.raises(HTTPException) as e:
        asyncio.run(server.perimetres_connexion("zed", "zz-autre", ""))
    assert e.value.status_code == 404


def test_identifiants_mal_formes_refuses_avant_tout_appel(monde, monkeypatch):
    def refuse(email, jeton):
        raise server.jumeau_github.Invalide("adresse e-mail attendue")
    monkeypatch.setitem(server.SYSTEMES, "zed", types.SimpleNamespace(**{**vars(systeme_factice()), "identifiants": refuse}))
    with pytest.raises(HTTPException) as e:
        asyncio.run(server.declarer_connexion("zed", server.JetonAtlassian(email="pasunemail", jeton="t")))
    assert e.value.status_code == 400
