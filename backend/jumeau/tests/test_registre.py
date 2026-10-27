"""Projection des jumeaux réels dans le registre de l'application (Mongo) : Atlas, registre, Flore, Travaux."""
from jumeau import depot, registre
from jumeau.tests.conftest import ACTIVITE, JUMEAU, SOURCE, besoin_pg, claim


def test_document_du_registre_marque_le_jumeau_reel():
    doc = registre.document({"id": "tbt", "nom": "TBT", "equipe": "equipe-tbt", "domaine": "Paiement",
                             "mission": "Traite les virements", "curseur": "a" * 40, "claims": 12})
    assert doc["reel"] is True and doc["statut"] == "actif"
    assert (doc["id"], doc["nom"], doc["domaine"], doc["proprietaire"]) == ("tbt", "TBT", "Paiement", "equipe-tbt")
    assert doc["sources"]["code"] is True and doc["sources"]["documentation"] is False
    assert doc["couverture"] == registre.couverture(1)
    assert "aaaaaaaaaaaa" in doc["fraicheur"]


def test_mission_par_defaut():
    doc = registre.document({"id": "x", "nom": "X", "equipe": "e", "domaine": "À confirmer", "mission": None,
                             "curseur": "b" * 40, "claims": 0})
    assert doc["mission"]


@besoin_pg
def test_jumeaux_reels_lus_depuis_la_couche_cognitive(conn):
    depot.enregistrer(conn, {**JUMEAU, "domaine": "Paiement", "mission": "Traite les virements"}, SOURCE,
                      [claim("motor"), claim("fastapi", ligne=1)], ACTIVITE)
    [j] = registre.jumeaux_reels(conn)
    assert (j["id"], j["domaine"], j["mission"], j["claims"], j["curseur"]) == ("tbt", "Paiement", "Traite les virements", 2, "sha1")


@besoin_pg
def test_domaine_par_defaut_a_confirmer(conn):
    depot.enregistrer(conn, JUMEAU, SOURCE, [claim("motor")], ACTIVITE)
    assert registre.jumeaux_reels(conn)[0]["domaine"] == "À confirmer"
