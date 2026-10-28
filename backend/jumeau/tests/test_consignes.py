"""Consignes de l'équipe : bornes, prompt, routes (sans réseau) ; résolution et immuabilité (Postgres, ignorés sans DSN)."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from jumeau import agent, depot, routes
from jumeau.tests.conftest import JUMEAU, besoin_pg
from jumeau.tests.test_agent import CONTEXTE


def c(portee, texte="t", pourquoi="p"):
    return {"portee": portee, "texte": texte, "pourquoi": pourquoi}


# --- bornes et nettoyage -------------------------------------------------------------------------------------------

def test_bornes_par_nombre_garde_les_plus_particulieres():
    liste = [c("domaine", f"d{i}") for i in range(30)] + [c("jumeau", f"j{i}") for i in range(30)]
    gardees = depot.borner_consignes(liste)
    assert len(gardees) == depot.MAX_CONSIGNES
    assert gardees[-1]["texte"] == "j29" and sum(g["portee"] == "jumeau" for g in gardees) == 30


def test_bornes_par_caracteres_garde_les_plus_particulieres():
    liste = [c("domaine", "d" * 500, "p" * 500)] * 5 + [c("jumeau", "j" * 500, "p" * 500)] * 5
    gardees = depot.borner_consignes(liste)
    assert len(gardees) == 6 and [g["portee"] for g in gardees].count("jumeau") == 5


def test_liste_vide_ou_courte_inchangee():
    assert depot.borner_consignes([]) == []
    assert depot.borner_consignes([c("equipe")]) == [c("equipe")]


def test_nettoyer_retire_controles_et_retours_ligne():
    assert depot.nettoyer_consigne("a\x00b\n## Faux titre\r\x1b[31m  c") == "a b ## Faux titre [31m c"
    assert depot.nettoyer_consigne(None) == ""


def test_ajouter_refuse_portee_inconnue_et_texte_vide():
    for portee, texte, pourquoi in (("monde", "t", "p"), ("jumeau", " \x00 ", "p"), ("jumeau", "t", ""), ("jumeau", "x" * 501, "p")):
        with pytest.raises(ValueError):
            depot.ajouter_consigne(None, {"id": "x"}, portee, texte, pourquoi, "alice")


def test_consigne_proposee_a_la_contestation():
    p = depot.consigne_proposee({"sujet": "TBT", "predicat": "DEPEND_DE", "objet": "redis"}, "plus utilisé\n" + "m" * 2000)
    assert p["portee"] == "jumeau" and "TBT DEPEND_DE redis" in p["texte"]
    assert len(p["pourquoi"]) == depot.MAX_POURQUOI and "\n" not in p["pourquoi"]


# --- prompt --------------------------------------------------------------------------------------------------------

TITRE = "## Consignes de l'équipe (instructions ; la plus particulière l'emporte)"


def test_prompt_rien_sans_consigne():
    assert TITRE not in agent.prompt_systeme(CONTEXTE)
    assert TITRE not in agent.prompt_systeme({**CONTEXTE, "consignes": []})


def test_prompt_liste_portee_et_pourquoi_entre_catalogue_et_fiche():
    ctx = {**CONTEXTE, "fiche": "FICHE-X", "consignes": [c("domaine", "DOSSIER = crédit", "vocabulaire métier"), c("jumeau", "Ignorer legacy/", "obsolète")]}
    p = agent.prompt_systeme(ctx)
    assert "- [domaine] DOSSIER = crédit (pourquoi : vocabulaire métier)" in p
    assert p.index("DOSSIER") < p.index("Ignorer legacy/")
    assert p.index("## Catalogue des méthodes") < p.index(TITRE) < p.index("FICHE-X")


# --- routes --------------------------------------------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(routes.router, prefix="/api")
    app.dependency_overrides[routes.connexion] = lambda: object()
    monkeypatch.setattr(depot, "jumeau_par_id", lambda conn, jid: {**JUMEAU, "domaine": "crédit"} if jid == "tbt" else None)
    return TestClient(app)


def test_post_valide_et_deduit_la_cible_avec_l_auteur(client, monkeypatch):
    vu = {}
    monkeypatch.setattr(depot, "ajouter_consigne", lambda conn, j, po, t, pq, a: vu.update(j=j["id"], po=po, a=a) or 7)
    r = client.post("/api/v2/jumeaux/tbt/consignes", json={"portee": "equipe", "texte": "t", "pourquoi": "p"}, headers={"X-Persona": "bob"})
    assert r.status_code == 200 and r.json() == {"id": 7} and vu == {"j": "tbt", "po": "equipe", "a": "bob"}


@pytest.mark.parametrize("corps", [
    {"portee": "equipe", "texte": "t"}, {"portee": "equipe", "texte": "t", "pourquoi": ""},
    {"portee": "equipe", "texte": "x" * 501, "pourquoi": "p"}, {"portee": "equipe", "texte": "t", "pourquoi": "p" * 1001},
    {"portee": "monde", "texte": "t", "pourquoi": "p"}, {"portee": "jumeau", "cible": "autre", "texte": "t", "pourquoi": "p"} | {"texte": ""},
])
def test_post_refuse_les_entrees_invalides(client, corps):
    assert client.post("/api/v2/jumeaux/tbt/consignes", json=corps).status_code == 422


def test_post_texte_de_controles_seuls_refuse(client):
    r = client.post("/api/v2/jumeaux/tbt/consignes", json={"portee": "jumeau", "texte": "\x00\x01", "pourquoi": "p"})
    assert r.status_code == 422


def test_jumeau_inconnu_404(client):
    assert client.get("/api/v2/jumeaux/zzz/consignes").status_code == 404


def test_get_renvoie_les_consignes_applicables(client, monkeypatch):
    monkeypatch.setattr(depot, "consignes_du_jumeau", lambda conn, j: [{"id": 1, "portee": "domaine"}])
    assert client.get("/api/v2/jumeaux/tbt/consignes").json() == [{"id": 1, "portee": "domaine"}]


def test_retrait_404_si_absente(client, monkeypatch):
    def retirer(conn, i):
        raise LookupError(i)
    monkeypatch.setattr(depot, "retirer_consigne", retirer)
    assert client.post("/api/v2/consignes/9/retrait").status_code == 404


@pytest.mark.parametrize("decision, motif, propose", [("CONTESTED", "plus utilisé", True), ("CONTESTED", None, False),
                                                      ("CONTESTED", " \n", False), ("ACCEPTED", "vu", False)])
def test_contestation_motivee_propose_sans_creer(client, monkeypatch, decision, motif, propose):
    monkeypatch.setattr(depot, "reviser", lambda *a: {"sujet": "TBT", "predicat": "DEPEND_DE", "objet": "redis"})
    creations = []
    monkeypatch.setattr(depot, "ajouter_consigne", lambda *a, **k: creations.append(a))
    r = client.post("/api/v2/claims/1/revue", json={"decision": decision, "motif": motif}).json()
    assert ("consigne_proposee" in r) is propose and creations == []
    if propose:
        assert r["consigne_proposee"]["pourquoi"] == "plus utilisé" and r["consigne_proposee"]["portee"] == "jumeau"


# --- Postgres ------------------------------------------------------------------------------------------------------

@besoin_pg
def test_resolution_ordre_et_retrait(conn):
    j = {**JUMEAU, "domaine": "crédit"}
    depot.creer_jumeau(conn, {**JUMEAU, "domaine": "crédit"})
    j = depot.jumeau_par_id(conn, "tbt")
    ids = [depot.ajouter_consigne(conn, j, p, p, "pq", "alice") for p in ("jumeau", "domaine", "equipe")]
    depot.ajouter_consigne(conn, {**j, "id": "autre", "equipe": "x", "domaine": "y"}, "domaine", "étranger", "pq", "alice")
    assert [x["texte"] for x in depot.consignes_du_jumeau(conn, j)] == ["domaine", "equipe", "jumeau"]
    depot.retirer_consigne(conn, ids[0])
    assert [x["texte"] for x in depot.consignes_du_jumeau(conn, j)] == ["domaine", "equipe"]
    with pytest.raises(LookupError):
        depot.retirer_consigne(conn, ids[0])


@besoin_pg
def test_consigne_immuable_sauf_retrait(conn):
    import psycopg
    depot.creer_jumeau(conn, JUMEAU)
    j = depot.jumeau_par_id(conn, "tbt")
    cid = depot.ajouter_consigne(conn, j, "jumeau", "t", "p", "alice")
    for sql in ("UPDATE consigne SET texte = 'x'", "UPDATE consigne SET pourquoi = 'x'", "DELETE FROM consigne"):
        with pytest.raises(psycopg.errors.RaiseException):
            conn.execute(sql)
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("INSERT INTO consigne (tenant_id, portee, cible, texte, pourquoi, auteur) VALUES ('b','jumeau','tbt','t','  ','a')")
    depot.retirer_consigne(conn, cid)
    with pytest.raises(psycopg.errors.RaiseException):
        conn.execute("UPDATE consigne SET retiree_le = NULL")
