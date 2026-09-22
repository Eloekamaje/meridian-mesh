"""Gestion de projet : ce que les jumeaux savent par Jira (chantiers, trajectoire), droits, Flore, référence d'une décision."""
import os

import pytest
import requests

BASE = os.environ.get("MERIDIAN_API", "http://localhost:8001").rstrip("/") + "/api"
H = {"X-Persona": "architecte"}
HP = {"X-Persona": "paiements"}
TITRE = "Essai Jira (test)"


@pytest.fixture(scope="module")
def api():
    try:
        requests.get(BASE + "/health", timeout=3)
    except requests.RequestException:
        pytest.skip("backend non lancé")
    return requests.Session()


@pytest.fixture(scope="module", autouse=True)
def nettoyage():
    from nettoyage import supprimer_cases
    supprimer_cases({"titre": TITRE})
    yield
    supprimer_cases({"titre": TITRE})


def _jumeau(api, headers, jid):
    return next(j for j in api.get(f"{BASE}/mesh", headers=headers).json()["jumeaux"] if j["id"] == jid)


def test_jira_est_une_source_des_jumeaux_et_leurs_chantiers_sont_connus(api):
    j = _jumeau(api, H, "logistique")
    assert j["sources"]["projet"] is True and "Jira" in [s["nom"] for s in j["sources_detail"]]
    assert j["projets_resume"]["n"] == 2 and j["projets_resume"]["bloques"] >= 1 and j["projets_resume"]["prochaine"] == "2026-09-30"
    ops15 = next(p for p in j["projets"] if p["ref"] == "OPS-15")
    assert ops15["role"] == "porte" and ops15["statut"] == "bloque" and ops15["tickets"]["bloques"] == 3 and ops15["travail"] == "case-dette-files"
    assert set(ops15["impacte"]) == {"paiements", "notifications", "commandes"}


def test_un_jumeau_sans_chantier_n_a_pas_la_source_jira(api):
    j = _jumeau(api, H, "seo-pages")
    assert j["sources"]["projet"] is False and j["projets_resume"]["n"] == 0


def test_un_chantier_livre_ne_compte_pas_comme_vivant(api):
    j = _jumeau(api, H, "api-gateway")
    assert any(p["ref"] == "PLT-9" and p["statut"] == "termine" for p in j["projets"])
    assert j["projets_resume"]["n"] == 1  # DIG-88 seul est vivant


def test_les_droits_s_appliquent_aux_chantiers(api):
    j = _jumeau(api, HP, "paiements")
    rsk = next(p for p in j["projets"] if p["ref"] == "RSK-52")
    assert rsk["porteur"] is None  # Conformité est hors du périmètre de l'équipe Paiements : elle ne le voit pas
    assert all(i in {"paiements", "facturation", "comptes"} for p in j["projets"] for i in p["impacte"])
    noms = [x["id"] for x in api.get(f"{BASE}/mesh", headers=HP).json()["jumeaux"]]
    assert "conformite" not in noms


def test_flore_repond_sur_les_chantiers(api):
    q = lambda h, **kw: api.post(f"{BASE}/aurora/demander", headers=h, json={"contexte": "global", "question": "Quels chantiers Jira sont bloqués ?", "selection": [], **kw}).json()
    r = q(H)
    assert "OPS-15" in r["reponse"] and "Jira" in r["preuves"][0]["source"] and "reste dans Jira" in r["reponse"]
    r = q(H, selection=["logistique"])
    assert "OPS-15" in r["reponse"] and "PAY-122" not in r["reponse"]  # seulement les chantiers de la sélection
    r = q(HP)
    assert "Conformité" not in r["reponse"] and "hors de votre périmètre" in r["reponse"]


def test_la_trajectoire_contredite_par_la_realite_est_une_actualite(api):
    h = next(h for h in api.get(f"{BASE}/actualites", headers=H).json()["histoires"] if h["id"] == "sit-sit-trajectoire-files")
    assert h["genre"] == "trajectoire" and h["section"] == "transformations" and "OPS-15" in h["titre"]
    d = api.get(f"{BASE}/actualites/histoire/sit-sit-trajectoire-files", headers=H).json()
    assert any(p["source"] == "Jira" for p in d["rapport"]["preuves"])


def test_une_decision_garde_la_reference_du_chantier_sans_le_suivre(api):
    cid = api.post(f"{BASE}/cases", headers=H, json={"titre": TITRE, "jumeaux": ["paiements"]}).json()["id"]
    dec = lambda ref: api.post(f"{BASE}/cases/{cid}/decisions", headers=H, json={"texte": "Basculer", "passation": {
        "inconnues": [{"texte": "Effet sur Support"}], "reference": {"systeme": "Jira", "ref": ref}}})
    assert dec("pas une référence").status_code == 400
    assert dec("PAY-140").status_code == 201
    c = api.get(f"{BASE}/cases/{cid}", headers=H).json()
    assert c["veille"]["passation"]["reference"] == {"systeme": "Jira", "ref": "PAY-140", "titre": "Basculer les contrôles Fraude en asynchrone"}
    assert "rattachée au chantier Jira PAY-140" in c["conversation"][-1]["texte"]


def test_le_brouillon_propose_le_chantier_deja_rattache_au_travail(api):
    b = api.get(f"{BASE}/cases/case-dette-files/passation/brouillon", headers=H).json()
    assert b["reference"] == {"systeme": "Jira", "ref": "OPS-15", "titre": "Migrer les files legacy vers Kafka"}
