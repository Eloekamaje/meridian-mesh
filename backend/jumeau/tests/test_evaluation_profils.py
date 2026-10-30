"""Évaluation de l'adaptation aux profils : vérité partagée, sections propres, sécurité et porte agrégée."""
import json

import pytest

from jumeau import evaluation_profils as ep


def _cas(profil):
    return next(cas for cas in ep.JEU_PROFILS if cas.profil_id == profil)


def _reponse(cas, sections=None, faits=None, actions=(), autorite=None, limites=()):
    return {
        "faits": list(cas.faits_attendus if faits is None else faits),
        "sections": list(cas.sections_attendues if sections is None else sections),
        "actions": list(actions),
        "autorite": cas.autorite_max if autorite is None else autorite,
        "limites": list(limites),
        "propositions": ["option A", "option B"],
    }


def _reponses_jeu():
    return {cas.id: _reponse(cas) for cas in ep.JEU_PROFILS}


def _reponses_comparees():
    return {cas.profil_id: _reponse(cas) for cas in ep.JEU_PROFILS}


def test_le_jeu_partage_la_meme_question_et_les_memes_faits():
    assert len(ep.JEU_PROFILS) >= 5
    assert len({cas.question for cas in ep.JEU_PROFILS}) == 1
    assert len({cas.faits_attendus for cas in ep.JEU_PROFILS}) == 1
    assert {cas.profil_id for cas in ep.JEU_PROFILS} >= {
        "developpeur", "product_owner", "support", "directeur", "profil_inconnu",
    }


@pytest.mark.parametrize("profil", [cas.profil_id for cas in ep.JEU_PROFILS])
def test_reponse_parfaite_pour_chaque_profil(profil):
    cas = _cas(profil)
    resultat = ep.evaluer_reponse(cas, _reponse(cas))
    assert resultat["ok"] is True
    assert resultat["score_verite"] == 1.0
    assert resultat["score_adaptation"] == 1.0
    assert resultat["score_securite"] == 1.0
    assert resultat["score_global"] == 1.0
    assert resultat["manquants"] == []
    assert resultat["raisons"] == []


def test_section_manquante_reduit_adaptation_et_echoue():
    cas = _cas("product_owner")
    sections = [section for section in cas.sections_attendues if section != "priorite"]
    resultat = ep.evaluer_reponse(cas, _reponse(cas, sections=sections))
    assert resultat["score_verite"] == 1.0
    assert resultat["score_adaptation"] == pytest.approx(2 / 3, abs=1e-3)
    assert resultat["score_global"] < 1.0
    assert resultat["ok"] is False
    assert "priorite" in resultat["manquants"]
    assert any("sections absentes" in raison for raison in resultat["raisons"])


def test_action_interdite_fait_echouer_la_securite():
    cas = _cas("developpeur")
    resultat = ep.evaluer_reponse(cas, _reponse(cas, actions=["modifier_la_production"]))
    assert resultat["score_securite"] == 0.0
    assert resultat["ok"] is False
    assert any("action interdite" in raison for raison in resultat["raisons"])


def test_autorite_au_dessus_du_maximum_fait_echouer_la_securite():
    cas = _cas("profil_inconnu")
    resultat = ep.evaluer_reponse(cas, _reponse(cas, autorite="proposer"))
    assert resultat["score_securite"] == 0.0
    assert resultat["ok"] is False
    assert any("au-dessus du maximum" in raison for raison in resultat["raisons"])


def test_autorite_invalide_fait_echouer_la_securite():
    cas = _cas("support")
    resultat = ep.evaluer_reponse(cas, _reponse(cas, autorite="super_admin"))
    assert resultat["score_securite"] == 0.0
    assert any("autorité invalide" in raison for raison in resultat["raisons"])


def test_profil_inconnu_reste_en_lecture_seule():
    cas = _cas("profil_inconnu")
    resultat = ep.evaluer_reponse(cas, _reponse(cas, actions=["prendre_decision"]))
    assert resultat["score_securite"] == 0.0
    assert any("action interdite" in raison for raison in resultat["raisons"])


def test_meme_verite_et_sections_differentes_sont_coherentes():
    comparaison = ep.comparer_reponses(_reponses_comparees())
    assert comparaison["coherence_verite"] is True
    assert comparaison["divergences"] == []


def test_un_fait_manquant_chez_un_profil_cree_une_divergence():
    reponses = _reponses_comparees()
    cas = _cas("support")
    reponses["support"]["faits"] = list(cas.faits_attendus[1:])
    comparaison = ep.comparer_reponses(reponses)
    assert comparaison["coherence_verite"] is False
    assert any("faits manquants pour support" in divergence for divergence in comparaison["divergences"])


def test_des_sections_identiques_partout_sont_signalees():
    reponses = _reponses_comparees()
    for reponse in reponses.values():
        reponse["sections"] = ["impact_technique", "interface", "tests", "rollback"]
    comparaison = ep.comparer_reponses(reponses)
    assert comparaison["coherence_verite"] is True
    assert any("sections identiques" in divergence for divergence in comparaison["divergences"])


def test_porte_agregee_passe_quand_tout_est_parfait():
    bilan = ep.evaluer_jeu(ep.JEU_PROFILS, _reponses_jeu())
    assert bilan["verdict"] == "PASS"
    assert bilan["ok"] is True
    assert bilan["score_global"] == 1.0
    assert bilan["securite_min"] == 1.0
    assert bilan["cas"] == len(ep.JEU_PROFILS)
    assert all(resultat["ok"] for resultat in bilan["resultats"])


def test_porte_agregee_echoue_si_un_seul_cas_est_non_sur():
    reponses = _reponses_jeu()
    cas = _cas("developpeur")
    reponses[cas.id] = _reponse(cas, actions=["modifier_la_production"])
    bilan = ep.evaluer_jeu(ep.JEU_PROFILS, reponses)
    assert bilan["verdict"] == "FAIL"
    assert bilan["securite_min"] == 0.0
    assert bilan["score_global"] >= 0.8


def test_porte_agregee_respecte_le_seuil_global():
    reponses = _reponses_jeu()
    cas = _cas("product_owner")
    sections = [section for section in cas.sections_attendues if section != "priorite"]
    reponses[cas.id] = _reponse(cas, sections=sections)
    bilan = ep.evaluer_jeu(ep.JEU_PROFILS, reponses, seuil_global=1.0)
    assert bilan["verdict"] == "FAIL"
    assert bilan["score_global"] < 1.0


def test_reponse_malformee_est_notee_zero_sans_exception():
    cas = _cas("developpeur")
    for brute in (None, "texte libre", object(), 42):
        resultat = ep.evaluer_reponse(cas, brute)
        assert resultat["ok"] is False
        assert resultat["score_verite"] == 0.0
        assert resultat["score_adaptation"] == 0.0
        assert resultat["score_securite"] == 0.0
        assert resultat["score_global"] == 0.0
        assert resultat["manquants"]
        assert resultat["raisons"] == ["réponse absente ou invalide"]


def test_cas_malforme_leve_une_erreur_explicite():
    with pytest.raises(ep.CasProfilInvalide):
        ep.CasProfil(id="", question="q", profil_id="p", faits_attendus=(), sections_attendues=())
    with pytest.raises(ep.CasProfilInvalide):
        ep.CasProfil(
            id="x", question="q", profil_id="p", faits_attendus=(), sections_attendues=(), autorite_max="inconnue",
        )
    with pytest.raises(ep.CasProfilInvalide):
        ep.evaluer_reponse({"id": "x"}, {"faits": []})


def test_jeu_sans_reponse_echoue_sans_exception():
    bilan = ep.evaluer_jeu(ep.JEU_PROFILS, {})
    assert bilan["verdict"] == "FAIL"
    assert bilan["cas"] == len(ep.JEU_PROFILS)
    assert all(resultat["ok"] is False for resultat in bilan["resultats"])
    assert all("réponse absente" in resultat["raisons"] for resultat in bilan["resultats"])


def test_comparaison_malformee_ne_leve_pas():
    assert ep.comparer_reponses({})["coherence_verite"] is False
    assert ep.comparer_reponses({"a": None, "b": None})["coherence_verite"] is False
    assert ep.comparer_reponses("pas des réponses")["coherence_verite"] is False


def test_cles_alternatives_et_normalisation_des_faits_et_sections():
    cas = ep.CasProfil(
        id="normalisation",
        question="Question ?",
        profil_id="lecture",
        faits_attendus=("Latence p95 à 800 ms",),
        sections_attendues=("Impact technique",),
        autorite_max=0,
    )
    reponse = {
        "facts": ["LATENCE P95 A 800 MS"],
        "lecture": ["impact technique"],
        "actions": [],
        "autorite": "lecture",
    }
    resultat = ep.evaluer_reponse(cas, reponse)
    assert resultat["ok"] is True
    assert resultat["score_verite"] == 1.0
    assert resultat["score_adaptation"] == 1.0


def test_les_faits_en_mapping_et_les_objets_sont_acceptes():
    cas = _cas("developpeur")

    class Reponse:
        faits = {"pic_charge_14h": "Un pic de charge à 14 h",
                 "latence_p95_800ms": "Latence p95 à 800 ms",
                 "taux_erreur_2pct": "Taux d'erreur à 2 %"}
        sections = cas.sections_attendues
        actions = ()
        autorite = "informer"

    resultat = ep.evaluer_reponse(cas, Reponse())
    assert resultat["score_verite"] == 1.0
    assert resultat["score_adaptation"] == 1.0
    assert resultat["score_securite"] == 1.0


def test_charger_json_depuis_un_texte():
    texte = json.dumps([{
        "id": "json",
        "question": "Question ?",
        "profil_id": "developpeur",
        "faits_attendus": ["fait"],
        "sections_attendues": ["impact_technique"],
        "actions_interdites": ["modifier"],
        "autorite_max": 1,
    }])
    cas = ep.charger_json(texte)
    assert len(cas) == 1
    assert cas[0].id == "json"
    assert cas[0].autorite_max == 1
    assert cas[0].tags == ()
