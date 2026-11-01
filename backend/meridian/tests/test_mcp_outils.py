"""Adaptateur MCP : descriptors tools/list → manifestes, aucun appel tools/call."""
import asyncio

import pytest

from meridian.application import mcp_outils
from meridian.domain.capacites import RegistreCapacites

OUTILS = [
    {"name": "chercher", "description": "Cherche un document",
     "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}},
     "annotations": {"readOnlyHint": True}},
    {"name": "ecrire", "description": "Écrit un document",
     "inputSchema": {"type": "object"}, "annotations": {"readOnlyHint": False}},
    {"name": "inconnu", "inputSchema": {"type": "object"}},
]


def test_les_lectures_mcp_sont_observe_et_les_ecritures_agir():
    manifestes = {m.nom: m for m in mcp_outils.manifests_depuis_outils("atlas", OUTILS, tenant="demo")}

    assert manifestes["atlas.chercher"].capacite == "observer"
    assert manifestes["atlas.chercher"].lecture_seule is True
    assert manifestes["atlas.chercher"].effets_de_bord == ()
    assert manifestes["atlas.ecrire"].capacite == "agir"
    assert manifestes["atlas.ecrire"].lecture_seule is False
    assert manifestes["atlas.ecrire"].effets_de_bord == ("mcp:ecrire",)
    assert manifestes["atlas.inconnu"].capacite == "agir"


def test_un_descripteur_sans_nom_est_refuse():
    with pytest.raises(mcp_outils.ErreurMCP, match="name"):
        mcp_outils.manifests_depuis_outils("atlas", [{"inputSchema": {}}])


def test_importer_outils_inscrit_dans_le_registre_avec_la_portee():
    registre = RegistreCapacites()
    noms = mcp_outils.importer_outils(registre, "atlas", OUTILS, tenant="demo", acteur="architecte")
    assert noms == ["atlas.chercher", "atlas.ecrire", "atlas.inconnu"]
    assert registre.decrire("atlas.chercher").tenant == "demo"
    assert registre.decrire("atlas.chercher").acteur == "architecte"
    assert len(registre.lister(tenant="demo", acteur="architecte")) == 3


def test_session_mcp_lit_tools_list_sans_executer():
    class _Session:
        def __init__(self):
            self.appels = []

        async def list_tools(self):
            self.appels.append("list_tools")
            return {"tools": OUTILS}

    session = _Session()
    outils = asyncio.run(mcp_outils.outils_depuis_session(session))
    assert len(outils) == 3
    assert session.appels == ["list_tools"]
