"""Évaluation déterministe et rejeu : preuves, empreintes, autorité, abstention et outils."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from jumeau import contexte, evaluation_cognitive, raisonnement

PROFIL = SimpleNamespace(id="business_analyst", autorite="proposition")
PLAN = SimpleNamespace(
    methodes=[SimpleNamespace(id="m1")],
    competences=[SimpleNamespace(id="c1")],
    specialistes_socle=("preuve",),
)


def _resultat(
    *,
    preuves=True,
    autorite="proposition",
    recommandation="Automatiser",
    abstention=None,
    statut="ok",
    erreur=None,
    latence_ms=12.5,
    cout=0.01,
    faits=True,
):
    propositions = []
    if faits:
        propositions.append({
            "specialiste": "preuve",
            "type": "FAIT",
            "titre": "Délai observé",
            "resume": "Le délai est de 12 jours",
            "preuves": ["preuve-1"] if preuves else [],
            "confiance": 0.8,
        })
    dossier = {
        "tenant": "banque",
        "statut": "ok",
        "propositions": propositions,
        "specialistes": [{
            "specialiste": "preuve",
            "statut": statut,
            "erreur": erreur,
            "limites": [],
        }],
        "limites": [],
    }
    reponse = {
        "autorite": autorite,
        "decision_support": {
            "recommandation": recommandation,
            "confidence": 0.7,
            "abstention": abstention,
            "options": [{"id": "a"}],
        },
    }
    pack = contexte.construire("Question ?", PROFIL, dossier)
    trace = raisonnement.construire(
        "Question ?", PROFIL, PLAN, pack, dossier, reponse)
    resultat = {
        "reponse": reponse,
        "contexte": pack.as_dict(),
        "raisonnement": trace.as_dict(),
        "dossier": dossier,
    }
    if latence_ms is not None:
        resultat["latence_ms"] = latence_ms
    if cout is not None:
        resultat["cout"] = cout
    return resultat


def test_bonne_evaluation_note_les_verifications_sans_raison():
    resultat = _resultat()

    evaluation = evaluation_cognitive.evaluer(resultat)

    assert evaluation["score"] == 1.0
    assert evaluation["raisons"] == []
    assert evaluation["limites"] == []
    assert evaluation["verifications"] == {
        "preuves": True,
        "contexte": True,
        "autorite": True,
        "abstention": True,
        "outils": True,
    }
    assert evaluation["metriques"] == {"latence_ms": 12.5, "cout": 0.01}


def test_mauvaise_evaluation_explique_chaque_echec():
    resultat = _resultat(
        preuves=False,
        autorite="action",
        recommandation=None,
        abstention=None,
        statut="erreur",
        erreur="délai dépassé",
        latence_ms=None,
        cout=None,
    )

    evaluation = evaluation_cognitive.evaluer(resultat)

    assert evaluation["score"] == 0.2
    assert evaluation["verifications"]["contexte"] is True
    assert any("preuve" in raison for raison in evaluation["raisons"])
    assert any("autorité" in raison for raison in evaluation["raisons"])
    assert any("abstention" in raison for raison in evaluation["raisons"])
    assert any("erreur d'outil" in raison for raison in evaluation["raisons"])
    assert "latence non fournie" in evaluation["limites"]
    assert "coût non fourni" in evaluation["limites"]


def test_abstention_sans_fait_est_acceptee_et_bornee():
    resultat = _resultat(
        faits=False,
        recommandation=None,
        abstention="aucun fait vérifié : décision impossible",
    )

    evaluation = evaluation_cognitive.evaluer(resultat)

    assert evaluation["score"] == 1.0
    assert evaluation["raisons"] == []
    assert "aucun fait : évaluation bornée à l'abstention" in evaluation["limites"]


def test_latence_en_secondes_est_convertie_et_valeur_invalide_signalee():
    resultat = _resultat(latence_ms=None)
    resultat["latence_s"] = 0.42
    resultat["cout"] = -1

    evaluation = evaluation_cognitive.evaluer(resultat)

    assert evaluation["metriques"]["latence_ms"] == 420.0
    assert evaluation["metriques"]["cout"] is None
    assert "coût invalide : valeur non négative attendue" in evaluation["limites"]


def test_autorite_max_inconnue_refusee():
    with pytest.raises(evaluation_cognitive.EvaluationInvalide):
        evaluation_cognitive.evaluer(_resultat(), autorite_max="inconnue")


def test_rejeu_reconstruit_le_contexte_et_la_trace_sans_modele():
    resultat = _resultat()

    rejeu = evaluation_cognitive.rejouer(resultat)

    assert rejeu["reconstructible"] is True
    assert rejeu["etapes"] == 1
    assert rejeu["evenements"] == 0
    assert rejeu["empreintes"]["contexte"]["ok"] is True
    assert rejeu["empreintes"]["raisonnement"]["ok"] is True
    assert rejeu["raisons"] == []


def test_rejeu_detecte_un_contexte_altere():
    resultat = deepcopy(_resultat())
    resultat["contexte"]["faits"][0]["resume"] = "Le délai est de 2 jours"

    rejeu = evaluation_cognitive.rejouer(resultat)

    assert rejeu["reconstructible"] is False
    assert rejeu["empreintes"]["contexte"]["ok"] is False
    assert "empreinte de contexte non reconstructible" in rejeu["raisons"]


def test_rejeu_detecte_une_trace_alteree():
    resultat = deepcopy(_resultat())
    resultat["raisonnement"]["etapes"][0]["statut"] = "erreur"

    rejeu = evaluation_cognitive.rejouer(resultat)

    assert rejeu["reconstructible"] is False
    assert rejeu["empreintes"]["raisonnement"]["ok"] is False
    assert "trace_id non reconstructible" in rejeu["raisons"]


def test_rejeu_sans_contexte_ni_trace_n_est_pas_reconstructible():
    rejeu = evaluation_cognitive.rejouer({"reponse": {}})

    assert rejeu["reconstructible"] is False
    assert "contexte absent : empreinte non rejouable" in rejeu["limites"]
    assert "raisonnement absent : trace non rejouable" in rejeu["limites"]
    assert "aucune étape ni événement à rejouer" in rejeu["limites"]


def test_rejeu_d_un_contexte_seul_ne_prouve_pas_le_resultat():
    resultat = _resultat()
    resultat.pop("raisonnement")

    rejeu = evaluation_cognitive.rejouer(resultat)

    assert rejeu["empreintes"]["contexte"]["ok"] is True
    assert rejeu["reconstructible"] is False
    assert "raisonnement absent : trace non rejouable" in rejeu["limites"]
