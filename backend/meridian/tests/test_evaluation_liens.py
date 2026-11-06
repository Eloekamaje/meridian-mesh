"""Évaluation d'un rapport de liens contre un jeu d'or."""
from __future__ import annotations

from meridian.application.evaluation_liens import (
    JeuOrLiens,
    LienAttendu,
    QuestionAttendue,
    evaluer_liens,
)
from meridian.domain.liens_composants import (
    LienPropose,
    Preuve,
    QuestionLien,
    RapportLiens,
)


def _preuve(locator="code:a:1") -> Preuve:
    return Preuve(source="CODE", locator=locator, detail="GET /x", confidence=0.9)


def _lien(consommateur="a", fournisseur="b", operation="GET /x", *,
          nature="mesh", state="suggere", preuves=None, portee="SERVICE",
          missing=""):
    return LienPropose(
        consommateur_composant_id=consommateur,
        consommateur_application_id=consommateur,
        fournisseur_composant_id=fournisseur,
        fournisseur_application_id=fournisseur,
        operation=operation, environment="prod", nature=nature, state=state, portee=portee,
        preuves=tuple(preuves if preuves is not None else (_preuve(),)),
        missing_evidence=missing,
    )


def test_precision_rappel_et_f1():
    rapport = RapportLiens(liens=(
        _lien("a", "b", "GET /x"),
        _lien("a", "d", "GET /surplus"),
    ))
    jeu = JeuOrLiens(liens=(
        LienAttendu("a", "b", "GET /x"),
        LienAttendu("a", "c", "GET /manquant"),
    ))

    resultat = evaluer_liens(rapport, jeu)

    assert resultat.vrais_positifs == 1
    assert resultat.faux_positifs == 1
    assert resultat.faux_negatifs == 1
    assert resultat.precision == 0.5
    assert resultat.rappel == 0.5
    assert resultat.f1 == 0.5
    assert "a → b · GET /x" in resultat.couverts
    assert "a → c · GET /manquant" in resultat.manquants
    assert any("GET /surplus" in libelle for libelle in resultat.surplus)


def test_une_fausse_certitude_est_comptee():
    rapport = RapportLiens(liens=(
        _lien("a", "b", "GET /sans-preuve", preuves=(), state="confirme"),
        _lien("a", "c", "GET /preuve-manquante", state="confirme",
              missing="service non rattaché"),
        _lien("a", "d", "GET /portee-inconnue", state="confirme", portee="UNKNOWN"),
        _lien("a", "e", "GET /valide", state="confirme"),
    ))

    resultat = evaluer_liens(rapport, JeuOrLiens())

    assert resultat.fausses_certitudes == 3
    assert resultat.taux_preuves == 0.75


def test_questions_externes_et_contradictions():
    contradictoire = _lien("a", "b", "GET /x", state="conteste")
    externe = LienPropose(
        consommateur_composant_id="a", consommateur_application_id="a",
        fournisseur_composant_id="", fournisseur_application_id="",
        fournisseur_service="api.stripe.com", operation="POST /v1/charges",
        nature="externe", state="suggere", portee="UNKNOWN",
    )
    rapport = RapportLiens(
        liens=(contradictoire, externe),
        questions=(QuestionLien(
            type="SERVICE_INCONNU", sujet="GET /x", question="Qui fournit ?",
            environment="prod"),),
    )
    jeu = JeuOrLiens(
        questions=(QuestionAttendue("SERVICE_INCONNU", "GET /x"),),
        externes=("api.stripe.com",),
        contradictions=(("a", "GET /x"),),
    )

    resultat = evaluer_liens(rapport, jeu)

    assert resultat.questions_trouvees == 1
    assert resultat.questions_manquantes == 0
    assert resultat.externes_trouves == 1
    assert resultat.externes_manquants == 0
    assert resultat.contradictions_trouvees == 1
    assert resultat.contradictions_manquantes == 0
    assert "vrai(s) positif" in resultat.resume()
