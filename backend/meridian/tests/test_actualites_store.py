"""Le fil Aujourd'hui lit les travaux via TravailStore, pas directement dans db.cases."""
from meridian.tests.aides_actualites import StoreFaux, cas, client_actualites


def test_la_route_actualites_lit_les_travaux_via_le_store(monkeypatch):
    travail = cas("demo-store", "Travail servi par le store")
    store = StoreFaux([travail])
    client = client_actualites(monkeypatch, store=store)

    reponse = client.get("/api/actualites")
    assert reponse.status_code == 200, reponse.text
    histoires = {h["id"]: h for h in reponse.json()["histoires"]}
    assert "case-demo-store" in histoires
    assert histoires["case-demo-store"]["titre"] == "Travail servi par le store"
    assert store.appels == [("lister_recents", None)]


def test_le_detail_d_un_travail_lit_le_store(monkeypatch):
    travail = cas("demo-store", "Travail servi par le store")
    store = StoreFaux([travail])
    client = client_actualites(monkeypatch, store=store)

    reponse = client.get("/api/actualites/histoire/case-demo-store")
    assert reponse.status_code == 200, reponse.text
    assert reponse.json()["histoire"]["titre"] == "Travail servi par le store"
    assert ("lire", "demo-store") in store.appels
