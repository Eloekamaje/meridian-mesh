"""Enveloppe unique : clés stables, valeurs conservées, aucune donnée inventée."""
from meridian.application.tour_reponse import CLES, enveloppe, normaliser


def test_normaliser_complete_les_cles_sans_ecraser_les_valeurs():
    source = {"reponse": "ok", "preuves": [{"id": "p1"}], "x_extra": 1}
    resultat = normaliser(source)

    assert resultat["reponse"] == "ok"
    assert resultat["preuves"] == [{"id": "p1"}]
    assert resultat["x_extra"] == 1
    assert set(CLES) <= set(resultat)
    assert resultat["questions"] == []


def test_enveloppe_conserve_origine_et_ne_partage_pas_les_listes():
    a = enveloppe({"reponse": "a"}, origine="modele")
    b = enveloppe({"reponse": "b"}, origine="scenario")
    a["preuves"].append("x")

    assert a["origine"] == "modele"
    assert b["origine"] == "scenario"
    assert b["preuves"] == []
