"""Packs de domaine Paiements/Risque : chargement, validation et composition."""
from copy import deepcopy

import pytest

from meridian.application import composition
from meridian.domain import packs_domaines


def _packs():
    return {pack.id: pack for pack in packs_domaines.charger_packs()}


def test_les_deux_packs_sont_charges_et_valides():
    packs = _packs()
    assert set(packs) == {"paiements", "risque"}
    for pack in packs.values():
        assert pack.schema == packs_domaines.SCHEMA_PACK
        assert pack.nom and pack.description and pack.scope["domaines"]
        assert 3 <= len(pack.evaluations) <= 5
        assert pack.methodes and pack.competences and pack.specialistes
        assert packs_domaines.valider_pack(pack)["valide"] is True


def test_la_frontiere_d_autorite_est_lecture_seule():
    for pack in _packs().values():
        autorite = pack.autorite
        assert autorite.lecture_seule is True
        assert autorite.ecriture is False
        assert autorite.promotion is False
        assert autorite.execution is False
        assert autorite.approbation_humaine is True
        assert autorite.niveau_max in {"lecture", "proposition"}
        assert autorite.limite


def test_chaque_evaluation_porte_preuves_et_cle_de_reponse():
    for pack in _packs().values():
        identifiants = [evaluation.id for evaluation in pack.evaluations]
        assert len(identifiants) == len(set(identifiants))
        for evaluation in pack.evaluations:
            assert evaluation.question
            assert len(evaluation.expected_evidence) >= 3
            cle = evaluation.answer_key
            assert cle["claims"]
            assert cle["decision"]
            assert cle["abstention"]
            assert isinstance(cle["forbidden"], list)


def test_un_pack_malforme_est_refuse():
    brut = deepcopy(_packs()["paiements"].as_dict())
    brut["methodes"] = ["methode_inventee"]
    with pytest.raises(packs_domaines.PackInvalide, match="méthode inconnue"):
        packs_domaines.charger_pack(brut)

    brut = deepcopy(_packs()["paiements"].as_dict())
    brut["evaluations"] = brut["evaluations"][:2]
    with pytest.raises(packs_domaines.PackInvalide, match="entre 3 et 5"):
        packs_domaines.charger_pack(brut)

    brut = deepcopy(_packs()["risque"].as_dict())
    brut["autorite"]["ecriture"] = True
    with pytest.raises(packs_domaines.PackInvalide, match="lecture seule"):
        packs_domaines.charger_pack(brut)

    brut = deepcopy(_packs()["risque"].as_dict())
    brut["champ_inconnu"] = True
    with pytest.raises(packs_domaines.PackInvalide, match="champ inconnu"):
        packs_domaines.charger_pack(brut)


def test_un_pack_active_methodes_et_competences_sans_depasser_son_autorite():
    pack = _packs()["paiements"]
    plan = composition.planifier("ops", "incident de paiement", pack="paiements")

    assert plan.pack == "paiements"
    assert set(pack.methodes) <= {methode.id for methode in plan.methodes}
    assert set(pack.competences) <= {competence.id for competence in plan.competences}
    assert plan.autorite in {"lecture", "proposition"}
    assert composition.valider_plan(plan)["ok"] is True
    assert any("pack paiements" in justification for justification in plan.justification)


def test_le_pack_risque_plafonne_un_profil_a_approbation():
    plan = composition.planifier("risque", "risque de conformité R-118", pack="risque")

    assert plan.pack == "risque"
    assert plan.profil.id == "risque"
    assert plan.autorite == "proposition"
    assert set(_packs()["risque"].competences) <= {
        competence.id for competence in plan.competences}
    assert composition.valider_plan(plan)["ok"] is True


def test_un_pack_inconnu_est_refuse_sans_invention():
    with pytest.raises(ValueError, match="pack de domaine invalide"):
        composition.planifier("ops", "incident", pack="pack-inconnu")
    assert packs_domaines.pack_par_id("pack-inconnu") is None
    with pytest.raises(packs_domaines.PackInvalide, match="pack inconnu"):
        packs_domaines.charger_pack("pack-inconnu")
    assert packs_domaines.charger_pack("paiements").id == "paiements"


def test_valider_renvoie_un_rapport_json_safe():
    rapport = packs_domaines.valider_packs()
    assert rapport["valide"] is True
    assert rapport["packs"] == 2
    assert rapport["ids"] == ["paiements", "risque"]
    assert packs_domaines.valider_pack({"id": "incomplet"})["valide"] is False
