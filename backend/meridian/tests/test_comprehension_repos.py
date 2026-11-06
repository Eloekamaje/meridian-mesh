"""Le découpage du batch doit séparer les sous-systèmes source, pas les fichiers."""
import importlib.util
import json
import subprocess
from pathlib import Path

RACINE = Path(__file__).resolve().parents[3]


def _module():
    spec = importlib.util.spec_from_file_location(
        "comprehension_repos", RACINE / "scripts" / "comprehension-repos.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_groupes_separent_les_racines_source_et_les_sous_dossiers():
    cr = _module()
    fichiers = (
        [f"api/controllers/console/c{i}.py" for i in range(300)]
        + [f"api/controllers/service_api/s{i}.py" for i in range(300)]
        + [f"api/core/x{i}.py" for i in range(600)]
        + [f"web/w{i}.py" for i in range(100)]
        + [f"docs/d{i}.md" for i in range(100)]
    )
    groupes = dict(cr._groupes(fichiers, max_fichiers=500, max_parties=10))
    assert "api/controllers/console" in groupes
    assert "api/controllers/service_api" in groupes
    assert "api/core" in groupes
    assert "web" in groupes
    assert "reste" not in groupes
    assert all(not prefixe.endswith(".py") for prefixe in groupes)


def test_depot_surtout_documentaire_reste_en_un_groupe():
    cr = _module()
    fichiers = ([f"src/f{i}.py" for i in range(10)]
                + [f"data/d{i}.bin" for i in range(900)])
    groupes = cr._groupes(fichiers, max_fichiers=100, max_parties=10)
    assert groupes == [("", fichiers)]


def test_groupes_ne_depassent_pas_le_plafond_de_parties():
    cr = _module()
    fichiers = [f"src/module{i}/fichier.py" for i in range(20) for _ in range(40)]
    groupes = cr._groupes(fichiers, max_fichiers=10, max_parties=8)
    assert len(groupes) <= 8


def _depot(tmp_path):
    depot = tmp_path / "dify"
    (depot / "api" / "controllers" / "console" / "app").mkdir(parents=True)
    (depot / "api" / "controllers" / "console" / "__init__.py").write_text(
        'bp = Blueprint("console", __name__, url_prefix="/console/api")\n'
        'console_ns = Namespace("console", path="/")\n', encoding="utf-8")
    (depot / "api" / "controllers" / "console" / "app" / "app.py").write_text(
        '@console_ns.route("/apps")\n', encoding="utf-8")
    subprocess.run(["git", "-C", str(depot), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(depot), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(depot), "config", "user.name", "T"], check=True)
    subprocess.run(["git", "-C", str(depot), "add", "."], check=True)
    subprocess.run(["git", "-C", str(depot), "commit", "-qm", "init"], check=True)
    return depot


def test_prefixe_unique_et_normalisation_des_claims(tmp_path):
    cr = _module()
    from meridian.application.exploration_agent import RepoSnapshot
    snapshot = RepoSnapshot.depuis_git("dify", _depot(tmp_path))
    prefixe = "api/controllers/console/app"
    assert cr._prefixe_unique(snapshot, prefixe) == "/console/api"
    etat = tmp_path / "state"
    etat.mkdir()
    (etat / "claims.json").write_text(json.dumps([{
        "predicat": "EXPOSE", "objet": "GET /apps",
        "preuves": [{"chemin": "api/controllers/console/app/app.py"}],
    }]), encoding="utf-8")
    assert cr._normaliser_claims(etat, "/console/api", prefixe) == 1
    claim = json.loads((etat / "claims.json").read_text(encoding="utf-8"))[0]
    assert claim["objet"] == "GET /console/api/apps"


def test_normalisation_ignore_une_preuve_hors_du_groupe(tmp_path):
    cr = _module()
    etat = tmp_path / "state"
    etat.mkdir()
    (etat / "claims.json").write_text(json.dumps([{
        "predicat": "EXPOSE", "objet": "GET /apps",
        "preuves": [{"chemin": "api/controllers/web/app.py"}],
    }]), encoding="utf-8")
    assert cr._normaliser_claims(etat, "/console/api", "api/controllers/console") == 0
    claim = json.loads((etat / "claims.json").read_text(encoding="utf-8"))[0]
    assert claim["objet"] == "GET /apps"


def test_est_source():
    cr = _module()
    assert cr._est_source("api")
    assert cr._est_source("dify-agent-runtime")
    assert cr._est_source("backend")
    assert not cr._est_source("docs")
    assert not cr._est_source(".github")
