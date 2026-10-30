"""Contradicteur : relecture de la réponse de Flore avant envoi (méta-expert, Agentic §10)."""
import asyncio

from jumeau import contradicteur
from jumeau.source_git import sha_courant


def source_de(depot_git):
    return [{"nom": "tbt-repo", "emplacement": str(depot_git), "curseur": sha_courant(depot_git)}]


def test_citations_invalides_detectees(depot_git):
    texte = "Elle s'appuie sur motor `requirements.txt#L2` et sur `requirements.txt#L8-L9` et `absent.py#L1`."
    assert contradicteur.citations_invalides(texte, source_de(depot_git)) == ["requirements.txt#L8-L9", "absent.py#L1-L1"]


def test_verdict_json_extrait_d_un_texte_bavard():
    assert contradicteur.analyser_verdict('Voici : {"ok": false, "problemes": ["jargon"]} merci') == \
        {"ok": False, "problemes": ["jargon"], "etat": "relue"}


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


def test_citation_de_piece_est_verifiee_contre_les_sections_du_travail(monkeypatch):
    appels = []

    async def juge(*_):
        appels.append(1)
        return {"ok": True, "problemes": []}
    monkeypatch.setattr(contradicteur, "_juger", juge)
    doc = {"id": "p1", "nom": "spec.docx", "texte": "# Alpha\nx\n# Beta\ny",
           "sections": [{"id": "s1", "titre": "Alpha", "niveau": 1, "debut": 0, "fin": 9},
                        {"id": "s2", "titre": "Beta", "niveau": 1, "debut": 9, "fin": 18}]}
    verdict = asyncio.run(contradicteur.relire("q", "D'après `pièce:p1#s1`, x.", [], {}, modele=None,
                                               pieces_jointes=[doc]))
    assert verdict["ok"] is True and appels == [1]
    appels.clear()
    verdict = asyncio.run(contradicteur.relire("q", "D'après `pièce:p1#s9`, x.", [], {}, modele=None,
                                               pieces_jointes=[doc]))
    assert verdict["ok"] is False and "pièce:p1#s9" in verdict["problemes"][0]
    assert appels == []


def test_citations_invalides_retirees_du_texte():
    texte = "A `a.py#L1` et B `absent.py#L3-L4`, puis C git://d@abc1234:absent.py#L3-L4."
    assert contradicteur.retirer_citations_invalides(texte, ["absent.py#L3-L4", "d:absent.py#L3-L4"]) == \
        "A `a.py#L1` et B, puis C."


# --- Attribution à l'équipe (constaté : « confirmé par l'équipe propriétaire » sur Conduit, sans aucune validation) --

def test_confirmation_inventee_detectee_sans_validation():
    texte = ("Elle conserve tout dans une base unique — confirmé par l'équipe propriétaire. "
             "Rien de tout cela n'est validé par l'équipe. La mission déclarée par l'équipe est « publier » ✓. "
             "Observé dans le code, pas encore confirmé par l'équipe.")
    assert contradicteur.attributions_infondees(texte, 0) == [
        "Elle conserve tout dans une base unique — confirmé par l'équipe propriétaire."]
    assert contradicteur.attributions_infondees("Règle R12 ✓.", 0) == ["Règle R12 ✓."]
    assert contradicteur.attributions_infondees(texte, 2) == []  # des validées existent : non contrôlé ici


def test_relire_demande_revision_sans_appeler_le_modele(monkeypatch):
    async def juge(*a):
        raise AssertionError("le modèle ne doit pas être appelé")
    monkeypatch.setattr(contradicteur, "_juger", juge)
    verdict = asyncio.run(contradicteur.relire("q", "Une base unique, validée par l'équipe.", [], {}, None, validees=0))
    assert not verdict["ok"] and "aucune connaissance" in verdict["problemes"][0]
