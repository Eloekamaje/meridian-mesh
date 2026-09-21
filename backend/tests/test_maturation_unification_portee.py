"""Veille avant la décision (maturation), réponses aux propositions et délégations dans le travail, portée d'un travail."""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import maturation  # noqa: E402
import ouverture_travail  # noqa: E402
from nettoyage import remettre_initiatives, supprimer_cases, supprimer_delegations, supprimer_ecarts  # noqa: E402

BASE = os.environ.get("MERIDIAN_API", "http://localhost:8001").rstrip("/") + "/api"
H = {"X-Persona": "architecte"}
HP = {"X-Persona": "paiements"}
TITRE = "Essai portée (test)"


@pytest.fixture(scope="module")
def api():
    try:
        requests.get(BASE + "/health", timeout=3)
    except requests.RequestException:
        pytest.skip("backend non lancé")
    return requests.Session()


MES_HISTOIRES = ["rel-r12", "sit-sit-optimisation-facturation"]
DELEGATIONS_CREEES: list = []


@pytest.fixture(scope="module", autouse=True)
def nettoyage():
    """Travaux, délégations, écarts et propositions touchés par ces tests : remis à zéro avant et après (seuls SES identifiants : d'autres modules tournent en parallèle)."""
    def faire():
        supprimer_cases({"$or": [{"titre": TITRE}, {"origine.histoire_id": {"$in": MES_HISTOIRES}}, {"origine.initiative_id": "init-delai-j3"},
                                 {"origine.delegation_id": {"$in": DELEGATIONS_CREEES}}]})
        supprimer_delegations({"id": {"$in": DELEGATIONS_CREEES}})
        supprimer_ecarts({"histoire_id": "sit-sit-latence-paiements", "persona": "paiements"})
        remettre_initiatives(["init-delai-j3"])
    faire()
    yield
    faire()


# ---- le moteur de maturation (pur) -------------------------------------------------------------------
def _mat(*effets, depart=64, seuil=75, plancher=40):
    base = datetime(2026, 9, 1, tzinfo=timezone.utc)
    return {"sujet": "S", "confiance_depart": depart, "seuil": seuil, "plancher": plancher,
            "observations": [{"id": f"o{i}", "quand": (base + timedelta(days=i)).isoformat(), "jumeau": "x", "effet": e, "texte": "t"} for i, e in enumerate(effets)]}


MAINTENANT = datetime(2026, 9, 30, tzinfo=timezone.utc)


def test_le_seuil_de_confirmation_n_est_signale_qu_une_fois():
    ev = maturation.evaluer(_mat(5, 8, 3, -2, 4), MAINTENANT)
    types = [e["type"] for e in ev]
    assert types.count("seuil_atteint") == 1 and types.count("preuve_pour") == 4 and types.count("preuve_contre") == 1
    seuil = next(e for e in ev if e["type"] == "seuil_atteint")
    assert seuil["niveau"] == 1 and seuil["confiance"] == 77 and seuil["id"] == "seuil-o1"  # 64 + 5 + 8 = 77, franchi à la 2e observation


def test_un_phenomene_contredit_est_propose_a_l_ecart():
    ev = maturation.evaluer(_mat(-10, -15, -5), MAINTENANT)
    assert [e["type"] for e in ev].count("affaiblie") == 1 and next(e for e in ev if e["type"] == "affaiblie")["confiance"] == 39


def test_les_indices_intermediaires_ne_derangent_pas():
    ev = maturation.evaluer(_mat(3, -2, 2), MAINTENANT)
    assert {e["niveau"] for e in ev} == {3}  # entre les deux seuils : rien qui demande une décision


def test_les_observations_futures_sont_ignorees_et_la_confiance_bornee():
    m = _mat(5, 8)
    assert maturation.evaluer(m, datetime(2026, 8, 1, tzinfo=timezone.utc)) == []
    assert maturation.confiance_a(m, datetime(2026, 9, 1, 12, tzinfo=timezone.utc)) == 69
    assert maturation.confiance_a(_mat(60), MAINTENANT) == 100


def test_seuils_par_defaut_et_confiance_depuis_un_libelle():
    assert maturation.bornes(50) == (75, 25) and maturation.bornes(80) == (90, 55)
    assert [maturation.confiance_depuis_libelle(x) for x in ("Élevée · 18 observations", "Modérée", "Faible", "?")] == [75, 55, 35, 50]


# ---- suivre = vérifier : une veille avant la décision ---------------------------------------------------
def _suivre(api, hid="rel-r12"):
    return api.post(f"{BASE}/actualites/histoire/{hid}/travail", headers=H, json={"intention": "suivre"}).json()["id"]


def test_suivre_ouvre_une_verification_et_flore_dit_ce_qu_elle_guette(api):
    cid = _suivre(api)
    c = api.get(f"{BASE}/cases/{cid}", headers=H).json()
    v = c["veille"]
    assert v["mode"] == "maturation" and v["statut"] == "en_veille" and v["maturation"]["confiance_depart"] == 64 and v["maturation"]["relation_id"] == "r12"
    assert c["portee"] == "personnel"
    dernier = c["conversation"][-1]
    assert dernier["type"] == "suivi" and "au-dessus de 75 %" in dernier["texte"] and "sous 39 %" in dernier["texte"]


def test_les_indices_s_ajoutent_puis_flore_pose_la_question(api):
    cid = _suivre(api)
    obs = lambda **kw: api.post(f"{BASE}/cases/{cid}/veille/observations", headers=H, json={"jumeau": "conformite", "source": "Splunk", **kw})
    assert obs(texte="x").status_code == 400  # un effet est obligatoire
    assert obs(effet=90, texte="x").status_code == 400
    assert obs(effet=3).status_code == 400  # dire ce qui a été observé
    assert obs(effet=4, texte="Un dossier de plus").status_code == 201
    c = api.get(f"{BASE}/cases/{cid}", headers=H).json()
    assert [m.get("type") for m in c["conversation"][-1:]] == ["preuve_pour"] and not any(m.get("reponses") for m in c["conversation"])  # 68 % : rien à décider
    assert c["veille"]["confiance"] == 68
    obs(effet=9, texte="Quatorze appels sur quatorze")
    c = api.get(f"{BASE}/cases/{cid}", headers=H).json()
    q = c["conversation"][-1]
    assert q["type"] == "seuil_atteint" and [r["action"] for r in q["reponses"]] == ["confirmer", "continuer", "ecarter"] and "Je vous suggère de la confirmer" in q["texte"]
    liste = next(x for x in api.get(f"{BASE}/cases", headers=H).json() if x["id"] == cid)
    assert liste["en_veille"] and liste["veille_mode"] == "maturation" and liste["mouvement"]["niveau"] == 1
    # un seul lecteur écrit le message : relire n'en ajoute pas
    assert len([m for m in api.get(f"{BASE}/cases/{cid}", headers=H).json()["conversation"] if m.get("type") == "seuil_atteint"]) == 1
    # continuer d'observer : la question reçoit sa réponse, la veille continue
    r = api.post(f"{BASE}/cases/{cid}/veille/decision", headers=H, json={"action": "continuer"}).json()
    assert r["veille"]["statut"] == "en_veille" and r["conversation"][-2]["texte"] == "Continuer d'observer" and next(m for m in r["conversation"] if m.get("type") == "seuil_atteint")["reponse"] == "continuer"
    # écarter : la vérification se termine, la trace est gardée
    r = api.post(f"{BASE}/cases/{cid}/veille/decision", headers=H, json={"action": "ecarter"}).json()
    assert r["veille"]["statut"] == "terminee" and r["statut"] == "clos" and r["decisions"][-1]["texte"].startswith("Écarter")
    assert api.post(f"{BASE}/cases/{cid}/veille/decision", headers=H, json={"action": "ecarter"}).status_code == 409


def test_confirmer_sans_relation_garde_la_verite_dans_le_travail(api):
    cid = _suivre(api, "sit-sit-optimisation-facturation")
    api.post(f"{BASE}/cases/{cid}/veille/observations", headers=H, json={"jumeau": "paiements", "effet": 30, "texte": "Preuve nette", "source": "Datadog"})
    c = api.get(f"{BASE}/cases/{cid}", headers=H).json()
    assert c["conversation"][-1]["type"] == "seuil_atteint"
    r = api.post(f"{BASE}/cases/{cid}/veille/decision", headers=H, json={"action": "confirmer"}).json()
    assert r["veille"]["statut"] == "terminee" and r["decisions"][-1]["texte"].startswith("Confirmer")
    assert api.post(f"{BASE}/cases/{cid}/veille/decision", headers=H, json={"action": "n'importe quoi"}).status_code in (400, 409)


def test_la_verification_de_demonstration_est_en_place(api):
    c = api.get(f"{BASE}/cases/case-verification-fraude-conformite", headers=H).json()
    assert c["veille"]["confiance"] == 75 and [m.get("type") for m in c["conversation"] if m.get("role") != "flore" or m.get("type")][-1] == "seuil_atteint"


def test_une_verification_est_une_actualite_a_trancher(api):
    h = next(h for h in api.get(f"{BASE}/actualites", headers=H).json()["histoires"] if h["id"] == "case-case-verification-fraude-conformite")
    assert h["genre"] == "verification" and h["action_label"] == "Trancher" and "depuis que je la suis" in h["recit"]


# ---- répondre à une proposition du Mesh se passe dans le travail ---------------------------------------
def test_les_messages_de_reponse_disent_la_reponse_de_la_personne_puis_celle_de_flore():
    init = {"titre": "Dates de règlement"}
    for nature, mot in (("comparaison", "comparaison"), ("validation", "validation"), ("incertain", "pas de certitude"), ("decision", "J'ai enregistré votre réponse")):
        moi, flore = ouverture_travail.messages_reponse_initiative(init, "Mon choix", nature, "2026-09-21T10:00:00+00:00")
        assert moi == {"role": "utilisateur", "texte": "Mon choix", "quand": "2026-09-21T10:00:00+00:00"} and mot in flore["texte"]
    assert ouverture_travail.messages_reponse_initiative(init, "x", "decision", "q")[1]["propose_passation"] is True


def test_choisir_une_option_ouvre_un_travail_avec_la_decision(api):
    r = api.post(f"{BASE}/initiatives/init-delai-j3/repondre", headers=HP, json={"choix": "Non, il est anormal"})
    assert r.status_code == 200
    body = r.json()
    assert body["travail_id"] and body["initiative"]["reponse"]["travail_id"] == body["travail_id"]
    c = api.get(f"{BASE}/cases/{body['travail_id']}", headers=HP).json()
    assert c["conversation"][0]["role"] == "flore" and c["conversation"][-2] == {**c["conversation"][-2], "role": "utilisateur", "texte": "Non, il est anormal"}
    assert c["conversation"][-1]["propose_passation"] is True and c["decisions"][-1]["texte"] == "Non, il est anormal" and c["portee"] == "personnel"
    assert api.post(f"{BASE}/initiatives/init-delai-j3/repondre", headers=HP, json={"choix": "Oui, il est attendu"}).status_code == 409  # une seule réponse


# ---- une délégation est un travail ------------------------------------------------------------------------
def test_une_delegation_ouvre_un_travail_ou_flore_dit_le_mandat(api):
    r = api.post(f"{BASE}/delegations", headers=H, json={"type": "surveillance", "jumeaux": ["paiements", "fraude"], "duree_h": 24})
    assert r.status_code == 201
    d = r.json()
    DELEGATIONS_CREEES.append(d["id"])
    assert d["travail_id"]
    c = api.get(f"{BASE}/cases/{d['travail_id']}", headers=H).json()
    m = c["conversation"][0]
    assert m["type"] == "mandat" and "Vous m'avez confié un mandat" in m["texte"] and "Paiements" in m["texte"] and "validation humaine" in m["texte"]
    assert c["statut"] == "en_cours" and c["portee"] == "personnel" and c["origine"]["delegation_id"] == d["id"]
    lues = {x["id"]: x for x in api.get(f"{BASE}/delegations", headers=H).json()}
    assert lues[d["id"]]["travail_id"] == d["travail_id"] and lues[d["id"]]["statut"] == "active"
    # idempotent : la relire ne crée pas un second travail
    assert api.get(f"{BASE}/delegations", headers=H).json() and len([x for x in api.get(f"{BASE}/cases", headers=H).json() if x.get("origine", {}).get("delegation_id") == d["id"]]) == 1


def test_un_mandat_echu_est_termine_et_flore_le_dit(api):
    ancien = next(x for x in api.get(f"{BASE}/delegations", headers=H).json() if x["id"] == "deleg-surveillance-paiement")
    assert ancien["statut"] == "terminee" and ancien["travail_id"]
    c = api.get(f"{BASE}/cases/{ancien['travail_id']}", headers=H).json()
    assert c["statut"] == "clos" and c["conversation"][-1]["type"] == "mandat_termine" and "reconduise" in c["conversation"][-1]["texte"]


# ---- portée d'un travail --------------------------------------------------------------------------------------
def _creer(api, **kw):
    return api.post(f"{BASE}/cases", headers=HP, json={"titre": TITRE, "jumeaux": ["paiements"], **kw}).json()["id"]


def test_un_travail_neuf_est_personnel(api):
    cid = _creer(api)
    assert api.get(f"{BASE}/cases/{cid}", headers=HP).json()["portee"] == "personnel"
    assert api.get(f"{BASE}/cases/{cid}", headers=H).status_code == 403  # même avec un périmètre qui couvre ses jumeaux
    assert cid not in [c["id"] for c in api.get(f"{BASE}/cases", headers=H).json()]
    assert cid in [c["id"] for c in api.get(f"{BASE}/cases", headers=HP).json()]
    assert api.post(f"{BASE}/cases", headers=HP, json={"titre": TITRE, "portee": "galaxie"}).status_code == 400


def test_ceder_a_l_equipe_puis_a_l_entreprise(api):
    cid = _creer(api)
    equipe = {**H, "X-Espace": "espace-paiements"}
    assert api.get(f"{BASE}/cases/{cid}", headers=equipe).status_code == 403
    c = api.post(f"{BASE}/cases/{cid}/portee", headers=HP, json={"portee": "equipe"}).json()
    assert c["portee"] == "equipe" and c["espace_label"] == "Équipe Paiements" and c["peut_partager"] is True
    assert c["historique"][-1]["texte"].startswith("Travail partagé avec l'équipe")
    assert api.get(f"{BASE}/cases/{cid}", headers=equipe).status_code == 200  # un collègue de l'espace le voit
    autre = api.get(f"{BASE}/cases/{cid}", headers=equipe).json()
    assert autre["peut_partager"] is False
    assert api.get(f"{BASE}/cases/{cid}", headers=H).status_code == 403  # depuis un autre espace, non
    assert api.post(f"{BASE}/cases/{cid}/portee", headers=equipe, json={"portee": "entreprise"}).status_code == 403  # seul le responsable décide
    assert api.post(f"{BASE}/cases/{cid}/portee", headers=HP, json={"portee": "galaxie"}).status_code == 400
    api.post(f"{BASE}/cases/{cid}/portee", headers=HP, json={"portee": "entreprise"})
    assert api.get(f"{BASE}/cases/{cid}", headers=H).status_code == 200
    api.post(f"{BASE}/cases/{cid}/portee", headers=HP, json={"portee": "personnel"})
    assert api.get(f"{BASE}/cases/{cid}", headers=H).status_code == 403


def test_la_portee_ne_donne_jamais_plus_que_le_perimetre(api):
    cid = _creer(api, portee="entreprise", jumeaux=["fraude"])  # Risque : hors du périmètre de l'équipe Paiements
    assert api.get(f"{BASE}/cases/{cid}", headers=HP).status_code == 403
    assert api.get(f"{BASE}/cases/{cid}", headers=H).status_code == 200


def test_un_travail_personnel_n_est_pas_une_actualite_pour_les_autres(api):
    cid = _creer(api)
    voit = lambda h: [x["id"] for x in api.get(f"{BASE}/actualites", headers=h).json()["histoires"]]
    assert f"case-{cid}" in voit(HP) and f"case-{cid}" not in voit(H)
    assert api.get(f"{BASE}/actualites/histoire/case-{cid}", headers=H).status_code == 404


def test_les_travaux_d_origine_restent_visibles_de_tous(api):
    assert next(c for c in api.get(f"{BASE}/cases", headers=H).json() if c["id"] == "case-dette-files")["portee"] == "entreprise"


# ---- écarter pour l'équipe --------------------------------------------------------------------------------------
def test_ecarter_pour_l_equipe_ne_touche_que_l_espace(api):
    hid = "sit-sit-latence-paiements"
    equipe = {**H, "X-Espace": "espace-paiements"}
    assert api.post(f"{BASE}/actualites/histoire/{hid}/ecarter", headers=HP, json={"raison": "traite", "portee": "galaxie"}).status_code == 400
    try:
        assert api.post(f"{BASE}/actualites/histoire/{hid}/ecarter", headers=HP, json={"raison": "traite", "portee": "equipe"}).json()["portee"] == "equipe"
        d = api.get(f"{BASE}/actualites", headers=equipe).json()
        assert hid not in [h["id"] for h in d["histoires"]]
        assert next(e for e in d["ecartees"] if e["id"] == hid) == {"id": hid, "titre": next(e for e in d["ecartees"] if e["id"] == hid)["titre"], "raison": "Traité ailleurs", "portee": "equipe", "par": "paiements"}
        assert hid in [h["id"] for h in api.get(f"{BASE}/actualites", headers=H).json()["histoires"]]  # l'architecte, dans son espace, la voit toujours
        assert api.delete(f"{BASE}/actualites/histoire/{hid}/ecarter", headers=equipe).status_code == 200  # un collègue de l'espace peut la rétablir
        assert hid in [h["id"] for h in api.get(f"{BASE}/actualites", headers=equipe).json()["histoires"]]
    finally:
        supprimer_ecarts({"histoire_id": hid, "persona": "paiements"})
