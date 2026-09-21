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


MES_HISTOIRES = ["sit-sit-latence-paiements", "sit-sit-changement-settlement"]
MES_INITIATIVES = ["init-info-contrat-comptes", "init-contrat-paiements"]


@pytest.fixture(scope="module", autouse=True)
def _nettoyage_travaux_de_test():
    """Pas d'endpoint de suppression : les travaux ouverts par ces tests sont retirés de la base (avant et après le module) ;
    les propositions auxquelles ils répondent sont remises en attente. Seuls SES identifiants sont touchés : d'autres modules tournent en parallèle."""
    from nettoyage import remettre_initiatives, supprimer_cases
    filtre = {"$or": [{"origine.histoire_id": {"$in": MES_HISTOIRES}}, {"origine.initiative_id": {"$in": MES_INITIATIVES}}]}
    supprimer_cases(filtre)
    remettre_initiatives(MES_INITIATIVES)
    yield
    supprimer_cases(filtre)
    remettre_initiatives(MES_INITIATIVES)


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


# ---- propositions du Mesh (Radar, À traiter) et décisions attendues ------------------------------
INIT = "init-info-contrat-comptes"


def test_une_proposition_du_mesh_devient_un_travail_sans_changer_son_etat(api):
    a = api.post(f"{BASE}/initiatives/{INIT}/travail", headers=H, json={"intention": "comprendre"}).json()
    b = api.post(f"{BASE}/initiatives/{INIT}/travail", headers=H, json={"intention": "comprendre"}).json()
    assert a["id"] == b["id"] and b["cree"] is False
    c = api.get(f"{BASE}/cases/{a['id']}", headers=H).json()
    assert c["conversation"][0]["texte"].startswith("Voici ce que Méridian a découvert") and c["origine"]["initiative_id"] == INIT
    init = next(i for i in api.get(f"{BASE}/initiatives?vue=toutes", headers=H).json() if i["id"] == INIT)
    assert init["statut"] == "en_attente"  # comprendre ne répond pas à la proposition


def test_suivre_une_proposition_cree_un_travail_en_surveillance(api):
    r = api.post(f"{BASE}/initiatives/init-contrat-paiements/repondre", headers=H, json={"choix": "Suivre"})
    if r.status_code == 409:
        pytest.skip("proposition déjà traitée par un essai précédent")
    assert r.status_code == 200 and r.json()["travail_id"]
    c = api.get(f"{BASE}/cases/{r.json()['travail_id']}", headers=H).json()
    assert "sous surveillance" in c["conversation"][0]["texte"]


def test_les_decisions_attendues_accompagnent_la_situation_et_s_appliquent_dans_le_fil(api):
    hid = "sit-sit-changement-settlement"
    cid = api.post(f"{BASE}/actualites/histoire/{hid}/travail", headers=H, json={"intention": "investiguer"}).json()["id"]
    c = api.get(f"{BASE}/cases/{cid}", headers=H).json()
    m = c["conversation"][0]
    assert m["decisions"] and all(isinstance(d, str) for d in m["decisions"])
    assert api.post(f"{BASE}/cases/{cid}/decision-attendue", headers=H, json={"texte": "Décision inventée"}).status_code == 400
    r = api.post(f"{BASE}/cases/{cid}/decision-attendue", headers=H, json={"texte": m["decisions"][0]})
    assert r.status_code == 200
    c2 = r.json()
    assert c2["conversation"][-2]["role"] == "utilisateur" and c2["conversation"][-2]["texte"] == m["decisions"][0]
    assert c2["conversation"][-1]["role"] == "flore" and c2["conversation"][0]["reponse"] == m["decisions"][0]
