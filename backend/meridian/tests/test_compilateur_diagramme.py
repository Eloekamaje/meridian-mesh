"""Le compilateur design-diagram produit un artefact SVG pour le Canvas."""
import json
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[3]


def test_compile_un_diagramme_et_produit_un_artefact_svg(tmp_path):
    source = RACINE / "docs/diagrammes/architecture.html"
    sortie = tmp_path / "architecture.json"
    resultat = subprocess.run(
        [sys.executable, str(RACINE / "scripts/compiler-diagramme.py"), str(source),
         "--titre", "Architecture", "--sortie", str(sortie)],
        capture_output=True, text=True, timeout=60,
        env={**__import__("os").environ, "DIAGRAM_EXPORT_SCRIPT": "/chemin/inexistant"})
    assert resultat.returncode == 0, resultat.stderr
    artefact = json.loads(sortie.read_text())
    assert artefact["type"] == "svg"
    assert artefact["titre"] == "Architecture"
    assert artefact["artefact_id"] and artefact["svg"].startswith("<?xml")
