"""Calibration : Brier, tranches, exclusion des non-résolues, tenant et validation."""
from datetime import datetime, timedelta, timezone
import os
import sqlite3
import uuid

import pytest

from meridian.adapters.outbound.postgres import calibration
from meridian.adapters.outbound.postgres import resolution_besoins

DSN = os.environ.get("JUMEAU_PG_DSN")
besoin_pg = pytest.mark.skipif(not DSN, reason="JUMEAU_PG_DSN non défini")

MAINTENANT = datetime(2026, 11, 16, 9, 0, tzinfo=timezone.utc)
ECHUE = (MAINTENANT - timedelta(days=1)).isoformat(timespec="seconds")
FUTURE = (MAINTENANT + timedelta(days=7)).isoformat(timespec="seconds")


@pytest.fixture
def conn():
    connexion = sqlite3.connect(":memory:", check_same_thread=False)
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


@pytest.fixture
def conn_etendue():
    """Schéma C4 : colonnes sujet/echeance/source/statut/issue en plus."""
    connexion = sqlite3.connect(":memory:", check_same_thread=False)
    connexion.execute(
        "CREATE TABLE prediction_calibration ("
        " id TEXT NOT NULL,"
        " tenant_id TEXT NOT NULL,"
        " decision_id TEXT NOT NULL,"
        " confidence REAL NOT NULL,"
        " outcome INTEGER,"
        " cree_le TEXT,"
        " resolue_le TEXT,"
        " sujet TEXT,"
        " echeance TEXT,"
        " source TEXT,"
        " statut TEXT,"
        " issue TEXT,"
        " PRIMARY KEY (tenant_id, id))"
    )
    yield connexion
    connexion.close()


@pytest.fixture
def conn_pg():
    """Schéma jetable sur la vraie base (sautée sans JUMEAU_PG_DSN)."""
    import psycopg
    from meridian.adapters.outbound.postgres import depot
    schema = f"test_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(DSN, autocommit=True) as connexion:
        connexion.execute(f"CREATE SCHEMA {schema}")
        connexion.execute(f"SET search_path TO {schema}")
        depot.appliquer_schema(connexion)
        yield connexion
        connexion.execute(f"DROP SCHEMA {schema} CASCADE")


def _prediction(sujet, probabilite=0.8, echeance=ECHUE, source="contournement", **extra):
    charge = {"sujet": sujet, "probabilite": probabilite,
              "echeance": echeance, "source": source}
    charge.update(extra)
    return charge


def _ligne(conn, identifiant, tenant="banque"):
    return conn.execute(
        "SELECT outcome, statut, issue, source, sujet, confidence "
        "FROM prediction_calibration WHERE tenant_id = ? AND id = ?",
        (tenant, identifiant)).fetchone()


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


# --- C4 : prédictions datées résolues contre les outcomes réels ---


def test_enregistrer_prediction_ouverte_puis_resolue_quand_le_signal_survient(conn_etendue):
    prediction = calibration.enregistrer_prediction(
        conn_etendue, "banque", _prediction("need-1", probabilite=0.8))

    assert prediction.statut == "ouverte"
    assert prediction.outcome is None and prediction.issue is None
    assert prediction.sujet == "need-1" and prediction.source == "contournement"
    assert prediction.decision_id == "need-1"
    assert _ligne(conn_etendue, prediction.id) == (
        None, "ouverte", None, "contournement", "need-1", 0.8)

    rapport = calibration.resoudre(
        conn_etendue, "banque", maintenant=MAINTENANT,
        observateur=lambda conn, tenant, ligne: True)

    assert rapport["totaux"] == {"echues": 1, "resolues": 1, "succes": 1,
                                 "echecs": 0, "ignorees": 0, "erreurs": 0}
    assert rapport["resolues"] == [{"id": prediction.id, "sujet": "need-1",
                                    "source": "contournement", "issue": "succes"}]
    assert _ligne(conn_etendue, prediction.id) == (
        1, "resolue", "succes", "contournement", "need-1", 0.8)
    assert calibration.lire(conn_etendue, "banque", prediction.id).outcome is True


def test_prediction_echue_signal_absent_devient_echec(conn_etendue):
    echue = calibration.enregistrer_prediction(
        conn_etendue, "banque", _prediction("need-1", probabilite=0.7))
    future = calibration.enregistrer_prediction(
        conn_etendue, "banque", _prediction("need-2", echeance=FUTURE))

    rapport = calibration.resoudre(
        conn_etendue, "banque", maintenant=MAINTENANT,
        observateur=lambda conn, tenant, ligne: False)

    assert rapport["totaux"]["resolues"] == 1
    assert rapport["totaux"]["echecs"] == 1
    assert _ligne(conn_etendue, echue.id)[:3] == (0, "resolue", "echec")
    # l'échéance non atteinte reste ouverte
    assert _ligne(conn_etendue, future.id)[:3] == (None, "ouverte", None)


def test_prediction_ouverte_non_echue_ignoree_par_la_passe(conn_etendue):
    calibration.enregistrer_prediction(
        conn_etendue, "banque", _prediction("need-2", echeance=FUTURE))

    rapport = calibration.resoudre_echues(conn_etendue, "banque", maintenant=MAINTENANT)

    assert rapport["totaux"]["echues"] == 0
    assert rapport["totaux"]["resolues"] == 0


def test_prediction_sans_sonde_est_ignoree_pas_resolue(conn_etendue):
    """Source inconnue : la passe ne peut pas juger → ignorée, jamais inventée."""
    prediction = calibration.enregistrer_prediction(
        conn_etendue, "banque", _prediction("s-1", source="source_inconnue"))

    rapport = calibration.resoudre(conn_etendue, "banque", maintenant=MAINTENANT)

    assert rapport["totaux"]["ignorees"] == 1
    assert rapport["ignorees"][0]["id"] == prediction.id
    assert _ligne(conn_etendue, prediction.id)[:3] == (None, "ouverte", None)


def test_resoudre_echues_fail_closed_erreur_remontee_prediction_ouverte(conn_etendue):
    prediction = calibration.enregistrer_prediction(
        conn_etendue, "banque", _prediction("need-1"))

    def sonde_en_panne(conn, tenant, ligne):
        raise RuntimeError("sonde indisponible")

    rapport = calibration.resoudre(
        conn_etendue, "banque", maintenant=MAINTENANT, observateur=sonde_en_panne)

    assert rapport["totaux"]["erreurs"] == 1
    assert rapport["totaux"]["resolues"] == 0
    assert "sonde indisponible" in rapport["erreurs"][0]["erreur"]
    assert _ligne(conn_etendue, prediction.id)[:3] == (None, "ouverte", None)


def test_resoudre_sans_colonnes_c4_refuse_explicitement(conn):
    with pytest.raises(calibration.CalibrationInvalide):
        calibration.resoudre(conn, "banque", maintenant=MAINTENANT)
    # un outcome sans prédiction ciblée est refusé aussi
    with pytest.raises(calibration.CalibrationInvalide):
        calibration.resoudre(conn, "banque", None, True)


@pytest.mark.parametrize("prediction", [
    {},
    {"sujet": "need-1"},
    {"sujet": "need-1", "probabilite": 0.8},
    {"sujet": "need-1", "probabilite": 0.8, "source": "  "},
    {"sujet": "need-1", "probabilite": 1.4, "source": "contournement"},
    {"sujet": "need-1", "probabilite": 0.8, "echeance": "pas-une-date",
     "source": "contournement"},
    {"sujet": "need-1", "probabilite": 0.8, "source": "contournement", "outcome": "oui"},
])
def test_enregistrer_prediction_refuse_les_incompletes(conn_etendue, prediction):
    with pytest.raises(calibration.CalibrationInvalide):
        calibration.enregistrer_prediction(conn_etendue, "banque", prediction)
    assert conn_etendue.execute(
        "SELECT count(*) FROM prediction_calibration").fetchone() == (0,)


def test_enregistrer_prediction_retombe_sur_les_colonnes_de_base(conn):
    """Schéma historique : la prédiction est écrite sans les colonnes C4."""
    prediction = calibration.enregistrer_prediction(
        conn, "banque", _prediction("need-1"))
    assert prediction.statut == "ouverte"
    assert calibration.lire(conn, "banque", prediction.id).outcome is None


def test_score_brier_exact_et_ic95(conn_etendue):
    # 10 prédictions à 0,9 toutes confirmées → Brier = (1-0,9)² = 0,01
    for rang in range(10):
        calibration.enregistrer_prediction(
            conn_etendue, "banque",
            _prediction(f"s-{rang}", probabilite=0.9, outcome=True))
    calibration.enregistrer_prediction(  # non résolue : hors mesure
        conn_etendue, "banque", _prediction("ouverte", echeance=FUTURE))

    mesure = calibration.score_brier(conn_etendue, "banque")

    assert mesure["n"] == 10 and mesure["succes"] == 10
    assert mesure["non_resolues"] == 1
    assert mesure["brier"] == pytest.approx(0.01)
    assert mesure["taux"] == 1.0
    assert 0 < mesure["ic95"]["bas"] < mesure["ic95"]["haut"] <= 1
    assert mesure["par_source"]["contournement"]["n"] == 10
    assert mesure["par_source"]["contournement"]["brier"] == pytest.approx(0.01)


def test_score_brier_refuse_sous_le_minimum(conn_etendue):
    for rang in range(9):
        calibration.enregistrer_prediction(
            conn_etendue, "banque",
            _prediction(f"s-{rang}", probabilite=0.9, outcome=True))

    mesure = calibration.score_brier(conn_etendue, "banque")

    assert mesure["n"] == 9
    assert mesure["brier"] is None
    assert mesure["taux"] is None
    assert mesure["ic95"] is None
    assert mesure["par_source"]["contournement"]["n"] == 9
    assert mesure["par_source"]["contournement"]["brier"] is None


def test_score_brier_tenant_scope(conn_etendue):
    for rang in range(10):
        calibration.enregistrer_prediction(
            conn_etendue, "banque",
            _prediction(f"s-{rang}", probabilite=0.9, outcome=True))
        calibration.enregistrer_prediction(
            conn_etendue, "assurance",
            _prediction(f"s-{rang}", probabilite=0.2, outcome=False))

    banque = calibration.score_brier(conn_etendue, "banque")
    assurance = calibration.score_brier(conn_etendue, "assurance")

    assert banque["n"] == 10 and banque["brier"] == pytest.approx(0.01)
    assert assurance["n"] == 10 and assurance["brier"] == pytest.approx(0.04)


def test_score_brier_par_source_distingue_les_sondes(conn_etendue):
    for rang in range(10):
        calibration.enregistrer_prediction(
            conn_etendue, "banque",
            _prediction(f"c-{rang}", probabilite=0.9, source="contournement",
                        outcome=True))
        calibration.enregistrer_prediction(
            conn_etendue, "banque",
            _prediction(f"r-{rang}", probabilite=0.8, source="recurrence",
                        outcome=False))

    mesure = calibration.score_brier(conn_etendue, "banque")

    assert mesure["par_source"]["contournement"]["succes"] == 10
    assert mesure["par_source"]["recurrence"]["succes"] == 0
    assert mesure["par_source"]["recurrence"]["brier"] == pytest.approx(0.64)


def test_enregistrer_prediction_id_deterministe(conn_etendue):
    """Même charge → même identifiant : un enregistrement rejoué vise la même ligne."""
    premiere = calibration.enregistrer_prediction(
        conn_etendue, "banque", _prediction("need-1", probabilite=0.8))
    autre_conn = sqlite3.connect(":memory:")
    autre_conn.execute(
        "CREATE TABLE prediction_calibration (id TEXT, tenant_id TEXT, decision_id TEXT,"
        " confidence REAL, outcome INTEGER, cree_le TEXT, resolue_le TEXT)")
    try:
        seconde = calibration.enregistrer_prediction(
            autre_conn, "banque", _prediction("need-1", probabilite=0.8))
    finally:
        autre_conn.close()
    assert premiere.id == seconde.id


# --- C4 : verifier_paris écrit la prédiction du pari ---


def _persister_memoire():
    objets = {}

    def persister(conn, tenant, payload):
        lot = payload if isinstance(payload, list) else [payload]
        for objet in lot:
            objets[objet["id"]] = objet
        return lot

    return persister, objets


def _intention(identifiant="int-1", echeance=ECHUE, statut="a_faire", **donnees):
    return {"id": identifiant, "tenant_id": "banque", "objet": "Vérifier le besoin",
            "echeance": echeance, "scope": "tenant", "scope_id": "",
            "source": "resolution_besoins", "owner": "gardien",
            "statut": statut, "priorite": "normale", "evidence_ids": [],
            "donnees": dict(donnees)}


def _need(identifiant="need-1", **donnees):
    charge = {"statut": "QUALIFIE", "signature": "contournement",
              "sujet_detection": "app-cartes|CONSOMME", "confiance": 0.7,
              "porteur": "equipe-cartes", "exigence": "observé et déclaré coïncident",
              "ecart": "observé hors déclaré",
              "refutable_par": "réconcilié 30 jours",
              "claim_ids": ["claim-1"], "twin_ids": ["app-cartes"]}
    charge.update(donnees)
    return {"id": identifiant, "tenant_id": "banque", "famille": "emergence",
            "type": "NEED", "mode": "PROPOSED", "titre": identifiant,
            "donnees": charge}


def _assertion(objet, mode):
    return {"subject": "app-cartes", "predicate": "CONSOMME", "object": objet,
            "mode": mode, "source": "test", "environment": "prod"}


def test_verifier_paris_corrobore_ecrit_une_prediction_succes(conn_etendue):
    persister, _ = _persister_memoire()
    clotures = []

    rapport = resolution_besoins.verifier_paris(
        conn_etendue, "banque", maintenant=MAINTENANT,
        needs=[_need(intention_id="int-1")], unknowns=[],
        intentions=[_intention()],
        assertions=[_assertion("GET /v1/payments", "declared"),
                    _assertion("GET /v1/payments", "observed")],
        situations=[], claims=[],
        persister=persister,
        clore_intention=lambda conn, tenant, iid, **kw: clotures.append(kw),
        creer_intention=None)

    assert rapport["totaux"]["corroborés"] == 1
    assert rapport["erreurs"] == []
    (ligne,) = conn_etendue.execute(
        "SELECT outcome, statut, issue, source, sujet, confidence "
        "FROM prediction_calibration WHERE tenant_id = 'banque'").fetchall()
    assert ligne == (1, "resolue", "succes", "contournement", "need-1", 0.7)


def test_verifier_paris_expire_ecrit_une_prediction_echec(conn_etendue):
    persister, _ = _persister_memoire()

    rapport = resolution_besoins.verifier_paris(
        conn_etendue, "banque", maintenant=MAINTENANT,
        needs=[_need(intention_id="int-1")], unknowns=[],
        intentions=[_intention()],
        assertions=[_assertion("GET /v1/payments", "declared"),
                    _assertion("POST /v1/refunds", "observed")],
        situations=[], claims=[],
        persister=persister,
        clore_intention=lambda *a, **kw: None,
        creer_intention=None)

    assert rapport["totaux"]["persistants"] == 1
    assert rapport["erreurs"] == []
    (ligne,) = conn_etendue.execute(
        "SELECT outcome, statut, issue, source, sujet, confidence "
        "FROM prediction_calibration WHERE tenant_id = 'banque'").fetchall()
    assert ligne == (0, "resolue", "echec", "contournement", "need-1", 0.7)


def test_verifier_paris_ouverture_de_pari_pose_une_prediction_ouverte(conn_etendue):
    persister, _ = _persister_memoire()
    creees = []

    def creer_intention(conn, intention):
        ligne = intention.as_dict()
        creees.append(ligne)
        return ligne

    rapport = resolution_besoins.verifier_paris(
        conn_etendue, "banque", maintenant=MAINTENANT,
        needs=[_need(intention_id="")], unknowns=[], intentions=[],
        assertions=[], situations=[], claims=[],
        persister=persister, creer_intention=creer_intention)

    assert rapport["totaux"]["paris_ouverts"] == 1
    assert rapport["erreurs"] == []
    (ligne,) = conn_etendue.execute(
        "SELECT outcome, statut, issue, source, sujet, confidence "
        "FROM prediction_calibration WHERE tenant_id = 'banque'").fetchall()
    assert ligne == (None, "ouverte", None, "contournement", "need-1", 0.7)


def test_verifier_paris_calibrer_desactive_n_ecrit_rien(conn_etendue):
    persister, _ = _persister_memoire()

    rapport = resolution_besoins.verifier_paris(
        conn_etendue, "banque", maintenant=MAINTENANT,
        needs=[_need(intention_id="int-1")], unknowns=[],
        intentions=[_intention()],
        assertions=[_assertion("GET /v1/payments", "declared"),
                    _assertion("GET /v1/payments", "observed")],
        situations=[], claims=[],
        persister=persister, clore_intention=lambda *a, **kw: None,
        creer_intention=None, calibrer=None)

    assert rapport["totaux"]["corroborés"] == 1
    assert conn_etendue.execute(
        "SELECT count(*) FROM prediction_calibration").fetchone() == (0,)


def test_verifier_paris_calibrer_injectable_recoit_le_verdict(conn_etendue):
    persister, _ = _persister_memoire()
    appels = []

    resolution_besoins.verifier_paris(
        conn_etendue, "banque", maintenant=MAINTENANT,
        needs=[_need(intention_id="int-1")], unknowns=[],
        intentions=[_intention()],
        assertions=[_assertion("GET /v1/payments", "declared"),
                    _assertion("POST /v1/refunds", "observed")],
        situations=[], claims=[],
        persister=persister, clore_intention=lambda *a, **kw: None,
        creer_intention=None,
        calibrer=lambda **pari: appels.append(pari))

    (pari,) = appels
    assert pari["besoin_id"] == "need-1"
    assert pari["intention_id"] == "int-1"
    assert pari["outcome"] is False  # signal persistant → échec
    assert pari["confiance"] == 0.7


def test_verifier_paris_calibrer_en_erreur_remonte_dans_erreurs(conn_etendue):
    persister, _ = _persister_memoire()

    def calibrer_en_panne(**pari):
        raise RuntimeError("calibration indisponible")

    rapport = resolution_besoins.verifier_paris(
        conn_etendue, "banque", maintenant=MAINTENANT,
        needs=[_need(intention_id="int-1")], unknowns=[],
        intentions=[_intention()],
        assertions=[_assertion("GET /v1/payments", "declared"),
                    _assertion("GET /v1/payments", "observed")],
        situations=[], claims=[],
        persister=persister, clore_intention=lambda *a, **kw: None,
        creer_intention=None, calibrer=calibrer_en_panne)

    assert rapport["totaux"]["corroborés"] == 1  # le verdict tient
    assert len(rapport["erreurs"]) == 1
    assert "calibration indisponible" in rapport["erreurs"][0]["erreur"]


# --- C4 : résolution contre le signal réel (Postgres) ---


@besoin_pg
def test_resoudre_echues_contre_le_signal_reel_contournement(conn_pg):
    from meridian.adapters.outbound.postgres import boucle

    need = boucle.Need(
        id="need-c4", tenant_id="banque", titre="Contournement app-cartes",
        porteur="equipe-cartes", confiance=0.7, exigence="observé = déclaré",
        ecart="observé hors déclaré", statut="QUALIFIE", signature="contournement",
        refutable_par="couvert par le déclaré", intention_id="int-c4")
    payload = dict(need.to_dict())
    payload["sujet_detection"] = "app-cartes|CONSOMME"
    boucle.enregistrer_boucle(conn_pg, "banque", payload)

    def assertion(objet, mode):
        conn_pg.execute(
            "INSERT INTO interface_assertion "
            "(tenant_id, subject, predicate, object, mode, source, locator, "
            "environment, confidence, evidence) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            ("banque", "app-cartes", "CONSOMME", objet, mode, "test", "loc",
             "prod", 0.9, "preuve"))

    # Le déclaré couvre l'observé : le signal de contournement a disparu.
    assertion("GET /v1/payments", "declared")
    assertion("GET /v1/payments", "observed")

    calibration.enregistrer_prediction(
        conn_pg, "banque", _prediction("need-c4", probabilite=0.8))

    rapport = calibration.resoudre(conn_pg, "banque", maintenant=MAINTENANT)

    assert rapport["erreurs"] == []
    assert rapport["totaux"]["resolues"] == 1
    assert rapport["resolues"][0]["issue"] == "succes"
    assert calibration.lire(conn_pg, "banque", rapport["resolues"][0]["id"]).outcome is True

    # Même sujet, signal encore présent : l'observé déborde le déclaré → échec.
    assertion("POST /v1/refunds", "observed")
    prediction2 = calibration.enregistrer_prediction(
        conn_pg, "banque", _prediction("need-c4", probabilite=0.6))

    rapport2 = calibration.resoudre(conn_pg, "banque", maintenant=MAINTENANT)

    assert rapport2["totaux"]["resolues"] == 1
    assert rapport2["resolues"][0]["issue"] == "echec"
    assert calibration.lire(conn_pg, "banque", prediction2.id).outcome is False


# --- C4 : endpoint GET /api/boucle/calibration ---


class _ConnexionPartagee:
    """Rend la connexion sqlite sans la fermer à la sortie du ``with`` de la route."""

    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, *_):
        return False


def test_endpoint_boucle_calibration_rend_brier_n_ic95_tenant_scope(
        monkeypatch, conn_etendue):
    from fastapi import APIRouter, FastAPI
    from fastapi.testclient import TestClient
    from meridian.adapters.inbound.http import boucle as boucle_routes

    for rang in range(10):
        calibration.enregistrer_prediction(
            conn_etendue, "banque",
            _prediction(f"s-{rang}", probabilite=0.9, outcome=True))
    calibration.enregistrer_prediction(
        conn_etendue, "assurance",
        _prediction("hors-tenant", probabilite=0.1, outcome=False))

    monkeypatch.setenv("JUMEAU_PG_DSN", "postgresql://test/test")
    monkeypatch.setattr(
        boucle_routes.psycopg, "connect",
        lambda *_, **__: _ConnexionPartagee(conn_etendue))
    app = FastAPI()
    api = APIRouter(prefix="/api")
    api.include_router(boucle_routes.router)
    app.include_router(api)
    client = TestClient(app)

    reponse = client.get("/api/boucle/calibration", headers={"X-Tenant": "banque"})

    assert reponse.status_code == 200
    corps = reponse.json()
    assert corps["tenant"] == "banque"
    assert corps["n"] == 10 and corps["succes"] == 10
    assert corps["brier"] == pytest.approx(0.01)
    assert corps["ic95"]["bas"] < corps["ic95"]["haut"]
    assert corps["par_source"]["contournement"]["n"] == 10

    reponse_vide = client.get("/api/boucle/calibration", headers={"X-Tenant": "local"})
    assert reponse_vide.status_code == 200
    assert reponse_vide.json()["n"] == 0
    assert reponse_vide.json()["brier"] is None
    assert reponse_vide.json()["ic95"] is None


def test_endpoint_boucle_calibration_sans_dsn_repond_503(monkeypatch):
    from fastapi import APIRouter, FastAPI
    from fastapi.testclient import TestClient
    from meridian.adapters.inbound.http import boucle as boucle_routes

    monkeypatch.delenv("JUMEAU_PG_DSN", raising=False)
    app = FastAPI()
    api = APIRouter(prefix="/api")
    api.include_router(boucle_routes.router)
    app.include_router(api)

    reponse = TestClient(app).get(
        "/api/boucle/calibration", headers={"X-Tenant": "banque"})
    assert reponse.status_code == 503
