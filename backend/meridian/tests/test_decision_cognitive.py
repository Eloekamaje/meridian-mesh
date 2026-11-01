"""Decision cognitive : contrefactuel déclaratif, calibration et enrichissement sans invention."""
from copy import deepcopy
import sqlite3

import pytest

from meridian.adapters.outbound.postgres import calibration
from meridian.adapters.outbound.postgres import decision_cognitive


@pytest.fixture
def conn_calibration():
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


def test_construire_contrefactuel_delegue_sans_recommandation(monkeypatch):
    appels = {}

    def faux(options, changements=None, *, criteres=()):
        appels.update({
            "options": options,
            "changements": changements,
            "criteres": criteres,
        })
        return {"options": [], "recommandation": None}

    monkeypatch.setattr(decision_cognitive.contrefactuel, "comparer", faux)
    options = [{"id": "a", "valeurs": {"score": 3}}]
    changements = {"score": 1}

    resultat = decision_cognitive.construire_contrefactuel(
        options, changements, criteres=("score",))

    assert appels == {
        "options": options,
        "changements": changements,
        "criteres": ("score",),
    }
    assert resultat["recommandation"] is None


def test_contrefactuel_reel_reste_declaratif_et_ne_mute_pas_les_entrees():
    options = [
        {"id": "a", "valeurs": {"score": 3}, "deltas": {"cout": -1}},
        {"id": "b", "valeurs": {"score": 2}},
    ]
    avant = deepcopy(options)

    resultat = decision_cognitive.construire_contrefactuel(
        options, {"score": 1}, criteres=("score", "cout"))

    assert resultat["impacts"] == {
        "a": {"score": 4.0, "cout": -1.0},
        "b": {"score": 3.0, "cout": None},
    }
    assert resultat["recommandation"] is None
    assert options == avant


def test_enregistrer_confiance_delegue_avec_prediction_id(monkeypatch):
    appels = {}
    attendu = object()

    def faux(conn, tenant, *, id=None, decision_id, confidence, outcome=None):
        appels.update({
            "conn": conn,
            "tenant": tenant,
            "id": id,
            "decision_id": decision_id,
            "confidence": confidence,
            "outcome": outcome,
        })
        return attendu

    monkeypatch.setattr(decision_cognitive.calibration, "enregistrer", faux)

    resultat = decision_cognitive.enregistrer_confiance(
        "connexion", "banque", decision_id="d1", confidence=0.8, prediction_id="p1")

    assert resultat is attendu
    assert appels == {
        "conn": "connexion",
        "tenant": "banque",
        "id": "p1",
        "decision_id": "d1",
        "confidence": 0.8,
        "outcome": None,
    }


def test_resoudre_outcome_delegue(monkeypatch):
    appels = {}
    attendu = object()

    def faux(conn, tenant, id, outcome):
        appels.update({"conn": conn, "tenant": tenant, "id": id, "outcome": outcome})
        return attendu

    monkeypatch.setattr(decision_cognitive.calibration, "resoudre", faux)

    resultat = decision_cognitive.resoudre_outcome("connexion", "banque", "p1", True)

    assert resultat is attendu
    assert appels == {
        "conn": "connexion", "tenant": "banque", "id": "p1", "outcome": True}


def test_calibration_reelle_resout_dans_le_tenant(conn_calibration):
    creee = decision_cognitive.enregistrer_confiance(
        conn_calibration, "banque", decision_id="d1", confidence=0.75, prediction_id="p1")

    assert creee.id == "p1"
    assert creee.tenant == "banque"
    assert creee.decision_id == "d1"
    assert creee.confidence == 0.75
    assert creee.outcome is None

    with pytest.raises(calibration.PredictionIntrouvable):
        decision_cognitive.resoudre_outcome(conn_calibration, "assurance", "p1", True)
    assert calibration.lire(conn_calibration, "banque", "p1").outcome is None

    resolue = decision_cognitive.resoudre_outcome(conn_calibration, "banque", "p1", True)
    assert resolue.outcome is True
    assert calibration.lire(conn_calibration, "banque", "p1").outcome is True


@pytest.mark.parametrize(
    "champs",
    [
        {"decision_id": None, "confidence": 0.5},
        {"decision_id": "   ", "confidence": 0.5},
        {"decision_id": "d1", "confidence": None},
        {"decision_id": "d1", "confidence": 1.2},
        {"decision_id": "d1", "confidence": True},
    ],
)
def test_enregistrer_confiance_refuse_les_valeurs_manquantes(conn_calibration, champs):
    with pytest.raises(calibration.CalibrationInvalide):
        decision_cognitive.enregistrer_confiance(conn_calibration, "banque", **champs)


def test_resoudre_outcome_refuse_les_valeurs_manquantes(conn_calibration):
    decision_cognitive.enregistrer_confiance(
        conn_calibration, "banque", decision_id="d1", confidence=0.5, prediction_id="p1")

    with pytest.raises(calibration.CalibrationInvalide):
        decision_cognitive.resoudre_outcome(conn_calibration, "banque", None, True)
    with pytest.raises(calibration.CalibrationInvalide):
        decision_cognitive.resoudre_outcome(conn_calibration, "banque", "p1", None)


def test_decision_support_sans_options_ne_calcule_rien_et_ne_mute_pas(monkeypatch):
    appels = []
    monkeypatch.setattr(
        decision_cognitive.contrefactuel,
        "comparer",
        lambda *args, **kwargs: appels.append((args, kwargs)),
    )
    base = {"options": [{"id": "a"}], "recommandation": None, "abstention": None}
    avant = deepcopy(base)

    resultat = decision_cognitive.decision_support_enrichi(base)

    assert resultat == {**base, "contrefactuel": None}
    assert base == avant
    assert appels == []


def test_decision_support_avec_options_ajoute_le_seul_contrefactuel(monkeypatch):
    appels = {}
    retour = {"criteres": ["score"], "recommandation": None}

    def faux(options, changements=None, *, criteres=()):
        appels.update({
            "options": options,
            "changements": changements,
            "criteres": criteres,
        })
        return retour

    monkeypatch.setattr(decision_cognitive.contrefactuel, "comparer", faux)
    base = {
        "options": [{"id": "a", "label": "Garder"}],
        "conditions_de_retournement": ["si le volume double"],
        "recommandation": None,
    }
    avant = deepcopy(base)
    options = [{"id": "a", "valeurs": {"score": 3}}]
    changements = {"score": 1}

    resultat = decision_cognitive.decision_support_enrichi(
        base, options=options, changements=changements, criteres=("score",))

    assert resultat == {**base, "contrefactuel": retour}
    assert base == avant
    assert appels == {
        "options": options,
        "changements": changements,
        "criteres": ("score",),
    }


def test_decision_support_avec_options_reelles_ne_produit_pas_de_recommandation():
    base = {"options": [{"id": "a"}], "recommandation": None}
    avant = deepcopy(base)

    resultat = decision_cognitive.decision_support_enrichi(
        base,
        options=[{"id": "a", "valeurs": {"score": 3}}],
        criteres=("score",),
    )

    assert resultat["contrefactuel"]["impacts"] == {"a": {"score": 3.0}}
    assert resultat["contrefactuel"]["recommandation"] is None
    assert base == avant


def test_decision_support_invalide_refuse():
    with pytest.raises(TypeError):
        decision_cognitive.decision_support_enrichi(None)


def test_calibrer_decision_support_enregistre_puis_resout_sans_inventer(conn_calibration):
    support = {"decision_id": "d1", "confidence": 0.8}

    prediction = decision_cognitive.calibrer_decision_support(
        conn_calibration, "banque", support)

    assert prediction.decision_id == "d1"
    assert prediction.confidence == 0.8
    assert prediction.outcome is None
    assert len(calibration.lister(conn_calibration, "banque", "d1")) == 1

    encore = decision_cognitive.calibrer_decision_support(
        conn_calibration, "banque", support)
    assert encore.id == prediction.id
    assert len(calibration.lister(conn_calibration, "banque", "d1")) == 1

    resolue = decision_cognitive.calibrer_decision_support(
        conn_calibration, "banque", {**support, "outcome": True})
    assert resolue.outcome is True
    assert calibration.lire(conn_calibration, "banque", prediction.id).outcome is True


def test_calibrer_decision_support_sans_decision_n_ecrit_rien(conn_calibration):
    for support in (
        None,
        {},
        {"confidence": 0.8},
        {"decision_id": "d1"},
        {"decision_id": "d1", "confidence": None},
        {"decision_id": "   ", "confidence": 0.8},
    ):
        assert decision_cognitive.calibrer_decision_support(
            conn_calibration, "banque", support) is None

    assert calibration.lister(conn_calibration, "banque") == []


def test_calibrer_decision_support_refuse_un_outcome_non_booleen_sans_ecrire(conn_calibration):
    with pytest.raises(calibration.CalibrationInvalide):
        decision_cognitive.calibrer_decision_support(
            conn_calibration, "banque",
            {"decision_id": "d1", "confidence": 0.5, "outcome": "oui"})

    assert calibration.lister(conn_calibration, "banque") == []


def test_calibrer_decision_support_refuse_une_prediction_d_une_autre_decision(conn_calibration):
    decision_cognitive.enregistrer_confiance(
        conn_calibration, "banque", decision_id="d1", confidence=0.5, prediction_id="p1")

    with pytest.raises(calibration.CalibrationInvalide):
        decision_cognitive.calibrer_decision_support(
            conn_calibration, "banque",
            {"decision_id": "d2", "confidence": 0.5}, prediction_id="p1")

    assert calibration.lire(conn_calibration, "banque", "p1").decision_id == "d1"
