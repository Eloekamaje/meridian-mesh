"""Le cache de l'index est vérifié au démarrage : un démon déjà lancé avec un autre cache fait échouer toute indexation."""
import subprocess

import pytest

from jumeau import cbm

CONFLIT = "active account daemon uses a different cache directory"


@pytest.fixture(autouse=True)
def propre(monkeypatch):
    monkeypatch.setattr(cbm, "_cause", None)
    monkeypatch.delenv("CBM_BIN", raising=False)


def lancer(monkeypatch, retour=None, erreur=None):
    def faux(*a, **k):
        if erreur:
            raise erreur
        return subprocess.CompletedProcess(a, retour[0], retour[1], retour[2])
    monkeypatch.setattr(cbm.subprocess, "run", faux)


def test_conflit_journalise_une_erreur_avec_le_remede(monkeypatch, caplog):
    lancer(monkeypatch, (1, "", CONFLIT))
    assert cbm.verifier_cache() is False
    assert "JUMEAU_CBM_CACHE" in caplog.text and "daemon stop" in caplog.text
    assert any(r.levelname == "ERROR" for r in caplog.records)
    assert "en conflit avec le démon" in cbm.cause_panne()


def test_conflit_rend_indexe_explicite(monkeypatch):
    lancer(monkeypatch, (1, "", CONFLIT))
    cbm.verifier_cache()
    with pytest.raises(RuntimeError, match="en conflit avec le démon"):
        cbm.indexer("/x", "n")


def test_succes_ne_memorise_rien(monkeypatch, caplog):
    lancer(monkeypatch, (0, "{}", ""))
    assert cbm.verifier_cache() is True
    assert cbm.cause_panne() is None and not caplog.records


def test_binaire_absent_ne_fait_rien(monkeypatch):
    lancer(monkeypatch, erreur=FileNotFoundError())
    assert cbm.verifier_cache() is True and cbm.cause_panne() is None


def test_autre_erreur_ne_fait_pas_echouer(monkeypatch):
    lancer(monkeypatch, erreur=subprocess.TimeoutExpired("x", 1))
    assert cbm.verifier_cache() is True


def test_un_succes_ulterieur_efface_la_cause(monkeypatch):
    lancer(monkeypatch, (1, "", CONFLIT))
    cbm.verifier_cache()
    lancer(monkeypatch, (0, "{}", ""))
    cbm.verifier_cache()
    assert cbm.cause_panne() is None
