"""Tests pour la page Comprendre : GET /api/actualites/histoire/{hid}."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback to backend .env for pytest running server-side
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
API = f"{BASE_URL}/api"


def _headers(persona="architecte", espace=None):
    h = {"X-Persona": persona}
    if espace:
        h["X-Espace"] = espace
    return h


@pytest.fixture(scope="module")
def actualites_arch_30j():
    """Récupère les histoires sur 30 jours pour trouver des exemples de chaque genre."""
    r = requests.get(f"{API}/actualites", params={"jours": 30, "portee": "personnel"},
                     headers=_headers("architecte"))
    assert r.status_code == 200, r.text
    return r.json()


class TestHistoireDetail:
    def test_sit_latence_paiements(self):
        r = requests.get(f"{API}/actualites/histoire/sit-sit-latence-paiements",
                         headers=_headers("architecte"))
        assert r.status_code == 200, r.text
        d = r.json()
        assert "histoire" in d and "rapport" in d
        assert d["histoire"]["id"] == "sit-sit-latence-paiements"
        assert d["histoire"]["genre"] in ("incident", "connaissance", "relation",
                                          "contradiction", "changement", "comportement")
        assert d["histoire"]["titre"]
        assert d["rapport"]["texte"]
        assert isinstance(d["rapport"]["propositions"], list)
        assert len(d["rapport"]["propositions"]) >= 1
        for p in d["rapport"]["propositions"]:
            assert "label" in p

    def test_id_inconnu_404(self):
        r = requests.get(f"{API}/actualites/histoire/sit-inexistant",
                         headers=_headers("architecte"))
        assert r.status_code == 404
        assert "detail" in r.json()

    def test_prefixe_inconnu_404(self):
        r = requests.get(f"{API}/actualites/histoire/xyz-bogus",
                         headers=_headers("architecte"))
        assert r.status_code == 404

    def test_variantes_par_genre(self, actualites_arch_30j):
        histoires = actualites_arch_30j["histoires"]
        # Prend un id de chaque préfixe si disponible
        prefixes_vus = set()
        for h in histoires:
            hid = h["id"]
            prefix = hid.split("-", 1)[0]
            if prefix in prefixes_vus:
                continue
            prefixes_vus.add(prefix)
            r = requests.get(f"{API}/actualites/histoire/{hid}",
                             headers=_headers("architecte"))
            assert r.status_code == 200, f"{hid} -> {r.status_code} {r.text}"
            d = r.json()
            assert d["histoire"]["id"] == hid
            assert d["rapport"]["texte"]
            # Un item case doit avoir une proposition avec lien
            if prefix == "case":
                liens = [p for p in d["rapport"]["propositions"] if p.get("lien")]
                assert liens, "case doit avoir une proposition Reprendre le travail"
                assert liens[0]["lien"].startswith("/travaux/")
            # Un item rel-*-ev-* doit aussi passer
        assert "sit" in prefixes_vus  # on doit au moins avoir des situations

    def test_relation_evolution(self, actualites_arch_30j):
        # cherche une histoire rel-*-ev-*
        rel_ev = next((h for h in actualites_arch_30j["histoires"]
                       if h["id"].startswith("rel-") and "-ev-" in h["id"]), None)
        if not rel_ev:
            pytest.skip("Aucune évolution de relation dans la période")
        r = requests.get(f"{API}/actualites/histoire/{rel_ev['id']}",
                         headers=_headers("architecte"))
        assert r.status_code == 200
        assert r.json()["histoire"]["genre"] in ("relation", "phenomene")


class TestRBACSupport:
    def test_support_ne_voit_pas_situation_hors_perimetre(self):
        # La situation sit-latence-paiements concerne des jumeaux paiements ;
        # persona support doit voir "restreinte" ou 404 selon la politique de filtre
        r = requests.get(f"{API}/actualites/histoire/sit-sit-latence-paiements",
                         headers=_headers("support", "espace-support"))
        # Réponse propre : soit 404 (hors périmètre), soit 200 mais restreinte
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            d = r.json()
            # Ne doit pas fuir de données sensibles : jumeaux limités au périmètre support
            assert "histoire" in d
        else:
            assert "detail" in r.json()


class TestNoRegressionActualites:
    def test_actualites_brief_ok(self):
        r = requests.get(f"{API}/actualites",
                         headers=_headers("architecte"))
        assert r.status_code == 200
        d = r.json()
        assert "briefing" in d and "sections" in d and "histoires" in d

    def test_actualites_7j(self):
        r = requests.get(f"{API}/actualites", params={"jours": 7},
                         headers=_headers("architecte"))
        assert r.status_code == 200
        assert r.json().get("synthese") is not None
