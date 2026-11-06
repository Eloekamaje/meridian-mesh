"""Critique croisée : un modèle juge séparé, sans réécriture."""
import asyncio

from meridian.adapters.outbound.llm import critique_raisonnement
from meridian.application import noyau_raisonnement as noyau
from meridian.domain import dossier_raisonnement as domaine


class FauxAgent:
    def __init__(self, **options):
        self.options = options

    async def invoke_async(self, contenu, structured_output_model=None):
        return type("Resultat", (), {"structured_output": critique_raisonnement.CritiqueJuge(
            findings=[critique_raisonnement.FindingJuge(
                constat="Option non prouvée", severite="majeure", rubrique="options",
                remediation="ajouter une preuve")],
            dissensus=["désaccord sur le périmètre"],
            verdict="conditional",
        )})()


def test_un_n3_recoit_une_critique_croisee(monkeypatch):
    monkeypatch.setattr(critique_raisonnement, "Agent", FauxAgent)
    dossier = noyau.analyser_reponse(
        "Conçois une application", {"reponse": "Proposition"},
        contexte={"sans_questions": True})
    critique = asyncio.run(critique_raisonnement.critiquer(dossier, modele=object()))
    assert critique is not None
    assert critique.reviewer == "modele-juge"
    assert critique.findings[0].severite == "majeure"
    assert critique.dissensus == ("désaccord sur le périmètre",)


def test_un_n0_ne_declenche_pas_de_modele_juge(monkeypatch):
    dossier = noyau.analyser_reponse("Qui es-tu ?", {"reponse": "Flore"})
    assert asyncio.run(critique_raisonnement.critiquer(dossier)) is None


def test_une_panne_du_juge_ne_casse_pas_le_dossier(monkeypatch):
    class Panne:
        def __init__(self, **options):
            raise RuntimeError("indisponible")

    monkeypatch.setattr(critique_raisonnement, "Agent", Panne)
    dossier = noyau.analyser_reponse(
        "Conçois une application", {"reponse": "Proposition"},
        contexte={"sans_questions": True})
    assert asyncio.run(critique_raisonnement.critiquer(dossier, modele=object())) is None
