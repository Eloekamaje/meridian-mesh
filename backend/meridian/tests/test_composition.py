"""Composition dynamique bornée : profils, méthodes, compétences, spécialistes et autorité."""
import pytest

from meridian.application import composition
from meridian.domain import profils


def test_un_developpeur_et_un_po_ne_composent_pas_la_meme_equipe():
    dev = composition.planifier("developpeur", "impact d'un changement d'API et test de rollback")
    po = composition.planifier("product_owner", "priorité et bénéfice de la roadmap")

    assert {m.id for m in dev.methodes} != {m.id for m in po.methodes}
    assert "decouverte" in dev.specialistes or "impact" in dev.specialistes
    assert "faciliter_decision" in {c.id for c in po.competences}
    assert dev.autorite == po.autorite == "proposition"


def test_un_profil_inconnu_reste_en_lecture_avec_des_avertissements():
    profil = profils.resoudre_profil(profil="inconnu")
    plan = composition.planifier(profil, "question très vague")

    assert plan.profil.inconnu is True
    assert plan.autorite == "lecture"
    assert any("inconnu" in avertissement for avertissement in plan.avertissements)
    assert composition.valider_plan(plan)["ok"] is True


def test_l_autorite_maximale_borne_le_plan_et_ne_promeut_pas():
    plan = composition.planifier("directeur", "arbitrage budget", autorite_max="proposition")
    assert plan.autorite == "proposition"

    with pytest.raises(ValueError):
        composition.planifier("support", "incident", autorite_max="inconnue")


def test_les_methodes_et_competences_sont_dans_les_catalogues():
    plan = composition.planifier("support", "incident SLA production")
    validation = composition.valider_plan(plan)
    assert validation["ok"] is True
    assert plan.methodes and plan.competences
    assert {s for s in plan.specialistes} <= {"decouverte", "preuve", "impact", "outcome"}


def test_les_bornes_et_la_deterministicite_sont_respectees():
    premier = composition.planifier("architecte", "architecture API", limite_methodes=2, limite_competences=3)
    second = composition.planifier("architecte", "architecture API", limite_methodes=2, limite_competences=3)
    assert premier.as_dict() == second.as_dict()
    assert len(premier.methodes) <= 2
    assert len(premier.competences) <= 3


def test_les_catalogues_profils_methodes_et_competences_sont_coherents():
    from meridian.domain import competences_cognitives
    from meridian.domain import methodes_cognitives

    methodes = {m.id for m in methodes_cognitives.CATALOGUE_METHODES}
    competences = {c.id for c in competences_cognitives.CATALOGUE_COMPETENCES}
    for profil in profils.CATALOGUE_PROFILS.values():
        assert set(profil.methodes) <= methodes
        assert set(profil.competences) <= competences


def test_le_socle_de_preuves_est_independant_du_profil():
    dev = composition.planifier("developpeur", "incident API", application_id="conduit",
                                situation_id="sit-1", twin_ids=("paiements",))
    po = composition.planifier("product_owner", "priorité API", application_id="conduit",
                               situation_id="sit-1", twin_ids=("paiements",))
    assert dev.specialistes_socle == po.specialistes_socle
    assert dev.specialistes_socle == ("decouverte", "preuve", "impact", "outcome")
    assert {m.id for m in dev.methodes} != {m.id for m in po.methodes}
