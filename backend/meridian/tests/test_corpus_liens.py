"""Corpus labellisé : chargement, exécution et mesure."""
from __future__ import annotations

from pathlib import Path

from meridian.adapters.outbound.connectors.corpus_liens import charger_corpus
from meridian.application.evaluation_liens import evaluer_liens
from meridian.application.moteur_liens import moteur_liens

CORPUS = Path(__file__).parent / "fixtures" / "liens_corpus" / "corpus.json"


def test_le_corpus_est_charge_avec_la_politique_et_les_attentes():
    corpus = charger_corpus(CORPUS)

    assert corpus.tenant_id == "banque"
    assert corpus.politique.niveaux == (0, 1)
    assert corpus.politique.autorise("kubernetes")
    assert len(corpus.extractions) == 4
    assert len(corpus.jeu.liens) == 2
    assert corpus.jeu.externes == ("api.stripe.com",)


def test_le_corpus_atteint_precision_et_rappel_parfaits():
    corpus = charger_corpus(CORPUS)

    rapport = moteur_liens(corpus.extractions)
    resultat = evaluer_liens(rapport, corpus.jeu)

    assert resultat.precision == 1.0
    assert resultat.rappel == 1.0
    assert resultat.f1 == 1.0
    assert resultat.fausses_certitudes == 0
    assert resultat.taux_preuves == 1.0
    assert resultat.externes_trouves == 1
    assert resultat.externes_manquants == 0
    assert resultat.ambiguites == 0
    assert len(rapport.liens) == 3


def test_le_corpus_ne_produit_aucune_question_sur_les_cas_connus():
    corpus = charger_corpus(CORPUS)
    rapport = moteur_liens(corpus.extractions)

    assert rapport.questions == ()
    assert {lien.operation for lien in rapport.mesh} == {"GET /accounts/{id}"}
    assert {lien.operation for lien in rapport.internes} == {"GET /internal/accounts/{id}"}
    assert {lien.fournisseur_service for lien in rapport.externes} == {"api.stripe.com"}
