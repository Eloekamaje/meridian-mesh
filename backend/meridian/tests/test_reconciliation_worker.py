"""Boucle de réconciliation : passes, arrêt et tolérance aux erreurs."""
from __future__ import annotations

from meridian.adapters.inbound.worker.reconciliation_worker import BoucleReconciliation


def test_une_passe_appelle_l_executeur():
    appels = []
    boucle = BoucleReconciliation(lambda: appels.append("passe"))

    resultat = boucle.une_passe()

    assert resultat is None
    assert appels == ["passe"]
    assert boucle.passes == 1


def test_apres_arret_une_passe_ne_fait_rien():
    appels = []
    boucle = BoucleReconciliation(lambda: appels.append("passe"))
    boucle.arreter()

    assert boucle.une_passe() is None
    assert appels == []


def test_tourner_s_arrete_apres_la_passe_demandee():
    appels = []

    def executer():
        appels.append("passe")

    boucle = BoucleReconciliation(executer, intervalle=1)
    boucle._attendre = lambda _: boucle.arreter()

    boucle.tourner()

    assert appels == ["passe"]
    assert boucle.passes == 1
    assert boucle.arretee is True


def test_une_erreur_de_passe_ne_tue_pas_la_boucle():
    appels = []

    def executer():
        appels.append("passe")
        raise RuntimeError("base indisponible")

    boucle = BoucleReconciliation(executer, intervalle=1)
    boucle._attendre = lambda _: boucle.arreter()

    boucle.tourner()

    assert appels == ["passe"]
    assert boucle.passes == 1
    assert boucle.arretee is True


def test_intervalle_est_borne():
    boucle = BoucleReconciliation(lambda: None, intervalle=0)
    assert boucle.intervalle == 1.0
