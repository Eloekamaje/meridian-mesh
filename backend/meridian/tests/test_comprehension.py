"""Statuts des sept questions : la fiche est un rendu, pas le modèle."""
from meridian.domain.comprehension import (
    QuestionStatus,
    couverture,
    resume_couverture,
    statut_question,
    statuts_depuis_claims,
)


def _claim(identifiant, predicat, preuve="git://x@sha:a.py#L1-L2", statut="PROPOSED"):
    return {"id": identifiant, "predicat": predicat, "objet": "objet métier",
            "statut": statut, "preuve": preuve}


def test_sans_claim_tout_est_inconnu():
    statuts = statuts_depuis_claims([])
    assert len(statuts) == 7
    assert {statut.statut for statut in statuts} == {"unknown"}
    assert couverture(statuts)["unknown"] == 7


def test_claim_avec_preuve_repond():
    statut = statut_question("sert", [_claim(1, "REALISE_CAPACITE")])
    assert statut.statut == "answered"
    assert statut.claim_ids == (1,)
    assert statut.preuves == ("git://x@sha:a.py#L1-L2",)


def test_claim_sans_preuve_reste_partiel():
    statut = statut_question("sert", [_claim(1, "REALISE_CAPACITE", preuve=None)])
    assert statut.statut == "partial"
    assert "sans preuve" in statut.inconnues[0]


def test_claim_conteste_est_contradictoire():
    statut = statut_question("sert", [_claim(1, "REALISE_CAPACITE", statut="CONTESTED")])
    assert statut.statut == "contradicted"


def test_contradiction_explicite_est_contradictoire():
    statut = statut_question(
        "sert", [_claim(1, "REALISE_CAPACITE")], contradictions=[{"id": 9}])
    assert statut.statut == "contradicted"


def test_question_narrative_reste_inconnue():
    statut = statut_question("vie", [_claim(1, "REALISE_CAPACITE")])
    assert statut.statut == "unknown"


def test_couverture_compte_les_statuts():
    statuts = (
        QuestionStatus("sert", "answered"),
        QuestionStatus("pour_qui", "partial"),
        QuestionStatus("informations", "unknown"),
        QuestionStatus("regles", "contradicted"),
    )
    bilan = couverture(statuts)
    assert bilan["total"] == 4
    assert bilan["answered"] == 1
    assert bilan["partial"] == 1
    assert bilan["unknown"] == 1
    assert bilan["contradicted"] == 1
    assert bilan["couverture"] == 0.38


def test_resume_couverture():
    statuts = (QuestionStatus("sert", "answered"), QuestionStatus("pour_qui", "unknown"))
    assert resume_couverture(statuts) == "1/2 répondu, 1 inconnu(s)"
