"""Veille après décision : moteur pur (attendu contre observé) et routes /api/cases/{id}/veille/*."""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import veille  # noqa: E402

BASE = os.environ.get("MERIDIAN_API", "http://localhost:8001").rstrip("/") + "/api"
MAINTENANT = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)

PASSATION = {
    "attendus": [{"id": "a1", "indicateur": "Délai", "sens": "baisse", "depart": 18, "cible": 4, "unite": "mois"}],
    "risques": [{"id": "r1", "texte": "Charge des opérations", "jumeau": "x", "sens": "hausse", "seuil": 10, "unite": "%"}],
    "inconnues": [{"id": "i1", "texte": "Comportement de B."}],
    "revue_le": "2026-09-19T00:00:00+00:00",
}


def v(observations, **kw):
    return {"statut": "en_veille", "passation": {**PASSATION, **kw}, "observations": observations, "emis": []}


def obs(i, cible, quand="2026-09-10T00:00:00+00:00", **kw):
    return {"id": i, "quand": quand, "cible": cible, "jumeau": "x", "source": "s", **kw}


def types(evs):
    return [e["type"] for e in evs]


# ---- moteur ---------------------------------------------------------------------------------
def test_objectif_atteint_est_un_fait_de_niveau_2():
    evs = veille.evaluer(v([obs("1", "a1", valeur=4)], revue_le="2027-01-01T00:00:00+00:00"), MAINTENANT)
    assert types(evs) == ["conforme"] and evs[0]["niveau"] == 2


def test_ecart_a_contresens_remet_la_decision_en_question():
    evs = veille.evaluer(v([obs("1", "a1", valeur=21)], revue_le="2027-01-01T00:00:00+00:00"), MAINTENANT)
    assert types(evs) == ["ecart"] and evs[0]["niveau"] == 1
    assert "21 mois" in evs[0]["texte"] and "4 mois" in evs[0]["texte"]


def test_progression_partielle_est_mineure():
    evs = veille.evaluer(v([obs("1", "a1", valeur=11)], revue_le="2027-01-01T00:00:00+00:00"), MAINTENANT)
    assert types(evs) == ["progression"] and evs[0]["niveau"] == 3 and "50 %" in evs[0]["texte"]


def test_risque_sous_le_seuil_ne_fait_pas_de_bruit_fort_au_dessus_oui():
    sous = veille.evaluer(v([obs("1", "r1", valeur=4)], revue_le="2027-01-01T00:00:00+00:00"), MAINTENANT)
    assert types(sous) == ["risque_maitrise"] and sous[0]["niveau"] == 3
    over = veille.evaluer(v([obs("1", "r1", valeur=38)], revue_le="2027-01-01T00:00:00+00:00"), MAINTENANT)
    assert types(over) == ["effet_secondaire"] and over[0]["niveau"] == 1


def test_inconnue_levee():
    evs = veille.evaluer(v([obs("1", "i1", conclusion="Rien à signaler.")], revue_le="2027-01-01T00:00:00+00:00"), MAINTENANT)
    assert types(evs) == ["inconnue_levee"] and "Rien à signaler." in evs[0]["texte"]


def test_revue_due_resume_le_bilan():
    evs = veille.evaluer(v([obs("1", "a1", valeur=4), obs("2", "r1", valeur=38, quand="2026-09-11T00:00:00+00:00")]), MAINTENANT)
    revue = evs[-1]
    assert revue["type"] == "revue_due" and revue["niveau"] == 1
    assert "1 objectif(s) atteint(s)" in revue["texte"] and "1 effet(s) secondaire(s)" in revue["texte"]


def test_revue_faite_ne_reparait_pas():
    veille_ = v([])
    veille_["revue_faite_le"] = "2026-09-20T00:00:00+00:00"
    assert veille.evaluer(veille_, MAINTENANT) == []


def test_observation_future_ignoree_et_ids_stables():
    o = [obs("1", "a1", quand="2027-01-01T00:00:00+00:00", valeur=4)]
    assert veille.evaluer(v(o, revue_le="2028-01-01T00:00:00+00:00"), MAINTENANT) == []
    a = veille.evaluer(v([obs("1", "a1", valeur=4)]), MAINTENANT)
    b = veille.evaluer(v([obs("1", "a1", valeur=4)]), MAINTENANT)
    assert [e["id"] for e in a] == [e["id"] for e in b]


def test_pas_de_veille_pas_d_evenement():
    assert veille.evaluer({}, MAINTENANT) == [] and veille.evaluer({"statut": "terminee"}, MAINTENANT) == []


def test_mouvement_depuis_la_derniere_visite():
    evs = veille.evaluer(v([obs("1", "a1", valeur=4, quand="2026-09-10T00:00:00+00:00"), obs("2", "r1", valeur=38, quand="2026-09-17T00:00:00+00:00")]), MAINTENANT)
    m = veille.mouvement(evs, "2026-09-12T00:00:00+00:00")
    assert m["niveau"] == 1 and m["nb"] == 2  # l'effet secondaire (17/09) + la revue (19/09) ; l'objectif atteint (10/09) est déjà lu
    assert veille.mouvement(evs, "2026-09-30T00:00:00+00:00") is None


# ---- routes ---------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def api():
    try:
        requests.get(BASE + "/health", timeout=3)
    except requests.RequestException:
        pytest.skip("backend non lancé")
    return requests.Session()


H = {"X-Persona": "architecte"}


def test_le_travail_en_veille_recoit_des_evenements_dans_son_fil(api):
    c = api.get(f"{BASE}/cases/case-dette-files", headers=H).json()
    evs = [m for m in c["conversation"] if m["role"] == "evenement"]
    assert {e["type"] for e in evs} >= {"conforme", "inconnue_levee", "effet_secondaire"}
    # la revue est une QUESTION de Flore, pas une carte d'événement : message de Flore, à la première personne, avec ses réponses rapides
    revue = [m for m in c["conversation"] if m.get("type") == "revue_due"]
    assert len(revue) == 1 and revue[0]["role"] == "flore" and {r["action"] for r in revue[0]["reponses"]} == {"rouvrir", "maintenir", "clore"}
    assert "Que souhaitez-vous faire" in revue[0]["texte"] and "rouvrir" in revue[0]["texte"]  # une recommandation motivée
    assert [m["quand"] for m in c["conversation"]] == sorted(m["quand"] for m in c["conversation"])  # fil chronologique
    assert c["veille"]["passation"]["revue_le"]


def test_evenements_emis_une_seule_fois(api):
    a = api.get(f"{BASE}/cases/case-dette-files", headers=H).json()
    b = api.get(f"{BASE}/cases/case-dette-files", headers=H).json()
    ids = [m["id"] for m in b["conversation"] if m["role"] == "evenement"]
    assert len(ids) == len(set(ids)) == len([m for m in a["conversation"] if m["role"] == "evenement"])


def test_la_liste_expose_le_mouvement(api):
    liste = {c["id"]: c for c in api.get(f"{BASE}/cases", headers=H).json()}
    c = liste["case-dette-files"]
    assert c["en_veille"] is True and "veille" not in c and "conversation" not in c
    assert "mouvement" in c and c["revue_le"]
    # (le niveau dépend de la dernière visite de la personne : lu = None ; sinon la revue due et l'effet secondaire donnent 1 — voir test_mouvement_*)
    assert c["mouvement"] is None or c["mouvement"]["niveau"] == 1


def test_un_evenement_d_un_jumeau_hors_perimetre_n_apparait_pas(api):
    # l'espace Paiements n'a pas accès à Logistique/Notifications : son fil ne montre pas leurs observations
    r = api.get(f"{BASE}/cases/case-dette-files", headers={"X-Persona": "paiements"})
    if r.status_code != 200:
        pytest.skip("travail hors périmètre de ce persona")
    jum = {m["jumeau"] for m in r.json()["conversation"] if m["role"] == "evenement" and m.get("jumeau")}
    assert "logistique" not in jum and "notifications" not in jum



@pytest.fixture(scope="module", autouse=True)
def _nettoyage_travaux_de_test():
    yield
    from nettoyage import supprimer_cases
    supprimer_cases({"titre": "Essai veille (test)"})


# ---- cycle complet sur un travail temporaire -----------------------------------------------------
def _travail_en_veille(api, revue="2026-09-19T00:00:00+00:00"):
    c = api.post(f"{BASE}/cases", headers=H, json={"titre": "Essai veille (test)", "jumeaux": ["paiements"]}).json()
    api.post(f"{BASE}/cases/{c['id']}/decisions", headers=H, json={"texte": "Basculer en asynchrone", "passation": {
        "hypotheses": ["La bascule réduit la latence."],
        "attendus": [{"id": "a1", "indicateur": "Latence p95", "sens": "baisse", "depart": 1900, "cible": 300, "unite": "ms"}],
        "risques": [{"id": "r1", "texte": "Doublons de paiement", "jumeau": "paiements", "sens": "hausse", "seuil": 0, "unite": "doublons"}],
        "inconnues": [{"id": "i1", "texte": "Effet sur Support"}], "revue_le": revue}})
    return c["id"]


def test_decision_avec_passation_met_le_travail_en_veille(api):
    cid = _travail_en_veille(api, revue="2027-01-01T00:00:00+00:00")
    c = api.get(f"{BASE}/cases/{cid}", headers=H).json()
    assert c["veille"]["statut"] == "en_veille" and c["veille"]["passation"]["attendus"][0]["id"] == "a1"
    # un jumeau observe : l'événement apparaît dans le fil, une seule fois
    api.post(f"{BASE}/cases/{cid}/veille/observations", headers=H, json={"cible": "a1", "jumeau": "paiements", "valeur": 2400, "unite": "ms", "source": "Datadog"})
    for _ in range(2):
        evs = [m for m in api.get(f"{BASE}/cases/{cid}", headers=H).json()["conversation"] if m["role"] == "evenement"]
    assert [e["type"] for e in evs] == ["ecart"] and evs[0]["niveau"] == 1


def test_observation_refusee_hors_note_ou_hors_perimetre(api):
    cid = _travail_en_veille(api, revue="2027-01-01T00:00:00+00:00")
    assert api.post(f"{BASE}/cases/{cid}/veille/observations", headers=H, json={"cible": "inconnue", "jumeau": "paiements", "valeur": 1}).status_code == 400
    assert api.post(f"{BASE}/cases/{cid}/veille/observations", headers=H, json={"cible": "a1", "jumeau": "jumeau-inexistant", "valeur": 1}).status_code == 403


@pytest.mark.parametrize("action,statut_travail,statut_veille", [("rouvrir", "en_cours", "rouverte"), ("clore", "clos", "terminee"), ("maintenir", None, "en_veille")])
def test_reponse_a_la_revue(api, action, statut_travail, statut_veille):
    cid = _travail_en_veille(api)  # revue déjà due
    avant = api.get(f"{BASE}/cases/{cid}", headers=H).json()
    assert any(m.get("type") == "revue_due" for m in avant["conversation"])
    r = api.post(f"{BASE}/cases/{cid}/veille/decision", headers=H, json={"action": action})
    assert r.status_code == 200
    c = r.json()
    assert c["veille"]["statut"] == statut_veille
    if statut_travail:
        assert c["statut"] == statut_travail
    # le choix est le message de la personne, Flore répond, et la question de revue est marquée répondue
    assert c["conversation"][-2]["role"] == "utilisateur" and c["conversation"][-1]["role"] == "flore"
    assert [m for m in c["conversation"] if m.get("type") == "revue_due"][0]["reponse"] == action
    if action == "rouvrir":
        assert "rouverte" in c["conversation"][-1]["texte"]
    if action == "maintenir":
        assert c["veille"]["passation"]["revue_le"] > "2026-09-21"  # nouvelle date de revue
    # une fois traitée, la veille n'écrit plus rien de nouveau pour la revue passée
    assert api.post(f"{BASE}/cases/{cid}/veille/decision", headers=H, json={"action": "inconnue"}).status_code in (400, 409)


def test_lectures_simultanees_n_ecrivent_qu_une_fois_chaque_evenement(api):
    """Page, panneau Flore et menu lisent le même travail en même temps : aucun événement ni question de revue en double."""
    from concurrent.futures import ThreadPoolExecutor

    cid = _travail_en_veille(api)
    api.post(f"{BASE}/cases/{cid}/veille/observations", headers=H, json={"cible": "a1", "jumeau": "paiements", "valeur": 2400, "unite": "ms", "source": "Datadog", "quand": "2026-09-18T10:00:00+00:00"})
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(lambda _: requests.get(f"{BASE}/cases/{cid}", headers=H, timeout=20), range(12)))
    c = api.get(f"{BASE}/cases/{cid}", headers=H).json()
    ids = [m["id"] for m in c["conversation"] if m.get("id") and (m["role"] == "evenement" or m.get("type") == "revue_due")]
    assert len(ids) == len(set(ids)) == 2  # l'écart + la question de revue
    assert len(c["historique"]) == len({(h["quand"], h["texte"]) for h in c["historique"]})


def test_la_decision_entre_dans_la_conversation_avec_ce_qui_sera_observe(api):
    cid = _travail_en_veille(api, revue="2027-01-01T00:00:00+00:00")
    c = api.get(f"{BASE}/cases/{cid}", headers=H).json()
    m = [x for x in c["conversation"] if x.get("type") == "decision"]
    assert len(m) == 1 and m[0]["role"] == "flore"
    assert "Basculer en asynchrone" in m[0]["texte"] and "Latence p95" in m[0]["texte"] and "1 janvier" in m[0]["texte"]
    assert "Doublons de paiement" in m[0]["texte"] and "Effet sur Support" in m[0]["texte"]  # risque et inconnue nommés


def test_le_travail_de_demonstration_raconte_la_decision_avant_les_faits(api):
    fil = api.get(f"{BASE}/cases/case-dette-files", headers=H).json()["conversation"]
    genres = [m.get("type") or m["role"] for m in fil]
    assert genres.index("decision") < min(i for i, g in enumerate(genres) if g in ("conforme", "inconnue_levee", "effet_secondaire"))
