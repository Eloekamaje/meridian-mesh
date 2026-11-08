"""C8 — épilogue de requête : l'événement est inséré, jamais bloquant, inconnu propagé."""
import pytest

from meridian.tests.conftest import besoin_pg

from meridian.adapters.outbound.postgres import evenements_requete


def test_construire_normalise_un_tour():
    evenement = evenements_requete.construire(
        {"comportement": "expliquer", "reponse": "tout est clair",
         "preuves": [{"source": "a", "detail": "b"}],
         "sonde": {"verdict": "clair", "preuves": [{"id": "c1"}]},
         "groundedness": {"total": 2, "verifiees": 2, "non_resolues": 0},
         "usage": {"total": 123, "modele": "modele-x"}},
        question="Quelle dépendance ?", episode_id="ep-1", duree_ms=42.5)
    assert evenement["question_hash"] == evenements_requete.question_hash("Quelle dépendance ?")
    assert evenement["question_hash"] != "Quelle dépendance ?"  # jamais le texte brut
    assert evenement["classe"] == "expliquer"
    assert evenement["verdict_sonde"] == "clair"
    assert evenement["preuves_consultees"] == 2
    assert evenement["confiance"] == 1.0
    assert evenement["citations_verifiees"] == 2
    assert evenement["non_resolues"] == 0
    assert evenement["inconnu_question"] is False
    assert evenement["episode_id"] == "ep-1"
    assert evenement["model"] == "modele-x"
    assert evenement["tokens"] == 123
    assert evenement["duree_ms"] == 42.5


def test_reponse_concluante_n_est_pas_inconnue():
    assert evenements_requete.non_concluante(
        {"reponse": "tout est clair", "comportement": "repondre"}) is None


def test_reponse_non_concluante_est_inconnue():
    for reponse, attendu in (
        ({"reponse": "résultat non observé dans le périmètre"}, "non observé"),
        ({"reponse": "x", "limite_preuve": True}, "limite"),
        ({"reponse": "x", "raisonnement_statut": "partiel"}, "partiel"),
        ({"reponse": "x", "origine": "repli"}, "repli"),
        ({"reponse": "x", "resolution": {"absent": True}}, "absent"),
        ({"reponse": "x", "resolution": {"statut": "ambigu"}}, "ambigu"),
    ):
        raison = evenements_requete.non_concluante(reponse)
        assert raison is not None and attendu in raison, (reponse, raison)


@besoin_pg
def test_consigner_insere_l_evenement(conn):
    evenement = evenements_requete.construire(
        {"comportement": "expliquer", "reponse": "clair",
         "sonde": {"verdict": "incertain"},
         "usage": {"total": 10, "modele": "m"}},
        question="insert ?", episode_id="ep-2", duree_ms=3.5)
    ligne_id = evenements_requete.consigner(conn, "banque", evenement)
    assert ligne_id
    ligne = conn.execute(
        "SELECT tenant_id, question_hash, verdict_sonde, inconnu_question, episode_id, "
        "model, tokens, duree_ms FROM evenement_requete WHERE id = %s",
        (ligne_id,)).fetchone()
    assert ligne[0] == "banque"
    assert ligne[1] == evenements_requete.question_hash("insert ?")
    assert ligne[2] == "incertain"
    assert ligne[3] is False
    assert ligne[4] == "ep-2"
    assert ligne[5] == "m"
    assert ligne[6] == 10
    assert abs(ligne[7] - 3.5) < 1e-6


@besoin_pg
def test_inconnu_question_est_propage(conn):
    evenement = evenements_requete.construire(
        {"reponse": "pas pu interpréter la demande", "comportement": "signaler"},
        question="???", duree_ms=1)
    assert evenement["inconnu_question"] is True
    ligne_id = evenements_requete.consigner(conn, "banque", evenement)
    ligne = conn.execute(
        "SELECT inconnu_question, inconnu_raison FROM evenement_requete WHERE id = %s",
        (ligne_id,)).fetchone()
    assert ligne[0] is True
    assert "pas pu interpréter" in ligne[1]


def test_consigner_ne_leve_jamais():
    """Une panne de l'infra ne casse pas l'épilogue : ``None`` rendu, pas d'exception."""
    class ConnexionCassee:
        def cursor(self):
            raise RuntimeError("postgres down")

    assert evenements_requete.consigner(
        ConnexionCassee(), "banque", {"question_hash": "x"}) is None
    assert evenements_requete.consigner(
        ConnexionCassee(), "", {"question_hash": "x"}) is None


def test_construire_ne_leve_jamais_sur_reponse_vide():
    evenement = evenements_requete.construire(None, question="q")
    assert evenement["inconnu_question"] is True
    assert evenement["question_hash"]
