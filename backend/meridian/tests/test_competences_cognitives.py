"""Registre des compétences cognitives : intégrité, spécialités, sélection et sérialisation."""
import dataclasses

import pytest

from meridian.domain.competences_cognitives import CATALOGUE_COMPETENCES, SPECIALISTES, Competence, as_dict, competence_par_id, competences_du_specialiste, competences_pour, valider_competences
from meridian.domain.methodes_cognitives import CATALOGUE_METHODES

ATTENDUES = {
    "lire_interfaces",
    "compiler_manifestes",
    "verifier_preuve",
    "detecter_contradiction",
    "analyser_impact",
    "tracer_chemin",
    "retrouver_learning",
    "mesurer_outcome",
    "modeliser_processus",
    "faciliter_decision",
    "evaluer_risque",
    "qualifier_donnee",
    "rechercher_memoire",
    "rediger_adr",
}


def test_le_catalogue_est_complet_et_coherent():
    ids = [competence.id for competence in CATALOGUE_COMPETENCES]
    assert len(ids) == len(set(ids))
    assert ATTENDUES <= set(ids)

    requises = {
        competence
        for methode in CATALOGUE_METHODES
        for competence in methode.competences
    }
    assert requises <= set(ids)

    for competence in CATALOGUE_COMPETENCES:
        assert competence.nom and competence.description
        assert competence.specialiste in SPECIALISTES
        assert isinstance(competence.outils, tuple)
        assert isinstance(competence.eval, tuple)
        assert competence.entrees and competence.sorties
        assert isinstance(competence.lecture_seule, bool)


def test_les_fiches_sont_immuables_et_les_alias_sont_coherents():
    competence = competence_par_id("verifier_preuve")
    with pytest.raises(dataclasses.FrozenInstanceError):
        competence.nom = "Autre"

    assert competence.specialite == competence.specialiste

    minimale = Competence(id="Exemple", nom="Exemple", description="Description")
    assert minimale.id == "exemple"
    assert minimale.specialiste == "outil"
    assert minimale.outils == ()
    assert minimale.eval == ()


def test_lookup_et_validation_des_ids():
    assert competence_par_id("VERIFIER_PREUVE").id == "verifier_preuve"
    assert competence_par_id("inventee") is None

    validees = valider_competences(["verifier_preuve", "analyser_impact", "verifier_preuve"])
    assert [competence.id for competence in validees] == ["verifier_preuve", "analyser_impact"]
    validees = valider_competences("rediger_adr,verifier_preuve")
    assert [competence.id for competence in validees] == ["rediger_adr", "verifier_preuve"]

    with pytest.raises(ValueError, match="inconnue"):
        valider_competences(["verifier_preuve", "inventee"])


def test_competences_du_specialiste_et_limite():
    preuve = competences_du_specialiste("preuve")
    assert {"verifier_preuve", "detecter_contradiction", "evaluer_risque"} <= {
        competence.id for competence in preuve
    }
    assert all(competence.specialiste == "preuve" for competence in preuve)
    assert len(competences_du_specialiste("outil", limite=1)) == 1
    assert competences_du_specialiste("inconnu") == ()


def test_selection_developpeur_privilegie_rediger_adr():
    profil = {"postures": ["concepteur"], "competences": ["rediger_adr"]}
    choix = competences_pour(profil, "consigner une architecture", limite=4)

    assert choix[0].id == "rediger_adr"
    assert len(choix) <= 4
    assert all(competence in CATALOGUE_COMPETENCES for competence in choix)


def test_un_profil_objet_est_accepte_sans_import_de_profils():
    class Profil:
        postures = ("concepteur",)
        competences = ("rediger_adr",)
        specialiste = "impact"

    choix = competences_pour(Profil(), "consigner une décision", limite=3)

    assert choix[0].id == "rediger_adr"
    assert len(choix) <= 3


def test_selection_po_privilegie_faciliter_decision():
    profil = {"postures": ["facilitateur"], "competences": ["faciliter_decision"]}
    choix = competences_pour(profil, "prioriser le backlog", limite=5)

    assert choix[0].id == "faciliter_decision"
    assert {competence.id for competence in choix} <= {
        competence.id for competence in CATALOGUE_COMPETENCES
    }


def test_selection_support_incident_privilegie_preuve_et_chemin():
    profil = {"postures": ["operateur", "investigateur"]}
    choix = competences_pour(
        profil, "incident avec preuve contradictoire et chemin de dépendance", limite=6)
    ids = {competence.id for competence in choix}

    assert {"verifier_preuve", "detecter_contradiction", "tracer_chemin"} <= ids


def test_selection_risque_privilegie_evaluer_risque():
    profil = {"postures": ["gardien"]}
    choix = competences_pour(profil, "risque de conformité", limite=5)

    assert choix[0].id == "evaluer_risque"


def test_profil_inconnu_rend_un_noyau_general_borne():
    profil = {"postures": ["inventee"], "competences": ["inventee"]}
    choix = competences_pour(profil, "sujet sans indice", limite=8)

    assert {competence.id for competence in choix} == {"rechercher_memoire", "verifier_preuve"}
    assert all(competence in CATALOGUE_COMPETENCES for competence in choix)
    assert competences_pour(None, "", limite=1)[0].id == "rechercher_memoire"


def test_selection_deterministe_et_sans_invention():
    profil = {"postures": ["concepteur"], "competences": ["verifier_preuve", "inventee"]}
    premier = competences_pour(profil, "preuve et impact", limite=8)
    second = competences_pour(profil, "preuve et impact", limite=8)

    assert [competence.id for competence in premier] == [competence.id for competence in second]
    assert {competence.id for competence in premier} <= {
        competence.id for competence in CATALOGUE_COMPETENCES
    }
    assert all(competence_par_id(competence.id) is not None for competence in premier)


def test_les_bornes_sont_respectees():
    profil = {"postures": ["concepteur"]}

    assert competences_pour(profil, "", limite=0) == []
    assert competences_pour(profil, "", limite=-3) == []
    assert len(competences_pour(profil, "", limite=2)) <= 2
    assert len(competences_pour(profil, "", limite=1000)) <= len(CATALOGUE_COMPETENCES)
    assert len(competences_pour(profil, "", limite="2")) <= 2


def test_as_dict_est_serialisable_et_fidele():
    competence = competence_par_id("verifier_preuve")
    vue = competence.as_dict()

    assert vue["id"] == "verifier_preuve"
    assert vue["specialiste"] == "preuve"
    assert vue["outils"] == list(competence.outils)
    assert vue["entrees"] == competence.entrees
    assert vue["sorties"] == competence.sorties
    assert vue["eval"] == list(competence.eval)
    assert vue["lecture_seule"] == competence.lecture_seule
    assert as_dict("verifier_preuve") == vue

    with pytest.raises(ValueError, match="inconnue"):
        as_dict("inconnue")
