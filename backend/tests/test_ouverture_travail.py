"""Une actualité qu'on ouvre devient un travail, avec la parole de Flore selon l'intention."""
import os
import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ouverture_travail  # noqa: E402

BASE = os.environ.get("MERIDIAN_API", "http://localhost:8001").rstrip("/") + "/api"
H = {"X-Persona": "architecte"}
HID = "sit-sit-latence-paiements"


@pytest.fixture(scope="module")
def api():
    try:
        requests.get(BASE + "/health", timeout=3)
    except requests.RequestException:
        pytest.skip("backend non lancé")
    return requests.Session()


def _supprimer(api, cid):
    pass  # pas d'endpoint de suppression : le nettoyage se fait en base (voir conftest / scripts)


RAPPORT = {"texte": "Une dérive de latence.\n\nReste à comprendre :\n— la cause.", "preuves": [{"source": "Datadog", "detail": "4 traces"}],
           "propositions": [{"label": "Que reste-t-il ?", "question": "Que reste-t-il à comprendre ?"}, {"label": "Reprendre", "question": None, "lien": "/x"}]}
HISTOIRE = {"titre": "Latence du parcours de paiement", "genre": "incident"}


def test_comprendre_presente_la_situation():
    m = ouverture_travail.message_flore("comprendre", HISTOIRE, RAPPORT, None, "2026-09-21T10:00:00+00:00")
    assert m["role"] == "flore" and m["texte"].startswith("Voici ma lecture de la situation « Latence du parcours de paiement »")
    assert m["preuves"] and [s["label"] for s in m["suggestions"]] == ["Que reste-t-il ?"]  # seules les propositions à question deviennent des suggestions


def test_investiguer_pose_la_question():
    m = ouverture_travail.message_flore("investiguer", HISTOIRE, RAPPORT, {"question": "Pourquoi le paiement ralentit-il ?"}, "2026-09-21T10:00:00+00:00")
    assert "La question : « Pourquoi le paiement ralentit-il ? »" in m["texte"] and len(m["suggestions"]) == 3


def test_suivre_garde_sous_verification():
    m = ouverture_travail.message_flore("suivre", HISTOIRE, RAPPORT, None, "2026-09-21T10:00:00+00:00")
    assert "sous vérification" in m["texte"]


def test_le_type_du_travail_suit_le_genre():
    assert ouverture_travail.type_travail("incident") == "incident" and ouverture_travail.type_travail("relation") == "decouverte"
    assert ouverture_travail.type_travail("inconnu") == "demande"


def test_ouvrir_cree_un_travail_puis_le_rouvre(api):
    a = api.post(f"{BASE}/actualites/histoire/{HID}/travail", headers=H, json={"intention": "comprendre"}).json()
    b = api.post(f"{BASE}/actualites/histoire/{HID}/travail", headers=H, json={"intention": "comprendre"}).json()
    assert a["id"] == b["id"] and b["cree"] is False  # même actualité, même personne : un seul travail
    c = api.get(f"{BASE}/cases/{a['id']}", headers=H).json()
    assert c["origine"]["histoire_id"] == HID and c["conversation"][0]["role"] == "flore" and c["type"] == "incident"
    assert c["situations"] == ["sit-latence-paiements"] and c["responsable"] == "architecte"
    assert any(x["id"] == a["id"] for x in api.get(f"{BASE}/cases", headers=H).json())  # il est dans la liste des travaux


def test_approfondir_ajoute_l_investigation_au_meme_travail(api):
    a = api.post(f"{BASE}/actualites/histoire/{HID}/travail", headers=H, json={"intention": "comprendre"}).json()
    api.post(f"{BASE}/actualites/histoire/{HID}/travail", headers=H, json={"intention": "investiguer"})
    api.post(f"{BASE}/actualites/histoire/{HID}/travail", headers=H, json={"intention": "investiguer"})  # idempotent
    c = api.get(f"{BASE}/cases/{a['id']}", headers=H).json()
    assert [m.get("intention") for m in c["conversation"] if m.get("intention")] == ["comprendre", "investiguer"]
    assert set(c["origine"]["intentions"]) == {"comprendre", "investiguer"}


def test_refus(api):
    assert api.post(f"{BASE}/actualites/histoire/{HID}/travail", headers=H, json={"intention": "x"}).status_code == 400
    assert api.post(f"{BASE}/actualites/histoire/sit-inexistante/travail", headers=H, json={"intention": "comprendre"}).status_code == 404
    assert api.post(f"{BASE}/actualites/histoire/case-case-dette-files/travail", headers=H, json={}).json()["cree"] is False  # un travail existant est repris
