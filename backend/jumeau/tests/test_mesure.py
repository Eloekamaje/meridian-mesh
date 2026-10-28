"""Durées par phase : on ne tient pas un objectif de latence qu'on ne mesure pas."""
import time
from types import SimpleNamespace

from jumeau import mesure


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
