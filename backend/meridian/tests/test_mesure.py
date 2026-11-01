"""Durées par phase : on ne tient pas un objectif de latence qu'on ne mesure pas."""
import time
from types import SimpleNamespace

from meridian.application import mesure


def test_phases_et_partage_modele_outils():
    c = mesure.Chrono()
    with c.phase("contexte"):
        time.sleep(0.01)
    c.phases["agent"] = 5.0
    c.agent(SimpleNamespace(event_loop_metrics=SimpleNamespace(tool_metrics={
        "lire_code": SimpleNamespace(total_time=1.5), "suivre_appels": SimpleNamespace(total_time=0.5)})))
    b = c.bilan()
    assert b["outils"] == 2.0 and b["modele"] == 3.0 and "agent" not in b and b["contexte"] >= 0.01
    assert b["total"] >= b["contexte"]


def test_agent_sans_metriques():
    c = mesure.Chrono()
    c.phases["agent"] = 1.0
    c.agent(object())
    assert c.bilan()["modele"] == 1.0 and c.bilan()["outils"] == 0


def _usage_agent(entree=1000, sortie=200, total=1200):
    return SimpleNamespace(event_loop_metrics=SimpleNamespace(accumulated_usage={
        "inputTokens": entree, "outputTokens": sortie, "totalTokens": total,
        "cacheReadInputTokens": 0, "cacheWriteInputTokens": 0,
    }))


def test_usage_et_cout_estime(monkeypatch):
    u = mesure.usage(_usage_agent())
    assert u == {"entree": 1000, "sortie": 200, "total": 1200, "cache_lu": 0, "cache_ecrit": 0}
    monkeypatch.setenv("JUMEAU_MODELE", "deepseek")
    monkeypatch.delenv("JUMEAU_COUT_ENTREE_MILLION", raising=False)
    monkeypatch.delenv("JUMEAU_COUT_SORTIE_MILLION", raising=False)
    cout = mesure.cout(u)
    assert cout["devise"] == "USD" and cout["montant"] > 0 and cout["estimation"] is True
    monkeypatch.setenv("JUMEAU_COUT_ENTREE_MILLION", "0")
    monkeypatch.setenv("JUMEAU_COUT_SORTIE_MILLION", "0")
    assert mesure.cout(u) is None


def test_fusionner_usages_additionne_les_tours():
    assert mesure.fusionner_usages(
        {"entree": 10, "sortie": 2, "total": 12},
        {"entree": 5, "sortie": 1, "total": 6},
        None,
    ) == {"entree": 15, "sortie": 3, "total": 18, "cache_lu": 0, "cache_ecrit": 0}
