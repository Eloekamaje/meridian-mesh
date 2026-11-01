"""Noyau des spécialistes : autorité, parallélisme, timeout, erreurs et artefacts."""
import asyncio
import time

import pytest

from meridian.domain.specialistes import ContexteSpecialiste, OrchestrateurSpecialistes, Proposition, ResultatSpecialiste


class _Specialiste:
    def __init__(self, nom, resultat=None, delai=0.0):
        self.nom = nom
        self.autorite = "proposition"
        self.resultat = resultat
        self.delai = delai
        self.vus = []

    def analyser(self, contexte):
        self.vus.append(contexte)
        if self.delai:
            time.sleep(self.delai)
        if isinstance(self.resultat, Exception):
            raise self.resultat
        return self.resultat if self.resultat is not None else [
            Proposition(self.nom, "CONSTAT", f"Constat {self.nom}")]


def _contexte():
    return ContexteSpecialiste(tenant="demo", question="Pourquoi ?", twin_ids=["a"])


def test_les_specialistes_sont_executes_et_les_propositions_fusionnees():
    un = _Specialiste("un")
    deux = _Specialiste("deux")
    resultat = asyncio.run(OrchestrateurSpecialistes([un, deux]).analyser(_contexte()))

    assert resultat["statut"] == "ok"
    assert {p["specialiste"] for p in resultat["propositions"]} == {"un", "deux"}
    assert all(v.tenant == "demo" for v in un.vus + deux.vus)


def test_un_specialiste_echoue_sans_bloquer_les_autres():
    bon = _Specialiste("bon")
    mauvais = _Specialiste("mauvais", resultat=RuntimeError("secret"))
    resultat = asyncio.run(OrchestrateurSpecialistes([bon, mauvais]).analyser(_contexte()))

    assert resultat["statut"] == "partiel"
    assert [p["specialiste"] for p in resultat["propositions"]] == ["bon"]
    assert resultat["specialistes"][1]["erreur"] == "RuntimeError"
    assert "secret" not in str(resultat)


def test_le_timeout_est_borne_et_signale():
    lent = _Specialiste("lent", delai=0.3)
    resultat = asyncio.run(
        OrchestrateurSpecialistes([lent], timeout_s=0.05).analyser(_contexte()))
    assert resultat["statut"] == "partiel"
    assert resultat["specialistes"][0]["erreur"] == "TimeoutError"


def test_un_specialiste_ne_peut_pas_avoir_une_autorite_de_decision():
    class Decision(_Specialiste):
        pass

    decision = Decision("x")
    decision.autorite = "decision"
    with pytest.raises(ValueError, match="autorité"):
        OrchestrateurSpecialistes([decision])


def test_les_resultats_et_propositions_sont_dedupliques_et_tries():
    un = _Specialiste("un", resultat=[
        Proposition("un", "CONSTAT", "Même", confiance=0.4),
        Proposition("un", "CONSTAT", "Même", confiance=0.9),
    ])
    resultat = asyncio.run(OrchestrateurSpecialistes([un]).analyser(_contexte()))
    assert len(resultat["propositions"]) == 1
    assert resultat["propositions"][0]["confiance"] == 0.9


def test_un_resultat_partiel_est_conserve():
    specialiste = _Specialiste("un", resultat=ResultatSpecialiste(
        "un", statut="partiel", propositions=[Proposition("un", "QUESTION", "À vérifier")],
        limites=["source absente"]))
    resultat = asyncio.run(OrchestrateurSpecialistes([specialiste]).analyser(_contexte()))
    assert resultat["statut"] == "partiel"
    assert resultat["specialistes"][0]["limites"] == ["source absente"]

    mauvais_type = _Specialiste("un", resultat=[{"titre": "x", "type": "INCONNU"}])
    resultat = asyncio.run(OrchestrateurSpecialistes([mauvais_type]).analyser(_contexte()))
    assert resultat["statut"] == "partiel"
    assert resultat["specialistes"][0]["erreur"] == "ValueError"
