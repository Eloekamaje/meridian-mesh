"""Contradicteur : relecture de la réponse de Flore avant envoi (méta-expert, Agentic §10)."""
import asyncio

from jumeau import contradicteur
from jumeau.source_git import sha_courant


def source_de(depot_git):
    return {"nom": "tbt-repo", "emplacement": str(depot_git), "curseur": sha_courant(depot_git)}


def test_citations_invalides_detectees(depot_git):
    texte = "Elle s'appuie sur motor `requirements.txt#L2` et sur `requirements.txt#L8-L9` et `absent.py#L1`."
    assert contradicteur.citations_invalides(texte, source_de(depot_git)) == ["requirements.txt#L8-L9", "absent.py#L1-L1"]


def test_verdict_json_extrait_d_un_texte_bavard():
    assert contradicteur.analyser_verdict('Voici : {"ok": false, "problemes": ["jargon"]} merci') == \
        {"ok": False, "problemes": ["jargon"]}


def test_verdict_illisible_ne_bloque_pas_la_reponse():
    assert contradicteur.analyser_verdict("je ne sais pas")["ok"] is True


def test_consigne_de_revision_porte_les_problemes_et_demande_la_seule_reponse():
    consigne = contradicteur.consigne_revision(["Pas de preuve pour la phrase 2"])
    assert "Pas de preuve pour la phrase 2" in consigne and "uniquement" in consigne


def test_citation_introuvable_rend_le_verdict_negatif_meme_si_le_relecteur_approuve(depot_git, monkeypatch):
    async def juge_indulgent(*_):
        return {"ok": True, "problemes": []}
    monkeypatch.setattr(contradicteur, "_juger", juge_indulgent)
    verdict = asyncio.run(contradicteur.relire("q", "Voir `absent.py#L1`.", source_de(depot_git), {}, modele=None))
    assert verdict["ok"] is False and "absent.py#L1-L1" in verdict["problemes"][0]


def test_citation_invalide_epargne_l_appel_au_relecteur(depot_git, monkeypatch):
    appels = []

    async def juge(*_):
        appels.append(1)
        return {"ok": True, "problemes": []}
    monkeypatch.setattr(contradicteur, "_juger", juge)
    asyncio.run(contradicteur.relire("q", "Voir `absent.py#L1`.", source_de(depot_git), {}, modele=None))
    assert appels == []
