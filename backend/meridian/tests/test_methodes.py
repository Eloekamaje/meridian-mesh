"""Méthodes de Flore : fiches chargées à la demande selon la question (comme des skills)."""
from meridian.adapters.outbound.llm import agent
from meridian.application import methodes
from meridian.tests.test_agent import CONTEXTE, modele_factice


def test_catalogue_liste_les_methodes_avec_leur_description():
    noms = {m["nom"]: m["description"] for m in methodes.catalogue()}
    assert {"presenter-application", "expliquer-regle", "evaluer-impact"} <= set(noms)
    assert all(d.strip() for d in noms.values())


def test_lire_une_methode_renvoie_ses_consignes_sans_l_entete():
    texte = methodes.lire("presenter-application")
    assert texte and not texte.startswith("---") and "description:" not in texte


def test_methode_inconnue_ou_chemin_detourne():
    assert methodes.lire("inconnue") is None
    assert methodes.lire("../charte_flore") is None


def test_le_prompt_porte_le_catalogue_et_l_agent_l_outil(tmp_path, monkeypatch):
    assert "presenter-application" in agent.prompt_systeme(CONTEXTE)
    monkeypatch.setattr(agent, "SESSIONS", tmp_path)
    a = agent.construire(CONTEXTE, dsn="postgresql://inutilise", session="t", modele=modele_factice())
    assert "consulter_methode" in a.tool_names


def test_fiche_malformee_ignoree_et_fins_de_ligne_windows(tmp_path, monkeypatch):
    (tmp_path / "sans-entete.md").write_text("juste du texte")
    (tmp_path / "windows.md").write_bytes(b"---\r\nnom: windows\r\ndescription: test : CRLF\r\n---\r\nCorps\r\n")
    monkeypatch.setattr(methodes, "DOSSIER", tmp_path)
    assert methodes.catalogue() == [{"nom": "windows", "description": "test : CRLF"}]
    assert methodes.lire("windows") == "Corps"
