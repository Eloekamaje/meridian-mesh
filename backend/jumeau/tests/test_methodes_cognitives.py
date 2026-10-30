"""Registre des méthodes cognitives : intégrité, sélection, bornes et sérialisation."""
import dataclasses

import pytest

from jumeau.competences_cognitives import CATALOGUE_COMPETENCES
from jumeau.methodes_cognitives import (
    CATALOGUE_METHODES,
    MODES_PREUVE,
    POSTURES,
    Methode,
    as_dict,
    methode_par_id,
    methodes_pour,
    valider_methodes,
)

ATTENDUES = {
    "babok",
    "bpmn",
    "impact_mapping",
    "story_mapping",
    "scrum",
    "kanban",
    "okr",
    "pmbok",
    "postmortem",
    "adr",
    "a3",
    "benefits",
    "capa",
    "dama",
}


def test_le_catalogue_est_complet_et_coherent():
    ids = [methode.id for methode in CATALOGUE_METHODES]
    assert len(ids) == len(set(ids))
    assert ATTENDUES <= set(ids)

    competences = {competence.id for competence in CATALOGUE_COMPETENCES}
    for methode in CATALOGUE_METHODES:
        assert methode.nom and methode.description and methode.version
        assert methode.mode_preuve in MODES_PREUVE
        assert isinstance(methode.lecture_seule, bool)
        assert methode.postures and set(methode.postures) <= set(POSTURES)
        assert methode.competences and set(methode.competences) <= competences
        assert len(methode.etapes) >= 3
        assert methode.artefacts
        assert methode.gates
        assert all(gate.lower().startswith(("humain", "preuve")) for gate in methode.gates)


def test_les_fiches_sont_immuables_et_les_alias_sont_coherents():
    methode = methode_par_id("adr")
    with pytest.raises(dataclasses.FrozenInstanceError):
        methode.nom = "Autre"

    assert methode.postures_compatibles == methode.postures
    assert methode.competences_requises == methode.competences
    assert methode.artefacts_attendus == methode.artefacts
    assert methode.gate == methode.gates[0]

    minimale = Methode(id="Exemple", nom="Exemple", description="Description")
    assert minimale.id == "exemple"
    assert minimale.postures == ()
    assert minimale.gate is None


def test_lookup_et_validation_des_ids():
    assert methode_par_id("BPMN").id == "bpmn"
    assert methode_par_id("inconnue") is None

    validees = valider_methodes(["bpmn", "adr", "bpmn"])
    assert [methode.id for methode in validees] == ["bpmn", "adr"]
    assert [methode.id for methode in valider_methodes("adr,postmortem")] == ["adr", "postmortem"]

    with pytest.raises(ValueError, match="inconnue"):
        valider_methodes(["bpmn", "inventee"])


def test_selection_developpeur_privilegie_architecture_et_adr():
    profil = {"postures": ["concepteur"], "competences": ["rediger_adr", "analyser_impact"]}
    choix = methodes_pour(profil, "choisir une architecture et consigner la décision", limite=4)

    assert choix[0].id == "adr"
    assert len(choix) <= 4
    assert all(methode in CATALOGUE_METHODES for methode in choix)


def test_un_profil_objet_est_accepte_sans_import_de_profils():
    class Profil:
        postures = ("concepteur",)
        methodes = ("adr",)
        competences = ("rediger_adr",)

    choix = methodes_pour(Profil(), "consigner une décision", limite=3)

    assert choix[0].id == "adr"
    assert len(choix) <= 3


def test_selection_po_privilegie_scrum_et_roadmap():
    profil = {"postures": ["facilitateur"], "methodes": ["scrum"]}
    choix = methodes_pour(profil, "prioriser la roadmap du prochain sprint", limite=6)
    ids = {methode.id for methode in choix}

    assert choix[0].id == "scrum"
    assert {"okr", "story_mapping"} <= ids
    assert len(choix) <= 6


def test_selection_support_incident_produit_postmortem():
    profil = {"postures": ["operateur", "investigateur"]}
    choix = methodes_pour(profil, "incident SLA en production", limite=5)

    assert choix[0].id == "postmortem"
    assert len(choix) <= 5


def test_selection_risque_privilegie_capa_et_pmbok():
    profil = {"postures": ["gardien"]}
    choix = methodes_pour(profil, "risque de conformité et plan de traitement", limite=6)
    ids = [methode.id for methode in choix]

    assert ids[0] == "capa"
    assert "pmbok" in ids


def test_profil_inconnu_rend_un_noyau_general_borne():
    profil = {"postures": ["inventee"], "methodes": ["inexistante"]}
    choix = methodes_pour(profil, "sujet sans indice", limite=6)

    assert {methode.id for methode in choix} == {"adr", "postmortem"}
    assert all(methode in CATALOGUE_METHODES for methode in choix)
    assert methodes_pour(None, "", limite=1)[0].id == "adr"


def test_selection_deterministe_et_sans_invention():
    profil = {"postures": ["concepteur", "facilitateur"], "methodes": ["bpmn", "inconnue"]}
    premier = methodes_pour(profil, "processus et data", limite=6)
    second = methodes_pour(profil, "processus et data", limite=6)

    assert [methode.id for methode in premier] == [methode.id for methode in second]
    assert {methode.id for methode in premier} <= {methode.id for methode in CATALOGUE_METHODES}
    assert all(methode_par_id(methode.id) is not None for methode in premier)


def test_les_bornes_sont_respectees():
    profil = {"postures": ["concepteur"]}

    assert methodes_pour(profil, "", limite=0) == []
    assert methodes_pour(profil, "", limite=-3) == []
    assert len(methodes_pour(profil, "", limite=2)) <= 2
    assert len(methodes_pour(profil, "", limite=1000)) <= len(CATALOGUE_METHODES)
    assert len(methodes_pour(profil, "", limite="2")) <= 2


def test_as_dict_est_serialisable_et_fidele():
    methode = methode_par_id("postmortem")
    vue = methode.as_dict()

    assert vue["id"] == "postmortem"
    assert vue["postures"] == list(methode.postures)
    assert vue["competences"] == list(methode.competences)
    assert vue["artefacts"] == list(methode.artefacts)
    assert vue["etapes"] == list(methode.etapes)
    assert vue["gates"] == list(methode.gates)
    assert vue["mode_preuve"] in MODES_PREUVE
    assert vue["lecture_seule"] == methode.lecture_seule
    assert as_dict("postmortem") == vue

    with pytest.raises(ValueError, match="inconnue"):
        as_dict("inconnue")
