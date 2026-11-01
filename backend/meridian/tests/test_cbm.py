"""codebase-memory-mcp par le protocole MCP (serveur réel ; ignoré sans CBM_BIN)."""
import os

import pytest

from meridian.adapters.outbound.connectors import cbm

pytestmark = pytest.mark.skipif(not os.environ.get("CBM_BIN"), reason="CBM_BIN non défini")


def test_appel_mcp_reel_et_reutilisation_du_client():
    assert "projects" in cbm.appeler("list_projects")
    premier = cbm._client
    cbm.appeler("list_projects")
    assert cbm._client is premier  # un seul serveur MCP par processus


def test_erreur_d_outil_remontee():
    with pytest.raises(RuntimeError):
        cbm.appeler("get_architecture", project="projet-inexistant-xyz")
