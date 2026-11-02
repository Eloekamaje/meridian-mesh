"""Domaine générique : unités, statuts, charge et rôles."""
from datetime import date

import pytest

from meridian.domain import planification as p


def test_statuts_et_unites_sont_normalises():
    assert p.normaliser_statut("Done") == "termine"
    assert p.normaliser_statut("In Progress") == "en_cours"
    assert p.normaliser_statut("backlog") == "a_faire"
    assert p.normaliser_statut("done-ish") == "inconnu"
    assert p.normaliser_unite("Points") == "points"
    with pytest.raises(ValueError):
        p.normaliser_unite("story-points")


def test_charge_par_equipe_et_unite_sans_fusion():
    elements = [
        p.ElementTravail("1", "s", "A-1", "eq1", "A", estimation=p.Estimation(3, "points")),
        p.ElementTravail("2", "s", "A-2", "eq1", "B", estimation=p.Estimation(2, "points"),
                         categorie_charge="engagee"),
        p.ElementTravail("3", "s", "A-3", "eq2", "C", estimation=p.Estimation(5, "points")),
        p.ElementTravail("4", "s", "A-4", "eq1", "D"),
    ]
    charges = p.agreger_charge(elements)
    assert charges[("eq1", "points")].total == 5
    assert charges[("eq1", "points")].engagee == 2
    assert charges[("eq2", "points")].total == 5
    assert charges[("eq1", "items")].elements_sans_estimation == 1
    assert p.marge(10, charges[("eq1", "points")].total) == 5


def test_capacite_refuse_une_periode_inversee():
    with pytest.raises(ValueError):
        p.Capacite("eq", date(2026, 2, 1), date(2026, 1, 1), "jours", 10)


def test_matrice_de_roles_ne_confond_pas_lecture_et_decision():
    assert p.role_autorise("po", "proposer_plan")
    assert not p.role_autorise("po", "gerer_roles")
    assert p.role_autorise("observateur", "lire_charge")
    assert not p.role_autorise("observateur", "simuler")
    assert p.role_autorise("admin", "gerer_roles")
