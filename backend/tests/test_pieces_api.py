"""Pièces jointes d'un Travail : dépôt réel, lecture bornée, téléchargement en pièce jointe, droits et retrait."""
import os
from uuid import uuid4

import pytest
import requests

BASE = os.environ.get("MERIDIAN_API", "http://localhost:8001").rstrip("/") + "/api"
H = {"X-Persona": "architecte"}


@pytest.fixture(scope="module")
def api():
    try:
        requests.get(BASE + "/health", timeout=3)
    except requests.RequestException:
        pytest.skip("backend non lancé")
    return requests.Session()


@pytest.fixture(scope="module")
def cid(api):
    r = api.post(f"{BASE}/cases", json={"titre": f"TEST_pieces_{uuid4().hex[:8]}", "statut": "conversation"}, headers=H)
    assert r.status_code == 201, r.text
    identifiant = r.json()["id"]
    yield identifiant
    api.delete(f"{BASE}/cases/{identifiant}", headers=H)  # une conversation se supprime, avec ses pièces


def test_un_texte_est_depose_lu_et_liste(api, cid):
    r = api.post(f"{BASE}/cases/{cid}/pieces", headers=H,
                 files={"fichier": ("note.md", b"# Note\n\nBonjour", "text/markdown")})
    assert r.status_code == 201, r.text
    piece = r.json()
    assert piece["nom"] == "note.md"
    assert piece["etat"] == "lu"
    assert piece["caracteres"] == 15
    assert "texte" not in piece  # l'API de liste ne renvoie pas le contenu extrait

    r = api.get(f"{BASE}/cases/{cid}/pieces", headers=H)
    assert r.status_code == 200
    assert [p["id"] for p in r.json()] == [piece["id"]]
    assert r.headers["cache-control"] == "private, no-store"

    r = api.get(f"{BASE}/cases/{cid}", headers=H)
    assert r.status_code == 200
    assert r.json()["pieces"][0]["id"] == piece["id"]


def test_l_extrait_et_le_telechargement_sont_reels(api, cid):
    r = api.post(f"{BASE}/cases/{cid}/pieces", headers=H,
                 files={"fichier": ("preuve.txt", b"Le parcours paiement est lent.", "text/plain")})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]

    r = api.get(f"{BASE}/cases/{cid}/pieces/{pid}/extrait", headers=H)
    assert r.status_code == 200
    assert "paiement" in r.json()["texte"]
    assert r.headers["cache-control"] == "private, no-store"

    r = api.get(f"{BASE}/cases/{cid}/pieces/{pid}", headers=H)
    assert r.status_code == 200
    assert r.content == b"Le parcours paiement est lent."
    assert r.headers["content-disposition"].startswith("attachment;")
    assert r.headers["x-content-type-options"] == "nosniff"


def test_la_route_de_section_sert_le_texte_et_une_citation(api, cid):
    r = api.post(f"{BASE}/cases/{cid}/pieces", headers=H,
                 files={"fichier": ("sections.md", b"# Introduction\nintro\n\n# Paiement\nle parcours est lent",
                                    "text/markdown")})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]

    r = api.get(f"{BASE}/cases/{cid}/pieces/{pid}/sections/s2", headers=H)
    assert r.status_code == 200, r.text
    section = r.json()
    assert section["titre"] == "Paiement" and "parcours" in section["texte"]
    assert section["citation"] == f"pièce:{pid}#s2" and section["tronque"] is False
    assert section["joint_par"] == "architecte" and section["joint_le"]
    assert r.headers["cache-control"] == "private, no-store"

    r = api.get(f"{BASE}/cases/{cid}/pieces/{pid}/sections/s2", params={"debut": 4, "limite": 5}, headers=H)
    assert r.status_code == 200, r.text
    fenetre = r.json()
    assert fenetre["debut"] == 4 and fenetre["fin"] == 9 and fenetre["tronque"] is True
    assert len(fenetre["texte"]) == 5 and fenetre["texte"] == section["texte"][4:9]
    assert fenetre["section_fin"] - fenetre["section_debut"] >= fenetre["fin"]
    assert fenetre["section_debut"] >= 0 and fenetre["debut"] + fenetre["fin"] >= fenetre["fin"]

    r = api.get(f"{BASE}/cases/{cid}/pieces/{pid}/sections/s2", params={"debut": -1}, headers=H)
    assert r.status_code == 422
    r = api.get(f"{BASE}/cases/{cid}/pieces/{pid}/sections/s2", params={"limite": 10_000_000}, headers=H)
    assert r.status_code == 422

    r = api.get(f"{BASE}/cases/{cid}/pieces/{pid}/sections/s99", headers=H)
    assert r.status_code == 404


def test_les_metadonnees_de_tableaux_sont_dans_la_liste_sans_le_texte(api, cid):
    r = api.post(f"{BASE}/cases/{cid}/pieces", headers=H,
                 files={"fichier": ("ventes.csv", b"nom,montant\nA,1\nB,2\n", "text/csv")})
    assert r.status_code == 201, r.text
    piece = r.json()
    assert piece["tables_count"] == 1
    assert piece["tables"][0]["colonnes"] == ["nom", "montant"]
    assert piece["tables"][0]["lignes"] == 2
    assert "texte" not in piece and "grille" not in str(piece["tables"])


def test_un_faux_pdf_est_refuse(api, cid):
    r = api.post(f"{BASE}/cases/{cid}/pieces", headers=H,
                 files={"fichier": ("faux.pdf", b"pas un pdf", "application/pdf")})
    assert r.status_code == 400
    assert "PDF" in r.json()["detail"]


def test_un_format_inconnu_est_refuse(api, cid):
    r = api.post(f"{BASE}/cases/{cid}/pieces", headers=H,
                 files={"fichier": ("script.exe", b"MZ", "application/octet-stream")})
    assert r.status_code == 400


def test_les_droits_du_travail_s_appliquent(api, cid):
    r = api.get(f"{BASE}/cases/{cid}/pieces", headers={"X-Persona": "support"})
    assert r.status_code == 404  # conversation privée : on ne révèle pas qu'elle existe


def test_une_piece_se_retire(api, cid):
    r = api.post(f"{BASE}/cases/{cid}/pieces", headers=H,
                 files={"fichier": ("a-retirer.txt", b"temporaire", "text/plain")})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    r = api.delete(f"{BASE}/cases/{cid}/pieces/{pid}", headers=H)
    assert r.status_code == 204
    assert api.get(f"{BASE}/cases/{cid}/pieces/{pid}", headers=H).status_code == 404


def test_une_piece_du_travail_a_est_inaccessible_depuis_le_travail_b(api, cid):
    r = api.post(f"{BASE}/cases/{cid}/pieces", headers=H,
                 files={"fichier": ("secret.txt", b"Reserve au travail A", "text/plain")})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    autre = api.post(f"{BASE}/cases", json={"titre": f"TEST_pieces_autre_{uuid4().hex[:8]}", "statut": "conversation"},
                     headers=H)
    assert autre.status_code == 201, autre.text
    cid_b = autre.json()["id"]
    try:
        assert api.get(f"{BASE}/cases/{cid_b}/pieces/{pid}/extrait", headers=H).status_code == 404
        assert api.get(f"{BASE}/cases/{cid_b}/pieces/{pid}/sections/s1", headers=H).status_code == 404
        assert api.get(f"{BASE}/cases/{cid_b}/pieces/{pid}", headers=H).status_code == 404
        assert api.delete(f"{BASE}/cases/{cid_b}/pieces/{pid}", headers=H).status_code == 404
    finally:
        api.delete(f"{BASE}/cases/{cid_b}", headers=H)


def _nettoyer_case_en_base(cid):
    """Un Travail ordinaire ne se supprime pas par l'API : le test enlève ses pièces et son document."""
    from bson import ObjectId
    from dotenv import dotenv_values
    from gridfs import GridFSBucket
    from pymongo import MongoClient
    env = dotenv_values(os.path.join(os.path.dirname(__file__), "..", ".env"))
    db = MongoClient(env.get("MONGO_URL", "mongodb://localhost:27017"))[env.get("DB_NAME", "meridian_db")]
    bucket = GridFSBucket(db, bucket_name="pieces_fichiers")
    for doc in list(db.pieces.find({"case_id": cid})):
        try:
            bucket.delete(ObjectId(doc["fichier_id"]))
        except Exception:
            pass
    db.pieces.delete_many({"case_id": cid})
    db.cases.delete_one({"id": cid})


def test_une_persona_non_auteure_non_responsable_ne_retire_pas_une_piece(api):
    r = api.post(f"{BASE}/cases", json={"titre": f"TEST_pieces_droits_{uuid4().hex[:8]}", "portee": "entreprise"},
                 headers=H)
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    try:
        r = api.post(f"{BASE}/cases/{cid}/pieces", headers=H,
                     files={"fichier": ("preuve.txt", b"Une preuve", "text/plain")})
        assert r.status_code == 201, r.text
        pid = r.json()["id"]
        r = api.delete(f"{BASE}/cases/{cid}/pieces/{pid}", headers={"X-Persona": "support"})
        assert r.status_code == 403
        assert api.get(f"{BASE}/cases/{cid}/pieces/{pid}", headers=H).status_code == 200
    finally:
        _nettoyer_case_en_base(cid)


def test_un_support_non_participant_ne_peut_pas_ajouter_une_piece(api):
    r = api.post(f"{BASE}/cases", json={"titre": f"TEST_pieces_ajout_{uuid4().hex[:8]}", "portee": "entreprise"},
                 headers=H)
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    try:
        r = api.post(f"{BASE}/cases/{cid}/pieces", headers={"X-Persona": "support"},
                     files={"fichier": ("note.txt", b"Bonjour", "text/plain")})
        assert r.status_code == 403
        assert api.get(f"{BASE}/cases/{cid}/pieces", headers=H).json() == []
    finally:
        _nettoyer_case_en_base(cid)


def test_un_participant_peut_ajouter_une_piece(api):
    r = api.post(f"{BASE}/cases",
                 json={"titre": f"TEST_pieces_participant_{uuid4().hex[:8]}", "portee": "personnel",
                       "participants": ["support"]},
                 headers=H)
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    try:
        r = api.post(f"{BASE}/cases/{cid}/pieces", headers={"X-Persona": "support"},
                     files={"fichier": ("participant.txt", b"Une source partagee", "text/plain")})
        assert r.status_code == 201, r.text
        assert r.json()["joint_par"] == "support"
    finally:
        _nettoyer_case_en_base(cid)


def test_le_dossier_de_demonstration_refuse_les_pieces(api):
    demo = "demo-polaris-work-g"
    r = api.post(f"{BASE}/cases/{demo}/pieces", headers=H,
                 files={"fichier": ("note.txt", b"Bonjour", "text/plain")})
    assert r.status_code == 403
    r = api.delete(f"{BASE}/cases/{demo}/pieces/inconnu", headers=H)
    assert r.status_code == 403


def test_la_fusion_transfere_les_pieces_de_la_conversation(api):
    source = api.post(f"{BASE}/cases", json={"titre": f"TEST_fusion_source_{uuid4().hex[:8]}",
                                              "statut": "conversation"}, headers=H)
    assert source.status_code == 201, source.text
    source_cid = source.json()["id"]
    r = api.post(f"{BASE}/cases/{source_cid}/pieces", headers=H,
                 files={"fichier": ("note.txt", b"Piece de la conversation", "text/plain")})
    assert r.status_code == 201, r.text
    cible = api.post(f"{BASE}/cases", json={"titre": f"TEST_fusion_cible_{uuid4().hex[:8]}"}, headers=H)
    assert cible.status_code == 201, cible.text
    cible_cid = cible.json()["id"]
    try:
        r = api.post(f"{BASE}/cases/{cible_cid}/fusion", headers=H, json={"source_cid": source_cid})
        assert r.status_code == 200, r.text
        assert api.get(f"{BASE}/cases/{source_cid}", headers=H).status_code == 404
        pieces = api.get(f"{BASE}/cases/{cible_cid}/pieces", headers=H).json()
        assert [p["nom"] for p in pieces] == ["note.txt"]
    finally:
        _nettoyer_case_en_base(cible_cid)


def test_un_xlsm_est_refuse(api, cid):
    r = api.post(f"{BASE}/cases/{cid}/pieces", headers=H,
                 files={"fichier": ("classeur.xlsm", b"PK\x03\x04", "application/octet-stream")})
    assert r.status_code == 400
    assert "xlsm" in r.json()["detail"]


def test_retirer_une_piece_purge_ses_derives_dans_la_conversation(api):
    r = api.post(f"{BASE}/cases", json={"titre": f"TEST_pieces_purge_{uuid4().hex[:8]}", "statut": "conversation"},
                 headers=H)
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    try:
        r = api.post(f"{BASE}/cases/{cid}/pieces", headers=H,
                     files={"fichier": ("source.txt", b"Le parcours paiement est lent.", "text/plain")})
        assert r.status_code == 201, r.text
        pid = r.json()["id"]
        conversation = [
            {"role": "utilisateur", "texte": "Et le paiement ?", "quand": "2026-10-29T10:00:00+00:00"},
            {"role": "flore", "texte": "D'après la pièce.", "quand": "2026-10-29T10:00:01+00:00",
             "pieces_selection": [{"piece_id": pid, "section_id": "s1"},
                                  {"piece_id": "autre", "section_id": "s1"}],
             "pieces_lectures": [
                 {"outil": "lire_piece", "piece_id": pid, "section_id": "s1"},
                 {"outil": "chercher_pieces", "question": "paiement",
                  "hits": [{"piece_id": pid, "section_id": "s1"}, {"piece_id": "autre", "section_id": "s1"}]},
             ],
             "activite": [{"label": "Je lis la pièce", "outil": {"nom": "lire_piece",
                                                                 "arguments": {"piece_id": pid},
                                                                 "extrait": "paiement"}},
                          {"label": "Je lis le code", "outil": {"nom": "lire_code", "extrait": "def f()"}}]},
        ]
        # La conversation ne s'écrit plus par PATCH : on injecte les dérivés directement pour tester la purge.
        from dotenv import dotenv_values
        from pymongo import MongoClient
        env = dotenv_values(os.path.join(os.path.dirname(__file__), "..", ".env"))
        db = MongoClient(env.get("MONGO_URL", "mongodb://localhost:27017"))[env.get("DB_NAME", "meridian_db")]
        db.cases.update_one({"id": cid}, {"$set": {"conversation": conversation}})

        assert api.delete(f"{BASE}/cases/{cid}/pieces/{pid}", headers=H).status_code == 204
        message = api.get(f"{BASE}/cases/{cid}", headers=H).json()["conversation"][1]
        assert message["pieces_selection"] == [{"piece_id": "autre", "section_id": "s1"}]
        assert message["pieces_lectures"] == [
            {"outil": "chercher_pieces", "question": "paiement",
             "hits": [{"piece_id": "autre", "section_id": "s1"}]}
        ]
        assert [op["outil"]["nom"] for op in message["activite"]] == ["lire_code"]
    finally:
        api.delete(f"{BASE}/cases/{cid}", headers=H)
