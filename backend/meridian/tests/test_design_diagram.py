"""Authoring design-diagram : HTML éditorial -> SVG autonome, avec repli."""
import asyncio

import pytest

from meridian.adapters.outbound.llm import design_diagram


@pytest.fixture(autouse=True)
def cache_isolee(tmp_path, monkeypatch):
    monkeypatch.setenv(design_diagram._CACHE_ENV, str(tmp_path))
    design_diagram._CACHE.clear()


SCHEMA = {
    "type": "architecture", "titre": "Paiements",
    "boites": [{"id": "api", "libelle": "API"}, {"id": "db", "libelle": "Base"}],
    "fleches": [{"de": "api", "vers": "db", "libelle": "écrit", "etat": "code"}],
}


class FauxAgent:
    def __init__(self, **options):
        pass

    async def invoke_async(self, contenu, structured_output_model=None):
        html = '''<html><body><svg viewBox="0 0 200 120" role="img" aria-label="Paiements">
        <title>Paiements</title><desc>API vers Base</desc>
        <g data-node-id="api"><rect x="10" y="10" width="80" height="40" fill="#071019"/><text x="20" y="40" fill="#F2F6F8">API</text></g>
        <g data-node-id="db"><rect x="140" y="60" width="50" height="40" fill="#071019"/><text x="150" y="85" fill="#F2F6F8">Base</text></g>
        <path d="M 90 30 H 140" marker-end="url(#a)" fill="none" stroke="#60A5FA"/></svg></body></html>'''
        return type("Resultat", (), {"structured_output": design_diagram.HTMLDiagramme(html=html)})()


def test_l_auteur_produit_un_svg_autonome(monkeypatch):
    design_diagram._CACHE.clear()
    monkeypatch.setattr(design_diagram, "Agent", FauxAgent)
    artefact = asyncio.run(design_diagram.authoriser(SCHEMA, modele=object()))
    assert artefact is not None
    assert artefact["mode"] == "auteur"
    assert artefact["largeur"] == 200 and artefact["hauteur"] == 120
    assert "<svg" in artefact["svg"]
    assert f'width="{artefact["largeur"]}"' in artefact["svg"]
    assert f'height="{artefact["hauteur"]}"' in artefact["svg"]
    assert "<?xml" not in artefact["svg"]


def test_le_cache_evite_un_second_authoring(monkeypatch):
    design_diagram._CACHE.clear()
    appels = []

    class Compteur(FauxAgent):
        async def invoke_async(self, contenu, structured_output_model=None):
            appels.append(1)
            return await super().invoke_async(contenu, structured_output_model)

    monkeypatch.setattr(design_diagram, "Agent", Compteur)
    premier = asyncio.run(design_diagram.authoriser(SCHEMA, modele=object()))
    second = asyncio.run(design_diagram.authoriser(SCHEMA, modele=object()))
    assert premier["hash"] == second["hash"]
    assert len(appels) == 1


def test_une_panne_d_auteur_donne_un_repli(monkeypatch):
    design_diagram._CACHE.clear()
    monkeypatch.setenv(design_diagram._MODE_ENV, "editorial")

    class Panne:
        def __init__(self, **options):
            raise RuntimeError("modèle absent")

    monkeypatch.setattr(design_diagram, "Agent", Panne)
    reponse = asyncio.run(design_diagram.enrichir_reponse({"schemas": [SCHEMA]}))
    assert reponse["diagrammes"]
    assert reponse["diagrammes"][0]["type"] == "design-diagram"
    assert reponse["diagrammes"][0]["mode"] == "deterministe"


def test_le_mode_rapide_n_appelle_jamais_l_auteur(monkeypatch):
    monkeypatch.setenv(design_diagram._MODE_ENV, "fast")

    class Interdit:
        def __init__(self, **options):
            raise AssertionError("l'auteur ne doit pas être appelé en mode rapide")

    monkeypatch.setattr(design_diagram, "Agent", Interdit)
    reponse = asyncio.run(design_diagram.enrichir_reponse({"schemas": [SCHEMA]}))
    assert reponse["diagrammes"][0]["mode"] == "deterministe"


def test_un_auteur_trop_lent_est_coupe_et_remplace(monkeypatch):
    design_diagram._CACHE.clear()
    monkeypatch.setenv(design_diagram._MODE_ENV, "editorial")
    monkeypatch.setenv(design_diagram._TIMEOUT_ENV, "0.01")

    async def lent(schema):
        await asyncio.sleep(0.2)
        return {"mode": "auteur"}

    monkeypatch.setattr(design_diagram, "authoriser", lent)
    reponse = asyncio.run(design_diagram.enrichir_reponse({"schemas": [SCHEMA]}))
    assert reponse["diagrammes"][0]["mode"] == "deterministe"


def test_le_mode_editorial_est_le_defaut(monkeypatch):
    monkeypatch.delenv(design_diagram._MODE_ENV, raising=False)
    assert design_diagram._mode_editorial() is True
    monkeypatch.setenv(design_diagram._MODE_ENV, "editorial")
    assert design_diagram._mode_editorial() is True
    monkeypatch.setenv(design_diagram._MODE_ENV, "fast")
    assert design_diagram._mode_editorial() is False


def test_un_html_actif_est_refuse(monkeypatch):
    design_diagram._CACHE.clear()

    class Actif(FauxAgent):
        async def invoke_async(self, contenu, structured_output_model=None):
            html = '<html><body><svg viewBox="0 0 10 10"><script>alert(1)</script></svg></body></html>'
            return type("Resultat", (), {"structured_output": design_diagram.HTMLDiagramme(html=html)})()

    monkeypatch.setattr(design_diagram, "Agent", Actif)
    assert asyncio.run(design_diagram.authoriser(SCHEMA, modele=object())) is None


def test_un_cache_corrompu_est_ignore_et_reecrit(monkeypatch):
    cle, _ = design_diagram._cle(SCHEMA)
    chemin = design_diagram._chemin_cache(cle)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text("{pas du json", encoding="utf-8")
    monkeypatch.setattr(design_diagram, "Agent", FauxAgent)
    artefact = asyncio.run(design_diagram.authoriser(SCHEMA, modele=object()))
    assert artefact is not None and artefact["mode"] == "auteur"
    assert design_diagram._lire_cache(cle) is not None


def test_un_artefact_survit_a_un_redemarrage(monkeypatch):
    appels = []

    class Compteur(FauxAgent):
        async def invoke_async(self, contenu, structured_output_model=None):
            appels.append(1)
            return await super().invoke_async(contenu, structured_output_model)

    monkeypatch.setattr(design_diagram, "Agent", Compteur)
    premier = asyncio.run(design_diagram.authoriser(SCHEMA, modele=object()))
    assert premier is not None
    design_diagram._CACHE.clear()  # simule un redémarrage du processus

    class Interdit:
        def __init__(self, **options):
            raise AssertionError("le cache disque doit éviter un second authoring")

    monkeypatch.setattr(design_diagram, "Agent", Interdit)
    second = asyncio.run(design_diagram.authoriser(SCHEMA, modele=object()))
    assert second is not None
    assert second["hash"] == premier["hash"]
    assert len(appels) == 1


def test_le_contenu_impose_le_plan_de_placement():
    contenu = design_diagram._contenu(SCHEMA)
    assert "PLAN DE PLACEMENT IMPOSÉ" in contenu
    assert '"viewBox"' in contenu


def test_un_svg_qui_deborde_est_refuse(monkeypatch):
    appels = []

    class Deborde(FauxAgent):
        async def invoke_async(self, contenu, structured_output_model=None):
            appels.append(1)
            html = '''<html><body><svg viewBox="0 0 200 120" role="img" aria-label="Déborde">
            <title>Déborde</title><desc>nœud hors cadre</desc>
            <g data-node-id="api"><rect x="10" y="100" width="80" height="60" fill="#071019"/></g>
            <path d="M 90 30 H 140" marker-end="url(#a)" fill="none" stroke="#60A5FA"/></svg></body></html>'''
            return type("Resultat", (), {"structured_output": design_diagram.HTMLDiagramme(html=html)})()

    monkeypatch.setattr(design_diagram, "Agent", Deborde)
    assert asyncio.run(design_diagram.authoriser(SCHEMA, modele=object())) is None
    assert len(appels) == 1


def test_un_noeud_du_plan_manquant_est_refuse(monkeypatch):
    class Incomplet(FauxAgent):
        async def invoke_async(self, contenu, structured_output_model=None):
            html = '''<html><body><svg viewBox="0 0 200 120" role="img" aria-label="Incomplet">
            <title>Incomplet</title><desc>un seul nœud</desc>
            <g data-node-id="api"><rect x="10" y="10" width="80" height="40" fill="#071019"/></g>
            <path d="M 90 30 H 140" marker-end="url(#a)" fill="none"/></svg></body></html>'''
            return type("Resultat", (), {"structured_output": design_diagram.HTMLDiagramme(html=html)})()

    monkeypatch.setattr(design_diagram, "Agent", Incomplet)
    assert asyncio.run(design_diagram.authoriser(SCHEMA, modele=object())) is None


def test_des_noeuds_qui_se_chevauchent_sont_refuses():
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 120">
    <title>Chevauche</title><desc>deux nœuds</desc>
    <g data-node-id="a"><rect x="10" y="10" width="80" height="40"/></g>
    <g data-node-id="b"><rect x="50" y="20" width="80" height="40"/></g></svg>'''
    assert "se chevauchent" in " ".join(design_diagram._problemes_geometrie(svg))


def test_un_conteneur_avec_ses_enfants_est_accepte():
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 120">
    <title>Conteneur</title><desc>contenance</desc>
    <g data-node-id="outer"><rect x="10" y="10" width="160" height="90"/></g>
    <g data-node-id="inner"><rect x="40" y="40" width="60" height="30"/></g></svg>'''
    assert design_diagram._problemes_geometrie(svg) == []


def test_un_auteur_invalide_deux_fois_donne_le_repli(monkeypatch):
    class Deborde(FauxAgent):
        async def invoke_async(self, contenu, structured_output_model=None):
            html = '''<html><body><svg viewBox="0 0 200 120" role="img" aria-label="Déborde">
            <title>Déborde</title><desc>nœud hors cadre</desc>
            <g data-node-id="api"><rect x="10" y="100" width="80" height="60"/></g>
            <path d="M 90 30 H 140" marker-end="url(#a)" fill="none"/></svg></body></html>'''
            return type("Resultat", (), {"structured_output": design_diagram.HTMLDiagramme(html=html)})()

    monkeypatch.setattr(design_diagram, "Agent", Deborde)
    reponse = asyncio.run(design_diagram.enrichir_reponse({"schemas": [SCHEMA]}))
    assert reponse["diagrammes"][0]["mode"] == "deterministe"


def test_le_budget_est_reduit_avant_authoring():
    schema = {"type": "architecture", "titre": "Grand",
              "boites": [{"id": f"n{i}", "libelle": f"N{i}"} for i in range(12)],
              "fleches": [{"de": f"n{i}", "vers": f"n{i+1}", "libelle": "lien"} for i in range(11)]}
    reduit = design_diagram._reduire(schema)
    assert len(reduit["boites"]) == 9
    assert len(reduit["fleches"]) <= 12
    assert reduit["_budget_reduit"]["noeuds_retires"] == 3
