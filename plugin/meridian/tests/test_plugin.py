"""Plugin Méridian : manifest, skills, agents, policy et tools MCP read-only."""
import asyncio
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]


def _json(chemin):
    return json.loads((ROOT / chemin).read_text(encoding="utf-8"))


def test_manifest_et_catalogues_sont_valides():
    manifest = _json("meridian.plugin.json")
    profils = _json("profiles.json")["profiles"]
    policy = _json("policies/authority.json")
    contrat = _json("contracts/reponse.json")

    assert manifest["schema"] == "meridian.plugin/1"
    assert set(profils) == {"ops", "architecte", "product_owner"}
    assert len(manifest["skills"]) == 4 and len(manifest["agents"]) == 3
    assert manifest["read_only"] is True
    assert policy["writes"]["allowed"] is False
    assert policy["unknown_profile"] == "generaliste_lecture_seule"
    assert "socle" in contrat["required"] and "autorite" in contrat["required"]


def test_skills_et_agents_ont_un_frontmatter_exploitable():
    for chemin in _json("meridian.plugin.json")["skills"]:
        texte = (ROOT / chemin).read_text(encoding="utf-8")
        assert texte.startswith("---\n")
        assert "name:" in texte and "description:" in texte
        assert "compatibility:" in texte
        dossier = (ROOT / chemin).parent
        evals = _json(str((dossier / "evals" / "evals.json").relative_to(ROOT)))
        assert evals["skill_name"].startswith("meridian-")
        assert evals["evals"] and all(case["expectations"] for case in evals["evals"])
        assert any((dossier / "references").glob("*.md"))
    for chemin in _json("meridian.plugin.json")["agents"]:
        texte = (ROOT / chemin).read_text(encoding="utf-8")
        assert texte.startswith("---\n")
        assert "name:" in texte and "description:" in texte
        assert "mode: subagent" in texte


def test_les_profils_du_plugin_existent_dans_le_noyau():
    import sys

    sys.path.insert(0, str(REPO / "backend"))
    from jumeau import profils

    plugin = _json("profiles.json")["profiles"]
    for identifiant, configuration in plugin.items():
        profil = profils.resoudre_profil(profil=identifiant)
        assert profil.inconnu is False
        assert set(configuration["methods"]) <= set(profil.methodes)
        assert set(configuration["skills"]) <= set(profil.competences)


def test_le_serveur_mcp_expose_des_tools_read_only(monkeypatch):
    import sys

    sys.path.insert(0, str(REPO))
    from plugin.meridian.mcp import server as module

    outils = asyncio.run(module.server.list_tools())
    noms = {outil.name for outil in outils}
    attendus = {"meridian_analyser", "meridian_portefeuille", "meridian_impact",
                "meridian_claims", "meridian_learnings", "meridian_valeurs",
                "meridian_valeur_resume", "meridian_contexte", "meridian_memoire_durable",
                "meridian_memoire_consolidation", "meridian_calibration",
                "meridian_contrefactuel"}
    assert attendus <= noms
    assert "meridian_ecrire" not in noms and "meridian_supprimer" not in noms
    for outil in outils:
        assert outil.annotations is not None
        assert outil.annotations.read_only_hint is True
        assert outil.annotations.destructive_hint is False


def test_un_tool_mcp_appelle_l_api_avec_tenant_et_persona(monkeypatch):
    import sys

    sys.path.insert(0, str(REPO))
    from plugin.meridian.mcp import server as module

    appels = []

    class Reponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True}

    def faux(methode, url, **kwargs):
        appels.append((methode, url, kwargs))
        return Reponse()

    monkeypatch.setattr(module.requests, "request", faux)
    monkeypatch.setattr(module, "API", "http://test/api")
    monkeypatch.setattr(module, "TENANT", "demo")
    monkeypatch.setattr(module, "PERSONA", "architecte")

    assert module.meridian_impact("paiements") == {"ok": True}
    methode, url, kwargs = appels[0]
    assert (methode, url) == ("GET", "http://test/api/boucle/graphe/paiements/impact")
    assert kwargs["headers"]["X-Tenant"] == "demo"
    assert kwargs["headers"]["X-Persona"] == "architecte"


def test_les_nouveaux_tools_sont_annotes_read_only():
    import sys

    sys.path.insert(0, str(REPO))
    from plugin.meridian.mcp import server as module

    outils = {outil.name: outil for outil in asyncio.run(module.server.list_tools())}
    nouveaux = {"meridian_contexte", "meridian_memoire_durable",
                "meridian_memoire_consolidation", "meridian_calibration",
                "meridian_contrefactuel"}
    assert nouveaux <= set(outils)
    for nom in nouveaux:
        annotations = outils[nom].annotations
        assert annotations is not None
        assert annotations.read_only_hint is True
        assert annotations.destructive_hint is False
        assert annotations.idempotent_hint is True


def test_les_nouveaux_tools_construisent_des_requetes_read_only(monkeypatch):
    import sys

    sys.path.insert(0, str(REPO))
    from plugin.meridian.mcp import server as module

    appels = []

    class Reponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True}

    def faux(methode, url, **kwargs):
        appels.append((methode, url, kwargs))
        return Reponse()

    monkeypatch.setattr(module.requests, "request", faux)
    monkeypatch.setattr(module, "API", "http://test/api")
    monkeypatch.setattr(module, "TENANT", "demo")
    monkeypatch.setattr(module, "PERSONA", "architecte")

    module.meridian_contexte("twins", twin_id="paiements", domaine="finance")
    module.meridian_memoire_durable(scope="tenant", q="latence", limite=10)
    module.meridian_memoire_consolidation([{"id": "m1"}], seuil_similarite=0.8)
    module.meridian_calibration("dec-1")
    module.meridian_contrefactuel([{"id": "a"}], {"cout": 1}, criteres=["cout"])

    methode, url, kwargs = appels[0]
    assert (methode, url) == ("POST", "http://test/api/boucle/contexte/resoudre")
    assert kwargs["json"] == {
        "surface": "twins", "twin_id": "paiements", "situation_id": None,
        "work_id": None, "domaine": "finance", "date": None,
        "utilisateur": None, "perimetre": None,
    }

    methode, url, kwargs = appels[1]
    assert (methode, url) == ("GET", "http://test/api/boucle/memoire/durable")
    assert kwargs["params"] == {"limite": 10, "scope": "tenant", "q": "latence"}

    methode, url, kwargs = appels[2]
    assert (methode, url) == ("POST", "http://test/api/boucle/memoire/consolidation")
    assert kwargs["json"] == {"memoires": [{"id": "m1"}], "seuil_similarite": 0.8}
    assert "ids" not in kwargs["json"] and "acteur" not in kwargs["json"]

    methode, url, kwargs = appels[3]
    assert (methode, url) == ("GET", "http://test/api/boucle/calibration/rapport")
    assert kwargs["params"] == {"decision_id": "dec-1"}

    methode, url, kwargs = appels[4]
    assert (methode, url) == ("POST", "http://test/api/boucle/contrefactuel")
    assert kwargs["json"] == {
        "options": [{"id": "a"}], "changements": {"cout": 1}, "criteres": ["cout"],
    }
    assert all(kwargs["headers"]["X-Tenant"] == "demo" for _, _, kwargs in appels)
    assert all(kwargs["headers"]["X-Persona"] == "architecte" for _, _, kwargs in appels)
