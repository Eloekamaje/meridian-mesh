"""Diagnostic des dépendances runtime : visible, sans secret, dégradation explicite."""
from meridian.application import dependances


def test_etat_nomme_les_dependances_et_ne_divulgue_aucun_secret(monkeypatch):
    monkeypatch.setenv("MONGO_URL", "mongodb://exemple")
    monkeypatch.setenv("DB_NAME", "meridian")
    monkeypatch.setenv("JUMEAU_PG_DSN", "postgresql://user:secret@db/meridian")
    monkeypatch.setenv("JUMEAU_MODELE", "deepseek")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("CBM_BIN", "/chemin/inexistant")
    etat = dependances.etat()
    assert etat["status"] in {"degraded", "down"}
    assert "codebase-memory-mcp" in etat["manquantes"]
    assert "modele" in etat["manquantes"]
    assert "secret" not in str(etat)


def test_exiger_donne_la_dependance_manquante(monkeypatch):
    monkeypatch.setenv("CBM_BIN", "/chemin/inexistant")
    try:
        dependances.exiger("codebase-memory-mcp")
    except RuntimeError as erreur:
        assert "codebase-memory-mcp" in str(erreur)
    else:
        raise AssertionError("dépendance absente acceptée")
