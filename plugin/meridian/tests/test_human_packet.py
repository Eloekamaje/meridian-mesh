"""Packet de revue humaine : anonymisation, mapping et formulaire vide."""
import json
from pathlib import Path

from plugin.meridian.evals import build_human_packet


def test_construit_un_packet_aveugle(tmp_path):
    run = tmp_path / "runs" / "skill_mcp" / "incident" / "run-01.json"
    run.parent.mkdir(parents=True)
    run.write_text(json.dumps({"scenario": "incident", "condition": "skill+mcp",
                               "result": "Réponse A", "cost_usd": 0.5}), encoding="utf-8")
    autre = tmp_path / "runs" / "checklist" / "incident" / "run-01.json"
    autre.parent.mkdir(parents=True)
    autre.write_text(json.dumps({"scenario": "incident", "condition": "checklist+mcp",
                                 "result": "Réponse B"}), encoding="utf-8")
    sortie = tmp_path / "packet"
    resultat = build_human_packet.construire([tmp_path / "runs"], sortie, seed=1, limite=10)

    assert resultat["echantillons"] == 2
    mapping = json.loads((sortie / "mapping.json").read_text())
    assert len(mapping) == 2
    assert all("condition" in valeur for valeur in mapping.values())
    for fichier in (sortie / "samples").glob("*.md"):
        texte = fichier.read_text()
        assert "skill+mcp" not in texte and "checklist+mcp" not in texte
    assert (sortie / "review-form.json").exists()
