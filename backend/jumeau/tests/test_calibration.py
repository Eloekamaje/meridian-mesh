"""Calibration : Brier, tranches, exclusion des non-résolues, tenant et validation."""
import sqlite3

import pytest

from jumeau import calibration


@pytest.fixture
def conn():
    connexion = sqlite3.connect(":memory:")
    connexion.execute(
        "CREATE TABLE prediction_calibration ("
        " id TEXT NOT NULL,"
        " tenant_id TEXT NOT NULL,"
        " decision_id TEXT NOT NULL,"
        " confidence REAL NOT NULL,"
        " outcome INTEGER,"
        " cree_le TEXT,"
        " resolue_le TEXT,"
        " PRIMARY KEY (tenant_id, id))"
    )
    yield connexion
    connexion.close()


def test_enregistrer_lire_lister_et_resoudre(conn):
    creee = calibration.enregistrer(conn, "banque", id="p1", decision_id="d1", confidence=0.8)

    assert creee.id == "p1"
    assert creee.tenant == "banque"
    assert creee.decision_id == "d1"
    assert creee.confidence == 0.8
    assert creee.outcome is None
    assert creee.resolue_le is None

    lue = calibration.lire(conn, "banque", "p1")
    assert lue is not None
    assert (lue.id, lue.tenant, lue.decision_id, lue.confidence, lue.outcome) == (
        "p1", "banque", "d1", 0.8, None)
    assert lue["tenant_id"] == "banque" and lue["outcome"] is None
    assert lue.get("inconnu") is None

    resolue = calibration.resoudre(conn, "banque", creee, False)
    assert resolue.outcome is False
    assert resolue.resolue_le is not None
    assert calibration.lire(conn, "banque", "p1").outcome is False

    autre = calibration.enregistrer(
        conn, "banque", decision_id="d1", confidence=0.4, outcome=True)
    assert autre.id.startswith("pred-")
    assert autre.outcome is True
    assert autre.resolue_le is not None

    listing = calibration.lister(conn, "banque", decision_id="d1")
    assert {prediction.id for prediction in listing} == {"p1", autre.id}
    assert calibration.lister(conn, "banque", decision_id="d2") == []


def test_brier_sur_les_seules_predictions_resolues(conn):
    calibration.enregistrer(conn, "banque", id="p1", decision_id="d1", confidence=0.8, outcome=True)
    calibration.enregistrer(conn, "banque", id="p2", decision_id="d1", confidence=0.3, outcome=False)
    calibration.enregistrer(conn, "banque", id="p3", decision_id="d1", confidence=0.5)
    calibration.enregistrer(conn, "banque", id="p4", decision_id="d2", confidence=0.9, outcome=False)

    assert calibration.brier(conn, "banque", decision_id="d1") == pytest.approx(0.065)
    assert calibration.brier(conn, "banque") == pytest.approx((0.04 + 0.09 + 0.81) / 3)
    assert calibration.brier(conn, "banque", decision_id="inconnue") is None
    assert calibration.brier(conn, "autre") is None


def test_rapport_par_tranches_exclut_les_non_resolues(conn):
    for identifiant, confiance, outcome in (
        ("p1", 0.1, True),
        ("p2", 0.1, False),
        ("p3", 0.3, True),
        ("p4", 0.7, False),
        ("p5", 0.9, True),
        ("p6", 0.9, None),
    ):
        calibration.enregistrer(
            conn, "banque", id=identifiant, decision_id="d1",
            confidence=confiance, outcome=outcome)

    resultat = calibration.rapport(conn, "banque", decision_id="d1")

    assert resultat["total"] == 6
    assert resultat["resolues"] == 5
    assert resultat["non_resolues"] == 1
    assert resultat["brier"] == pytest.approx(1.81 / 5)
    assert [tranche["nombre"] for tranche in resultat["bins"]] == [2, 1, 0, 1, 1]

    premiere = resultat["bins"][0]
    assert premiere["intervalle"] == [0.0, 0.2]
    assert premiere["taux_observe"] == 0.5
    assert premiere["confiance_moyenne"] == 0.1
    assert premiere["ecart"] == pytest.approx(0.4)

    vide = resultat["bins"][2]
    assert vide["nombre"] == 0
    assert vide["taux_observe"] is None
    assert vide["ecart"] is None

    derniere = resultat["bins"][4]
    assert derniere["nombre"] == 1  # la non-résolue à 0,9 est exclue
    assert derniere["taux_observe"] == 1.0
    assert derniere["ecart"] == pytest.approx(0.1)


def test_resume_agrege_sans_inventer_de_mesure(conn):
    vide = calibration.resume(conn, "banque")
    assert vide == {
        "total": 0, "resolues": 0, "non_resolues": 0, "brier": None,
        "confiance_moyenne": None, "taux_observe": None, "ecart": None,
    }

    calibration.enregistrer(conn, "banque", id="p1", decision_id="d1", confidence=0.6, outcome=True)
    calibration.enregistrer(conn, "banque", id="p2", decision_id="d1", confidence=0.4, outcome=False)
    calibration.enregistrer(conn, "banque", id="p3", decision_id="d1", confidence=0.2)

    resultat = calibration.resume(conn, "banque", decision_id="d1")
    assert resultat["total"] == 3
    assert resultat["resolues"] == 2
    assert resultat["non_resolues"] == 1
    assert resultat["confiance_moyenne"] == 0.5
    assert resultat["taux_observe"] == 0.5
    assert resultat["ecart"] == 0.0
    assert resultat["brier"] == pytest.approx(0.16)


def test_isolation_tenant_lecture_ecriture_et_mesures(conn):
    calibration.enregistrer(conn, "banque", id="p1", decision_id="d1", confidence=0.9, outcome=True)
    calibration.enregistrer(conn, "assurance", id="p1", decision_id="d1", confidence=0.2, outcome=False)

    assert calibration.lire(conn, "banque", "p1").outcome is True
    assert calibration.lire(conn, "assurance", "p1").outcome is False
    assert [prediction.id for prediction in calibration.lister(conn, "banque")] == ["p1"]
    assert calibration.brier(conn, "banque") == pytest.approx(0.01)
    assert calibration.brier(conn, "assurance") == pytest.approx(0.04)

    calibration.resoudre(conn, "assurance", "p1", True)
    assert calibration.lire(conn, "banque", "p1").outcome is True
    assert calibration.lire(conn, "assurance", "p1").outcome is True

    with pytest.raises(calibration.PredictionIntrouvable):
        calibration.resoudre(conn, "autre", "p1", True)
    assert calibration.lire(conn, "autre", "p1") is None


@pytest.mark.parametrize("confidence", [-0.1, 1.1, float("nan"), float("inf"), True, "0.5", None])
def test_confiance_invalide_refusee(conn, confidence):
    with pytest.raises(calibration.CalibrationInvalide):
        calibration.enregistrer(conn, "banque", decision_id="d1", confidence=confidence)


@pytest.mark.parametrize("outcome", [1, 0, "true", "false", []])
def test_outcome_non_booleen_refuse(conn, outcome):
    with pytest.raises(calibration.CalibrationInvalide):
        calibration.enregistrer(
            conn, "banque", decision_id="d1", confidence=0.5, outcome=outcome)


def test_champs_obligatoires_et_limite_valides(conn):
    for arguments in (
        {"tenant": "", "decision_id": "d1", "confidence": 0.5},
        {"tenant": "banque", "decision_id": "", "confidence": 0.5},
        {"tenant": "banque", "decision_id": "d1", "confidence": 0.5, "id": ""},
    ):
        tenant = arguments.pop("tenant")
        with pytest.raises(calibration.CalibrationInvalide):
            calibration.enregistrer(conn, tenant, **arguments)

    calibration.enregistrer(conn, "banque", id="p1", decision_id="d1", confidence=0.5)
    with pytest.raises(calibration.CalibrationInvalide):
        calibration.lister(conn, "banque", limite=0)
    with pytest.raises(calibration.PredictionIntrouvable):
        calibration.resoudre(conn, "banque", "absente", True)
