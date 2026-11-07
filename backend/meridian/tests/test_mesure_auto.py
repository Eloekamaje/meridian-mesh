"""Mesure automatique : observation pure → Outcome canonique, sans Learning.

Le module testé ne lit aucune base. Il normalise une observation (générique ou issue de la
veille legacy), refuse tout ce qui est incomplet/ambigu, et construit un événement d'outbox C1
signé, d'identifiant déterministe et d'origine ``exploitation``.
"""
from __future__ import annotations

import json

import pytest

from meridian.application import mesure_auto
from meridian.application import pont_canonique as pont

TENANT = "banque"
INITIATIVE = "ini-dec-case-c1-1"
CLE = "cle-de-test-mesure-auto-32"


@pytest.fixture(autouse=True)
def _cle_pont(monkeypatch):
    monkeypatch.setenv(pont.PONT_KEY_ENV, CLE)


def _observation(**champs):
    base = {
        "id": "obs-1",
        "tenant_id": TENANT,
        "initiative_id": INITIATIVE,
        "metrique": "delai_moyen_jours",
        "attendu": {"valeur": 5, "unite": "j"},
        "observe": {"valeur": 7, "unite": "j"},
        "effets_secondaires": [
            {"type": "rework", "libelle": "reprises", "observe": 3},
        ],
        "periode": "2026-11",
        "quand": "2026-11-05T09:00:00+00:00",
        "maj_le": "2026-11-05T09:01:00+00:00",
        "source": {"type": "twin", "nom": "tbt"},
        "interpretation": "Le délai augmente malgré l'automatisation.",
    }
    base.update(champs)
    return base


def _passation():
    return {
        "attendus": [
            {"id": "att-1", "indicateur": "Délai moyen", "sens": "baisse",
             "depart": 10, "cible": 5, "unite": "j"},
        ],
        "risques": [
            {"id": "risque-1", "texte": "Rejets de paiement", "jumeau": "tbt",
             "sens": "hausse", "seuil": 3, "unite": "%"},
        ],
        "inconnues": [
            {"id": "inc-1", "texte": "Cause racine des reprises"},
        ],
    }


def _veille_observation(cible, **champs):
    observation = {
        "id": "o-1",
        "cible": cible,
        "quand": "2026-11-05T09:00:00+00:00",
        "jumeau": "tbt",
        "source": "datadog",
        "valeur": 7,
        "unite": "j",
        "conclusion": "",
    }
    observation.update(champs)
    return {
        "_id": "proj-c1-o-1",
        "id": "proj-c1-o-1",
        "tenant_id": TENANT,
        "maj_le": "2026-11-05T09:01:00+00:00",
        "case": {
            "id": "c1",
            "tenant_id": TENANT,
            "decisions": [
                {"texte": "Automatiser", "par": "alice",
                 "quand": "2026-11-01T10:00:00+00:00", "statut": "decidee"},
            ],
            "veille": {"statut": "en_veille", "passation": _passation()},
        },
        "observation": observation,
    }


# ---------------------------------------------------------------------------
# Observation générique
# ---------------------------------------------------------------------------


def test_observation_complete_produit_un_outcome_avec_attendu_observe_effets_et_periode():
    resultat = mesure_auto.mesurer_observation(_observation())

    assert resultat.produit is True
    assert resultat.raison is None
    mesure = resultat.mesure
    assert mesure.tenant_id == TENANT
    assert mesure.observation_id == "obs-1"
    assert mesure.initiative_id == INITIATIVE
    assert mesure.metrique == "delai_moyen_jours"
    assert mesure.attendu == {"valeur": 5, "unite": "j"}
    assert mesure.observe == {"valeur": 7, "unite": "j"}
    assert mesure.effets_secondaires == (
        {"type": "rework", "libelle": "reprises", "observe": 3},
    )
    assert mesure.periode == "2026-11"
    assert mesure.mesure_le == "2026-11-05T09:00:00+00:00"

    evenement = resultat.evenement
    assert evenement["operation"] == pont.OPERATION_OUTCOME
    assert evenement["tenant_id"] == TENANT
    assert evenement["payload"]["initiative_id"] == INITIATIVE

    outcome = pont.objets_depuis_evenement(evenement, tenant_id=TENANT)[0]
    assert outcome["type"] == "OUTCOME"
    assert outcome["donnees"]["valeur_attendue"] == {"valeur": 5, "unite": "j"}
    assert outcome["donnees"]["valeur_observee"] == 7
    assert outcome["donnees"]["effets_secondaires"] == [
        {"type": "rework", "libelle": "reprises", "observe": 3},
    ]
    assert outcome["donnees"]["periode"] == "2026-11"
    assert outcome["donnees"]["_pont"]["origine"] == pont.ORIGINE_EXPLOITATION


def test_id_deterministe_et_rejeu_produit_le_meme_evenement():
    premier = mesure_auto.mesurer_observation(_observation())
    second = mesure_auto.mesurer_observation(_observation())

    assert premier.produit and second.produit
    assert premier.evenement["_id"] == second.evenement["_id"]
    assert premier.evenement["canonical_id"] == second.evenement["canonical_id"]
    assert premier.evenement["payload"] == second.evenement["payload"]
    assert premier.evenement["signature"] == second.evenement["signature"]


def test_l_identifiant_change_quand_le_contenu_de_l_observation_change():
    premier = mesure_auto.mesurer_observation(_observation())
    second = mesure_auto.mesurer_observation(_observation(observe={"valeur": 8, "unite": "j"}))

    assert premier.evenement["canonical_id"] == second.evenement["canonical_id"]
    assert premier.evenement["_id"] != second.evenement["_id"]


def test_periode_derivee_de_quand_et_periode_explicite_respectee():
    sans_periode = _observation()
    sans_periode.pop("periode")
    assert mesure_auto.mesurer_observation(sans_periode).mesure.periode == "2026-11"

    explicite = _observation(periode="2026-11-01/2026-11-07")
    assert mesure_auto.mesurer_observation(explicite).mesure.periode == "2026-11-01/2026-11-07"


def test_la_mesure_porte_la_source_de_l_observation_et_l_origine_exploitation():
    resultat = mesure_auto.mesurer_observation(_observation())
    mesure = resultat.evenement["payload"]["mesure"]

    assert mesure["attendu"] == {"valeur": 5, "unite": "j"}
    assert mesure["observe"] == {"valeur": 7, "unite": "j"}
    assert mesure["effets_secondaires"] == [
        {"type": "rework", "libelle": "reprises", "observe": 3},
    ]
    assert mesure["source_observation"]["id"] == "obs-1"
    assert "token" not in json.dumps(mesure).lower()


@pytest.mark.parametrize("champ", ["id", "tenant_id", "quand"])
def test_observation_incomplete_ne_produit_rien_et_expose_la_raison(champ):
    document = _observation()
    document.pop(champ)

    resultat = mesure_auto.mesurer_observation(document)

    assert resultat.produit is False
    assert resultat.evenement is None
    assert resultat.raison
    assert champ.split("_")[0] in resultat.raison.lower()


@pytest.mark.parametrize("observe", [None, "", [], {}, True, False])
def test_mesure_observee_vide_ou_booleenne_ne_produit_rien(observe):
    resultat = mesure_auto.mesurer_observation(_observation(observe=observe))

    assert resultat.produit is False
    assert "observ" in resultat.raison.lower()


def test_initiative_absente_ne_produit_rien():
    document = _observation()
    document.pop("initiative_id")

    resultat = mesure_auto.mesurer_observation(document)

    assert resultat.produit is False
    assert "initiative" in resultat.raison.lower()


def test_initiative_derivee_d_une_decision_canonique():
    document = _observation(decision_id="dec-case-c1-1")
    document.pop("initiative_id")

    resultat = mesure_auto.mesurer_observation(document)

    assert resultat.produit is True
    assert resultat.mesure.initiative_id == "ini-dec-case-c1-1"


def test_metrique_absente_ne_produit_rien():
    document = _observation()
    document.pop("metrique")

    resultat = mesure_auto.mesurer_observation(document)

    assert resultat.produit is False
    assert "métrique" in resultat.raison.lower() or "metrique" in resultat.raison.lower()


def test_tenant_incoherent_est_refuse_sans_produire():
    resultat = mesure_auto.mesurer_observation(_observation(), tenant_id="assurance")

    assert resultat.produit is False
    assert "tenant" in resultat.raison.lower()


def test_quand_illisible_ne_produit_rien():
    resultat = mesure_auto.mesurer_observation(_observation(quand="hier soir"))

    assert resultat.produit is False
    assert "quand" in resultat.raison.lower()


def test_aucun_learning_n_est_produit():
    resultat = mesure_auto.mesurer_observation(_observation())

    evenement = resultat.evenement
    assert evenement["operation"] == pont.OPERATION_OUTCOME
    assert evenement["operation"] != pont.OPERATION_LEARNING
    assert "learning" not in json.dumps(evenement["payload"]).lower()
    assert "enseignement" not in json.dumps(evenement["payload"]).lower()


# ---------------------------------------------------------------------------
# Observation de veille legacy (note de passation)
# ---------------------------------------------------------------------------


def test_veille_attendu_mappe_attendu_et_observe():
    resultat = mesure_auto.mesurer_observation(_veille_observation("att-1"))

    assert resultat.produit is True
    mesure = resultat.mesure
    assert mesure.type_observation == "attendu"
    assert mesure.metrique == "Délai moyen"
    assert mesure.attendu["cible"] == 5 and mesure.attendu["depart"] == 10
    assert mesure.observe == {"valeur": 7, "unite": "j", "conclusion": ""}
    assert mesure.effets_secondaires == ()
    assert mesure.initiative_id == "ini-dec-case-c1-1"
    assert "7" in mesure.interpretation and "5" in mesure.interpretation


def test_veille_risque_franchi_produit_un_effet_secondaire_materialise():
    resultat = mesure_auto.mesurer_observation(
        _veille_observation("risque-1", valeur=5, unite="%"))

    assert resultat.produit is True
    mesure = resultat.mesure
    assert mesure.type_observation == "risque"
    assert mesure.metrique == "risque:Rejets de paiement"
    assert mesure.attendu["seuil"] == 3
    assert mesure.effets_secondaires == ({
        "type": "risque_materialise",
        "libelle": "Rejets de paiement",
        "attendu": {"seuil": 3, "sens": "hausse", "unite": "%"},
        "observe": 5,
        "seuil": 3,
        "sens": "hausse",
        "unite": "%",
        "jumeau": "tbt",
    },)


def test_veille_risque_sous_le_seuil_reste_un_risque_maitrise():
    resultat = mesure_auto.mesurer_observation(
        _veille_observation("risque-1", valeur=2, unite="%"))

    assert resultat.produit is True
    assert resultat.mesure.effets_secondaires[0]["type"] == "risque_maitrise"


def test_veille_inconnue_levee():
    resultat = mesure_auto.mesurer_observation(
        _veille_observation("inc-1", valeur=None, conclusion="Le cache sature."))

    assert resultat.produit is True
    mesure = resultat.mesure
    assert mesure.type_observation == "inconnue"
    assert mesure.metrique == "inconnue:Cause racine des reprises"
    assert mesure.attendu is None
    assert mesure.observe == "Le cache sature."


def test_veille_inconnue_sans_conclusion_ne_produit_rien():
    resultat = mesure_auto.mesurer_observation(
        _veille_observation("inc-1", valeur=None, conclusion=""))

    assert resultat.produit is False
    assert "conclusion" in resultat.raison.lower()


def test_veille_cible_inconnue_ne_produit_rien():
    resultat = mesure_auto.mesurer_observation(_veille_observation("inconnue-42"))

    assert resultat.produit is False
    assert "cible" in resultat.raison.lower()


def test_veille_sans_passation_ne_produit_rien():
    document = _veille_observation("att-1")
    document["case"]["veille"] = {"statut": "en_veille"}

    resultat = mesure_auto.mesurer_observation(document)

    assert resultat.produit is False
    assert "passation" in resultat.raison.lower()


def test_veille_attendu_sans_valeur_numerique_ne_produit_rien():
    resultat = mesure_auto.mesurer_observation(
        _veille_observation("att-1", valeur="beaucoup"))

    assert resultat.produit is False
    assert "numérique" in resultat.raison.lower() or "numerique" in resultat.raison.lower()


def test_veille_sans_decision_tranchee_ne_produit_rien():
    document = _veille_observation("att-1")
    document["case"]["decisions"] = [{"texte": "Peut-être", "statut": "proposee"}]

    resultat = mesure_auto.mesurer_observation(document)

    assert resultat.produit is False
    assert "décision" in resultat.raison.lower() or "decision" in resultat.raison.lower()


def test_veille_observation_sans_id_ne_produit_rien():
    document = _veille_observation("att-1")
    document["observation"].pop("id")

    resultat = mesure_auto.mesurer_observation(document)

    assert resultat.produit is False
    assert "id" in resultat.raison.lower()


def test_veille_tenant_incoherent_est_refuse():
    document = _veille_observation("att-1")
    document["case"]["tenant_id"] = "assurance"

    resultat = mesure_auto.mesurer_observation(document)

    assert resultat.produit is False
    assert "tenant" in resultat.raison.lower()


# ---------------------------------------------------------------------------
# Bords du normaliseur
# ---------------------------------------------------------------------------


def test_observation_non_mapping_ne_produit_rien():
    resultat = mesure_auto.mesurer_observation(None)

    assert resultat.produit is False
    assert "observation" in resultat.raison.lower()


def test_effets_secondaires_mapping_unique_et_chaine_sont_tolerees():
    resultat = mesure_auto.mesurer_observation(_observation(
        effets_secondaires=[{"type": "latence"}, "reprise manuelle"]))

    assert resultat.mesure.effets_secondaires == (
        {"type": "latence"},
        {"libelle": "reprise manuelle"},
    )


def test_effets_secondaires_invalides_ne_produisent_rien():
    resultat = mesure_auto.mesurer_observation(_observation(effets_secondaires=42))

    assert resultat.produit is False
    assert "effets_secondaires" in resultat.raison


def test_initiative_incoherente_entre_argument_et_document():
    resultat = mesure_auto.mesurer_observation(
        _observation(), initiative_id="ini-autre")

    assert resultat.produit is False
    assert "initiative" in resultat.raison.lower()


def test_source_textuelle_est_normalisee():
    resultat = mesure_auto.mesurer_observation(_observation(source="datadog:prod"))

    assert resultat.mesure.source["nom"] == "datadog:prod"
    assert resultat.mesure.source["id"] == "obs-1"


def test_valeur_non_finie_ne_produit_rien():
    resultat = mesure_auto.mesurer_observation(_observation(observe=float("nan")))

    assert resultat.produit is False
    assert "observ" in resultat.raison.lower()


def test_metrique_derivee_de_l_attendu():
    document = _observation(attendu={"indicateur": "Délai moyen", "cible": 5})
    document.pop("metrique")

    resultat = mesure_auto.mesurer_observation(document)

    assert resultat.produit is True
    assert resultat.mesure.metrique == "Délai moyen"


def test_quand_accepte_une_date():
    from datetime import date

    resultat = mesure_auto.mesurer_observation(_observation(quand=date(2026, 11, 5)))

    assert resultat.produit is True
    assert resultat.mesure.mesure_le == "2026-11-05T00:00:00+00:00"


def test_evenement_outcome_sans_origine_reste_legacy():
    evenement = pont.evenement_outcome(
        tenant_id=TENANT, initiative_id=INITIATIVE,
        mesure={"metrique": "delai", "valeur": 2}, metrique="delai",
        periode="2026-11", source_event_id="out-legacy")

    outcome = pont.objets_depuis_evenement(evenement, tenant_id=TENANT)[0]
    assert outcome["donnees"]["_pont"]["origine"] == pont.ORIGINE_LEGACY
